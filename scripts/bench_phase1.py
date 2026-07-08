#!/usr/bin/env python3
"""Phase 1 performance benchmark (docs/QUALITY_GATES.md Performance Gate).

No pre-declared budget exists yet for Phase 1 in docs/QUALITY_GATES.md;
per D-032 this run establishes the initial measurement. Results are
written to benchmarks/.
"""

from __future__ import annotations

import json
import random
import resource
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.types import TF, Bar
from src.displacement.d1_body import D1BodyRatio
from src.fvg.engine import FVGEngine
from src.store.state_store import StateStore
from src.structure.engine import StructureEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
ONE_YEAR_4H_BARS = 365 * 6


def synthetic_4h_bars(n: int, seed: int = 3) -> list[Bar]:
    rng = random.Random(seed)
    bars = []
    price = 2000.0
    ts = datetime(2023, 1, 1, tzinfo=UTC)
    interval = timedelta(hours=4)
    for _ in range(n):
        o = price
        c = o + rng.uniform(-4.0, 4.0)
        h = max(o, c) + rng.uniform(0.0, 2.0)
        low = min(o, c) - rng.uniform(0.0, 2.0)
        bars.append(
            Bar(tf=TF.H4, open_ts=ts, close_ts=ts + interval, o=o, h=h, l=low, c=c, tick_volume=1)
        )
        price = c
        ts += interval
    return bars


def peak_rss_mb() -> float:
    """Peak resident set size so far, in MB (Linux: ru_maxrss is KB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main() -> None:
    bars = synthetic_4h_bars(ONE_YEAR_4H_BARS)
    print(f"bars: {len(bars)} (~1 year of synthetic 4H bars)")

    store = StateStore()
    structure = StructureEngine(TF.H4, is_bias_source=True)
    fvg_engine = FVGEngine(TF.H4, displacement_model=D1BodyRatio(), displacement_params={})

    t0 = time.perf_counter()
    for bar in bars:
        structure.step(bar, store)
        fvg_engine.step_bar_close(bar, store)
    elapsed = time.perf_counter() - t0

    result = {
        "measured_at": datetime.now(UTC).isoformat(),
        "bar_count": len(bars),
        "seconds": round(elapsed, 4),
        "bars_per_second": round(len(bars) / elapsed, 1) if elapsed > 0 else None,
        "swings": len(store.all_swings(TF.H4)),
        "fvgs": len(store.all_fvgs(TF.H4)),
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "note": (
            "No pre-declared Phase 1 budget in QUALITY_GATES.md; "
            "this establishes D-032's initial measurement."
        ),
    }

    bench_dir = REPO_ROOT / "benchmarks"
    bench_dir.mkdir(exist_ok=True)
    out_path = bench_dir / "phase1_bench.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"\nwritten to {out_path}")


if __name__ == "__main__":
    main()
