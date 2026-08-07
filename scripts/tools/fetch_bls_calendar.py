#!/usr/bin/env python3
"""B-7 Commit 1 -- BLS economic-calendar acquisition tool (Stage A, KI-010 Phase 1).

Fetches BLS's public annual "Schedule of Releases" pages
(https://www.bls.gov/schedule/news_release/{YEAR}_sched.htm) and extracts the release
date+time of exactly two release types -- Consumer Price Index (CPI) and Employment
Situation (Non-Farm Payrolls) -- into a CSV matching the Data Contract in
WORK_ORDER_B7.md Sec 3: `date,time_et,release,source`.

Standard-library only (urllib.request + html.parser) -- no new project dependency.
One-time, manual-trigger acquisition tool (KI010_DECISION_DOC.md Sec 1: "a single
historical list, not a live feed") -- NOT part of the production pipeline, NOT run
automatically, NOT a scraper of any non-government source.

Must be run on a machine with real network access -- this Sandbox's egress proxy
blocks bls.gov (confirmed in PREFLIGHT_B7.md Sec a.8); this tool cannot be executed
or smoke-tested here.

Fail-loud by design (CLAUDE.md: no silent partial results on data anomalies):
  - A year page that fails to fetch aborts the whole run -- no partial CSV is written.
  - A year page in which CPI or Employment Situation cannot be found at all aborts the
    whole run.
  - A matched release row from which a date or time cannot be extracted aborts the
    whole run, naming the exact row text that failed.
None of these produce a truncated/best-effort CSV -- every failure is a hard error.

Does not touch src/, config/, or any existing file. Writes only the CSV named by
--output (default: data/news/bls_calendar.csv).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BLS_SCHEDULE_URL = "https://www.bls.gov/schedule/news_release/{year}_sched.htm"

# Canonical BLS release names this tool looks for (case-insensitive substring match).
# release_key -> (needle, output "release" column value)
RELEASE_TARGETS: dict[str, tuple[str, str]] = {
    "cpi": ("consumer price index", "CPI"),
    "nfp": ("employment situation", "Employment Situation"),
}

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)
_DATE_RE = re.compile(rf"\b({_MONTHS})\s+(\d{{1,2}}),\s*(\d{{4}})\b")
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*([AaPp]\.?[Mm]\.?)\b")

_MONTH_NUM = {
    name: i + 1
    for i, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
    )
}


class BLSFetchError(RuntimeError):
    """Fail-loud: a year page could not be fetched, or a required release was missing."""


class _RowTextExtractor(HTMLParser):
    """Collects each <tr>...</tr> element's flattened visible text, in document order."""

    def __init__(self) -> None:
        super().__init__()
        self._depth = 0
        self._current: list[str] = []
        self.rows: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._depth += 1
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._depth > 0:
            self._depth -= 1
            self.rows.append(" ".join(self._current))

    def handle_data(self, data: str) -> None:
        if self._depth > 0:
            text = data.strip()
            if text:
                self._current.append(text)


def fetch_year_html(year: int) -> str:
    url = BLS_SCHEDULE_URL.format(year=year)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - fixed https host
            if resp.status != 200:
                raise BLSFetchError(f"{url} returned HTTP {resp.status} (expected 200)")
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise BLSFetchError(f"failed to fetch {url}: {exc}") from exc


def _parse_date(match: re.Match[str]) -> date:
    month_name, day, year = match.group(1), match.group(2), match.group(3)
    return date(int(year), _MONTH_NUM[month_name], int(day))


def _parse_time_et(match: re.Match[str]) -> str:
    hour, minute, meridiem = match.group(1), match.group(2), match.group(3)
    is_pm = meridiem.lower().startswith("p")
    hour_i = int(hour) % 12
    if is_pm:
        hour_i += 12
    return f"{hour_i:02d}:{minute}"


def extract_release_rows(html: str, year: int) -> dict[str, list[tuple[date, str]]]:
    """Find every row matching each RELEASE_TARGETS needle; extract (date, time_et).

    Raises BLSFetchError (fail-loud) if a target release has zero matching rows in
    this year's page, or if a matched row's date/time cannot be parsed.
    """
    parser = _RowTextExtractor()
    parser.feed(html)

    found: dict[str, list[tuple[date, str]]] = {key: [] for key in RELEASE_TARGETS}
    for row_text in parser.rows:
        lowered = row_text.lower()
        for key, (needle, _label) in RELEASE_TARGETS.items():
            if needle not in lowered:
                continue
            date_match = _DATE_RE.search(row_text)
            time_match = _TIME_RE.search(row_text)
            if date_match is None or time_match is None:
                raise BLSFetchError(
                    f"{year}: matched release row for '{needle}' but could not extract "
                    f"a date and/or time from it. Row text: {row_text!r}"
                )
            found[key].append((_parse_date(date_match), _parse_time_et(time_match)))

    for key, (needle, _label) in RELEASE_TARGETS.items():
        if not found[key]:
            raise BLSFetchError(
                f"{year}: zero rows matched '{needle}' on {BLS_SCHEDULE_URL.format(year=year)} "
                "-- refusing to write a partial CSV. Inspect the page's real HTML structure "
                "and fix the parser before re-running."
            )
    return found


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--years", type=int, nargs="+", default=[2022, 2023, 2024, 2025])
    p.add_argument("--start", default="2022-10-03", help="YYYY-MM-DD, inclusive")
    p.add_argument("--end", default="2025-12-31", help="YYYY-MM-DD, inclusive")
    p.add_argument(
        "--output", default=str(REPO_ROOT / "data" / "news" / "bls_calendar.csv")
    )
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    all_rows: list[tuple[date, str, str, str]] = []  # (date, time_et, release, source)
    for year in args.years:
        print(f"Fetching {BLS_SCHEDULE_URL.format(year=year)} ...")
        html = fetch_year_html(year)
        found = extract_release_rows(html, year)
        source = f"BLS:{year}_sched.htm"
        for key, (_needle, label) in RELEASE_TARGETS.items():
            for event_date, time_et in found[key]:
                all_rows.append((event_date, time_et, label, source))
        print(
            f"  {year}: CPI={len(found['cpi'])} rows, "
            f"Employment Situation={len(found['nfp'])} rows"
        )

    all_rows.sort(key=lambda r: (r[0], r[2]))

    seen = set()
    for row in all_rows:
        key = (row[0], row[2])
        if key in seen:
            raise BLSFetchError(f"duplicate release detected: {row[2]} on {row[0]}")
        seen.add(key)

    filtered = [r for r in all_rows if start <= r[0] <= end]
    if not filtered:
        raise BLSFetchError(
            f"zero rows fall inside the requested range [{start}, {end}] -- refusing "
            "to write an empty CSV."
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "time_et", "release", "source"])
        for event_date, time_et, release, source in filtered:
            writer.writerow([event_date.isoformat(), time_et, release, source])

    content = output_path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    cpi_count = sum(1 for r in filtered if r[2] == "CPI")
    nfp_count = sum(1 for r in filtered if r[2] == "Employment Situation")

    print(f"\nWrote {output_path}")
    print("\n=== Evidence ===")
    print(f"Row count (excl. header): {len(filtered)}")
    print(f"CPI rows: {cpi_count}")
    print(f"Employment Situation rows: {nfp_count}")
    print(f"Date range: {filtered[0][0].isoformat()} .. {filtered[-1][0].isoformat()}")
    print(f"SHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BLSFetchError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
