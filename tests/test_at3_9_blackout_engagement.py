"""AT-3.9 (partial, SetupStream-level): Blackout blocks new Setup Engagement (SPEC S11:
"no new Setups"). Order-cancellation-on-blackout-onset is an Orchestrator-level concern,
covered separately once T3.3 wires FillSimulator.cancel().
"""

from datetime import timedelta

from src.core.types import NewsEvent
from src.entry.setup_stream import SetupStream
from src.session.calendar_engine import CalendarEngine
from tests.fixtures.setup_stream import IN_WINDOW, m1, seed_store

TOP, BOTTOM = 100.0, 95.0


def test_engagement_blocked_during_blackout():
    blackout = CalendarEngine.from_config(
        [NewsEvent(ts_utc=IN_WINDOW, currency="USD", impact="red", title="NFP", source="test")],
        currencies=("USD",), impacts=("red",), blackout_before_min=30, blackout_after_min=30,
    )
    store = seed_store("long", TOP, BOTTOM, calendar=blackout)
    stream = SetupStream()
    # IN_WINDOW is exactly the event time -- deep inside its +/-30min blackout.
    stream.on_bar_close(m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    events = stream.step(store.as_of(IN_WINDOW + timedelta(minutes=1)))
    assert not any(e.kind == "engaged" for e in events)
    assert not stream.active_setups()


def test_engagement_resumes_after_blackout_ends():
    blackout = CalendarEngine.from_config(
        [NewsEvent(ts_utc=IN_WINDOW, currency="USD", impact="red", title="NFP", source="test")],
        currencies=("USD",), impacts=("red",), blackout_before_min=30, blackout_after_min=30,
    )
    store = seed_store("long", TOP, BOTTOM, calendar=blackout)
    stream = SetupStream()
    after_blackout = IN_WINDOW + timedelta(minutes=31)
    stream.on_bar_close(m1(after_blackout, 100.5, 100.6, 99.5, 100.2), store)
    events = stream.step(store.as_of(after_blackout + timedelta(minutes=1)))
    assert any(e.kind == "engaged" for e in events)
