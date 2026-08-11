#!/usr/bin/env python3
"""Post-backfill validation report (KI-001/KI-002 closure evidence).

Reads whatever ``scripts/backfill_full_range.py`` has already written to the
``TickParquetStore`` for the given range and runs the existing, already-
tested analysis components over it -- no new analysis logic is implemented
here, only assembly and reporting:

  * ``src.data.validator.Validator``       -- gap/spike detection (AT-0.3)
  * ``src.data.spread_report.build_spread_report`` -- hourly ET spread
    (PHASE0_KICKOFF item 4, RA-10/min_stop calibration input)
  * ``src.data.bar_builder.BarBuilder``    -- 1M/5M/4H bars, NY-Close anchor
    (AT-0.4/0.5/0.6 sanity spot-check)
  * ``src.data.tick_store.TickParquetStore.data_version`` -- content-hash
    identity for the exact range covered

Design note: all months in range are concatenated into a single sorted
DataFrame before calling ``Validator.validate()``. This is required for
correctness, not a style choice -- ``Validator`` detects gaps via a diff()
over consecutive timestamps, so validating one month at a time would flag a
false gap at every month boundary (last tick of month N vs first tick of
month N+1) that isn't a real discontinuity in the feed, only an artifact of
how the store happens to be partitioned on disk. The trade-off is memory:
the full 3-year tick set must fit in memory at once. If that ever becomes a
real constraint, a chunked pass with an overlap window would fix it -- not
needed at today's Phase 0 scale.

Usage:
    python scripts/validate_full_range.py --symbol XAUUSD \\
        --start 2022-10-03 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.types import TF  # noqa: E402
from src.data.bar_builder import BarBuilder  # noqa: E402
from src.data.holdout import XAUUSD_HOLDOUT_RANGE  # noqa: E402
from src.data.spread_report import build_spread_report  # noqa: E402
from src.data.tick_store import TickParquetStore, months_between  # noqa: E402
from src.data.validator import (  # noqa: E402
    DEFAULT_GAP_THRESHOLD,
    DEFAULT_SPIKE_Z_THRESHOLD,
    ValidationReport,
    Validator,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


def _contiguous_runs(months: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    """Split a sorted (year, month) list into maximal runs of consecutive months.

    Needed so gap-detection never sees a jump across a *missing* month as
    if it were a real feed discontinuity -- see the module docstring's
    "Design note". Without this, a single not-yet-backfilled month would
    make ``Validator`` flag a multi-week fake "gap" spanning the whole
    missing month, indistinguishable in the report from a genuine anomaly.
    """
    if not months:
        return []
    runs: list[list[tuple[int, int]]] = [[months[0]]]
    for year, month in months[1:]:
        prev_year, prev_month = runs[-1][-1]
        is_next = (prev_month == 12 and (year, month) == (prev_year + 1, 1)) or (
            year == prev_year and month == prev_month + 1
        )
        if is_next:
            runs[-1].append((year, month))
        else:
            runs.append([(year, month)])
    return runs


def _run_bounds(
    run: list[tuple[int, int]], overall_start: datetime, overall_end: datetime
) -> tuple[datetime, datetime]:
    """[start, end) covered by one contiguous run of months, clipped to the overall range."""
    first_year, first_month = run[0]
    last_year, last_month = run[-1]
    run_start = datetime(first_year, first_month, 1, tzinfo=UTC)
    run_end = (datetime(last_year, last_month, 1, tzinfo=UTC) + timedelta(days=32)).replace(day=1)
    return max(run_start, overall_start), min(run_end, overall_end)


def _per_month_price_bounds(ticks: pl.DataFrame) -> pl.DataFrame:
    """KI-002 sanity: min/max bid/ask per calendar month, for a quick eyeball
    check that no month's decoded prices fall outside a plausible historical
    XAUUSD band (would indicate a point_value/scale error, not a market move)."""
    return (
        ticks.with_columns(
            [pl.col("ts").dt.year().alias("year"), pl.col("ts").dt.month().alias("month")]
        )
        .group_by(["year", "month"])
        .agg(
            [
                pl.len().alias("tick_count"),
                pl.col("bid").min().alias("bid_min"),
                pl.col("bid").max().alias("bid_max"),
                pl.col("ask").min().alias("ask_min"),
                pl.col("ask").max().alias("ask_max"),
            ]
        )
        .sort(["year", "month"])
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--start", required=True, help="YYYY-MM-DD (UTC, inclusive)")
    p.add_argument("--end", required=True, help="YYYY-MM-DD (UTC, inclusive)")
    p.add_argument("--ticks-dir", default=str(REPO_ROOT / "data" / "ticks"))
    p.add_argument(
        "--report-out",
        default=None,
        help="defaults to data/reports/validation_<symbol>_<start>_<end>.md",
    )
    p.add_argument(
        "--gap-threshold-minutes",
        type=float,
        default=DEFAULT_GAP_THRESHOLD.total_seconds() / 60,
    )
    p.add_argument("--spike-z-threshold", type=float, default=DEFAULT_SPIKE_Z_THRESHOLD)
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    start = _parse_date(args.start)
    end = _parse_date(args.end) + timedelta(days=1)

    store = TickParquetStore(
        Path(args.ticks_dir),
        holdout_range=XAUUSD_HOLDOUT_RANGE,
        holdout_unlock=True,
        unlock_reason="data integrity validation, not research (D-085 Category A)",
        usage_log_path=Path(args.ticks_dir).parent / "holdout_access_log.jsonl",
    )
    months = months_between(start, end - timedelta(seconds=1))

    available, missing = [], []
    for y, m in months:
        (available if store.month_path(args.symbol, y, m).exists() else missing).append((y, m))

    if missing:
        print(f"WARNING: {len(missing)} of {len(months)} months are not yet in the store "
              f"(backfill incomplete or not yet run): {missing}")
    if not available:
        print("No data available in this range -- nothing to validate.")
        return 1

    print(f"Loading {len(available)} available month(s) from {args.ticks_dir} ...")
    frames = [store.read_month(args.symbol, y, m) for y, m in available]
    ticks = (
        pl.concat(frames)
        .sort("ts")
        .filter((pl.col("ts") >= start) & (pl.col("ts") < end))
    )
    print(f"Total ticks loaded: {ticks.height:,}")

    print("Running Validator (gap/spike detection, per contiguous coverage run)...")
    validator = Validator(
        gap_threshold=timedelta(minutes=args.gap_threshold_minutes),
        spike_z_threshold=args.spike_z_threshold,
    )
    runs = _contiguous_runs(available)
    if len(runs) > 1:
        print(
            f"  NOTE: {len(available)} available months split into {len(runs)} "
            "non-contiguous coverage run(s) (missing months in between) -- "
            "validating each run separately so a missing month is never "
            "mistaken for a real feed gap."
        )
    flagged_gaps, weekend_gaps, spikes = [], [], []
    for run in runs:
        run_start, run_end = _run_bounds(run, start, end)
        run_ticks = ticks.filter((pl.col("ts") >= run_start) & (pl.col("ts") < run_end))
        run_validation = validator.validate(run_ticks, args.symbol)
        flagged_gaps += run_validation.flagged_gaps
        weekend_gaps += run_validation.weekend_gaps
        spikes += run_validation.spikes
    validation = ValidationReport(
        symbol=args.symbol,
        tick_count=ticks.height,
        flagged_gaps=flagged_gaps,
        weekend_gaps=weekend_gaps,
        spikes=spikes,
    )

    print("Building hourly (ET) spread report...")
    spread = build_spread_report(ticks, args.symbol)

    print("Building 1M/5M/4H bars (sanity spot-check)...")
    builder = BarBuilder()
    bars_1m = builder.build(ticks, TF.M1)
    bars_5m = builder.build(ticks, TF.M5)
    bars_4h = builder.build(ticks, TF.H4)

    price_bounds = _per_month_price_bounds(ticks) if ticks.height else None
    data_version = store.data_version(args.symbol, available) if available else None

    report_out = Path(args.report_out) if args.report_out else (
        REPO_ROOT / "data" / "reports" / f"validation_{args.symbol}_{args.start}_{args.end}.md"
    )
    report_out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Validation report: {args.symbol} {args.start} .. {args.end}",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"data_version (available months only): `{data_version}`",
        "",
        "## Coverage",
        f"- Calendar months in range: {len(months)}",
        f"- Available in TickParquetStore: {len(available)}",
        f"- Missing (backfill incomplete): {len(missing)} {missing if missing else ''}",
        f"- Total ticks loaded: {ticks.height:,}",
        "",
        "## Integrity summary (Validator)",
        f"- Flagged (non-weekend) gaps: {len(validation.flagged_gaps)}",
        f"- Weekend gaps (expected, excluded): {len(validation.weekend_gaps)}",
        f"- Spikes flagged (z > {args.spike_z_threshold}): {len(validation.spikes)}",
        f"- is_clean (no flagged gaps or spikes): {validation.is_clean}",
        "",
    ]

    if validation.flagged_gaps:
        lines.append("### Flagged (non-weekend) gaps -- require interpretation, not classified")
        for gap in validation.flagged_gaps[:50]:
            lines.append(
                f"- {gap.start.isoformat()} -> {gap.end.isoformat()} (duration {gap.duration})"
            )
        if len(validation.flagged_gaps) > 50:
            remaining = len(validation.flagged_gaps) - 50
            lines.append(f"- ... and {remaining} more (see raw ValidationReport)")
        lines.append("")

    if validation.spikes:
        lines.append("### Flagged spikes")
        for spike in validation.spikes[:50]:
            lines.append(f"- {spike.ts.isoformat()} mid={spike.mid:.3f} move={spike.move:.3f}")
        if len(validation.spikes) > 50:
            lines.append(f"- ... and {len(validation.spikes) - 50} more (see raw ValidationReport)")
        lines.append("")

    lines += [
        "## Spread report by ET hour (RA-10 / min_stop calibration input -- never auto-applied)",
        "",
        spread.to_markdown(),
        "",
        "## Bar counts (sanity spot-check, AT-0.4/0.5/0.6)",
        f"- 1M bars: {len(bars_1m):,}",
        f"- 5M bars: {len(bars_5m):,}",
        f"- 4H bars (NY-Close anchored): {len(bars_4h):,}",
        "",
    ]

    if price_bounds is not None:
        lines.append("## KI-002 sanity: price bounds per month")
        lines.append("| year-month | ticks | bid_min | bid_max | ask_min | ask_max |")
        lines.append("|---|---|---|---|---|---|")
        for row in price_bounds.iter_rows(named=True):
            lines.append(
                f"| {row['year']:04d}-{row['month']:02d} | {row['tick_count']:,} | "
                f"{row['bid_min']:.3f} | {row['bid_max']:.3f} | "
                f"{row['ask_min']:.3f} | {row['ask_max']:.3f} |"
            )
        lines.append("")

    report_out.write_text("\n".join(lines))
    print(f"\nReport written to {report_out}")
    print(f"\nSummary: is_clean={validation.is_clean}  "
          f"flagged_gaps={len(validation.flagged_gaps)}  spikes={len(validation.spikes)}  "
          f"ticks={ticks.height:,}  months_available={len(available)}/{len(months)}")

    # Distinct exit codes so a caller (human or script) can tell "backfill just
    # isn't finished yet" apart from "a real integrity problem was found" --
    # collapsing both into one code would hide which situation you're in.
    if missing:
        return 2  # incomplete coverage; not a verdict on the data that IS present
    return 0 if validation.is_clean else 1


if __name__ == "__main__":
    sys.exit(main())
