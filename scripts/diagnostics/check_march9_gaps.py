"""Diagnostic-only export: ticks surrounding two specific gap boundaries
(2023-03-09, both flagged non-daily-rollover gaps).

NOT part of production code. Read-only. Does not modify validator.py,
validate_full_range.py, or any module under src/.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.tick_store import TickParquetStore, months_between  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# The two flagged gaps under review (2023-03-09).
GAPS = [
    (
        datetime(2023, 3, 9, 13, 51, 56, 896000, tzinfo=UTC),
        datetime(2023, 3, 9, 14, 0, 0, 85000, tzinfo=UTC),
    ),
    (
        datetime(2023, 3, 9, 14, 54, 36, 359000, tzinfo=UTC),
        datetime(2023, 3, 9, 15, 0, 0, 27000, tzinfo=UTC),
    ),
]

N_AROUND = 4  # ticks shown before gap-start and after gap-end


def main() -> int:
    symbol = "XAUUSD"
    store = TickParquetStore(REPO_ROOT / "data" / "ticks")

    day_start = datetime(2023, 3, 9, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    months = months_between(day_start, day_end - timedelta(seconds=1))
    frames = [store.read_month(symbol, y, m) for y, m in months]
    ticks = (
        pl.concat(frames)
        .sort("ts")
        .filter((pl.col("ts") >= day_start) & (pl.col("ts") < day_end))
    )
    print(f"Loaded {ticks.height:,} ticks for {symbol} on {day_start.date()}\n")

    for i, (gap_start, gap_end) in enumerate(GAPS, start=1):
        print(f"=== Gap {i}: {gap_start} -> {gap_end} ===")

        before = ticks.filter(pl.col("ts") < gap_start).tail(N_AROUND)
        after = ticks.filter(pl.col("ts") >= gap_end).head(N_AROUND)

        print(f"\n-- {N_AROUND} ticks BEFORE gap start --")
        print(before.select(["ts", "bid", "ask"]))

        print(f"\n-- {N_AROUND} ticks AFTER gap end --")
        print(after.select(["ts", "bid", "ask"]))

        if before.height and after.height:
            bid_before = before["bid"][-1]
            bid_after = after["bid"][0]
            print(
                f"\nbid jump across gap: {bid_before} -> {bid_after} "
                f"(delta={bid_after - bid_before:+.3f})"
            )
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())