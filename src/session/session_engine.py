"""Session window + NY day boundary (docs/SPEC_V1_FROZEN.md §1, T3.1).

Pure functions of a UTC timestamp -- no internal state. The Orchestrator
detects window-close / day-roll *transitions* itself by comparing
consecutive timestamps' results (``in_window``/``ny_date``), rather than
``SessionEngine`` tracking history -- keeps this trivially testable and
avoids any processing-order dependence (ARCHITECTURE.md principle #2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SessionEngine:
    """``window`` = (start, end) as "HH:MM" strings in ``tz`` (config/rules_v1.yaml session)."""

    window_start: time
    window_end: time
    tz: ZoneInfo = ZoneInfo("America/New_York")

    @classmethod
    def from_config(cls, window: tuple[str, str], tz: str) -> SessionEngine:
        """Build from the raw ``["08:30", "10:30"]`` / ``"America/New_York"`` config shape."""
        start_h, start_m = (int(x) for x in window[0].split(":"))
        end_h, end_m = (int(x) for x in window[1].split(":"))
        return cls(
            window_start=time(start_h, start_m),
            window_end=time(end_h, end_m),
            tz=ZoneInfo(tz),
        )

    def local(self, ts: datetime) -> datetime:
        """``ts`` (UTC) converted to this session's local (NY) time."""
        return ts.astimezone(self.tz)

    def in_window(self, ts: datetime) -> bool:
        """Whether ``ts`` falls inside [window_start, window_end) in NY local time."""
        local_time = self.local(ts).time()
        return self.window_start <= local_time < self.window_end

    def ny_date(self, ts: datetime) -> date:
        """The NY calendar date ``ts`` falls on -- the unit the daily quota resets by."""
        return self.local(ts).date()

    def window_bounds_utc(self, ny_date: date) -> tuple[datetime, datetime]:
        """This session's [start, end) on ``ny_date``, as UTC instants (DST-correct)."""
        start_local = datetime.combine(ny_date, self.window_start, tzinfo=self.tz)
        end_local = datetime.combine(ny_date, self.window_end, tzinfo=self.tz)
        return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))
