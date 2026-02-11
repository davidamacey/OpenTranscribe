#!/usr/bin/env python
"""
Compare two benchmark JSON files (before/after optimization).

Usage:
    cd /mnt/nvm/repos/transcribe-app/backend
    python -m scripts.compare_benchmarks baseline.json optimized.json
"""

import json
import sys
from pathlib import Path


def fmt(ms: float) -> str:
    """Format milliseconds for display."""
    if ms < 1:
        return f"{ms:.3f} ms"
    return f"{ms:.1f} ms"


def pct_change(before: float, after: float) -> str:
    """Format percentage change."""
    if before == 0:
        return "N/A"
    change = ((before - after) / before) * 100
    sign = "+" if change < 0 else ""
    return f"{sign}{change:.1f}% {'faster' if change > 0 else 'slower'}"


def compare(baseline_path: str, optimized_path: str):
    baseline = json.loads(Path(baseline_path).read_text())
    optimized = json.loads(Path(optimized_path).read_text())

    print("=" * 72)
    print("  Performance Comparison Report")
    print("=" * 72)
    print(f"  Baseline:  {baseline.get('timestamp', 'unknown')}")
    print(f"  Optimized: {optimized.get('timestamp', 'unknown')}")
    print(f"  Files:     {baseline.get('total_files', '?')}")
    print(f"  Segments:  {baseline.get('total_segments', '?')}")
    print("=" * 72)

    # Metrics to compare (label, key)
    metrics = [
        ("Gallery page 1", "gallery_page1"),
        ("Status (Python loop)", "status_python_loop"),
        ("Status (SQL GROUP BY)", "status_sql_group_by"),
        ("Speaker (JOIN+DISTINCT)", "speaker_join_distinct"),
        ("Speaker (EXISTS)", "speaker_exists_subquery"),
        ("Tag (chained JOIN)", "tag_chained_join"),
        ("Tag (HAVING COUNT)", "tag_having_count"),
        ("Transcript (ILIKE)", "transcript_ilike"),
    ]

    print(f"\n{'Metric':<28} {'Baseline':>12} {'Optimized':>12} {'Change':>20}")
    print("-" * 72)

    for label, key in metrics:
        b = baseline.get(key)
        o = optimized.get(key)
        if b is not None and o is not None:
            print(f"  {label:<26} {fmt(b):>12} {fmt(o):>12} {pct_change(b, o):>20}")
        elif b is not None:
            print(f"  {label:<26} {fmt(b):>12} {'—':>12} {'—':>20}")
        elif o is not None:
            print(f"  {label:<26} {'—':>12} {fmt(o):>12} {'—':>20}")

    print("\n" + "=" * 72)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <baseline.json> <optimized.json>")
        sys.exit(1)
    compare(sys.argv[1], sys.argv[2])
