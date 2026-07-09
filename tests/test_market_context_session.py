"""T3.1: MarketContext.in_window()/in_blackout() delegate to the wired engines (D-039 pattern)."""

from datetime import UTC, datetime

import pytest

from src.core.types import NewsEvent
from src.session.calendar_engine import CalendarEngine
from src.session.session_engine import SessionEngine
from src.store.state_store import StateStore

SESSION = SessionEngine.from_config(window=("08:30", "10:30"), tz="America/New_York")


def test_in_window_raises_until_session_engine_wired():
    store = StateStore()
    ctx = store.as_of(datetime(2024, 1, 10, 14, 0, tzinfo=UTC))
    with pytest.raises(NotImplementedError):
        ctx.in_window()


def test_in_window_delegates_once_wired():
    store = StateStore(session_engine=SESSION)
    in_window_ctx = store.as_of(datetime(2024, 1, 10, 14, 0, tzinfo=UTC))  # 09:00 ET
    outside_ctx = store.as_of(datetime(2024, 1, 10, 20, 0, tzinfo=UTC))  # 15:00 ET
    assert in_window_ctx.in_window() is True
    assert outside_ctx.in_window() is False


def test_in_blackout_delegates_once_wired():
    events = [
        NewsEvent(
            ts_utc=datetime(2024, 1, 10, 14, 0, tzinfo=UTC),
            currency="USD", impact="red", title="x", source="test",
        )
    ]
    cal = CalendarEngine.from_config(
        events, currencies=("USD",), impacts=("red",),
        blackout_before_min=30, blackout_after_min=30,
    )
    store = StateStore(calendar_engine=cal)
    inside = store.as_of(datetime(2024, 1, 10, 14, 15, tzinfo=UTC))
    outside = store.as_of(datetime(2024, 1, 10, 15, 0, tzinfo=UTC))
    assert inside.in_blackout() is True
    assert outside.in_blackout() is False
