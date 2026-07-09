"""News Blackout calendar (docs/SPEC_V1_FROZEN.md §11, T3.1).

Data-source-independent (D-037): consumes an injected ``list[NewsEvent]``
(``src.core.types``) exactly like ``Tick``/``Bar`` -- real events later,
synthetic fixtures now (AT-3.9). ``in_blackout`` doubles directly as the
``in_news_checker: Callable[[datetime], bool]`` that ``FillSimulator``
(Phase 2) already requires with no default.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from src.core.types import NewsEvent
from src.session.session_engine import SessionEngine


@dataclass(frozen=True)
class CalendarEngine:
    """±blackout window around each filtered (currency, impact) news event."""

    events: tuple[NewsEvent, ...]
    blackout_before: timedelta
    blackout_after: timedelta

    @classmethod
    def from_config(
        cls,
        events: list[NewsEvent],
        currencies: tuple[str, ...],
        impacts: tuple[str, ...],
        blackout_before_min: int,
        blackout_after_min: int,
    ) -> CalendarEngine:
        """Filter ``events`` to the declared (currency, impact) scope (config/rules_v1.yaml)."""
        filtered = tuple(e for e in events if e.currency in currencies and e.impact in impacts)
        return cls(
            events=filtered,
            blackout_before=timedelta(minutes=blackout_before_min),
            blackout_after=timedelta(minutes=blackout_after_min),
        )

    def in_blackout(self, ts: datetime) -> bool:
        """Whether ``ts`` falls inside any filtered event's ±blackout window."""
        return any(
            e.ts_utc - self.blackout_before <= ts <= e.ts_utc + self.blackout_after
            for e in self.events
        )

    def blackout_intervals_utc(self) -> list[tuple[datetime, datetime]]:
        """Each filtered event's raw [start, end) blackout interval, unmerged, any order."""
        return [
            (e.ts_utc - self.blackout_before, e.ts_utc + self.blackout_after) for e in self.events
        ]


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def effective_window_minutes(
    session: SessionEngine, calendar: CalendarEngine, ny_date: date
) -> int:
    """Session window minutes on ``ny_date``, minus any Blackout overlap (SPEC §11 H5)."""
    window_start, window_end = session.window_bounds_utc(ny_date)
    window_minutes = (window_end - window_start).total_seconds() / 60.0

    covered = 0.0
    for start, end in _merge_intervals(calendar.blackout_intervals_utc()):
        overlap_start = max(start, window_start)
        overlap_end = min(end, window_end)
        if overlap_start < overlap_end:
            covered += (overlap_end - overlap_start).total_seconds() / 60.0

    return round(window_minutes - covered)
