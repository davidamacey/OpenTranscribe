#!/usr/bin/env python3
"""End-to-end transcription pipeline benchmark.

Triggers a reprocess via the API, polls Redis for timing data,
calculates stage durations + inter-stage gaps, runs N iterations,
and outputs a CSV + summary table + VRAM map.

Requires:
    - ENABLE_BENCHMARK_TIMING=true in .env
    - ENABLE_VRAM_PROFILING=true in .env (optional, for VRAM data)
    - Backend running and accessible at BACKEND_URL
    - Redis accessible at REDIS_URL

Usage:
    BENCHMARK_EMAIL=admin@example.com BENCHMARK_PASSWORD=password \\
        python scripts/benchmark_e2e.py --file-uuid <UUID> [--iterations 3] [--output benchmark_results.csv]

Credentials are read from environment variables to avoid exposure in shell
history and process listings:
    BENCHMARK_EMAIL     Login email    (default: admin@example.com)
    BENCHMARK_PASSWORD  Login password (default: password)
"""

import argparse
import csv
import json
import os
import sys
import time

import redis
import requests

DEFAULT_BACKEND_URL = 'http://localhost:5174'
DEFAULT_REDIS_URL = 'redis://localhost:6379/0'
POLL_INTERVAL = 2.0
POLL_TIMEOUT = 600  # 10 minutes max


def get_auth_token(backend_url: str, email: str, password: str, verify: bool = True) -> str:
    """Authenticate and return JWT token."""
    resp = requests.post(
        f'{backend_url}/api/auth/login',
        json={'email': email, 'password': password},
        verify=verify,
    )
    resp.raise_for_status()
    return resp.json()['access_token']


def trigger_reprocess(backend_url: str, file_uuid: str, token: str, verify: bool = True) -> str:
    """Trigger reprocessing of a file. Returns the task_id."""
    resp = requests.post(
        f'{backend_url}/api/files/{file_uuid}/reprocess',
        headers={'Authorization': f'Bearer {token}'},
        verify=verify,
    )
    resp.raise_for_status()
    data = resp.json()
    task_id = data.get('task_id') or data.get('id')
    if not task_id:
        raise ValueError(f'No task_id in response: {data}')
    return task_id


def poll_task_completion(backend_url: str, file_uuid: str, token: str, verify: bool = True) -> bool:
    """Poll until the file status is completed or error."""
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        resp = requests.get(
            f'{backend_url}/api/files/{file_uuid}',
            headers={'Authorization': f'Bearer {token}'},
            verify=verify,
        )
        if resp.status_code == 200:
            status = resp.json().get('status', '')
            if status == 'completed':
                return True
            if status == 'error':
                print('  ERROR: File reached error status', file=sys.stderr)
                return False
        time.sleep(POLL_INTERVAL)
    print(f'  TIMEOUT: Poll exceeded {POLL_TIMEOUT}s', file=sys.stderr)
    return False


def collect_benchmark_data(r: redis.Redis, task_id: str) -> dict:
    """Collect all benchmark timing data from Redis."""
    key = f'benchmark:{task_id}'
    raw = r.hgetall(key)
    return {k.decode(): float(v.decode()) for k, v in raw.items()}


def collect_vram_data(r: redis.Redis, task_id: str) -> dict | None:
    """Collect VRAM profiler data from Redis."""
    key = f'vram_profile:{task_id}'
    raw = r.get(key)
    if raw:
        return json.loads(raw)
    return None


def calculate_stages(data: dict) -> dict:
    """Calculate stage durations and inter-stage gaps."""
    stages = {}

    dispatch = data.get('dispatch_timestamp')
    pre_end = data.get('preprocess_end')
    gpu_recv = data.get('gpu_received')
    gpu_end = data.get('gpu_end')
    post_recv = data.get('postprocess_received')

    if dispatch and pre_end:
        stages['preprocess_duration'] = pre_end - dispatch

    if pre_end and gpu_recv:
        stages['preprocess_to_gpu_gap'] = gpu_recv - pre_end

    if gpu_recv and gpu_end:
        stages['gpu_duration'] = gpu_end - gpu_recv

    if gpu_end and post_recv:
        stages['gpu_to_postprocess_gap'] = post_recv - gpu_end

    if dispatch and gpu_end:
        stages['total_dispatch_to_gpu_end'] = gpu_end - dispatch

    if dispatch and post_recv:
        stages['total_dispatch_to_postprocess'] = post_recv - dispatch

    return stages


def print_summary(all_results: list[dict]) -> None:
    """Print a summary table of benchmark results."""
    if not all_results:
        print('No results to summarize.')
        return

    # Collect all stage keys
    stage_keys = set()
    for r in all_results:
        stage_keys.update(r.get('stages', {}).keys())
    stage_keys = sorted(stage_keys)

    print('\n' + '=' * 70)
    print('BENCHMARK SUMMARY')
    print('=' * 70)
    print(f'{"Stage":<35} {"Mean (s)":>10} {"Min (s)":>10} {"Max (s)":>10}')
    print('-' * 70)

    for key in stage_keys:
        values = [r['stages'][key] for r in all_results if key in r.get('stages', {})]
        if values:
            mean = sum(values) / len(values)
            print(f'{key:<35} {mean:>10.3f} {min(values):>10.3f} {max(values):>10.3f}')

    print('=' * 70)


def print_vram_summary(all_vram: list[dict]) -> None:
    """Print VRAM profiler summary if data is available."""
    valid = [v for v in all_vram if v is not None]
    if not valid:
        return

    print('\n' + '=' * 70)
    print('VRAM PROFILE (last run)')
    print('=' * 70)

    last = valid[-1]
    snapshots = last.get('snapshots', {})
    steps = last.get('steps', {})

    if snapshots:
        print(f'\n{"Snapshot":<30} {"NVML Used (MB)":>15} {"Torch Alloc (MB)":>17}')
        print('-' * 65)
        for name, snap in snapshots.items():
            nvml = snap.get('nvml_used_mb', 0)
            torch_alloc = snap.get('torch_allocated_mb', 0)
            print(f'{name:<30} {nvml:>15.1f} {torch_alloc:>17.1f}')

    if steps:
        print(f'\n{"Step":<30} {"Duration (s)":>12} {"Peak VRAM (MB)":>15}')
        print('-' * 60)
        for name, step in steps.items():
            dur = step.get('duration_s', 0)
            peak = step.get('peak_allocated_mb', 0)
            print(f'{name:<30} {dur:>12.3f} {peak:>15.1f}')

    # Derived metrics
    ps = snapshots.get('pipeline_start', {})
    at = snapshots.get('after_transcriber_loaded', {})
    mw = snapshots.get('models_warm_no_inference', {})

    if ps and at:
        whisper_vram = at.get('nvml_used_mb', 0) - ps.get('nvml_used_mb', 0)
        print(f'\nWhisper warm VRAM: {whisper_vram:.1f} MB')

    if at and mw:
        pyannote_vram = mw.get('nvml_used_mb', 0) - at.get('nvml_used_mb', 0)
        print(f'PyAnnote warm VRAM: {pyannote_vram:.1f} MB')

    print('=' * 70)


def main():
    parser = argparse.ArgumentParser(description='E2E transcription benchmark')
    parser.add_argument('--file-uuid', required=True, help='UUID of file to benchmark')
    parser.add_argument('--iterations', type=int, default=3, help='Number of iterations')
    parser.add_argument('--output', default='benchmark_results.csv', help='Output CSV path')
    parser.add_argument('--backend-url', default=DEFAULT_BACKEND_URL, help='Backend URL')
    parser.add_argument('--redis-url', default=DEFAULT_REDIS_URL, help='Redis URL')
    parser.add_argument(
        '--no-verify',
        action='store_true',
        help='Disable TLS certificate verification (for self-signed certs)',
    )
    args = parser.parse_args()

    email = os.environ.get('BENCHMARK_EMAIL', 'admin@example.com')
    password = os.environ.get('BENCHMARK_PASSWORD', 'password')
    verify = not args.no_verify

    print(f'Authenticating to {args.backend_url}...')
    token = get_auth_token(args.backend_url, email, password, verify=verify)

    r = redis.from_url(args.redis_url, decode_responses=False)

    all_results = []
    all_vram = []

    for i in range(args.iterations):
        print(f'\n--- Iteration {i + 1}/{args.iterations} ---')

        print(f'  Triggering reprocess for {args.file_uuid}...')
        task_id = trigger_reprocess(args.backend_url, args.file_uuid, token, verify=verify)
        print(f'  Task ID: {task_id}')

        print('  Waiting for completion...')
        success = poll_task_completion(args.backend_url, args.file_uuid, token, verify=verify)

        if not success:
            print(f'  Skipping iteration {i + 1} (failed/timeout)')
            continue

        # Brief delay for Redis data propagation
        time.sleep(1)

        bench_data = collect_benchmark_data(r, task_id)
        vram_data = collect_vram_data(r, task_id)
        stages = calculate_stages(bench_data)

        result = {
            'iteration': i + 1,
            'task_id': task_id,
            'raw_timestamps': bench_data,
            'stages': stages,
        }
        all_results.append(result)
        all_vram.append(vram_data)

        print(f'  Stages: {json.dumps(stages, indent=2)}')

    # Write CSV
    if all_results:
        stage_keys = set()
        for r_item in all_results:
            stage_keys.update(r_item.get('stages', {}).keys())
        stage_keys = sorted(stage_keys)

        with open(args.output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['iteration', 'task_id'] + stage_keys)
            for r_item in all_results:
                row = [r_item['iteration'], r_item['task_id']]
                row += [r_item['stages'].get(k, '') for k in stage_keys]
                writer.writerow(row)

        print(f'\nCSV written to {args.output}')

    print_summary(all_results)
    print_vram_summary(all_vram)


if __name__ == '__main__':
    main()
