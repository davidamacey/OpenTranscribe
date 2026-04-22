#!/usr/bin/env python3
"""Direct PyAnnote diarization benchmark — stock vs optimized.

Runs PyAnnote speaker diarization directly on WAV files, bypassing the
OpenTranscribe API. Captures per-stage timing, speaker counts, segment counts,
per-stage peak VRAM, RTTM output for DER scoring, and optional torch.profiler
traces.

Usage:
    # Single-run baseline (stock)
    python scripts/benchmark-pyannote-direct.py --variant stock --files 0.5h_1899s

    # 5-run statistical benchmark with RTTM export (for DER scoring)
    python scripts/benchmark-pyannote-direct.py --variant optimized \\
        --files 0.5h_1899s 2.2h_7998s --runs 5 \\
        --tag baseline_a6000_20260421 \\
        --rttm-out benchmark/results/rttm/baseline_a6000_20260421

    # Profiled run (chrome trace export)
    python scripts/benchmark-pyannote-direct.py --variant optimized \\
        --files 2.2h_7998s --profiler --tag phase1_profile_cuda

    # MPS (Apple Silicon)
    python scripts/benchmark-pyannote-direct.py --variant optimized \\
        --device mps --files 0.5h_1899s --runs 5 --tag baseline_m2max

    # Compare saved results (single-run tags only; use compare-runs for statistical)
    python scripts/benchmark-pyannote-direct.py --compare stock optimized

Environment:
    HUGGINGFACE_TOKEN    HF token for gated model downloads
    CUDA_DEVICE_INDEX    Which GPU to use (default: 0)
    PYANNOTE_OPTIMIZED_SRC  Override path to optimized pyannote-audio src
                             (default: /mnt/nvm/repos/pyannote-audio-fork/src,
                             the canonical davidamacey/pyannote-audio fork on
                             the gpu-optimizations branch).
    PYANNOTE_MODEL       Override diarization model (default: v4 community-1)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import statistics
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger('benchmark-pyannote')

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
AUDIO_DIR = PROJECT_ROOT / 'benchmark' / 'test_audio'
RESULTS_DIR = PROJECT_ROOT / 'benchmark' / 'results'

TEST_FILES = [
    '0.5h_1899s',
    '1.0h_3758s',
    '2.2h_7998s',
    '3.2h_11495s',
    '4.7h_17044s',
]

DEFAULT_MODEL = os.environ.get('PYANNOTE_MODEL', 'pyannote/speaker-diarization-community-1')

HF_TOKEN = os.environ.get('HUGGINGFACE_TOKEN', '')
GPU_INDEX = int(os.environ.get('CUDA_DEVICE_INDEX', '0'))

# Default location of the canonical davidamacey/pyannote-audio fork (gpu-optimizations
# branch). Can be overridden via PYANNOTE_OPTIMIZED_SRC. When running inside
# docker-compose.benchmark.yml, the fork is bind-mounted over site-packages and
# this path is unused (the bind-mount wins regardless of sys.path).
DEFAULT_OPTIMIZED_SRC = Path('/mnt/nvm/repos/pyannote-audio-fork/src')


# ---------------------------------------------------------------------------
# VRAM instrumentation
# ---------------------------------------------------------------------------


def get_gpu_info() -> dict | None:
    """Get GPU info via pynvml; fall back to torch if pynvml is unavailable."""
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(GPU_INDEX)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode()
        result = {
            'gpu_name': name,
            'vram_total_mb': round(mem.total / (1024**2)),
            'vram_used_mb': round(mem.used / (1024**2)),
            'vram_free_mb': round(mem.free / (1024**2)),
        }
        pynvml.nvmlShutdown()
        return result
    except Exception:
        pass
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(GPU_INDEX)
            free, total = torch.cuda.mem_get_info(GPU_INDEX)
            return {
                'gpu_name': props.name,
                'vram_total_mb': round(total / (1024**2)),
                'vram_used_mb': round((total - free) / (1024**2)),
                'vram_free_mb': round(free / (1024**2)),
            }
    except Exception:
        pass
    return None


def get_vram_used_mb() -> int | None:
    """Current VRAM used via NVML (all processes; not per-process)."""
    info = get_gpu_info()
    return info['vram_used_mb'] if info else None


def get_mps_driver_allocated_mb() -> int | None:
    """Current MPS allocator high-water mark for this process."""
    try:
        import torch

        if torch.backends.mps.is_available():
            return int(torch.mps.driver_allocated_memory() / (1024**2))
    except Exception:
        pass
    return None


class MPSVRAMPoller:
    """Poll MPS allocator at fixed cadence; track peak.

    MPS lacks `max_memory_allocated()`; poll `driver_allocated_memory()` on a
    background thread and take the high-water mark. Cadence of 100 ms matches
    the pattern in `vram-probe-diarization-mps.py`.
    """

    def __init__(self, interval_s: float = 0.1):
        self.interval_s = interval_s
        self._peak_mb = 0
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._peak_mb = get_mps_driver_allocated_mb() or 0
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running:
            v = get_mps_driver_allocated_mb()
            if v is not None and v > self._peak_mb:
                self._peak_mb = v
            time.sleep(self.interval_s)

    def peek(self) -> int:
        """Current peak without stopping the thread."""
        v = get_mps_driver_allocated_mb()
        if v is not None and v > self._peak_mb:
            self._peak_mb = v
        return self._peak_mb

    def reset(self) -> None:
        """Reset peak to current allocator value (stage-boundary reset)."""
        self._peak_mb = get_mps_driver_allocated_mb() or 0

    def stop(self) -> int:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        return self._peak_mb


def sync_device(device_str: str) -> None:
    """Flush async kernel queue so subsequent timestamps are accurate."""
    import torch

    if device_str.startswith('cuda'):
        torch.cuda.synchronize()
    elif device_str == 'mps':
        torch.mps.synchronize()


def device_peak_vram_mb(device_str: str, mps_poller: MPSVRAMPoller | None = None) -> int:
    """Device-agnostic peak VRAM (MB) since last reset."""
    import torch

    if device_str.startswith('cuda'):
        device_idx = int(device_str.split(':', 1)[1]) if ':' in device_str else 0
        return int(torch.cuda.max_memory_allocated(device=device_idx) / (1024**2))
    if device_str == 'mps' and mps_poller is not None:
        return mps_poller.peek()
    return 0


def reset_device_peak_vram(device_str: str, mps_poller: MPSVRAMPoller | None = None) -> None:
    """Reset peak counter at a stage boundary."""
    import torch

    if device_str.startswith('cuda'):
        device_idx = int(device_str.split(':', 1)[1]) if ':' in device_str else 0
        torch.cuda.reset_peak_memory_stats(device=device_idx)
    elif device_str == 'mps' and mps_poller is not None:
        mps_poller.reset()


def device_steady_state_vram_mb(
    device_str: str,
    mps_poller: MPSVRAMPoller | None = None,  # noqa: ARG001 (API symmetry)
) -> int:
    """Current (not peak) device-allocated VRAM — sampled after pipeline returns."""
    import torch

    if device_str.startswith('cuda'):
        device_idx = int(device_str.split(':', 1)[1]) if ':' in device_str else 0
        return int(torch.cuda.memory_allocated(device=device_idx) / (1024**2))
    if device_str == 'mps':
        v = get_mps_driver_allocated_mb()
        return v if v is not None else 0
    return 0


# ---------------------------------------------------------------------------
# Pipeline loading
# ---------------------------------------------------------------------------


def _resolve_device_str(device: str, gpu_index: int) -> str:
    if device == 'mps':
        return 'mps'
    if device == 'cuda':
        return f'cuda:{gpu_index}'
    return device


def load_pipeline(
    variant: str,
    device: str = 'cuda',
    gpu_index: int = 0,
    onnx_cpu: bool = False,
    model_id: str = DEFAULT_MODEL,
    optimized_src: Path | None = None,
    torch_compile: bool = False,
    segmentation_step: float | None = None,
):
    """Load a PyAnnote pipeline for the given variant.

    Parameters
    ----------
    torch_compile : bool
        If True, wrap the segmentation and embedding models in torch.compile()
        after pipeline construction. Measures the Phase 2.1 visibility fix
        impact without touching the pipeline's __init__ default.
    segmentation_step : float | None
        If not None, override the pipeline's segmentation sliding-window step
        (default is typically 0.1 = 90% overlap). Higher values (0.2-0.3) make
        segmentation run on fewer chunks at a DER cost — measured in Phase 4.
    """
    import torch

    if variant in ('optimized', 'optimized_cpu'):
        opt_src = str(optimized_src or DEFAULT_OPTIMIZED_SRC)
        if opt_src and Path(opt_src).exists() and opt_src not in sys.path:
            sys.path.insert(0, opt_src)
            # Force reimport from optimized path so editable changes are picked up
            for mod in list(sys.modules.keys()):
                if 'pyannote' in mod:
                    del sys.modules[mod]

    from pyannote.audio import Pipeline

    device_str = _resolve_device_str(device, gpu_index)

    print(f'Loading PyAnnote pipeline ({variant}) on {device_str}: model={model_id}')
    t0 = time.perf_counter()
    try:
        pipeline = Pipeline.from_pretrained(
            model_id,
            use_auth_token=HF_TOKEN or None,
        )
    except TypeError:
        pipeline = Pipeline.from_pretrained(
            model_id,
            token=HF_TOKEN or None,
        )
    pipeline.to(torch.device(device_str))

    # Phase 4: sliding-window step override. pyannote's Inference object
    # stores the step on the underlying segmentation inference; the
    # SlidingWindow is rebuilt per-call so this is the simplest hook.
    if segmentation_step is not None and hasattr(pipeline, '_segmentation'):
        inner = pipeline._segmentation
        if hasattr(inner, 'step'):
            old_step = inner.step
            inner.step = float(segmentation_step)
            print(f'  segmentation_step: {old_step} -> {inner.step}')

    # Phase 2.1 follow-up: post-construction torch.compile. Bypasses the
    # pipeline's __init__ kwarg (which defaults False and isn't exposed by
    # Pipeline.from_pretrained) by compiling the resident models directly.
    if torch_compile and device_str != 'cpu':
        try:
            if hasattr(pipeline, '_segmentation') and hasattr(pipeline._segmentation, 'model'):
                pipeline._segmentation.model = torch.compile(
                    pipeline._segmentation.model, fullgraph=False
                )
            klustering = getattr(pipeline, 'klustering', None)
            if (
                hasattr(pipeline, '_embedding')
                and hasattr(pipeline._embedding, 'model_')
                and klustering != 'OracleClustering'
            ):
                pipeline._embedding.model_ = torch.compile(
                    pipeline._embedding.model_, mode='reduce-overhead'
                )
            print('  torch.compile enabled (segmentation + embedding)')
        except Exception as e:
            print(f'  torch.compile failed: {e}')

    # Embedding batch size is now pinned to 16 by the fork. Override only if the
    # user explicitly set PYANNOTE_FORCE_EMBEDDING_BATCH_SIZE (the fork respects it).
    if variant in ('optimized', 'optimized_cpu') and device_str != 'cpu':
        forced = os.environ.get('PYANNOTE_FORCE_EMBEDDING_BATCH_SIZE')
        if forced and hasattr(pipeline, 'embedding_batch_size'):
            try:
                old_bs = pipeline.embedding_batch_size
                new_bs = int(forced)
                pipeline.embedding_batch_size = new_bs
                print(
                    f'  Embedding batch size: {old_bs} -> {new_bs} (PYANNOTE_FORCE_EMBEDDING_BATCH_SIZE)'
                )
            except Exception:
                pass

    if onnx_cpu and hasattr(pipeline, '_setup_onnx_cpu'):
        print('  Enabling ONNX CPU inference (quantized INT8)...')
        pipeline._setup_onnx_cpu(quantize=True, num_threads=0)
        if getattr(pipeline, '_onnx_cpu', False):
            print('  ONNX CPU mode active')
        else:
            print('  WARNING: ONNX setup failed, falling back to PyTorch CPU')

    load_time = time.perf_counter() - t0
    print(f'  Pipeline loaded in {load_time:.1f}s on {device_str}')

    mod_file = sys.modules.get('pyannote.audio.pipelines.speaker_diarization', None)
    if mod_file:
        print(f'  Module: {getattr(mod_file, "__file__", "unknown")}')

    return pipeline, load_time


# ---------------------------------------------------------------------------
# Audio loading
# ---------------------------------------------------------------------------


def _load_waveform(audio_path: str):
    """Load audio into a torch Tensor. Tries pyannote.audio.Audio (torchcodec)
    first, then falls back to scipy.io.wavfile for WAV inputs.

    Returns
    -------
    waveform : torch.Tensor
        Shape (channels, samples), float32 in [-1, 1].
    sample_rate : int
    """
    import numpy as np
    import torch

    # Prefer pyannote's loader — respects torchcodec when available.
    try:
        from pyannote.audio import Audio

        loader = Audio(mono='downmix')
        waveform, sample_rate = loader({'audio': audio_path})
        return waveform, sample_rate
    except Exception as e:
        logger.debug('pyannote.Audio loader failed (%s); falling back to scipy', e)

    # Fallback: scipy.io.wavfile — WAV-only, but zero extra deps.
    from scipy.io import wavfile

    sample_rate, data = wavfile.read(audio_path)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float32) - 128.0) / 128.0
    elif data.dtype == np.float64:
        data = data.astype(np.float32)
    if data.ndim == 1:
        data = data[np.newaxis, :]
    else:
        data = data.T  # (samples, channels) -> (channels, samples)
        # Downmix to mono to match pyannote's mono="downmix" default
        data = data.mean(axis=0, keepdims=True)
    waveform = torch.from_numpy(np.ascontiguousarray(data))
    return waveform, int(sample_rate)


# ---------------------------------------------------------------------------
# RTTM export
# ---------------------------------------------------------------------------


def _annotation_to_rttm(annotation, uri: str) -> str:
    """Serialize an Annotation to RTTM format.

    Uses pyannote's built-in RTTM serializer when available; falls back to a
    manual emitter if the API is different across versions.
    """
    import io

    try:
        buf = io.StringIO()
        annotation.write_rttm(buf)
        content = buf.getvalue()
        if content:
            return content
    except Exception:
        pass

    # Manual fallback
    lines = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        # SPEAKER <uri> 1 <start> <dur> <NA> <NA> <spk> <NA> <NA>
        dur = turn.end - turn.start
        lines.append(f'SPEAKER {uri} 1 {turn.start:.3f} {dur:.3f} <NA> <NA> {speaker} <NA> <NA>')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# Single-run execution
# ---------------------------------------------------------------------------


def run_diarization(
    pipeline,
    audio_path: str,
    label: str,
    device_str: str,
    rttm_out_path: Path | None = None,
    run_idx: int = 0,
    mps_poller: MPSVRAMPoller | None = None,
) -> dict:
    """Run diarization on a single file with timing + per-stage VRAM hooks."""
    import torch

    stage_timing: dict[str, dict[str, float]] = {}
    stage_order: list[str] = []

    def timing_hook(step_name, step_artefact, **kwargs):  # noqa: ARG001 (pyannote hook signature)
        # Sync so the timestamp reflects actual kernel completion, not enqueue.
        sync_device(device_str)
        now = time.perf_counter()
        # Capture cumulative peak at this stage boundary WITHOUT resetting —
        # peak monotonically grows so the overall peak equals the final capture.
        cum_peak = device_peak_vram_mb(device_str, mps_poller)
        if stage_order:
            prev_stage = stage_order[-1]
            stage_timing[prev_stage]['cumulative_peak_vram_mb'] = cum_peak
        if step_name not in stage_timing:
            stage_timing[step_name] = {'start': now, 'cumulative_peak_vram_mb': 0}
            stage_order.append(step_name)
        stage_timing[step_name]['last'] = now

    vram_before_nvml = get_vram_used_mb()
    vram_before_alloc = device_steady_state_vram_mb(device_str, mps_poller)

    waveform, sample_rate = _load_waveform(audio_path)
    audio_input = {'waveform': waveform, 'sample_rate': sample_rate}
    duration_s = waveform.shape[1] / sample_rate
    print(f'  [{label} run={run_idx}] Diarizing ({duration_s:.0f}s, sr={sample_rate})...')

    # Reset peak before the pipeline call so the peak reflects only this run.
    reset_device_peak_vram(device_str, mps_poller)
    baseline_alloc_mb = device_steady_state_vram_mb(device_str, mps_poller)

    t0 = time.perf_counter()
    diarization = pipeline(audio_input, hook=timing_hook)
    sync_device(device_str)
    elapsed = time.perf_counter() - t0

    # Capture final cumulative peak (hook won't fire again after pipeline returns).
    final_peak = device_peak_vram_mb(device_str, mps_poller)
    if stage_order:
        last_stage = stage_order[-1]
        stage_timing[last_stage]['cumulative_peak_vram_mb'] = final_peak

    # Overall peak is monotonic — equals the final capture.
    overall_peak_mb = final_peak
    # Over-baseline delta (subtract resident allocation from before the run).
    overall_peak_over_baseline_mb = max(0, overall_peak_mb - baseline_alloc_mb)

    # Steady-state VRAM +2 seconds after pipeline returns
    time.sleep(2.0)
    steady_state_mb = device_steady_state_vram_mb(device_str, mps_poller)

    vram_after_nvml = get_vram_used_mb()

    # Extract results (v3 Annotation, v4 DiarizeOutput)
    annotation = getattr(diarization, 'speaker_diarization', diarization)
    speakers: set[str] = set()
    segments: list[dict[str, Any]] = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        speakers.add(speaker)
        segments.append(
            {
                'start': round(turn.start, 3),
                'end': round(turn.end, 3),
                'speaker': speaker,
            }
        )

    # RTTM output (for DER scoring downstream)
    rttm_path_str: str | None = None
    if rttm_out_path is not None:
        rttm_out_path.parent.mkdir(parents=True, exist_ok=True)
        rttm_text = _annotation_to_rttm(annotation, uri=label)
        rttm_out_path.write_text(rttm_text)
        rttm_path_str = str(rttm_out_path)

    # Compute stage durations and per-stage VRAM deltas.
    # `cumulative_peak_vram_mb` is monotonic — the stage's incremental peak is
    # the delta over the previous stage's cumulative peak.
    stage_durations: dict[str, float] = {}
    cumulative_peaks: dict[str, int] = {}
    stage_vram_delta: dict[str, int] = {}
    stages = sorted(stage_timing.items(), key=lambda x: x[1].get('start', 0))
    prev_cum = baseline_alloc_mb
    for i, (name, times) in enumerate(stages):
        if i + 1 < len(stages):
            next_start = stages[i + 1][1]['start']
            dur = next_start - times['start']
        else:
            dur = (t0 + elapsed) - times['start']
        stage_durations[name] = round(dur, 3)
        cum = int(times.get('cumulative_peak_vram_mb', 0))
        cumulative_peaks[name] = cum
        stage_vram_delta[name] = max(0, cum - prev_cum)
        prev_cum = max(prev_cum, cum)  # monotonic

    # Total speech duration
    total_speech_s = sum(s['end'] - s['start'] for s in segments)

    # Release cache at run end so subsequent runs start clean
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    if device_str == 'mps':
        with contextlib.suppress(Exception):
            torch.mps.empty_cache()

    result: dict[str, Any] = {
        'label': label,
        'run_idx': run_idx,
        'audio_file': str(audio_path),
        'duration_s': round(duration_s, 1),
        'wall_seconds': round(elapsed, 3),
        'speaker_count': len(speakers),
        'segment_count': len(segments),
        'total_speech_seconds': round(total_speech_s, 2),
        'speakers': sorted(speakers),
        'stage_durations': stage_durations,
        'stage_cumulative_peak_vram_mb': cumulative_peaks,
        'stage_vram_delta_mb': stage_vram_delta,
        'overall_peak_vram_mb': overall_peak_mb,
        'overall_peak_over_baseline_mb': overall_peak_over_baseline_mb,
        'baseline_alloc_mb': baseline_alloc_mb,
        'steady_state_vram_mb': steady_state_mb,
        'vram_before_nvml_mb': vram_before_nvml,
        'vram_after_nvml_mb': vram_after_nvml,
        'vram_before_alloc_mb': vram_before_alloc,
        'rttm_path': rttm_path_str,
    }

    # Only include segment list on the first run (saves disk on N-run benchmarks).
    if run_idx == 0:
        result['all_segments'] = segments

    print(
        f'  [{label} run={run_idx}] Done in {elapsed:.1f}s | '
        f'{len(speakers)} speakers | {len(segments)} segments | '
        f'peak VRAM {overall_peak_mb} MB | steady {steady_state_mb} MB'
    )
    if stage_durations:
        for stage, dur in stage_durations.items():
            cum = cumulative_peaks.get(stage, 0)
            delta = stage_vram_delta.get(stage, 0)
            print(f'    {stage}: {dur:.2f}s   cum peak {cum} MB   (+{delta} MB)')

    return result


def run_diarization_with_profiler(
    pipeline,
    audio_path: str,
    label: str,
    device_str: str,
    trace_out_path: Path,
    rttm_out_path: Path | None = None,
    mps_poller: MPSVRAMPoller | None = None,
) -> dict:
    """Single run wrapped in torch.profiler; exports a Chrome trace."""
    from torch.profiler import ProfilerActivity, profile

    activities: list[Any] = [ProfilerActivity.CPU]
    if device_str.startswith('cuda'):
        activities.append(ProfilerActivity.CUDA)
    # MPS activity is not a standard ProfilerActivity across torch versions;
    # CPU-only profiling on MPS still captures op-level timing.

    trace_out_path.parent.mkdir(parents=True, exist_ok=True)

    with profile(activities=activities, record_shapes=True, with_stack=False) as prof:
        result = run_diarization(
            pipeline,
            audio_path,
            label,
            device_str,
            rttm_out_path=rttm_out_path,
            run_idx=0,
            mps_poller=mps_poller,
        )

    prof.export_chrome_trace(str(trace_out_path))
    result['profiler_trace'] = str(trace_out_path)
    print(f'  [profiler] Chrome trace saved to {trace_out_path}')
    return result


# ---------------------------------------------------------------------------
# Statistical aggregation
# ---------------------------------------------------------------------------


_NUMERIC_METRICS = (
    'wall_seconds',
    'overall_peak_vram_mb',
    'overall_peak_over_baseline_mb',
    'steady_state_vram_mb',
    'baseline_alloc_mb',
    'speaker_count',
    'segment_count',
    'total_speech_seconds',
)


def _aggregate_scalar(values: list[float]) -> dict[str, float]:
    if not values:
        return {'n': 0}
    if len(values) == 1:
        return {
            'n': 1,
            'mean': values[0],
            'stdev': 0.0,
            'min': values[0],
            'max': values[0],
            'cv': 0.0,
        }
    mean = statistics.fmean(values)
    stdev = statistics.stdev(values)
    return {
        'n': len(values),
        'mean': round(mean, 4),
        'stdev': round(stdev, 4),
        'min': round(min(values), 4),
        'max': round(max(values), 4),
        'cv': round(stdev / mean, 4) if mean else 0.0,
    }


def aggregate_runs(runs: list[dict]) -> dict:
    """Produce per-metric mean/stdev/min/max/cv and per-stage aggregates."""
    if not runs:
        return {'runs': []}

    agg: dict[str, Any] = {}
    for metric in _NUMERIC_METRICS:
        agg[metric] = _aggregate_scalar([r[metric] for r in runs if metric in r])

    # Per-stage aggregates
    stage_names: set[str] = set()
    for r in runs:
        stage_names.update(r.get('stage_durations', {}).keys())

    stage_agg: dict[str, dict[str, Any]] = {}
    for stage in stage_names:
        durs = [r['stage_durations'].get(stage, 0) for r in runs if 'stage_durations' in r]
        cum = [
            r.get('stage_cumulative_peak_vram_mb', {}).get(stage, 0)
            for r in runs
            if 'stage_cumulative_peak_vram_mb' in r
        ]
        delta = [
            r.get('stage_vram_delta_mb', {}).get(stage, 0)
            for r in runs
            if 'stage_vram_delta_mb' in r
        ]
        stage_agg[stage] = {
            'duration_s': _aggregate_scalar(durs),
            'cumulative_peak_vram_mb': _aggregate_scalar(cum),
            'vram_delta_mb': _aggregate_scalar(delta),
        }
    agg['stages'] = stage_agg

    # Reliability flag — Phase A rule: cv > 10% on wall_seconds means "rerun"
    wall = agg.get('wall_seconds', {})
    agg['reliable'] = bool(wall and wall.get('cv', 1.0) <= 0.10)

    return agg


# ---------------------------------------------------------------------------
# Benchmark driver
# ---------------------------------------------------------------------------


def run_benchmark(
    variant: str,
    file_labels: list[str],
    device: str = 'cuda',
    gpu_index: int = 0,
    onnx_cpu: bool = False,
    runs: int = 1,
    tag: str | None = None,
    rttm_out: Path | None = None,
    profiler: bool = False,
    model_id: str = DEFAULT_MODEL,
    optimized_src: Path | None = None,
    torch_compile: bool = False,
    segmentation_step: float | None = None,
) -> dict:
    """Run benchmark suite. If `runs > 1`, per-file statistical aggregates emitted."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    gpu_info = get_gpu_info()
    if gpu_info:
        print(
            f'GPU: {gpu_info["gpu_name"]} | '
            f'VRAM: {gpu_info["vram_used_mb"]}/{gpu_info["vram_total_mb"]} MB'
        )

    device_str = _resolve_device_str(device, gpu_index)

    # MPS poller runs for the lifetime of the benchmark (lightweight at 100ms).
    mps_poller: MPSVRAMPoller | None = None
    if device_str == 'mps':
        mps_poller = MPSVRAMPoller(interval_s=0.1)
        mps_poller.start()

    try:
        pipeline, load_time = load_pipeline(
            variant,
            device,
            gpu_index,
            onnx_cpu=onnx_cpu,
            model_id=model_id,
            optimized_src=optimized_src,
            torch_compile=torch_compile,
            segmentation_step=segmentation_step,
        )

        per_file_results: list[dict] = []
        for label in file_labels:
            audio_path = AUDIO_DIR / f'{label}.wav'
            if not audio_path.exists():
                print(f'  SKIP {label} — {audio_path} not found')
                continue

            run_results: list[dict] = []
            for run_idx in range(runs):
                try:
                    rttm_out_path: Path | None = None
                    if rttm_out is not None:
                        rttm_out_path = rttm_out / f'{label}_run{run_idx}.rttm'

                    if profiler and run_idx == 0:
                        trace_out = RESULTS_DIR / 'traces' / f'{tag or variant}_{label}_run0.json'
                        r = run_diarization_with_profiler(
                            pipeline,
                            str(audio_path),
                            label,
                            device_str,
                            trace_out_path=trace_out,
                            rttm_out_path=rttm_out_path,
                            mps_poller=mps_poller,
                        )
                    else:
                        r = run_diarization(
                            pipeline,
                            str(audio_path),
                            label,
                            device_str,
                            rttm_out_path=rttm_out_path,
                            run_idx=run_idx,
                            mps_poller=mps_poller,
                        )
                    run_results.append(r)
                except Exception as e:
                    print(f'  [{label} run={run_idx}] ERROR: {e}')
                    import traceback

                    traceback.print_exc()
                    run_results.append(
                        {
                            'label': label,
                            'run_idx': run_idx,
                            'error': str(e),
                            'wall_seconds': 0,
                        }
                    )

            # Per-file summary with statistical aggregation
            successful = [r for r in run_results if 'error' not in r]
            per_file_entry: dict[str, Any] = {
                'label': label,
                'runs': run_results,
                'errors': len(run_results) - len(successful),
            }
            if successful:
                per_file_entry['aggregate'] = aggregate_runs(successful)
                # Legacy-compatible top-level fields (first successful run)
                first = successful[0]
                per_file_entry['total_seconds'] = first['wall_seconds']
                per_file_entry['speaker_count'] = first['speaker_count']
                per_file_entry['segment_count'] = first['segment_count']
                per_file_entry['stage_durations'] = first['stage_durations']
                per_file_entry['vram_before_mb'] = first.get('vram_before_nvml_mb')
                per_file_entry['vram_after_mb'] = first.get('vram_after_nvml_mb')
                per_file_entry['total_speech_seconds'] = first.get('total_speech_seconds')
                per_file_entry['all_segments'] = first.get('all_segments', [])
            per_file_results.append(per_file_entry)

    finally:
        if mps_poller is not None:
            mps_poller.stop()

    # Build full report
    timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
    import torch

    report: dict[str, Any] = {
        'variant': variant,
        'device': device,
        'device_str': device_str,
        'model_id': model_id,
        'tag': tag,
        'runs': runs,
        'timestamp': timestamp,
        'gpu_info': gpu_info,
        'pipeline_load_time_s': round(load_time, 2),
        'files': per_file_results,
        'torch_version': torch.__version__,
        'cuda_version': torch.version.cuda if torch.cuda.is_available() else None,
        'summary': {
            'total_files': len(per_file_results),
            'total_time_s': round(sum(f.get('total_seconds', 0) for f in per_file_results), 2),
            'errors': sum(f.get('errors', 0) for f in per_file_results),
        },
    }

    # Fork git SHA (best-effort)
    try:
        import subprocess

        src_for_sha = Path(os.environ.get('PYANNOTE_OPTIMIZED_SRC') or DEFAULT_OPTIMIZED_SRC)
        if src_for_sha.exists():
            repo_root = src_for_sha
            while repo_root != repo_root.parent and not (repo_root / '.git').exists():
                repo_root = repo_root.parent
            if (repo_root / '.git').exists():
                sha = subprocess.run(
                    ['git', '-C', str(repo_root), 'rev-parse', 'HEAD'],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                report['pyannote_fork_sha'] = sha
                report['pyannote_fork_path'] = str(repo_root)
    except Exception:
        pass

    # Tagged file + legacy "latest" for the --compare flow
    stem = f'benchmark_{variant}_{tag}_{timestamp}' if tag else f'benchmark_{variant}_{timestamp}'
    out_file = RESULTS_DIR / f'{stem}.json'
    with open(out_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f'\nResults saved to: {out_file}')

    latest_file = RESULTS_DIR / f'benchmark_{variant}_latest.json'
    with open(latest_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print_summary(report)
    return report


def print_summary(report: dict) -> None:
    """Formatted summary (statistical when runs > 1)."""
    print()
    variant = report['variant']
    runs = report.get('runs', 1)
    print(f'{"=" * 110}')
    title = f'  BENCHMARK RESULTS — {variant.upper()} PyAnnote'
    if report.get('tag'):
        title += f' [tag={report["tag"]}]'
    if runs > 1:
        title += f'  ({runs}-run statistical)'
    print(title)
    gpu_name = (report.get('gpu_info') or {}).get('gpu_name', 'N/A')
    print(f'  Device: {report["device_str"]} | GPU: {gpu_name}')
    print(f'  Model: {report.get("model_id")} | Load: {report["pipeline_load_time_s"]}s')
    if report.get('pyannote_fork_sha'):
        print(
            f'  Fork SHA: {report["pyannote_fork_sha"][:12]}  ({report.get("pyannote_fork_path")})'
        )
    print(f'{"=" * 110}')
    if runs > 1:
        print(
            f'  {"File":<16} {"Wall mean":>11} {"stdev":>8} {"cv":>6} '
            f'{"Peak VRAM":>10} {"Steady":>8} {"Spkrs":>6} {"Segs":>6} {"Reliable":>9}'
        )
    else:
        print(
            f'  {"File":<16} {"Wall":>8} {"Peak VRAM":>10} {"Steady":>8} '
            f'{"Spkrs":>7} {"Segs":>8} {"Stages"}'
        )
    print(f'  {"-" * 104}')
    for f in report['files']:
        errors = f.get('errors', 0)
        agg = f.get('aggregate', {}) or {}
        wall_agg = agg.get('wall_seconds', {})
        peak_agg = agg.get('overall_peak_vram_mb', {})
        steady_agg = agg.get('steady_state_vram_mb', {})
        reliable = agg.get('reliable', True)
        if runs > 1:
            if not wall_agg:
                print(f'  {f["label"]:<16} ERROR (all runs failed)')
                continue
            print(
                f'  {f["label"]:<16} '
                f'{wall_agg.get("mean", 0):>10.2f}s '
                f'{wall_agg.get("stdev", 0):>7.2f}s '
                f'{wall_agg.get("cv", 0):>5.1%} '
                f'{peak_agg.get("mean", 0):>8.0f}MB '
                f'{steady_agg.get("mean", 0):>6.0f}MB '
                f'{f.get("speaker_count", 0):>6} '
                f'{f.get("segment_count", 0):>6} '
                f'{"yes" if reliable else "NO":>9}'
            )
        else:
            stages_str = ', '.join(f'{k}={v:.1f}s' for k, v in f.get('stage_durations', {}).items())
            # Use first-run peak/steady if no aggregate
            first_peak = (
                peak_agg.get('mean') if peak_agg else f['runs'][0].get('overall_peak_vram_mb', 0)
            )
            first_steady = (
                steady_agg.get('mean')
                if steady_agg
                else f['runs'][0].get('steady_state_vram_mb', 0)
            )
            if errors:
                print(f'  {f["label"]:<16} ERROR in {errors}/{runs} runs')
                continue
            print(
                f'  {f["label"]:<16} {f.get("total_seconds", 0):>7.1f}s '
                f'{int(first_peak or 0):>8}MB '
                f'{int(first_steady or 0):>6}MB '
                f'{f.get("speaker_count", 0):>7} {f.get("segment_count", 0):>8}   '
                f'{stages_str}'
            )
    print(f'  {"-" * 104}')
    s = report['summary']
    print(
        f'  Total first-run time: {s["total_time_s"]}s across {s["total_files"]} files, {s["errors"]} errors'
    )
    print(f'{"=" * 110}')


def compare_results(variant_a: str, variant_b: str) -> None:
    """Compare two benchmark result sets (legacy single-run compare)."""
    file_a = RESULTS_DIR / f'benchmark_{variant_a}_latest.json'
    file_b = RESULTS_DIR / f'benchmark_{variant_b}_latest.json'

    if not file_a.exists():
        print(f"No results for '{variant_a}' — run benchmark first")
        return
    if not file_b.exists():
        print(f"No results for '{variant_b}' — run benchmark first")
        return

    with open(file_a) as f:
        report_a = json.load(f)
    with open(file_b) as f:
        report_b = json.load(f)

    results_a = {r['label']: r for r in report_a['files']}
    results_b = {r['label']: r for r in report_b['files']}

    print()
    print(f'{"=" * 110}')
    print(f'  COMPARISON: {variant_a.upper()} vs {variant_b.upper()}')
    print(f'  {variant_a}: {report_a["timestamp"]} | {variant_b}: {report_b["timestamp"]}')
    print(f'{"=" * 110}')
    print(
        f'  {"File":<16} '
        f'{"Time A":>8} {"Time B":>8} {"Speedup":>8} '
        f'{"Spkrs A":>8} {"Spkrs B":>8} '
        f'{"Segs A":>8} {"Segs B":>8} {"Seg Diff":>9}'
    )
    print(f'  {"-" * 104}')

    total_a = 0.0
    total_b = 0.0
    for label in TEST_FILES:
        ra = results_a.get(label)
        rb = results_b.get(label)
        if not ra or not rb:
            continue
        if 'error' in ra or 'error' in rb:
            print(f'  {label:<16} ERROR in one or both')
            continue

        ta = ra['total_seconds']
        tb = rb['total_seconds']
        total_a += ta
        total_b += tb
        speedup = ta / tb if tb > 0 else 0
        seg_diff = rb['segment_count'] - ra['segment_count']
        seg_pct = (seg_diff / ra['segment_count'] * 100) if ra['segment_count'] > 0 else 0

        print(
            f'  {label:<16} '
            f'{ta:>7.1f}s {tb:>7.1f}s {speedup:>7.2f}x '
            f'{ra["speaker_count"]:>8} {rb["speaker_count"]:>8} '
            f'{ra["segment_count"]:>8} {rb["segment_count"]:>8} '
            f'{seg_diff:>+8} ({seg_pct:>+.1f}%)'
        )

    print(f'  {"-" * 104}')
    overall_speedup = total_a / total_b if total_b > 0 else 0
    print(f'  {"TOTAL":<16} {total_a:>7.1f}s {total_b:>7.1f}s {overall_speedup:>7.2f}x')
    print(f'{"=" * 110}')

    print('\n  OUTPUT ACCURACY (segment timing differences):')
    print(f'  {"-" * 90}')
    for label in TEST_FILES:
        ra = results_a.get(label)
        rb = results_b.get(label)
        if not ra or not rb or 'error' in ra or 'error' in rb:
            continue
        segs_a = ra.get('all_segments', [])
        segs_b = rb.get('all_segments', [])
        if len(segs_a) != len(segs_b):
            print(f'  [{label}] Segment count mismatch: {len(segs_a)} vs {len(segs_b)}')
        else:
            max_diff = 0.0
            total_diff = 0.0
            speaker_mismatches = 0
            for sa, sb in zip(segs_a, segs_b, strict=False):
                d = abs(sa['start'] - sb['start']) + abs(sa['end'] - sb['end'])
                max_diff = max(max_diff, d)
                total_diff += d
                if sa['speaker'] != sb['speaker']:
                    speaker_mismatches += 1
            avg_diff = total_diff / len(segs_a) if segs_a else 0
            speech_a = ra.get('total_speech_seconds', 0)
            speech_b = rb.get('total_speech_seconds', 0)
            print(
                f'  [{label}] {len(segs_a)} segments | '
                f'timing: avg_diff={avg_diff:.4f}s max_diff={max_diff:.4f}s | '
                f'speaker_mismatches={speaker_mismatches} | '
                f'speech: {speech_a:.1f}s vs {speech_b:.1f}s'
            )
    print(f'  {"-" * 90}')

    print('\n  STAGE BREAKDOWN:')
    print(f'  {"-" * 90}')
    for label in TEST_FILES:
        ra = results_a.get(label)
        rb = results_b.get(label)
        if not ra or not rb or 'error' in ra or 'error' in rb:
            continue
        stages_a = ra.get('stage_durations', {})
        stages_b = rb.get('stage_durations', {})
        all_stages = sorted(set(list(stages_a.keys()) + list(stages_b.keys())))
        print(f'  [{label}]')
        for stage in all_stages:
            sa = stages_a.get(stage, 0)
            sb = stages_b.get(stage, 0)
            sp = sa / sb if sb > 0 else 0
            print(f'    {stage:<30} {sa:>7.2f}s -> {sb:>7.2f}s  ({sp:.2f}x)')
    print(f'  {"-" * 90}')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description='Direct PyAnnote diarization benchmark')
    parser.add_argument(
        '--variant',
        choices=['stock', 'optimized', 'optimized_cpu'],
        help='Which PyAnnote variant to benchmark',
    )
    parser.add_argument('--files', nargs='*', help='Specific file labels (default: all 5)')
    parser.add_argument(
        '--device',
        default='cuda',
        choices=['cuda', 'mps', 'cpu'],
        help='Device (cuda, mps, cpu)',
    )
    parser.add_argument('--gpu-index', type=int, default=0, help='GPU device index (cuda only)')
    parser.add_argument(
        '--runs',
        type=int,
        default=1,
        help='Number of runs per file (default 1; Phase A-style statistical: 5)',
    )
    parser.add_argument(
        '--tag',
        default=None,
        help='Label included in output filenames and report metadata',
    )
    parser.add_argument(
        '--rttm-out',
        default=None,
        help='Directory to write RTTM output per run (for DER scoring downstream)',
    )
    parser.add_argument(
        '--profiler',
        action='store_true',
        help='Wrap run 0 in torch.profiler and export a Chrome trace',
    )
    parser.add_argument(
        '--model',
        default=DEFAULT_MODEL,
        help=f'Diarization model id (default: {DEFAULT_MODEL})',
    )
    parser.add_argument(
        '--optimized-src',
        default=os.environ.get('PYANNOTE_OPTIMIZED_SRC'),
        help=(
            'Path to the canonical davidamacey/pyannote-audio fork src (default: '
            f'{DEFAULT_OPTIMIZED_SRC}).'
        ),
    )
    parser.add_argument(
        '--torch-compile',
        action='store_true',
        help=(
            'After loading the pipeline, wrap the segmentation and embedding '
            'models in torch.compile() (Phase 2.1 follow-up). First run pays a '
            'JIT warmup cost; subsequent runs should be ~5-15%% faster if '
            'Dynamo does not hit a graph break.'
        ),
    )
    parser.add_argument(
        '--segmentation-step',
        type=float,
        default=None,
        help=(
            'Override the segmentation sliding-window step (default ~0.1 = '
            '90%% overlap). Higher values make segmentation N× faster at a '
            'DER cost — Phase 4 measures this trade-off.'
        ),
    )
    parser.add_argument(
        '--both',
        action='store_true',
        help='Run stock then optimized back-to-back and compare',
    )
    parser.add_argument(
        '--compare',
        nargs=2,
        metavar=('A', 'B'),
        help='Compare two saved result sets (e.g., --compare stock optimized)',
    )
    args = parser.parse_args()

    if args.compare:
        compare_results(args.compare[0], args.compare[1])
        return

    file_labels = args.files or TEST_FILES
    rttm_out = Path(args.rttm_out) if args.rttm_out else None
    optimized_src = Path(args.optimized_src) if args.optimized_src else None

    if args.both:
        import subprocess

        script = str(Path(__file__).resolve())
        base_args = [sys.executable, '-W', 'ignore', script]
        extra = []
        if args.files:
            extra += ['--files'] + args.files
        extra += [
            '--device',
            args.device,
            '--gpu-index',
            str(args.gpu_index),
            '--runs',
            str(args.runs),
            '--model',
            args.model,
        ]
        if args.tag:
            extra += ['--tag', args.tag]
        if args.rttm_out:
            extra += ['--rttm-out', args.rttm_out]
        if args.profiler:
            extra += ['--profiler']

        print('=' * 60)
        print('  RUNNING STOCK BASELINE (subprocess)')
        print('=' * 60)
        subprocess.run(base_args + ['--variant', 'stock'] + extra, check=True)

        print('\n\n')
        print('=' * 60)
        print('  RUNNING OPTIMIZED (subprocess)')
        print('=' * 60)
        opt_env = os.environ.copy()
        opt_src_str = str(optimized_src or DEFAULT_OPTIMIZED_SRC)
        opt_env['PYTHONPATH'] = opt_src_str + ':' + opt_env.get('PYTHONPATH', '')
        if args.optimized_src:
            opt_env['PYANNOTE_OPTIMIZED_SRC'] = str(optimized_src)
            extra += ['--optimized-src', str(optimized_src)]
        subprocess.run(base_args + ['--variant', 'optimized'] + extra, env=opt_env, check=True)

        print('\n\n')
        compare_results('stock', 'optimized')
        return

    if not args.variant:
        parser.print_help()
        sys.exit(1)

    onnx_cpu = args.variant == 'optimized_cpu'
    device = 'cpu' if onnx_cpu else args.device
    run_benchmark(
        args.variant,
        file_labels,
        device,
        args.gpu_index,
        onnx_cpu=onnx_cpu,
        runs=args.runs,
        tag=args.tag,
        rttm_out=rttm_out,
        profiler=args.profiler,
        model_id=args.model,
        optimized_src=optimized_src,
        torch_compile=args.torch_compile,
        segmentation_step=args.segmentation_step,
    )


if __name__ == '__main__':
    main()
