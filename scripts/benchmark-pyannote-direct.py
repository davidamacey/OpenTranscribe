#!/usr/bin/env python3
"""Direct PyAnnote diarization benchmark — stock vs optimized.

Runs PyAnnote speaker diarization directly on WAV files, bypassing the
OpenTranscribe API. Captures per-stage timing, speaker counts, segment counts,
and VRAM usage. Results saved to JSON for PR evidence.

Usage:
    # Stock PyAnnote baseline (uses installed pyannote-audio)
    python scripts/benchmark-pyannote-direct.py --variant stock --files 0.5h_1899s

    # Optimized fork (uses reference_repos/pyannote-audio-optimized)
    python scripts/benchmark-pyannote-direct.py --variant optimized --files 0.5h_1899s

    # Run all 5 files
    python scripts/benchmark-pyannote-direct.py --variant stock

    # Compare saved results
    python scripts/benchmark-pyannote-direct.py --compare stock optimized
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
AUDIO_DIR = PROJECT_ROOT / "benchmark" / "test_audio"
RESULTS_DIR = PROJECT_ROOT / "benchmark" / "results"

TEST_FILES = [
    "0.5h_1899s",
    "1.0h_3758s",
    "2.2h_7998s",
    "3.2h_11495s",
    "4.7h_17044s",
]

HF_TOKEN = os.environ.get("HUGGINGFACE_TOKEN", "")
GPU_INDEX = int(os.environ.get("CUDA_DEVICE_INDEX", "0"))


def get_gpu_info() -> dict | None:
    """Get GPU info via pynvml."""
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode()
        result = {
            "gpu_name": name,
            "vram_total_mb": round(mem.total / (1024**2)),
            "vram_used_mb": round(mem.used / (1024**2)),
            "vram_free_mb": round(mem.free / (1024**2)),
        }
        pynvml.nvmlShutdown()
        return result
    except Exception:
        return None


def get_vram_used_mb() -> int | None:
    """Get current VRAM used in MB."""
    info = get_gpu_info()
    return info["vram_used_mb"] if info else None


def load_pipeline(
    variant: str,
    device: str = "cuda",
    gpu_index: int = 0,
    onnx_cpu: bool = False,
):
    """Load PyAnnote pipeline for the given variant.

    For 'optimized' variant, the optimized fork's src must be prepended to
    PYTHONPATH before launching this process (--both mode does this automatically).
    For single-variant runs, use --variant optimized which sets sys.path.
    """
    import torch

    if variant in ("optimized", "optimized_cpu"):
        opt_src = str(PROJECT_ROOT / "reference_repos" / "pyannote-audio-optimized" / "src")
        if opt_src not in sys.path:
            sys.path.insert(0, opt_src)
        # Force reimport from optimized path
        for mod in list(sys.modules.keys()):
            if "pyannote" in mod:
                del sys.modules[mod]

    from pyannote.audio import Pipeline

    device_str = f"cuda:{gpu_index}" if device == "cuda" else device

    print(f"Loading PyAnnote pipeline ({variant}) on {device_str}...")
    t0 = time.perf_counter()
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=HF_TOKEN or None,
        )
    except TypeError:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=HF_TOKEN or None,
        )
    pipeline.to(torch.device(device_str))

    # Enable optimizations for optimized variants
    if variant in ("optimized", "optimized_cpu") and device_str != "cpu":
        # Increase embedding batch size (default auto-detected is often too small)
        if hasattr(pipeline, "embedding_batch_size"):
            old_bs = pipeline.embedding_batch_size
            new_bs = max(old_bs, 128)
            pipeline.embedding_batch_size = new_bs
            print(f"  Embedding batch size: {old_bs} -> {new_bs}")

        # NOTE: torch.compile adds 20-30s JIT warmup per run — only beneficial
        # for repeated calls (e.g. batch processing). Disabled for benchmarks.
        # NOTE: mixed_precision (float16) causes segmentation accuracy loss
        # on some models (2 speakers detected instead of 5). Disabled.

    # Enable ONNX CPU inference for optimized_cpu variant
    if onnx_cpu and hasattr(pipeline, "_setup_onnx_cpu"):
        print("  Enabling ONNX CPU inference (quantized INT8)...")
        pipeline._setup_onnx_cpu(quantize=True, num_threads=0)
        if getattr(pipeline, "_onnx_cpu", False):
            print("  ONNX CPU mode active")
        else:
            print("  WARNING: ONNX setup failed, falling back to PyTorch CPU")

    load_time = time.perf_counter() - t0
    print(f"  Pipeline loaded in {load_time:.1f}s on {device_str}")

    # Verify which module is loaded
    mod_file = sys.modules.get("pyannote.audio.pipelines.speaker_diarization", None)
    if mod_file:
        print(f"  Module: {getattr(mod_file, '__file__', 'unknown')}")

    return pipeline, load_time


def run_diarization(pipeline, audio_path: str, label: str) -> dict:
    """Run diarization on a single file with timing hooks."""
    import torch

    stage_timing: dict[str, dict[str, float]] = {}

    def timing_hook(step_name, step_artefact, **kwargs):
        now = time.perf_counter()
        if step_name not in stage_timing:
            stage_timing[step_name] = {"start": now}
        stage_timing[step_name]["last"] = now

    vram_before = get_vram_used_mb()
    vram_peak = vram_before or 0

    # Pre-load audio with torchaudio (avoids torchcodec dependency)
    import torchaudio

    waveform, sample_rate = torchaudio.load(audio_path)
    audio_input = {"waveform": waveform, "sample_rate": sample_rate}
    duration_s = waveform.shape[1] / sample_rate
    print(f"  [{label}] Diarizing {audio_path} ({duration_s:.0f}s, sr={sample_rate})...")
    t0 = time.perf_counter()

    diarization = pipeline(audio_input, hook=timing_hook)

    elapsed = time.perf_counter() - t0
    vram_after = get_vram_used_mb()
    if vram_after and vram_after > vram_peak:
        vram_peak = vram_after

    # Clear GPU cache
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Extract results — v4 returns DiarizeOutput, v3 returns Annotation
    annotation = getattr(diarization, "speaker_diarization", diarization)
    speakers = set()
    segments = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        speakers.add(speaker)
        segments.append({
            "start": round(turn.start, 3),
            "end": round(turn.end, 3),
            "speaker": speaker,
        })

    # Compute stage durations from timing hooks
    # Each hook fires with a "start" time. We compute duration as the time
    # from this hook's first fire to the next hook's first fire.
    stage_durations = {}
    if stage_timing:
        stages = sorted(stage_timing.items(), key=lambda x: x[1].get("start", 0))
        for i, (name, times) in enumerate(stages):
            if i + 1 < len(stages):
                # Duration = time until next stage starts
                next_start = stages[i + 1][1]["start"]
                dur = next_start - times["start"]
            else:
                # Last stage: duration until pipeline returned
                dur = (t0 + elapsed) - times["start"]
            stage_durations[name] = round(dur, 3)

    # Compute total speech duration
    total_speech_s = sum(s["end"] - s["start"] for s in segments)

    result = {
        "label": label,
        "audio_file": str(audio_path),
        "total_seconds": round(elapsed, 2),
        "speaker_count": len(speakers),
        "segment_count": len(segments),
        "total_speech_seconds": round(total_speech_s, 2),
        "speakers": sorted(speakers),
        "stage_durations": stage_durations,
        "vram_before_mb": vram_before,
        "vram_after_mb": vram_after,
        "all_segments": segments,
    }

    print(
        f"  [{label}] Done in {elapsed:.1f}s | "
        f"{len(speakers)} speakers | {len(segments)} segments"
    )
    if stage_durations:
        for stage, dur in stage_durations.items():
            print(f"    {stage}: {dur:.1f}s")

    return result


def run_benchmark(
    variant: str,
    file_labels: list[str],
    device: str = "cuda",
    gpu_index: int = 0,
    onnx_cpu: bool = False,
) -> dict:
    """Run full benchmark suite."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    gpu_info = get_gpu_info()
    if gpu_info:
        print(
            f"GPU: {gpu_info['gpu_name']} | "
            f"VRAM: {gpu_info['vram_used_mb']}/{gpu_info['vram_total_mb']} MB"
        )

    pipeline, load_time = load_pipeline(variant, device, gpu_index, onnx_cpu=onnx_cpu)

    results = []
    for label in file_labels:
        audio_path = AUDIO_DIR / f"{label}.wav"
        if not audio_path.exists():
            print(f"  SKIP {label} — {audio_path} not found")
            continue

        try:
            result = run_diarization(pipeline, str(audio_path), label)
            results.append(result)
        except Exception as e:
            print(f"  [{label}] ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "label": label,
                "error": str(e),
                "total_seconds": 0,
            })

    # Build full report
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report = {
        "variant": variant,
        "device": device,
        "timestamp": timestamp,
        "gpu_info": gpu_info,
        "pipeline_load_time_s": round(load_time, 2),
        "files": results,
        "summary": {
            "total_files": len(results),
            "total_time_s": round(sum(r.get("total_seconds", 0) for r in results), 2),
            "errors": sum(1 for r in results if "error" in r),
        },
    }

    # Save to file
    out_file = RESULTS_DIR / f"benchmark_{variant}_{timestamp}.json"
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nResults saved to: {out_file}")

    # Also save as "latest" for easy comparison
    latest_file = RESULTS_DIR / f"benchmark_{variant}_latest.json"
    with open(latest_file, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary table
    print_summary(report)

    return report


def print_summary(report: dict) -> None:
    """Print a formatted summary table."""
    print()
    variant = report["variant"]
    print(f"{'=' * 100}")
    print(f"  BENCHMARK RESULTS — {variant.upper()} PyAnnote")
    print(f"  Device: {report['device']} | GPU: {report.get('gpu_info', {}).get('gpu_name', 'N/A')}")
    print(f"  Pipeline load: {report['pipeline_load_time_s']}s")
    print(f"{'=' * 100}")
    print(
        f"  {'File':<16} {'Time':>8} {'Spkrs':>7} {'Segs':>8} "
        f"{'VRAM-pre':>10} {'VRAM-post':>10} {'Stages'}"
    )
    print(f"  {'-' * 94}")
    for r in report["files"]:
        if "error" in r:
            print(f"  {r['label']:<16} ERROR: {r['error']}")
            continue
        stages_str = ", ".join(
            f"{k}={v:.0f}s" for k, v in r.get("stage_durations", {}).items()
        )
        print(
            f"  {r['label']:<16} {r['total_seconds']:>7.1f}s "
            f"{r['speaker_count']:>7} {r['segment_count']:>8} "
            f"{r.get('vram_before_mb', '?'):>9}M {r.get('vram_after_mb', '?'):>9}M "
            f"{stages_str}"
        )
    print(f"  {'-' * 94}")
    s = report["summary"]
    print(f"  Total: {s['total_time_s']}s across {s['total_files']} files, {s['errors']} errors")
    print(f"{'=' * 100}")


def compare_results(variant_a: str, variant_b: str) -> None:
    """Compare two benchmark result sets."""
    file_a = RESULTS_DIR / f"benchmark_{variant_a}_latest.json"
    file_b = RESULTS_DIR / f"benchmark_{variant_b}_latest.json"

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

    # Index by label
    results_a = {r["label"]: r for r in report_a["files"]}
    results_b = {r["label"]: r for r in report_b["files"]}

    print()
    print(f"{'=' * 110}")
    print(f"  COMPARISON: {variant_a.upper()} vs {variant_b.upper()}")
    print(f"  {variant_a}: {report_a['timestamp']} | {variant_b}: {report_b['timestamp']}")
    print(f"{'=' * 110}")
    print(
        f"  {'File':<16} "
        f"{'Time A':>8} {'Time B':>8} {'Speedup':>8} "
        f"{'Spkrs A':>8} {'Spkrs B':>8} "
        f"{'Segs A':>8} {'Segs B':>8} {'Seg Diff':>9}"
    )
    print(f"  {'-' * 104}")

    total_a = 0
    total_b = 0
    for label in TEST_FILES:
        ra = results_a.get(label)
        rb = results_b.get(label)
        if not ra or not rb:
            continue
        if "error" in ra or "error" in rb:
            print(f"  {label:<16} ERROR in one or both")
            continue

        ta = ra["total_seconds"]
        tb = rb["total_seconds"]
        total_a += ta
        total_b += tb
        speedup = ta / tb if tb > 0 else 0
        seg_diff = rb["segment_count"] - ra["segment_count"]
        seg_pct = (seg_diff / ra["segment_count"] * 100) if ra["segment_count"] > 0 else 0

        print(
            f"  {label:<16} "
            f"{ta:>7.1f}s {tb:>7.1f}s {speedup:>7.2f}x "
            f"{ra['speaker_count']:>8} {rb['speaker_count']:>8} "
            f"{ra['segment_count']:>8} {rb['segment_count']:>8} "
            f"{seg_diff:>+8} ({seg_pct:>+.1f}%)"
        )

    print(f"  {'-' * 104}")
    overall_speedup = total_a / total_b if total_b > 0 else 0
    print(
        f"  {'TOTAL':<16} "
        f"{total_a:>7.1f}s {total_b:>7.1f}s {overall_speedup:>7.2f}x"
    )
    print(f"{'=' * 110}")

    # Output accuracy comparison
    print(f"\n  OUTPUT ACCURACY (segment timing differences):")
    print(f"  {'-' * 90}")
    for label in TEST_FILES:
        ra = results_a.get(label)
        rb = results_b.get(label)
        if not ra or not rb or "error" in ra or "error" in rb:
            continue
        segs_a = ra.get("all_segments", [])
        segs_b = rb.get("all_segments", [])
        if len(segs_a) != len(segs_b):
            print(f"  [{label}] Segment count mismatch: {len(segs_a)} vs {len(segs_b)}")
        else:
            # Compare segment boundaries
            max_diff = 0.0
            total_diff = 0.0
            speaker_mismatches = 0
            for sa, sb in zip(segs_a, segs_b):
                d = abs(sa["start"] - sb["start"]) + abs(sa["end"] - sb["end"])
                max_diff = max(max_diff, d)
                total_diff += d
                if sa["speaker"] != sb["speaker"]:
                    speaker_mismatches += 1
            avg_diff = total_diff / len(segs_a) if segs_a else 0
            speech_a = ra.get("total_speech_seconds", 0)
            speech_b = rb.get("total_speech_seconds", 0)
            print(
                f"  [{label}] {len(segs_a)} segments | "
                f"timing: avg_diff={avg_diff:.4f}s max_diff={max_diff:.4f}s | "
                f"speaker_mismatches={speaker_mismatches} | "
                f"speech: {speech_a:.1f}s vs {speech_b:.1f}s"
            )
    print(f"  {'-' * 90}")

    # Stage-level comparison
    print(f"\n  STAGE BREAKDOWN:")
    print(f"  {'-' * 90}")
    for label in TEST_FILES:
        ra = results_a.get(label)
        rb = results_b.get(label)
        if not ra or not rb or "error" in ra or "error" in rb:
            continue
        stages_a = ra.get("stage_durations", {})
        stages_b = rb.get("stage_durations", {})
        all_stages = sorted(set(list(stages_a.keys()) + list(stages_b.keys())))
        print(f"  [{label}]")
        for stage in all_stages:
            sa = stages_a.get(stage, 0)
            sb = stages_b.get(stage, 0)
            sp = sa / sb if sb > 0 else 0
            print(f"    {stage:<30} {sa:>7.1f}s -> {sb:>7.1f}s  ({sp:.2f}x)")
    print(f"  {'-' * 90}")


def main():
    parser = argparse.ArgumentParser(description="Direct PyAnnote diarization benchmark")
    parser.add_argument(
        "--variant",
        choices=["stock", "optimized", "optimized_cpu"],
        help="Which PyAnnote variant to benchmark",
    )
    parser.add_argument("--files", nargs="*", help="Specific file labels (default: all 5)")
    parser.add_argument("--device", default="cuda", help="Device (cuda or cpu)")
    parser.add_argument("--gpu-index", type=int, default=0, help="GPU device index (default: 0)")
    parser.add_argument("--both", action="store_true", help="Run stock then optimized back-to-back and compare")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("A", "B"),
        help="Compare two saved result sets (e.g., --compare stock optimized)",
    )
    args = parser.parse_args()

    if args.compare:
        compare_results(args.compare[0], args.compare[1])
        return

    file_labels = args.files or TEST_FILES

    if args.both:
        import subprocess

        # Run each variant in a separate subprocess for clean module isolation
        script = str(Path(__file__).resolve())
        base_args = [sys.executable, "-W", "ignore", script]
        extra = []
        if args.files:
            extra += ["--files"] + args.files
        extra += ["--device", args.device, "--gpu-index", str(args.gpu_index)]

        print("=" * 60)
        print("  RUNNING STOCK BASELINE (subprocess)")
        print("=" * 60)
        subprocess.run(base_args + ["--variant", "stock"] + extra, check=True)

        print("\n\n")
        print("=" * 60)
        print("  RUNNING OPTIMIZED (subprocess)")
        print("=" * 60)
        opt_env = os.environ.copy()
        opt_src = str(PROJECT_ROOT / "reference_repos" / "pyannote-audio-optimized" / "src")
        opt_env["PYTHONPATH"] = opt_src + ":" + opt_env.get("PYTHONPATH", "")
        subprocess.run(base_args + ["--variant", "optimized"] + extra, env=opt_env, check=True)

        print("\n\n")
        compare_results("stock", "optimized")
        return

    if not args.variant:
        parser.print_help()
        sys.exit(1)

    onnx_cpu = args.variant == "optimized_cpu"
    device = "cpu" if onnx_cpu else args.device
    run_benchmark(args.variant, file_labels, device, args.gpu_index, onnx_cpu=onnx_cpu)


if __name__ == "__main__":
    main()
