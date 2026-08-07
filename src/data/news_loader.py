"""BLS-format economic-calendar loader (B-7, KI-010 Phase 1).

Converts the CSV Data Contract (WORK_ORDER_B7.md Sec 3 -- date,time_et,release,source)
into ``list[NewsEvent]`` (``src/core/types.py``, unmodified). Read-only, and does not
know or care that the only CSV in production today happens to be BLS-sourced beyond the
Phase-1 release-name whitelist below -- ``CalendarEngine`` (D-037) already consumes
whatever ``list[NewsEvent]`` it is given, source-agnostic.

Fail-loud (CLAUDE.md: no silent coercion on malformed data): every row must parse
cleanly -- unknown release names, malformed dates/times, and missing/empty required
fields all raise immediately. Nothing is silently skipped, defaulted, or coerced.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.core.types import NewsEvent

_ET = ZoneInfo("America/New_York")

# Phase 1 whitelist (WORK_ORDER_B7.md Sec 3): only these two release names are accepted,
# matching the exact strings written by data/news/bls_calendar.csv (B-7 Commit 2).
# CSV "release" column value -> NewsEvent.title
_RELEASE_WHITELIST: dict[str, str] = {
    "Consumer Price Index": "CPI",
    "Employment Situation": "Employment Situation",
}

_REQUIRED_COLUMNS = ("date", "time_et", "release", "source")


class NewsLoaderError(ValueError):
    """Fail-loud: malformed/unrecognized input -- never silently coerced or skipped."""


def load_bls_csv(path: str | Path) -> list[NewsEvent]:
    """Load a Data-Contract CSV (date,time_et,release,source) into ``NewsEvent`` objects.

    Returns events sorted by ``ts_utc`` -- deterministic regardless of input row order.

    Raises:
        NewsLoaderError: on an empty file, a missing required column, zero data rows,
            or any row with a missing/empty field, an unparseable date/time, or a
            release name outside the Phase 1 whitelist.
    """
    path = Path(path)
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise NewsLoaderError(f"{path}: empty file, no header row found")
        missing_columns = [c for c in _REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing_columns:
            raise NewsLoaderError(
                f"{path}: missing required column(s) {missing_columns} "
                f"(found: {reader.fieldnames})"
            )
        rows = list(reader)

    if not rows:
        raise NewsLoaderError(f"{path}: header row present but zero data rows")

    events = [_parse_row(row, line_num, path) for line_num, row in enumerate(rows, start=2)]
    events.sort(key=lambda e: e.ts_utc)
    return events


def _parse_row(row: dict[str, str], line_num: int, path: Path) -> NewsEvent:
    for column in _REQUIRED_COLUMNS:
        value = row.get(column)
        if value is None or value.strip() == "":
            raise NewsLoaderError(f"{path}:{line_num}: missing/empty required field '{column}'")

    release = row["release"].strip()
    if release not in _RELEASE_WHITELIST:
        raise NewsLoaderError(
            f"{path}:{line_num}: unrecognized release '{release}' -- not in the Phase 1 "
            f"whitelist {sorted(_RELEASE_WHITELIST)}"
        )

    ts_utc = _parse_et_to_utc(row["date"].strip(), row["time_et"].strip(), line_num, path)

    return NewsEvent(
        ts_utc=ts_utc,
        currency="USD",
        impact="red",
        title=_RELEASE_WHITELIST[release],
        source=row["source"].strip(),
    )


def _parse_et_to_utc(date_str: str, time_str: str, line_num: int, path: Path) -> datetime:
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise NewsLoaderError(
            f"{path}:{line_num}: unparseable date/time '{date_str} {time_str}' "
            f"(expected YYYY-MM-DD HH:MM): {exc}"
        ) from exc
    local_et = naive.replace(tzinfo=_ET)
    return local_et.astimezone(UTC)
