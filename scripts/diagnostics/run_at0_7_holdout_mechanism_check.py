#!/usr/bin/env python3
"""AT-0.7 Holdout-isolation mechanism check (Stage A, B-5, Commit 1).

Read-only diagnostic -- NOT part of the production pipeline or the pytest suite. Runs
separate_holdout()/HoldoutGuard/compute_holdout_range (src/data/holdout.py, unmodified)
against a COPY of real Dukascopy XAUUSD data (data/ticks/XAUUSD/2022/11.parquet, verified
in D-070/D-072), written into a throwaway temp directory outside the repo.

Scope (WORK_ORDER_B5.md Sec 1.2 / 2.5 / 6.3): this is a MECHANISM check only -- it proves
the holdout-isolation code moves/guards real tick data correctly. It does **not** touch
data/ticks/ or data/holdout/, and does **not** perform any physical separation of the real
Jul-Dec 2025 holdout window -- that remains explicitly out of scope for B-5, deferred to a
future Hardening Work Order tied to KI-023.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.holdout import (  # noqa: E402
    HoldoutAccessDenied,
    HoldoutGuard,
    compute_holdout_range,
    separate_holdout,
)
from src.data.tick_store import TickParquetStore  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--source-month",
        default=str(REPO_ROOT / "data" / "ticks" / "XAUUSD" / "2022" / "11.parquet"),
        help="Real monthly Parquet file to copy into the temp test store (default: 2022-11).",
    )
    p.add_argument("--symbol", default="XAUUSD")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    source = Path(args.source_month)
    if not source.exists():
        print(f"ERROR: source month file not found: {source}", file=sys.stderr)
        return 1

    tmp_root = Path(tempfile.mkdtemp(prefix="at0_7_holdout_check_"))
    ok = True
    try:
        print(f"Working directory (temp, outside repo/data/ticks and data/holdout): {tmp_root}")
        real_ticks = pl.read_parquet(source)
        print(f"Loaded {real_ticks.height:,} real ticks from {source} (unmodified).")

        ticks_root = tmp_root / "ticks"
        holdout_root = tmp_root / "holdout"
        usage_log = tmp_root / "holdout_usage.jsonl"

        holdout_range = compute_holdout_range(
            datetime(2022, 11, 1, tzinfo=UTC), datetime(2022, 11, 30, tzinfo=UTC), last_months=1
        )
        print(f"compute_holdout_range() -> {holdout_range.start} .. {holdout_range.end}")
        assert holdout_range.start == datetime(2022, 11, 1, tzinfo=UTC)

        # D-085: this store now carries the SAME holdout_range that separate_holdout()
        # below will physically move -- Track A (the store's own read_month() check)
        # therefore blocks access structurally, before physical absence even matters.
        # This proves defense-in-depth: Track A alone would already refuse this read,
        # independent of whether separate_holdout() (Track B) has run.
        store = TickParquetStore(ticks_root, holdout_range=holdout_range)
        store.write_month(args.symbol, 2022, 11, real_ticks)
        print("Wrote the real November-2022 ticks into the temp store as the only month present.")

        moved = separate_holdout(store, holdout_root, args.symbol, holdout_range)
        print(f"separate_holdout() moved {len(moved)} month(s): {[str(p) for p in moved]}")
        if len(moved) != 1:
            print(f"FAIL: expected exactly 1 moved month, got {len(moved)}")
            ok = False

        try:
            store.read_month(args.symbol, 2022, 11)
            print("FAIL: main store still able to read the moved (holdout) month")
            ok = False
        except HoldoutAccessDenied:
            print(
                "PASS: main store cannot read the moved (holdout) month "
                "(HoldoutAccessDenied, Track A -- D-085)"
            )

        guard = HoldoutGuard(holdout_root, usage_log)
        window_start = datetime(2022, 11, 15, tzinfo=UTC)
        window_end = datetime(2022, 11, 16, tzinfo=UTC)

        try:
            guard.load(args.symbol, window_start, window_end, holdout_range)
            print("FAIL: HoldoutGuard allowed access without holdout_unlock=True")
            ok = False
        except HoldoutAccessDenied:
            print("PASS: HoldoutGuard raised HoldoutAccessDenied without holdout_unlock=True")

        unlocked = guard.load(
            args.symbol,
            window_start,
            window_end,
            holdout_range,
            holdout_unlock=True,
            reason="AT-0.7 real-data mechanism check (Stage A, B-5, Commit 1)",
        )
        print(f"Loaded {unlocked.height:,} real ticks via HoldoutGuard.load(holdout_unlock=True).")
        if unlocked.height == 0:
            print("FAIL: unlocked load returned zero rows -- expected real Nov-15 ticks")
            ok = False
        else:
            in_window = bool(
                ((unlocked["ts"] >= window_start) & (unlocked["ts"] < window_end)).all()
            )
            print(f"All returned rows fall within the requested window: {in_window}")
            ok = ok and in_window

        print(f"Usage log written: {usage_log.exists()}")
        if usage_log.exists():
            print(usage_log.read_text())

        verdict = "PASS" if ok else "FAIL"
        print(f"\n=== Summary ===\nAT-0.7 (mechanism check on real-data copy): {verdict}")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        print(f"Cleaned up temp directory: {tmp_root}")


if __name__ == "__main__":
    sys.exit(main())
