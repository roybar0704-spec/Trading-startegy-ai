#!/usr/bin/env python3
"""AT-0.2 Cache immutability check (Stage A, B-5, Commit 2) -- home-computer only.

Read-only diagnostic -- NOT part of the production pipeline or the pytest suite. Runs the
real, unmodified DukascopyDownloader (src/data/dukascopy_downloader.py) against the real
raw-bytes cache already populated by the Backfill (data/raw/ by default, --raw-cache-dir
matches scripts/backfill_full_range.py's own default) for one or more hours that are
already fully cached from Batch 1-7.

Methodology: the downloader is constructed with a "poison" transport that raises if it is
ever called. If get_ticks() succeeds anyway, that proves the call was served entirely from
the on-disk cache -- no network fetch occurred. Each target hour's cache file (.bi5) and its
sha256 sidecar are read byte-for-byte before and after two separate get_ticks() calls (a
"first download" and a repeat "second download"), and data_version() is computed twice.

Pass criteria (AT-0.2, docs/ACCEPTANCE_TESTS.md): a repeat download does not change any
cached file, and data_version is stable. Concretely, for every target hour:
  1. The poison transport is never invoked (proves no re-fetch over the network).
  2. The cache file's bytes and sha256 sidecar are byte-identical before/after both calls.
  3. The two get_ticks() calls return identical tick DataFrames.
  4. data_version() returns the same value both times.
Any single failure on any hour -> overall FAIL, printed explicitly, not silently skipped.

Does NOT touch data/ticks/ (only reads data/raw/ raw hour-cache files) and does NOT modify
config. If data/raw/ (or the requested hour within it) is missing, this is reported clearly
and the script exits non-zero -- it does not fall back to a live download.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.dukascopy_downloader import DukascopyDownloader  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_HOURS = [
    datetime(2022, 11, 1, 0, tzinfo=UTC),
    datetime(2022, 11, 15, 12, tzinfo=UTC),
    datetime(2022, 11, 29, 23, tzinfo=UTC),
]


def _poison_transport(url: str) -> bytes:
    raise AssertionError(
        f"unexpected network fetch attempted for an hour that should already be cached: {url}"
    )


_CacheState = tuple[Path, Path, bytes, str]


def _cache_file_state(cache_dir: Path, symbol: str, hour_start: datetime) -> _CacheState | None:
    path = (
        cache_dir
        / symbol
        / f"{hour_start.year:04d}"
        / f"{hour_start.month:02d}"
        / f"{hour_start.day:02d}"
        / f"{hour_start.hour:02d}h_ticks.bi5"
    )
    hash_path = path.with_suffix(path.suffix + ".sha256")
    if not path.exists() or not hash_path.exists():
        return None
    content = path.read_bytes()
    return path, hash_path, content, hash_path.read_text().strip()


def check_hour(cache_dir: Path, symbol: str, hour_start: datetime) -> bool:
    hour_end = hour_start + timedelta(hours=1)
    label = hour_start.isoformat()
    print(f"\n--- Hour {label} ---")

    before = _cache_file_state(cache_dir, symbol, hour_start)
    if before is None:
        print(f"SKIP/FAIL: no cached .bi5 + .sha256 sidecar found for this hour under {cache_dir}")
        return False
    path, hash_path, bytes_before, hash_before = before
    print(f"cache file: {path}")
    print(f"cached bytes: {len(bytes_before):,}, recorded sha256: {hash_before}")
    actual_hash_before = hashlib.sha256(bytes_before).hexdigest()
    if actual_hash_before != hash_before:
        print(
            "FAIL: cache file content does not match its own recorded sha256 sidecar "
            "(tampered cache)"
        )
        return False

    downloader = DukascopyDownloader(cache_dir=cache_dir, transport=_poison_transport)

    ticks_1 = downloader.get_ticks(symbol, hour_start, hour_end)
    version_1 = downloader.data_version(symbol, hour_start, hour_end)
    after_1 = _cache_file_state(cache_dir, symbol, hour_start)
    unchanged_after_1 = (
        after_1 is not None and after_1[2] == bytes_before and after_1[3] == hash_before
    )
    print(f"get_ticks() call #1 (first 'download'): {ticks_1.height:,} ticks, no network call made")
    print(f"cache file unchanged after call #1: {unchanged_after_1}")

    ticks_2 = downloader.get_ticks(symbol, hour_start, hour_end)
    version_2 = downloader.data_version(symbol, hour_start, hour_end)
    after_2 = _cache_file_state(cache_dir, symbol, hour_start)
    unchanged_after_2 = (
        after_2 is not None and after_2[2] == bytes_before and after_2[3] == hash_before
    )
    print(f"get_ticks() call #2 (repeat 'download'): {ticks_2.height:,} ticks, no network call")
    print(f"cache file unchanged after call #2: {unchanged_after_2}")

    ticks_identical = ticks_1.equals(ticks_2)
    version_stable = version_1 == version_2
    print(f"ticks identical across both calls: {ticks_identical}")
    print(f"data_version stable across both calls: {version_stable} ({version_1})")

    return bool(unchanged_after_1 and unchanged_after_2 and ticks_identical and version_stable)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--raw-cache-dir", default=str(REPO_ROOT / "data" / "raw"))
    p.add_argument(
        "--hour",
        action="append",
        dest="hours",
        help="UTC hour to check, format YYYY-MM-DDTHH (repeatable). Default: 3 sample hours "
        "spread across November 2022 (start/middle/end of the already-verified real month).",
    )
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    cache_dir = Path(args.raw_cache_dir)
    print(f"Raw cache directory: {cache_dir}")
    if not cache_dir.exists():
        print(
            f"FAIL: {cache_dir} does not exist. AT-0.2 cannot be verified without the real "
            "raw hour-cache populated by the Backfill (scripts/backfill_full_range.py "
            "--raw-cache-dir, same default path). Do not proceed to a live download as a "
            "substitute -- report this back for a Decision Proposal."
        )
        return 1

    if args.hours:
        hours = [datetime.strptime(h, "%Y-%m-%dT%H").replace(tzinfo=UTC) for h in args.hours]
    else:
        hours = DEFAULT_HOURS

    results = {h.isoformat(): check_hour(cache_dir, args.symbol, h) for h in hours}

    print("\n=== Summary ===")
    for label, passed in results.items():
        print(f"{label}: {'PASS' if passed else 'FAIL'}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
