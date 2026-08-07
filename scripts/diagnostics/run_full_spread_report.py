#!/usr/bin/env python3
"""Read-only RA-10 calibration diagnostic (Stage A, B-4) -- NOT part of the
production pipeline. Does not modify spread_report.py, tick_store.py, or any
production code.

Loads real Ticks already written by scripts/backfill_full_range.py for a
date range, and runs the existing, unmodified ``build_spread_report()`` to
produce the per-ET-hour spread measurement that ``costs.slippage_stop_usd``
(RA-10) is meant to be calibrated against.

This script only *measures* -- it never proposes or applies a new RA-10
value. That comparison/decision step happens separately (WORK_ORDER_B4.md
Commit 2), with an explicit Decision Proposal to Roy before anything in
config/parameters.yaml changes.

Hard range guard (D-073): B-4 is scoped to 2022-10-01..2025-06-30 only.
2025-07 onward is the configured Hold-Out window (config/run_default.yaml
`holdout: {last_months: 6}` over the 2023-01-01..2025-12-31 period) and must
never be read for this calibration, by design of this project's
anti-data-snooping rules -- not just by convention of the caller passing the
"right" --end. Both a CLI-level check and a post-load check (on the actual
months resolved by ``months_between``) enforce this independently, so a
mistake in one does not silently bypass the other.

Usage:
    uv run python scripts/diagnostics/run_full_spread_report.py \\
        --symbol XAUUSD --start 2022-10-01 --end 2025-06-30
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.spread_report import build_spread_report  # noqa: E402
from src.data.tick_store import TickParquetStore, months_between  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# D-073: last calendar month this script is ever allowed to load. Not a
# config value -- deliberately hardcoded here so this guard cannot be
# silently loosened by editing config/run_default.yaml for an unrelated
# reason. Any change to this constant is itself a Scope change requiring
# the same Decision-Proposal process as everything else in B-4.
_LAST_ALLOWED_MONTH = (2025, 6)


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--start", required=True, help="YYYY-MM-DD (UTC, inclusive)")
    p.add_argument("--end", required=True, help="YYYY-MM-DD (UTC, inclusive)")
    p.add_argument("--ticks-dir", default=str(REPO_ROOT / "data" / "ticks"))
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    start = _parse_date(args.start)
    end = _parse_date(args.end) + timedelta(days=1)

    # Guard 1 (CLI-level): reject before touching the filesystem at all.
    end_date = date.fromisoformat(args.end)
    last_allowed_date = date(_LAST_ALLOWED_MONTH[0], _LAST_ALLOWED_MONTH[1], 30)
    if end_date > last_allowed_date:
        print(
            f"REFUSING TO RUN: --end {args.end} is after the B-4 Hold-Out boundary "
            f"({last_allowed_date.isoformat()}, D-073). This script must never load "
            "2025-07 onward. No data was read.",
            file=sys.stderr,
        )
        return 1

    if start >= end:
        print(f"ERROR: --start ({args.start}) must be before --end ({args.end}).", file=sys.stderr)
        return 1

    store = TickParquetStore(Path(args.ticks_dir))
    months = months_between(start, end - timedelta(seconds=1))

    # Guard 2 (post-resolution): re-check the actual (year, month) tuples
    # months_between() resolved, independent of Guard 1 -- catches any future
    # bug in date parsing/arithmetic that Guard 1 alone wouldn't.
    if any((y, m) > _LAST_ALLOWED_MONTH for y, m in months):
        offending = [f"{y:04d}-{m:02d}" for y, m in months if (y, m) > _LAST_ALLOWED_MONTH]
        print(
            f"REFUSING TO RUN: resolved month list includes Hold-Out months {offending} "
            f"(boundary: {_LAST_ALLOWED_MONTH[0]:04d}-{_LAST_ALLOWED_MONTH[1]:02d}, D-073). "
            "No data was read.",
            file=sys.stderr,
        )
        return 1

    print(f"Range: {args.start}..{args.end} ({len(months)} calendar months)")
    print(f"Months to load: {', '.join(f'{y:04d}-{m:02d}' for y, m in months)}")

    frames = [
        store.read_month(args.symbol, y, m).select(["ts", "bid", "ask"]) for y, m in months
    ]
    ticks = pl.concat(frames).sort("ts").filter((pl.col("ts") >= start) & (pl.col("ts") < end))
    total_ticks = ticks.height
    print(f"\nLoaded {total_ticks:,} ticks for {args.symbol} {args.start}..{args.end}")

    print("\nRunning the real, unmodified build_spread_report()...")
    report = build_spread_report(ticks, args.symbol)

    print("\n=== Per-ET-hour Spread Report ===")
    print(report.to_markdown())

    spread = ticks.select((pl.col("ask") - pl.col("bid")).alias("spread"))["spread"]
    print("\n=== Overall summary (all hours combined) ===")
    print(f"Total ticks: {total_ticks:,}")
    print(f"Overall mean spread:   {spread.mean():.4f}")
    print(f"Overall median spread: {spread.median():.4f}")
    print(f"Overall p95 spread:    {spread.quantile(0.95):.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
