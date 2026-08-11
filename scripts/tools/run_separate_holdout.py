#!/usr/bin/env python3
"""Track B (B-9, D-086): physically separate the real hold-out months.

Moves the 6 real hold-out months (2025-07..2025-12, computed from
``src.data.holdout.XAUUSD_HOLDOUT_RANGE`` -- never hardcoded here) out of
``data/ticks/`` into ``data/holdout/``, via the existing, unmodified
``src.data.holdout.separate_holdout()``.

Default is ``--dry-run``: prints exactly which 12 files (6 months x
.parquet + .sha256) would move, touches nothing. Mutation only happens with
an explicit ``--confirm``, and only after every Pre-Flight check below
passes -- this script never relies on ``separate_holdout()``'s own silent
idempotency (source-missing => skip) to reason about partial state; it
detects and refuses partial state itself, before touching anything.

On ANY Pre-Flight failure (hash mismatch, missing source file, an already-
existing destination, wrong total month count) this script stops
immediately and reports -- no auto-repair, no new hash written, no partial
completion, no continuation.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.holdout import XAUUSD_HOLDOUT_RANGE, separate_holdout  # noqa: E402
from src.data.tick_store import TickParquetStore, months_between  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "XAUUSD"
EXPECTED_TOTAL_MONTHS = 39


class PreFlightFailure(RuntimeError):
    """Raised on any Pre-Flight violation. Stop, report, never auto-repair."""


def _sha256_of(path: Path) -> str:
    """SHA256 hex digest of a file's current on-disk content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _holdout_months() -> list[tuple[int, int]]:
    """The hold-out (year, month) list, derived from code -- never hardcoded."""
    return months_between(XAUUSD_HOLDOUT_RANGE.start, XAUUSD_HOLDOUT_RANGE.end)


def run_preflight(ticks_dir: Path, holdout_dir: Path) -> list[tuple[int, int, str]]:
    """Run every Pre-Flight check; raise PreFlightFailure on the first violation.

    Returns a list of (year, month, verified_sha256) for the 6 hold-out
    months if -- and only if -- every check passed.
    """
    print("=== Pre-Flight ===")
    print(f"XAUUSD_HOLDOUT_RANGE: {XAUUSD_HOLDOUT_RANGE.start} .. {XAUUSD_HOLDOUT_RANGE.end}")
    holdout_months = _holdout_months()
    print(f"Hold-out months (computed from code): {holdout_months}")
    if len(holdout_months) != 6:
        raise PreFlightFailure(f"expected 6 hold-out months, computed {len(holdout_months)}")

    if holdout_dir.exists():
        existing = list(holdout_dir.rglob("*"))
        if existing:
            raise PreFlightFailure(
                f"{holdout_dir} already exists and is not empty ({len(existing)} entries) "
                "-- refusing to risk collision with a prior/partial run"
            )
        print(f"OK: {holdout_dir} exists but is empty")
    else:
        print(f"OK: {holdout_dir} does not exist")

    all_parquets = sorted((ticks_dir / SYMBOL).rglob("*.parquet"))
    print(f"Total .parquet files under {ticks_dir / SYMBOL}: {len(all_parquets)}")
    if len(all_parquets) != EXPECTED_TOTAL_MONTHS:
        raise PreFlightFailure(
            f"expected exactly {EXPECTED_TOTAL_MONTHS} months under {ticks_dir / SYMBOL}, "
            f"found {len(all_parquets)} -- refusing to run against an unexpected data range"
        )

    verified: list[tuple[int, int, str]] = []
    for year, month in holdout_months:
        src = ticks_dir / SYMBOL / f"{year:04d}" / f"{month:02d}.parquet"
        src_hash_path = src.with_suffix(".parquet.sha256")
        dst = holdout_dir / SYMBOL / f"{year:04d}" / f"{month:02d}.parquet"
        dst_hash_path = dst.with_suffix(".parquet.sha256")

        print(f"--- {year:04d}-{month:02d} ---")
        if not src.exists():
            raise PreFlightFailure(f"missing source file: {src}")
        if not src_hash_path.exists():
            raise PreFlightFailure(f"missing source sidecar: {src_hash_path}")

        recorded = src_hash_path.read_text().strip()
        computed = _sha256_of(src)
        print(f"  recorded hash: {recorded}")
        print(f"  computed hash: {computed}")
        if recorded != computed:
            raise PreFlightFailure(
                f"HASH MISMATCH for {src}: recorded={recorded} computed={computed} "
                "-- stopping, no auto-repair, do not proceed"
            )
        print("  OK: recorded hash matches recomputed hash")

        if dst.exists() or dst_hash_path.exists():
            raise PreFlightFailure(
                f"destination already exists (partial-state?): {dst} or {dst_hash_path} "
                "-- stopping, refusing to overwrite or continue a prior partial run"
            )
        print(f"  OK: destination does not yet exist ({dst})")

        verified.append((year, month, computed))

    print("=== Pre-Flight: ALL CHECKS PASSED ===")
    return verified


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI: --confirm is required to mutate; everything else is dry-run."""
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--ticks-dir", default=str(REPO_ROOT / "data" / "ticks"))
    p.add_argument("--holdout-dir", default=str(REPO_ROOT / "data" / "holdout"))
    p.add_argument(
        "--confirm", action="store_true",
        help="Actually perform the move. Without this flag the script only dry-runs "
        "and never touches a file.",
    )
    return p


def main() -> int:
    """Pre-Flight -> print planned moves -> dry-run stop, or --confirm -> move + verify."""
    args = build_arg_parser().parse_args()
    ticks_dir = Path(args.ticks_dir)
    holdout_dir = Path(args.holdout_dir)

    try:
        verified = run_preflight(ticks_dir, holdout_dir)
    except PreFlightFailure as exc:
        print(f"\nPRE-FLIGHT FAILED: {exc}", file=sys.stderr)
        print("STOPPING. No files were moved. No auto-repair attempted.", file=sys.stderr)
        return 1

    print("\n=== Files that WOULD move (12 total: 6 months x .parquet + .sha256) ===")
    for year, month, _ in verified:
        src = ticks_dir / SYMBOL / f"{year:04d}" / f"{month:02d}.parquet"
        dst = holdout_dir / SYMBOL / f"{year:04d}" / f"{month:02d}.parquet"
        print(f"  {src}  ->  {dst}")
        print(f"  {src}.sha256  ->  {dst}.sha256")

    if not args.confirm:
        print("\n=== DRY-RUN (default) -- no files were touched. Pass --confirm to execute. ===")
        return 0

    print("\n=== --confirm given: executing the move now ===")
    store = TickParquetStore(ticks_dir, holdout_range=XAUUSD_HOLDOUT_RANGE)
    moved = separate_holdout(store, holdout_dir, SYMBOL, XAUUSD_HOLDOUT_RANGE)
    print(f"separate_holdout() moved {len(moved)} file(s).")

    print("\n=== Post-move hash re-verification ===")
    ok = True
    for year, month, expected_hash in verified:
        dst = holdout_dir / SYMBOL / f"{year:04d}" / f"{month:02d}.parquet"
        if not dst.exists():
            print(f"FAIL: {dst} does not exist after move")
            ok = False
            continue
        actual = _sha256_of(dst)
        match = actual == expected_hash
        print(f"  {year:04d}-{month:02d}: pre-move={expected_hash} post-move={actual} "
              f"{'MATCH' if match else 'MISMATCH'}")
        ok = ok and match

    if not ok:
        print(
            "\nPOST-MOVE VERIFICATION FAILED -- inspect data/holdout/ and data/ticks/ "
            "manually before any further action. Do not re-run blindly.",
            file=sys.stderr,
        )
        return 1

    print("\n=== SUCCESS: all 6 months moved, all hashes verified pre==post. ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
