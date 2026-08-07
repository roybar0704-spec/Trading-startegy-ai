#!/usr/bin/env python3
"""B-6 Commit 2 -- Spike-vs-Spread cross-reference (Stage A, KI-022 controlled calibration).

Read-only diagnostic -- NOT part of the production pipeline or the pytest suite. Does not
modify src/data/validator.py, src/data/spread_report.py, or config/parameters.yaml. Runs the
real, unmodified ``Validator`` (per threshold, same grid as B-6 Commit 1) and the real,
unmodified ``build_spread_report()`` (src/data/spread_report.py, from B-4) against the same
real November 2022 XAUUSD data already used in Commit 1.

Purpose (WORK_ORDER_B6.md Sec 6, Commit 2 -- Step B of the approved Option D methodology):
generalize D-071's finding (flagged-spike median move at threshold=8.0 is smaller than
typical spread) across the full threshold grid, by comparing each flagged spike's move-size
to the real, measured per-ET-hour spread distribution of the hour it occurred in. A spike
whose move is smaller than (or comparable to) its own hour's normal spread is more likely
ordinary spread-noise than a genuine price jump. Draws no final-value conclusion -- that is
Commit 3 (Decision Proposal), not this script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.spread_report import build_spread_report  # noqa: E402
from src.data.tick_store import TickParquetStore  # noqa: E402
from src.data.validator import Validator  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ET = ZoneInfo("America/New_York")
DEFAULT_GRID = [4.0, 5.0, 6.0, 7.0, 7.5, 8.0, 8.5, 9.0, 10.0, 11.0, 12.0, 14.0, 16.0]


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--year", type=int, default=2022)
    p.add_argument("--month", type=int, default=11)
    p.add_argument("--ticks-dir", default=str(REPO_ROOT / "data" / "ticks"))
    p.add_argument(
        "--threshold",
        action="append",
        dest="thresholds",
        type=float,
        help="spike_z_threshold value to test (repeatable). Default: same grid as Commit 1.",
    )
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    thresholds = sorted(args.thresholds) if args.thresholds else DEFAULT_GRID

    store = TickParquetStore(Path(args.ticks_dir))
    month_label = f"{args.year:04d}-{args.month:02d}"
    print(f"Loading real data: {args.symbol} {month_label} from {args.ticks_dir}")
    ticks = store.read_month(args.symbol, args.year, args.month)
    print(f"Loaded {ticks.height:,} real ticks.\n")

    print("Building the real, unmodified per-ET-hour spread report (build_spread_report)...")
    spread = build_spread_report(ticks, args.symbol)
    print("\n=== Real per-ET-hour Spread Report (November 2022) ===")
    print(spread.to_markdown())

    overall_median_spread_list = sorted(s.median_spread for s in spread.by_hour.values())
    overall_median_spread = overall_median_spread_list[len(overall_median_spread_list) // 2]
    wide_hours = sorted(
        spread.by_hour.values(), key=lambda s: s.median_spread, reverse=True
    )[:3]
    wide_hour_set = {s.hour_et for s in wide_hours}
    print(
        f"\nOverall (across-hours) median of per-hour median_spread: {overall_median_spread:.4f}"
    )
    print(f"Top-3 widest-median-spread ET hours: {sorted(wide_hour_set)}")

    print("\n=== Cross-reference: flagged spikes vs. their own hour's real spread ===")
    header = (
        f"{'thr':>5}  {'flagged':>8}  {'median_move':>12}  {'move/hr_median':>15}  "
        f"{'%move<hr_p95':>13}  {'%in_wide_hrs':>13}"
    )
    print(header)
    rows = []
    for threshold in thresholds:
        report = Validator(spike_z_threshold=threshold).validate(ticks, args.symbol)
        spikes = report.spikes
        n = len(spikes)
        if n == 0:
            rows.append((threshold, 0, 0.0, 0.0, 0.0, 0.0))
            print(f"{threshold:5.1f}  {n:8,}  {'--':>12}  {'--':>15}  {'--':>13}  {'--':>13}")
            continue

        moves = sorted(s.move for s in spikes)
        median_move = moves[len(moves) // 2]

        ratios = []
        below_p95_count = 0
        wide_hour_count = 0
        for s in spikes:
            hour_et = s.ts.astimezone(ET).hour
            hour_stats = spread.by_hour.get(hour_et)
            if hour_stats is None:
                continue
            ratios.append(s.move / hour_stats.median_spread if hour_stats.median_spread else 0.0)
            if s.move < hour_stats.p95_spread:
                below_p95_count += 1
            if hour_et in wide_hour_set:
                wide_hour_count += 1

        ratios.sort()
        median_ratio = ratios[len(ratios) // 2] if ratios else 0.0
        pct_below_p95 = below_p95_count / n * 100
        pct_wide_hours = wide_hour_count / n * 100

        rows.append((threshold, n, median_move, median_ratio, pct_below_p95, pct_wide_hours))
        print(
            f"{threshold:5.1f}  {n:8,}  {median_move:12.4f}  {median_ratio:15.4f}  "
            f"{pct_below_p95:12.2f}%  {pct_wide_hours:12.2f}%"
        )

    print(
        "\nColumns: move/hr_median = spike's move-size divided by ITS OWN ET-hour's real "
        "median spread (< 1.0 means the 'spike' is smaller than typical spread-noise for "
        "that hour). %move<hr_p95 = fraction of spikes whose move is still smaller than "
        "their own hour's p95 spread (i.e., within the normal spread-widening range even "
        "at the tail). %in_wide_hrs = fraction of spikes falling in the 3 widest-spread "
        "ET hours (rollover/session-transition hours)."
    )
    print(
        "\n(No conclusion drawn here about a final threshold value -- see WORK_ORDER_B6.md "
        "Sec 6, Commit 3, for the Decision Proposal step.)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
