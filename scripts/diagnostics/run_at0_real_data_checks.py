#!/usr/bin/env python3
"""AT-0.1 / AT-0.4 / AT-0.6 real-data verification (Stage A, B-5, Commit 1).

Read-only diagnostic -- NOT part of the production pipeline or the pytest suite.
Runs the same pass criteria as tests/test_at0_1_download_integrity.py,
tests/test_at0_4_dst_build.py, and tests/test_at0_6_bar_tick_consistency.py, but
against real Dukascopy XAUUSD ticks (data/ticks/XAUUSD/2022/11.parquet, verified
in D-070/D-072) instead of synthetic fixtures/FakeTransport.

Does not modify TickParquetStore, BarBuilder, or any production code.
Scope: Sandbox execution only (WORK_ORDER_B5.md); does not touch data/holdout/
or any month outside the one requested via --year/--month.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.types import TF  # noqa: E402
from src.data.bar_builder import BarBuilder  # noqa: E402
from src.data.holdout import XAUUSD_HOLDOUT_RANGE  # noqa: E402
from src.data.tick_store import TickParquetStore  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
NY = ZoneInfo("America/New_York")


def check_at0_1(ticks: pl.DataFrame) -> bool:
    """Same pass criteria as test_at_0_1_download_integrity: ticks>0, bid<=ask, monotonic ts."""
    print("\n=== AT-0.1 Download integrity (real data) ===")
    height = ticks.height
    print(f"tick count: {height:,}")
    if height == 0:
        print("FAIL: zero ticks")
        return False
    bid_le_ask = bool((ticks["bid"] <= ticks["ask"]).all())
    print(f"bid <= ask (all rows): {bid_le_ask}")
    ts = ticks["ts"].to_list()
    is_sorted = ts == sorted(ts)
    is_unique = len(set(ts)) == len(ts)
    print(f"timestamps non-decreasing (sorted): {is_sorted}")
    print(f"timestamps strictly unique (no duplicate ts): {is_unique}")
    if not is_unique:
        print(
            "NOTE: duplicate timestamps are a known, expected property of real tick feeds "
            "(multiple quote updates can share the same millisecond). The original AT-0.1 "
            "fixture test asserts strict uniqueness because its synthetic ticks are spaced "
            "1s+ apart by construction -- this is a fixture artifact, not a real-data "
            "integrity requirement. Reported here explicitly, not silently passed or hidden."
        )
    return bool(bid_le_ask and is_sorted)


def check_at0_6(ticks: pl.DataFrame) -> bool:
    """Same pass criteria as test_at_0_6_bar_tick_consistency, vectorized for full-month scale.

    Ground truth is computed via an independent code path (manual epoch-floor bucketing +
    group_by) rather than BarBuilder's own group_by_dynamic, so this is a genuine
    cross-check of BarBuilder's output, not a self-comparison.
    """
    print("\n=== AT-0.6 Bar<->Tick consistency (real data, full month) ===")
    mid = ((pl.col("bid") + pl.col("ask")) / 2.0).alias("mid")
    df = ticks.sort("ts").with_columns(mid)
    truth = (
        df.with_columns((pl.col("ts").dt.epoch("us") // 60_000_000).alias("bucket"))
        .group_by("bucket", maintain_order=True)
        .agg(
            [
                pl.col("mid").first().alias("o"),
                pl.col("mid").max().alias("h"),
                pl.col("mid").min().alias("l"),
                pl.col("mid").last().alias("c"),
                pl.len().alias("tick_volume"),
            ]
        )
        .with_columns(
            pl.from_epoch(pl.col("bucket") * 60_000_000, time_unit="us")
            .dt.replace_time_zone("UTC")
            .alias("open_ts")
        )
        .sort("open_ts")
    )
    bars = BarBuilder().build(ticks, TF.M1)
    print(f"bars built: {len(bars):,}; independent ground-truth buckets: {truth.height:,}")
    if len(bars) != truth.height:
        print(f"FAIL: bar count mismatch ({len(bars)} vs {truth.height})")
        return False
    bars_df = pl.DataFrame(
        {
            "open_ts": [b.open_ts for b in bars],
            "o": [b.o for b in bars],
            "h": [b.h for b in bars],
            "l": [b.l for b in bars],
            "c": [b.c for b in bars],
            "tick_volume": [b.tick_volume for b in bars],
        }
    )
    joined = bars_df.join(truth, on="open_ts", suffix="_truth", how="left")
    unmatched = joined.filter(pl.col("o_truth").is_null())
    if unmatched.height > 0:
        print(f"FAIL: {unmatched.height} bar(s) had no matching ground-truth bucket")
        return False
    mismatches = joined.filter(
        (pl.col("o") != pl.col("o_truth"))
        | (pl.col("h") != pl.col("h_truth"))
        | (pl.col("l") != pl.col("l_truth"))
        | (pl.col("c") != pl.col("c_truth"))
        | (pl.col("tick_volume") != pl.col("tick_volume_truth"))
    )
    print(f"mismatched bars: {mismatches.height:,} / {bars_df.height:,}")
    if mismatches.height > 0:
        print(mismatches)
        return False
    return True


def check_at0_4(ticks: pl.DataFrame) -> bool:
    """Adapted from test_at_0_4_dst_build for real (non-continuous) market data.

    The original fixture asserts strict global 5-minute contiguity across a full week of
    *synthetic, continuous* ticks (no market closure modeled). Real XAUUSD data has genuine
    weekend/session closures, so contiguity is checked per single trading day instead of
    across the whole week -- the property under test is "no artificial dup/missing bars
    caused by the DST boundary computation itself", not "zero gaps anywhere in the data".
    """
    print("\n=== AT-0.4 DST build (real data, US Fall-Back 2022-11-06) ===")
    ok = True
    days = [
        ("2022-11-04 (last EDT trading day before fall-back)", datetime(2022, 11, 4, tzinfo=UTC)),
        ("2022-11-07 (first EST trading day after fall-back)", datetime(2022, 11, 7, tzinfo=UTC)),
    ]
    for label, day_start in days:
        day_end = day_start + timedelta(days=1)
        day_ticks = ticks.filter((pl.col("ts") >= day_start) & (pl.col("ts") < day_end))
        bars = BarBuilder().build(day_ticks, TF.M5)
        open_ts_list = [b.open_ts for b in bars]
        no_dup = len(open_ts_list) == len(set(open_ts_list))
        gaps = [
            (prev, nxt)
            for prev, nxt in zip(open_ts_list, open_ts_list[1:], strict=False)
            if nxt - prev != timedelta(minutes=5)
        ]
        expected_open = datetime(
            day_start.year, day_start.month, day_start.day, 8, 30, tzinfo=NY
        ).astimezone(UTC)
        matches = [b for b in bars if b.open_ts == expected_open]
        has_0830 = len(matches) == 1
        print(
            f"{label}: bars={len(bars)} no_duplicate_bars={no_dup} "
            f"non_5min_gaps={len(gaps)} 08:30_ET_bar_present={has_0830}"
        )
        day_ok = no_dup and has_0830
        if gaps:
            print(f"  gap details (informational): {gaps[:10]}")
            transition_related = [
                (p, n)
                for p, n in gaps
                if p.astimezone(NY).hour in (0, 1, 2) and label.startswith("2022-11-07")
            ]
            if transition_related:
                print(
                    f"  WARNING: {len(transition_related)} gap(s) near the 01:00-02:00 ET "
                    "transition window on the post-transition day -- flagged, not auto-passed."
                )
                day_ok = False
            else:
                print(
                    "  NOTE: gap(s) present but not near the DST transition hour -- consistent "
                    "with ordinary intraday liquidity gaps in real market data, not a DST defect."
                )
        ok = ok and day_ok
    return ok


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--ticks-dir", default=str(REPO_ROOT / "data" / "ticks"))
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--year", type=int, default=2022)
    p.add_argument("--month", type=int, default=11)
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    # D-085: AT-0 checks run against November 2022; no unlock flag.
    store = TickParquetStore(Path(args.ticks_dir), holdout_range=XAUUSD_HOLDOUT_RANGE)
    month_label = f"{args.year:04d}-{args.month:02d}"
    print(f"Loading real data: {args.symbol} {month_label} from {args.ticks_dir}")
    ticks = store.read_month(args.symbol, args.year, args.month)
    print(f"Loaded {ticks.height:,} real ticks.")

    results = {
        "AT-0.1": check_at0_1(ticks),
        "AT-0.4": check_at0_4(ticks),
        "AT-0.6": check_at0_6(ticks),
    }

    print("\n=== Summary ===")
    for name, passed in results.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
