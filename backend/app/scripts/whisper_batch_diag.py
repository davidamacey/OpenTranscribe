"""WhisperX batch_size vs VRAM diagnostic — Phase B study.

Sweeps batch_size across a range for a given model and audio file, recording
peak VRAM, stable VRAM, wall time, and real-time factor (RTF) at each setting.

Mirrors the diarization Phase A study methodology.  Results inform the
WHISPER_VRAM_BUDGET_MB table in hardware_detection.py.

Run inside the celery-worker container (has GPU + loaded torch):

    docker exec -it opentranscribe-celery-worker \\
        python -m app.scripts.whisper_batch_diag \\
            --audio /tmp/2.2h_7998s.wav \\
            --model large-v3-turbo \\
            --batch-sizes 2,4,8,12,16,24,32 \\
            --output /tmp/whisper_batch_a6000.csv

Save results to docs/whisper-vram-profile/ after each GPU run.
"""

from __future__ import annotations

import argparse
import csv
import gc
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

FIELDS = [
    "model",
    "compute_type",
    "batch_size",
    "audio_file",
    "audio_duration_s",
    "gpu_name",
    "gpu_total_vram_mb",
    "vram_baseline_mb",
    "vram_stable_before_mb",
    "vram_peak_mb",
    "vram_stable_after_mb",
    "wall_time_s",
    "rtf",
    "status",
    "note",
]


def _mb(bytes_: int) -> float:
    return round(bytes_ / 1024**2, 1)


def run_sweep(
    audio_path: Path,
    model_name: str,
    batch_sizes: list[int],
    compute_type: str,
    output_csv: Path,
) -> None:
    import numpy as np
    import torch

    if not torch.cuda.is_available():
        print("ERROR: CUDA not available — run inside the GPU worker container.", file=sys.stderr)
        sys.exit(1)

    gpu_name = torch.cuda.get_device_name(0)
    gpu_total = torch.cuda.get_device_properties(0).total_memory
    print(f"GPU : {gpu_name}  ({_mb(gpu_total):.0f} MB total)")
    print(f"Model: {model_name}  compute_type: {compute_type}")
    print(f"Audio: {audio_path.name}")

    # Load audio once — 16 kHz mono numpy array
    from app.transcription.audio import load_audio

    audio: np.ndarray = load_audio(str(audio_path))
    audio_duration = len(audio) / 16000.0
    print(f"Duration: {audio_duration:.1f}s  ({audio_duration / 3600:.2f}h)")

    # Baseline VRAM with no model loaded
    torch.cuda.empty_cache()
    gc.collect()
    baseline_mb = _mb(torch.cuda.memory_allocated())
    print(f"Baseline VRAM (no model): {baseline_mb:.0f} MB")
    print()
    print(
        f"{'batch':>6}  {'stable_before MB':>16}  {'peak MB':>9}  "
        f"{'stable_after MB':>15}  {'wall s':>8}  {'RTF':>7}  status"
    )
    print("-" * 80)

    rows: list[dict] = []

    for bs in batch_sizes:
        torch.cuda.empty_cache()
        gc.collect()
        torch.cuda.reset_peak_memory_stats()

        from app.transcription.config import TranscriptionConfig

        cfg = TranscriptionConfig(
            model_name=model_name,
            compute_type=compute_type,
            batch_size=bs,
            beam_size=5,
            device="cuda",
            device_index=0,
        )

        from app.transcription.transcriber import Transcriber

        transcriber = Transcriber(cfg)
        transcriber.load_model()

        stable_before = _mb(torch.cuda.memory_allocated())
        torch.cuda.reset_peak_memory_stats()

        t0 = time.perf_counter()
        status = "ok"
        note = ""
        peak_mb = stable_after = rtf = wall_time = None
        try:
            transcriber.transcribe(audio)
            wall_time = round(time.perf_counter() - t0, 2)
            peak_mb = _mb(torch.cuda.max_memory_allocated())
            stable_after = _mb(torch.cuda.memory_allocated())
            rtf = round(wall_time / audio_duration, 4)
        except torch.cuda.OutOfMemoryError as exc:
            status = "OOM"
            note = str(exc)[:120]
        except Exception as exc:
            status = "ERROR"
            note = str(exc)[:120]

        print(
            f"{bs:>6}  {stable_before:>16.0f}  {peak_mb or 0:>9.0f}  "
            f"{stable_after or 0:>15.0f}  {wall_time or 0:>8.1f}  "
            f"{rtf or 0:>7.3f}  {status}"
        )

        rows.append(
            {
                "model": model_name,
                "compute_type": compute_type,
                "batch_size": bs,
                "audio_file": audio_path.name,
                "audio_duration_s": round(audio_duration, 1),
                "gpu_name": gpu_name,
                "gpu_total_vram_mb": round(_mb(gpu_total), 0),
                "vram_baseline_mb": baseline_mb,
                "vram_stable_before_mb": stable_before,
                "vram_peak_mb": peak_mb,
                "vram_stable_after_mb": stable_after,
                "wall_time_s": wall_time,
                "rtf": rtf,
                "status": status,
                "note": note,
            }
        )

        del transcriber
        torch.cuda.empty_cache()
        gc.collect()

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved: {output_csv}")
    print()
    _print_summary(rows, gpu_total)


def _print_summary(rows: list[dict], gpu_total_bytes: int) -> None:
    total_mb = gpu_total_bytes / 1024**2
    print("=== VRAM budget headroom (80% rule: peak <= 0.80 x total) ===")
    print(f"{'batch':>6}  {'peak MB':>9}  {'80% threshold MB':>17}  {'safe?':>6}  {'RTF':>7}")
    threshold = total_mb * 0.80
    for r in rows:
        if r["status"] != "ok":
            print(f"{r['batch_size']:>6}  {'OOM/ERR':>9}  {threshold:>17.0f}  {'NO':>6}  —")
            continue
        safe = "YES" if r["vram_peak_mb"] <= threshold else "NO "
        print(
            f"{r['batch_size']:>6}  {r['vram_peak_mb']:>9.0f}  {threshold:>17.0f}  "
            f"{safe:>6}  {r['rtf']:>7.3f}"
        )


def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="WhisperX batch_size vs VRAM diagnostic")
    parser.add_argument("--audio", required=True, help="Path to WAV file (16 kHz preferred)")
    parser.add_argument("--model", default="large-v3-turbo", help="Whisper model name")
    parser.add_argument(
        "--batch-sizes",
        default="2,4,8,12,16,24,32",
        help="Comma-separated batch sizes to test (default: 2,4,8,12,16,24,32)",
    )
    parser.add_argument(
        "--compute-type",
        default="int8_float16",
        help="CTranslate2 compute type (default: int8_float16)",
    )
    parser.add_argument("--output", default="/tmp/whisper_batch_results.csv", help="Output CSV")  # noqa: S108  # nosec B108
    args = parser.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"ERROR: audio file not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    batch_sizes = [int(b.strip()) for b in args.batch_sizes.split(",")]

    run_sweep(
        audio_path=audio_path,
        model_name=args.model,
        batch_sizes=batch_sizes,
        compute_type=args.compute_type,
        output_csv=Path(args.output),
    )


if __name__ == "__main__":
    main()
