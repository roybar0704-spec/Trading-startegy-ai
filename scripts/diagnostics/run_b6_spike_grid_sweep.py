#!/usr/bin/env python3
"""B-6 Commit 1 -- Spike-threshold Grid-Sweep (Stage A, KI-022 controlled calibration).

Read-only diagnostic -- NOT part of the production pipeline or the pytest suite. Does not
modify src/data/validator.py or config/parameters.yaml. Runs the real, unmodified
``Validator`` (src/data/validator.py) once per ``spike_z_threshold`` value in a grid
centered on the current default (8.0), against the real November 2022 XAUUSD data already
present in data/ticks/ (verified in D-070/D-072).

Purpose (WORK_ORDER_B6.md Sec 6, Commit 1 -- Step A of the approved Option D methodology):
measure how flagged-spike count and move-size distribution change as spike_z_threshold
varies, to see whether 8.0 sits on a stable "plateau" (small, gradual change between
neighbouring values) or on a "cliff" (large, sharp change) -- the RA-08-style
level-vs-single-peak distinction. This step draws NO conclusion about a final value --
that is Commit 3 (Decision Proposal), not this script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.tick_store import TickParquetStore  # noqa: E402
from src.data.validator import Validator  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
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
        help="spike_z_threshold value to test (repeatable). Default: grid around 8.0.",
    )
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    thresholds = sorted(args.thresholds) if args.thresholds else DEFAULT_GRID

    store = TickParquetStore(Path(args.ticks_dir))
    month_label = f"{args.year:04d}-{args.month:02d}"
    print(f"Loading real data: {args.symbol} {month_label} from {args.ticks_dir}")
    ticks = store.read_month(args.symbol, args.year, args.month)
    total_ticks = ticks.height
    print(f"Loaded {total_ticks:,} real ticks.")
    print(f"Grid: {thresholds}\n")

    rows = []
    for threshold in thresholds:
        report = Validator(spike_z_threshold=threshold).validate(ticks, args.symbol)
        n = len(report.spikes)
        pct = (n / total_ticks * 100) if total_ticks else 0.0
        if n:
            moves = sorted(s.move for s in report.spikes)
            median = moves[len(moves) // 2]
            p95 = moves[int(len(moves) * 0.95)]
        else:
            median = p95 = 0.0
        rows.append(
            {
                "threshold": threshold,
                "flagged": n,
                "pct": pct,
                "median_move": median,
                "p95_move": p95,
            }
        )
        print(
            f"threshold={threshold:5.1f}  flagged={n:6,}  ({pct:6.4f}%)  "
            f"median_move={median:.4f}  p95_move={p95:.4f}"
        )

    print("\n=== Neighbour-to-neighbour stability (RA-08-style: plateau vs cliff) ===")
    print(f"{'from':>6} -> {'to':>6}   {'flagged_ratio':>14}   {'pct_change':>12}")
    for prev, cur in zip(rows, rows[1:], strict=False):
        ratio = (cur["flagged"] / prev["flagged"]) if prev["flagged"] else float("inf")
        pct_change = (
            (prev["flagged"] - cur["flagged"]) / prev["flagged"] * 100 if prev["flagged"] else 0.0
        )
        print(
            f"{prev['threshold']:6.1f} -> {cur['threshold']:6.1f}   "
            f"{ratio:14.4f}   {pct_change:11.2f}%"
        )

    at_8 = next((r for r in rows if r["threshold"] == 8.0), None)
    if at_8:
        print(f"\n=== 8.0 specifically ===\n{at_8}")

    print(
        "\n(No conclusion drawn here about a final threshold value -- see WORK_ORDER_B6.md "
        "Sec 6, Commit 3, for the Decision Proposal step.)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
