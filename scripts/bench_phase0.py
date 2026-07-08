#!/usr/bin/env python3
"""Phase 0 performance benchmark (docs/QUALITY_GATES.md Performance Gate).

Measures validate + bar-build (1M/5M/4H) + spread-report + Parquet-write
throughput on one synthetic month, then extrapolates to the 3-year budget
target. This is a synthetic-data proxy, not a real-hardware/real-data
measurement (real Dukascopy access is unavailable in this environment, see
docs/KNOWN_ISSUES.md) — per D-032, budgets get calibrated for real once a
real 3-year download is possible. Results are written to benchmarks/.
"""

from __future__ import annotations

import json
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.demo_phase0 import _synthetic_month

from src.core.types import TF
from src.data.bar_builder import BarBuilder
from src.data.spread_report import build_spread_report
from src.data.tick_store import TickParquetStore
from src.data.validator import Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
MONTHS_IN_3_YEARS = 36
BUDGET_3YR_SECONDS = 60 * 60


def peak_rss_mb() -> float:
    """Peak resident set size so far, in MB (Linux: ru_maxrss is KB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main() -> None:
    print("generating one synthetic month (not timed)...")
    ticks = _synthetic_month("XAUUSD", 2024, 3)
    print(f"tick count: {ticks.height:,}")

    t0 = time.perf_counter()
    Validator().validate(ticks, "XAUUSD")
    t_validate = time.perf_counter() - t0

    t0 = time.perf_counter()
    builder = BarBuilder()
    bars_1m = builder.build(ticks, TF.M1)
    bars_5m = builder.build(ticks, TF.M5)
    bars_4h = builder.build(ticks, TF.H4)
    t_build = time.perf_counter() - t0

    t0 = time.perf_counter()
    build_spread_report(ticks, "XAUUSD")
    t_spread = time.perf_counter() - t0

    bench_dir = REPO_ROOT / "benchmarks"
    bench_dir.mkdir(exist_ok=True)
    store = TickParquetStore(bench_dir / "_scratch_ticks")
    t0 = time.perf_counter()
    store.write_month("XAUUSD", 2024, 3, ticks)
    t_write = time.perf_counter() - t0

    total_month_seconds = t_validate + t_build + t_spread + t_write
    extrapolated_3yr_seconds = total_month_seconds * MONTHS_IN_3_YEARS

    result = {
        "measured_at": datetime.now(UTC).isoformat(),
        "data_source": "synthetic (real Dukascopy access unavailable in this environment)",
        "tick_count_one_month": ticks.height,
        "seconds": {
            "validate": round(t_validate, 4),
            "build_bars_1m_5m_4h": round(t_build, 4),
            "spread_report": round(t_spread, 4),
            "parquet_write": round(t_write, 4),
            "total_one_month": round(total_month_seconds, 4),
        },
        "bar_counts": {"1M": len(bars_1m), "5M": len(bars_5m), "4H": len(bars_4h)},
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "extrapolated_36_months_seconds": round(extrapolated_3yr_seconds, 1),
        "budget_3yr_seconds": BUDGET_3YR_SECONDS,
        "within_budget_extrapolated": extrapolated_3yr_seconds <= BUDGET_3YR_SECONDS,
        "note": (
            "Extrapolated linearly from one synthetic month; real tick "
            "density and I/O characteristics differ from Dukascopy's actual "
            "feed. Must be re-measured against a real 3-year download "
            "before this budget is treated as calibrated (D-032)."
        ),
    }

    out_path = bench_dir / "phase0_bench.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"\nwritten to {out_path}")


if __name__ == "__main__":
    main()
