#!/usr/bin/env python3
"""Full-range XAUUSD tick backfill (KI-001 closure infrastructure).

Orchestration only -- every download/cache/storage guarantee is delegated to
already-tested production components:

  * ``src.data.dukascopy_downloader.DukascopyDownloader`` does the actual
    HTTP fetch, LZMA decode, immutable per-hour ``.bi5`` caching, and retry/
    backoff. This script never re-implements any of that -- it only injects
    a paced, logging ``transport`` callable (the downloader's own documented
    extension point) and calls ``get_ticks()``/the constructor as-is.
  * ``src.data.tick_store.TickParquetStore`` does the actual monthly Parquet
    write + content-hash immutability check. This script only decides *when*
    to call ``write_month()`` and what range to pass it.

What this script adds on top (new, but pure orchestration -- no engine logic):

  1. A CLI-configurable date range, split into calendar months via the
     existing ``months_between()`` helper (not re-implemented).
  2. A checkpoint file recording which (year, month) have already been
     written to the ``TickParquetStore``, so a re-run after an interruption
     skips completed months entirely -- the *hour*-level resume safety is
     already free from ``DukascopyDownloader``'s own on-disk cache; this is
     only a month-level fast-skip on top of it.
  3. A month-level retry loop with a longer cooldown than the downloader's
     own per-hour backoff, for the case where an entire month's fetch is
     aborted by a ``DukascopyFetchError`` (all of the downloader's own
     per-hour retries exhausted). A single stubborn month is retried up to
     ``--month-retry-limit`` times, then marked failed in the checkpoint and
     skipped -- it does not abort the rest of the range.
  4. Structured JSONL request-level logging (one line per real HTTP call,
     via the injected transport) plus a human-readable progress log and a
     final run summary, so a long unattended run leaves a clear audit trail
     of what was requested, retried, and why anything failed.

Known, intentional trade-off: the first and/or last calendar month of the
range is often *partial* (e.g. the 90-day Warm-Up start falls mid-month, or
--end falls mid-month). ``TickParquetStore.write_month()`` is immutable per
month -- if this script is ever re-run with an *earlier* --start or a
*later* --end than a previously-completed run, that boundary month's stored
content will legitimately conflict (``TickStoreConflictError``) rather than
silently widen. That is the store's correct designed behavior (no silent
rewrite of published data), not a bug in this script; widening an
already-completed range's boundary requires a deliberate decision (e.g.
deleting that month's stored Parquet + checkpoint entry first), not an
automatic retry.

Usage:
    python scripts/backfill_full_range.py \\
        --symbol XAUUSD --start 2022-10-03 --end 2025-12-31

    python scripts/backfill_full_range.py --start 2022-10-03 --end 2025-12-31 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.dukascopy_downloader import (  # noqa: E402
    DukascopyDownloader,
    DukascopyFetchError,
    Transport,
    _default_transport,
)
from src.data.tick_store import (  # noqa: E402
    TickParquetStore,
    TickStoreConflictError,
    months_between,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


def _month_slice(
    year: int, month: int, overall_start: datetime, overall_end: datetime
) -> tuple[datetime, datetime]:
    """The [start, end) slice of one calendar month, clipped to the requested range."""
    month_start = datetime(year, month, 1, tzinfo=UTC)
    month_end = (month_start + timedelta(days=32)).replace(day=1)
    return max(month_start, overall_start), min(month_end, overall_end)


class PacedLoggingTransport:
    """Wraps the downloader's default transport with inter-request pacing and
    structured request logging. Does not touch ``DukascopyDownloader``'s own
    retry/backoff/caching logic -- it only observes and paces the raw HTTP call."""

    def __init__(self, inner: Transport, pacing_seconds: float, requests_log: Path) -> None:
        self.inner = inner
        self.pacing_seconds = pacing_seconds
        self.requests_log = requests_log
        self.total_calls = 0
        self.total_429 = 0
        self.total_errors = 0

    def __call__(self, url: str) -> bytes:
        if self.pacing_seconds > 0:
            time.sleep(self.pacing_seconds)
        self.total_calls += 1
        t0 = time.monotonic()
        try:
            body = self.inner(url)
            self._log(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "url": url,
                    "outcome": "success",
                    "bytes": len(body),
                    "duration_s": round(time.monotonic() - t0, 3),
                }
            )
            return body
        except Exception as exc:  # noqa: BLE001 - logged, then re-raised for the downloader's own retry
            self.total_errors += 1
            is_429 = isinstance(exc, urllib.error.HTTPError) and exc.code == 429
            if is_429:
                self.total_429 += 1
            self._log(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "url": url,
                    "outcome": "error",
                    "error_type": type(exc).__name__,
                    "error_msg": str(exc),
                    "is_429": is_429,
                    "duration_s": round(time.monotonic() - t0, 3),
                }
            )
            raise

    def _log(self, record: dict) -> None:
        with self.requests_log.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")


class Checkpoint:
    """Tracks which (year, month) are already fully written to the
    TickParquetStore. Purely a fast-skip on resume -- the store's own
    content-hash immutability check remains the real correctness guarantee
    even if this file is lost or stale."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if path.exists():
            self._data = json.loads(path.read_text())
        else:
            self._data = {"completed_months": [], "failed_months": {}, "month_details": {}}

    def is_completed(self, year: int, month: int) -> bool:
        return [year, month] in self._data["completed_months"]

    def mark_completed(self, year: int, month: int, data_version: str, row_count: int) -> None:
        key = [year, month]
        if key not in self._data["completed_months"]:
            self._data["completed_months"].append(key)
        self._data["failed_months"].pop(f"{year:04d}-{month:02d}", None)
        self._data["month_details"][f"{year:04d}-{month:02d}"] = {
            "data_version": data_version,
            "row_count": row_count,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        self._save()

    def mark_failed(self, year: int, month: int, reason: str, detail: str) -> None:
        self._data["failed_months"][f"{year:04d}-{month:02d}"] = {
            "reason": reason,
            "detail": detail,
            "failed_at": datetime.now(UTC).isoformat(),
        }
        self._save()

    def failed_month_keys(self) -> list[str]:
        """Read-only view of currently-failed month keys, for a run summary."""
        return list(self._data["failed_months"].keys())

    def _save(self) -> None:
        """Write atomically (temp file + rename) -- a checkpoint corrupted by a
        crash mid-write would break resume for every month, not just the one
        being processed, so this cannot use a plain non-atomic write_text()
        (same pattern TickParquetStore.write_month() already uses for the
        same reason)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(self._data, indent=2, default=str))
        tmp_path.replace(self.path)


def log(msg: str) -> None:
    print(f"{datetime.now(UTC).isoformat()}  {msg}", flush=True)


def process_month(
    downloader: DukascopyDownloader,
    store: TickParquetStore,
    checkpoint: Checkpoint,
    symbol: str,
    year: int,
    month: int,
    overall_start: datetime,
    overall_end: datetime,
    month_retry_limit: int,
    month_retry_cooldown_s: float,
) -> bool:
    """Download+store one calendar month. Returns True on success.

    A ``DukascopyFetchError`` (the downloader's own per-hour retries already
    exhausted) is retried at the *month* level, with a much longer cooldown,
    up to ``month_retry_limit`` times -- already-cached hours are not
    re-fetched, so each retry only re-attempts whatever hour actually failed.

    A ``TickStoreConflictError`` is NOT retried: it means this month's
    content genuinely differs from what's already stored, which a retry
    cannot fix -- it needs human review, so it's logged loudly and the month
    is marked failed immediately.
    """
    start, end = _month_slice(year, month, overall_start, overall_end)
    label = f"{year:04d}-{month:02d}"

    for attempt in range(1, month_retry_limit + 1):
        try:
            log(
                f"[{label}] fetching ({start.isoformat()} .. {end.isoformat()}), "
                f"attempt {attempt}/{month_retry_limit}"
            )
            ticks = downloader.get_ticks(symbol, start, end)
            log(f"[{label}] fetched {ticks.height:,} ticks; writing to TickParquetStore")
            result = store.write_month(symbol, year, month, ticks)
            checkpoint.mark_completed(year, month, result.data_version, result.row_count)
            log(
                f"[{label}] DONE row_count={result.row_count:,} "
                f"data_version={result.data_version[:16]}..."
            )
            return True
        except DukascopyFetchError as exc:
            log(f"[{label}] FAILED (download): {exc}")
            if attempt < month_retry_limit:
                log(f"[{label}] cooling down {month_retry_cooldown_s}s before retry...")
                time.sleep(month_retry_cooldown_s)
            else:
                checkpoint.mark_failed(year, month, "download_failed_after_retries", str(exc))
                log(f"[{label}] giving up after {month_retry_limit} attempts; marked failed")
                return False
        except TickStoreConflictError as exc:
            log(f"[{label}] CRITICAL (store conflict, NOT retried -- needs human review): {exc}")
            checkpoint.mark_failed(year, month, "tick_store_conflict", str(exc))
            return False
        except Exception as exc:  # noqa: BLE001 - isolate one bad month, keep the rest of the range going
            log(f"[{label}] CRITICAL (unexpected {type(exc).__name__}): {exc}")
            log(traceback.format_exc())
            detail = f"{type(exc).__name__}: {exc}"
            checkpoint.mark_failed(year, month, "unexpected_exception", detail)
            return False
    return False


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--start", required=True, help="YYYY-MM-DD (UTC, inclusive)")
    p.add_argument("--end", required=True, help="YYYY-MM-DD (UTC, inclusive)")
    p.add_argument("--raw-cache-dir", default=str(REPO_ROOT / "data" / "raw"))
    p.add_argument("--ticks-dir", default=str(REPO_ROOT / "data" / "ticks"))
    p.add_argument(
        "--checkpoint-file",
        default=str(REPO_ROOT / "data" / "backfill_state" / "checkpoint.json"),
    )
    p.add_argument("--log-dir", default=str(REPO_ROOT / "data" / "backfill_state" / "logs"))
    p.add_argument(
        "--pacing-seconds", type=float, default=0.5, help="extra delay before every real HTTP call"
    )
    p.add_argument(
        "--max-retries", type=int, default=4, help="passed through to DukascopyDownloader"
    )
    p.add_argument(
        "--backoff-seconds", type=float, default=1.0, help="passed through to DukascopyDownloader"
    )
    p.add_argument("--month-retry-limit", type=int, default=3)
    p.add_argument("--month-retry-cooldown-seconds", type=float, default=120.0)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned month list and checkpoint state; no network access",
    )
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    start = _parse_date(args.start)
    end = _parse_date(args.end) + timedelta(days=1)  # --end is an inclusive calendar date

    if start >= end:
        print(f"ERROR: --start ({args.start}) must be before --end ({args.end}); nothing to do.")
        return 1

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    requests_log = log_dir / "requests.jsonl"

    checkpoint = Checkpoint(Path(args.checkpoint_file))
    months = months_between(start, end - timedelta(seconds=1))

    log(f"Range: {start.isoformat()} .. {end.isoformat()} ({len(months)} calendar months)")
    pending = [(y, m) for (y, m) in months if not checkpoint.is_completed(y, m)]
    log(f"Already completed (checkpoint): {len(months) - len(pending)}; pending: {len(pending)}")

    if args.dry_run:
        for y, m in months:
            status = "completed" if checkpoint.is_completed(y, m) else "pending"
            print(f"  {y:04d}-{m:02d}: {status}")
        print("\n--dry-run: no network access performed.")
        return 0

    transport = PacedLoggingTransport(_default_transport, args.pacing_seconds, requests_log)
    downloader = DukascopyDownloader(
        cache_dir=Path(args.raw_cache_dir),
        transport=transport,
        max_retries=args.max_retries,
        backoff_seconds=args.backoff_seconds,
    )
    store = TickParquetStore(Path(args.ticks_dir))

    succeeded, failed = 0, 0
    for y, m in pending:
        ok = process_month(
            downloader, store, checkpoint, args.symbol, y, m, start, end,
            args.month_retry_limit, args.month_retry_cooldown_seconds,
        )
        succeeded += int(ok)
        failed += int(not ok)

    log(
        f"=== BACKFILL RUN COMPLETE === months_succeeded={succeeded} months_failed={failed} "
        f"transport_calls={transport.total_calls} 429s={transport.total_429} "
        f"errors={transport.total_errors}"
    )
    if failed:
        log(f"Failed months (see checkpoint file for detail): {checkpoint.failed_month_keys()}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
