#!/usr/bin/env python3
"""Read-only spike-detection diagnostic (KI-001 follow-up) -- NOT part of the
production pipeline. Does not modify validator.py or validate_full_range.py.

Reads whatever scripts/backfill_full_range.py already wrote to the
TickParquetStore for a date range, re-runs the existing, unmodified
``Validator`` to get the authoritative flagged-spike list (the real source
of truth), and separately recomputes the same rolling-std enrichment
Validator uses internally (dmid, baseline_std, z = dmid/baseline_std)
purely for descriptive statistics -- ``Validator`` itself only exposes the
final filtered ``Spike`` list (``move``, not the z-score/baseline that
produced it), so this is the one deliberate, minimal, diagnostic-only
duplication of a single ``rolling_std()`` expression, needed to answer
"what z-score actually triggered each flag" without touching validator.py.

A sanity check asserts the locally-recomputed flagged count matches
Validator's own real output exactly, so any divergence is caught
immediately rather than silently producing a misleading breakdown.

Usage:
    uv run python scripts/diagnostics/analyze_spikes.py --start 2022-11-01 --end 2022-11-30
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.tick_store import TickParquetStore, months_between  # noqa: E402
from src.data.validator import DEFAULT_SPIKE_Z_THRESHOLD, Validator  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# Standard, widely-used FX session-hour convention (fixed UTC bounds, not
# DST-adjusted per region). Not defined anywhere else in this codebase --
# src/session/session_engine.py is the strategy's own single configured
# entry window (a different concept entirely) -- this is a diagnostic-only
# grouping, introduced here because the project has no general-purpose
# Asia/London/NY session labels to reuse.
_SESSION_BOUNDS_UTC = [
    ("Sydney/Wellington", 21, 24),
    ("Tokyo/Asia", 0, 7),
    ("London", 7, 12),
    ("London-NY overlap", 12, 16),
    ("New York", 16, 21),
]


def _session_for_hour(hour_utc: int) -> str:
    for name, start, end in _SESSION_BOUNDS_UTC:
        if start <= hour_utc < end:
            return name
    return "unknown"


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
    p.add_argument("--spike-z-threshold", type=float, default=DEFAULT_SPIKE_Z_THRESHOLD)
    p.add_argument("--spike-baseline-window", type=int, default=500)
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    start = _parse_date(args.start)
    end = _parse_date(args.end) + timedelta(days=1)

    store = TickParquetStore(Path(args.ticks_dir))
    months = months_between(start, end - timedelta(seconds=1))
    frames = [store.read_month(args.symbol, y, m) for y, m in months]
    ticks = pl.concat(frames).sort("ts").filter((pl.col("ts") >= start) & (pl.col("ts") < end))
    total_ticks = ticks.height
    print(f"Loaded {total_ticks:,} ticks for {args.symbol} {args.start}..{args.end}")

    print("\nRunning the real, unmodified Validator (authoritative spike list)...")
    validation = Validator(spike_z_threshold=args.spike_z_threshold).validate(ticks, args.symbol)
    real_spike_count = len(validation.spikes)
    pct = (real_spike_count / total_ticks * 100) if total_ticks else 0.0
    print(f"Validator flagged spikes: {real_spike_count:,} ({pct:.4f}% of ticks)")

    print(
        "\nRecomputing the same rolling-std enrichment locally (diagnostic-only, "
        "for z-score/session detail Validator itself doesn't expose)..."
    )
    enriched = (
        ticks.with_columns([((pl.col("bid") + pl.col("ask")) / 2.0).alias("mid")])
        .with_columns([(pl.col("mid") - pl.col("mid").shift(1)).abs().alias("dmid")])
        .with_columns(
            [
                pl.col("dmid")
                .rolling_std(window_size=args.spike_baseline_window, min_samples=30)
                .alias("baseline_std")
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("baseline_std") > 0)
                .then(pl.col("dmid") / pl.col("baseline_std"))
                .otherwise(None)
                .alias("z_score")
            ]
        )
    )
    flagged = enriched.filter(
        pl.col("baseline_std").is_not_null()
        & (pl.col("baseline_std") > 0)
        & (pl.col("dmid") > args.spike_z_threshold * pl.col("baseline_std"))
    )
    local_spike_count = flagged.height
    print(f"Locally recomputed flagged count: {local_spike_count:,}")
    if local_spike_count != real_spike_count:
        print(
            f"WARNING: mismatch vs Validator's real count ({real_spike_count:,}) -- "
            "treat session/percentile breakdown below with caution, investigate before trusting it."
        )
    else:
        print("MATCH: local recomputation agrees exactly with the real Validator output.")

    print("\n=== 1. Spike statistics ===")
    print(f"Total ticks: {total_ticks:,}")
    print(f"Total flagged spikes (z > {args.spike_z_threshold}): {real_spike_count:,}")
    print(f"Percent of total ticks: {pct:.4f}%")

    print("\n=== 2. Move-size distribution (flagged spikes only) ===")
    if local_spike_count:
        moves = flagged["dmid"]
        print(f"min:    {moves.min():.4f}")
        print(f"median: {moves.median():.4f}")
        print(f"p75:    {moves.quantile(0.75):.4f}")
        print(f"p95:    {moves.quantile(0.95):.4f}")
        print(f"p99:    {moves.quantile(0.99):.4f}")
        print(f"max:    {moves.max():.4f}")
    else:
        print("No flagged spikes -- nothing to summarize.")

    print("\n=== 3. Time breakdown ===")
    if local_spike_count:
        flagged_tz = flagged.with_columns(
            [
                pl.col("ts").dt.hour().alias("hour_utc"),
                pl.col("ts").dt.convert_time_zone("America/New_York").dt.hour().alias("hour_et"),
            ]
        )
        print("\nBy UTC hour:")
        by_utc = flagged_tz.group_by("hour_utc").agg(pl.len().alias("count")).sort("hour_utc")
        for row in by_utc.iter_rows(named=True):
            print(f"  {row['hour_utc']:02d}:00 UTC -> {row['count']:,}")

        print("\nBy ET hour:")
        by_et = flagged_tz.group_by("hour_et").agg(pl.len().alias("count")).sort("hour_et")
        for row in by_et.iter_rows(named=True):
            print(f"  {row['hour_et']:02d}:00 ET -> {row['count']:,}")

        print("\nBy session (diagnostic-only UTC convention, see script header):")
        sessions = [_session_for_hour(h) for h in flagged_tz["hour_utc"].to_list()]
        session_counts: dict[str, int] = {}
        for s in sessions:
            session_counts[s] = session_counts.get(s, 0) + 1
        for name, count in sorted(session_counts.items(), key=lambda kv: -kv[1]):
            print(f"  {name}: {count:,} ({count / local_spike_count * 100:.1f}%)")

        print("\n=== 4. Concentration checks ===")
        rollover_band = flagged_tz.filter((pl.col("hour_utc") >= 21) | (pl.col("hour_utc") < 1))
        print(
            f"Spikes in 21:00-01:00 UTC band (rollover + immediate aftermath): "
            f"{rollover_band.height:,} ({rollover_band.height / local_spike_count * 100:.1f}%)"
        )

        transition_hours = {6, 7, 11, 12, 20, 21, 22}
        transitions = flagged_tz.filter(pl.col("hour_utc").is_in(transition_hours))
        print(
            f"Spikes within +/-1h of a session transition (06-07, 11-12, 20-22 UTC): "
            f"{transitions.height:,} ({transitions.height / local_spike_count * 100:.1f}%)"
        )

        print("\nSpikes per calendar day (top 10):")
        by_day = (
            flagged_tz.with_columns(pl.col("ts").dt.date().alias("date"))
            .group_by("date")
            .agg(pl.len().alias("count"))
            .sort("count", descending=True)
        )
        for row in by_day.head(10).iter_rows(named=True):
            print(f"  {row['date']}: {row['count']:,}")

        print("\n=== 5. Move size vs. z-score (sample of first 20 by time) ===")
        sample = flagged.sort("ts").head(20)
        for row in sample.iter_rows(named=True):
            print(
                f"  {row['ts']}  move={row['dmid']:.4f}  "
                f"baseline_std={row['baseline_std']:.4f}  z={row['z_score']:.2f}"
            )
        corr = flagged.select(pl.corr("dmid", "z_score")).item()
        print(
            f"\nCorrelation (move vs z-score) across all {local_spike_count:,} "
            f"flagged spikes: {corr:.4f}"
        )
    else:
        print("No flagged spikes -- sections 3-5 skipped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
