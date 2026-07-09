"""T3.1: CalendarEngine Blackout filtering, boundaries, and effective_window_minutes (H5)."""

from datetime import UTC, date, datetime

from src.core.types import NewsEvent
from src.session.calendar_engine import CalendarEngine, effective_window_minutes
from src.session.session_engine import SessionEngine

SESSION = SessionEngine.from_config(window=("08:30", "10:30"), tz="America/New_York")


def _events(*rows: tuple[str, str, str]) -> list[NewsEvent]:
    return [
        NewsEvent(
            ts_utc=datetime.fromisoformat(ts), currency=ccy, impact=impact,
            title="x", source="test",
        )
        for ts, ccy, impact in rows
    ]


def test_only_declared_currency_and_impact_create_blackout():
    events = _events(
        ("2024-01-10T14:00:00+00:00", "USD", "red"),
        ("2024-01-10T14:00:00+00:00", "EUR", "red"),  # wrong currency -- filtered out
        ("2024-01-10T14:00:00+00:00", "USD", "yellow"),  # wrong impact -- filtered out
    )
    cal = CalendarEngine.from_config(
        events, currencies=("USD",), impacts=("red",),
        blackout_before_min=30, blackout_after_min=30,
    )
    assert len(cal.events) == 1


def test_blackout_boundaries_inclusive():
    events = _events(("2024-01-10T14:00:00+00:00", "USD", "red"))
    cal = CalendarEngine.from_config(
        events, currencies=("USD",), impacts=("red",),
        blackout_before_min=30, blackout_after_min=30,
    )
    assert cal.in_blackout(datetime(2024, 1, 10, 13, 30, tzinfo=UTC))  # exactly -30min
    assert cal.in_blackout(datetime(2024, 1, 10, 14, 30, tzinfo=UTC))  # exactly +30min
    assert not cal.in_blackout(datetime(2024, 1, 10, 13, 29, tzinfo=UTC))
    assert not cal.in_blackout(datetime(2024, 1, 10, 14, 31, tzinfo=UTC))


def test_effective_window_minutes_no_news_is_full_window():
    cal = CalendarEngine.from_config(
        [], currencies=("USD",), impacts=("red",), blackout_before_min=30, blackout_after_min=30,
    )
    assert effective_window_minutes(SESSION, cal, date(2024, 1, 10)) == 120


def test_effective_window_minutes_nfp_at_open_eats_window():
    # NFP at 08:30 ET (13:30 UTC) -> blackout [08:00, 09:00) ET overlaps the window's first 30min.
    events = _events(("2024-01-10T13:30:00+00:00", "USD", "red"))
    cal = CalendarEngine.from_config(
        events, currencies=("USD",), impacts=("red",),
        blackout_before_min=30, blackout_after_min=30,
    )
    assert effective_window_minutes(SESSION, cal, date(2024, 1, 10)) == 90


def test_effective_window_minutes_overlapping_blackouts_not_double_counted():
    # Two events 10 minutes apart -> their +/-30min blackouts overlap heavily; must merge, not sum.
    events = _events(
        ("2024-01-10T13:30:00+00:00", "USD", "red"),
        ("2024-01-10T13:40:00+00:00", "USD", "red"),
    )
    cal = CalendarEngine.from_config(
        events, currencies=("USD",), impacts=("red",),
        blackout_before_min=30, blackout_after_min=30,
    )
    # merged blackout = [13:00,14:10) UTC; window = [13:30,15:30) UTC -> overlap = 40min
    assert effective_window_minutes(SESSION, cal, date(2024, 1, 10)) == 80
