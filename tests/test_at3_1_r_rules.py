"""AT-3.1 R rules: four Fixtures -- missing Wick / bearish body / not-in-zone / valid ->
only the valid one becomes R.
"""

from datetime import timedelta

from src.entry.setup_stream import SetupStream
from tests.fixtures.setup_stream import IN_WINDOW, m1, m5, seed_store

TOP, BOTTOM = 100.0, 95.0


def _engage_and_get_events(bar_offset_minutes: int = 0):
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()
    engage_ts = IN_WINDOW + timedelta(minutes=bar_offset_minutes)
    stream.on_bar_close(m1(engage_ts, 100.5, 100.6, 99.5, 100.2), store)  # touches zone
    events = stream.step(store.as_of(engage_ts + timedelta(minutes=1)))
    assert any(e.kind == "engaged" for e in events)
    return store, stream


def test_missing_wick_does_not_qualify_as_r():
    store, stream = _engage_and_get_events()
    ts = IN_WINDOW + timedelta(minutes=5)
    # in-zone, bullish body, but low == min(open, close) -- no lower wick at all.
    bar = m5(ts, 97.0, 99.0, 97.0, 99.0)
    stream.on_bar_close(bar, store)
    events = stream.step(store.as_of(ts + timedelta(minutes=1)))
    assert not any(e.kind == "reaction_seen" for e in events)


def test_bearish_body_does_not_qualify_as_r():
    store, stream = _engage_and_get_events()
    ts = IN_WINDOW + timedelta(minutes=5)
    # in-zone, has a lower wick, but close < open (bearish body).
    bar = m5(ts, 99.5, 99.8, 97.0, 99.0)
    stream.on_bar_close(bar, store)
    events = stream.step(store.as_of(ts + timedelta(minutes=1)))
    assert not any(e.kind == "reaction_seen" for e in events)


def test_not_in_zone_does_not_qualify_as_r():
    store, stream = _engage_and_get_events()
    ts = IN_WINDOW + timedelta(minutes=5)
    # bullish body, lower wick, but low(101) > fvg.top(100) -- never entered the zone.
    bar = m5(ts, 101.5, 102.0, 101.0, 101.8)
    stream.on_bar_close(bar, store)
    events = stream.step(store.as_of(ts + timedelta(minutes=1)))
    assert not any(e.kind == "reaction_seen" for e in events)


def test_valid_r_candle_qualifies():
    store, stream = _engage_and_get_events()
    ts = IN_WINDOW + timedelta(minutes=5)
    # in-zone (low=97<=100), bullish body (99.5>99), lower wick (97<99).
    bar = m5(ts, 99.0, 99.8, 97.0, 99.5)
    stream.on_bar_close(bar, store)
    events = stream.step(store.as_of(ts + timedelta(minutes=1)))
    assert any(e.kind == "reaction_seen" for e in events)
