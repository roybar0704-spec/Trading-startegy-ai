"""AT-3.2 R replacement + reset: a new qualifying R replaces the old one; a Close-Through
below R.low resets to ZONE_ENGAGED (D-053 doc-hygiene note: the trigger_spec diagram's
arrow to SCANNING is a drafting slip -- this exact wording is the authoritative AT).
"""

from datetime import timedelta

from src.entry.setup_stream import SetupStream
from tests.fixtures.setup_stream import IN_WINDOW, m1, m5, seed_store

TOP, BOTTOM = 100.0, 95.0


def _engaged_stream():
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()
    stream.on_bar_close(m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    stream.step(store.as_of(IN_WINDOW + timedelta(minutes=1)))
    return store, stream


def test_later_qualifying_r_replaces_earlier_one():
    store, stream = _engaged_stream()
    ts1 = IN_WINDOW + timedelta(minutes=5)
    stream.on_bar_close(m5(ts1, 99.0, 99.8, 97.0, 99.5), store)  # R1, low=97
    stream.step(store.as_of(ts1 + timedelta(minutes=1)))

    ts2 = ts1 + timedelta(minutes=5)
    # Also qualifies as R (in-zone, bullish body, lower wick) but doesn't undercut R1.low
    # (97.5 > 97.0) -- must not be mistaken for an S candle against R1.
    stream.on_bar_close(m5(ts2, 99.2, 99.6, 97.5, 99.4), store)
    stream.step(store.as_of(ts2 + timedelta(minutes=1)))

    [setup] = stream.active_setups()
    assert setup.r_bar.l == 97.5  # replaced, not the original 97.0
    assert setup.state == "REACTION_SEEN"


def test_close_through_below_r_low_resets_to_zone_engaged():
    store, stream = _engaged_stream()
    ts1 = IN_WINDOW + timedelta(minutes=5)
    stream.on_bar_close(m5(ts1, 99.0, 99.8, 97.0, 99.5), store)  # R, low=97
    stream.step(store.as_of(ts1 + timedelta(minutes=1)))

    ts2 = ts1 + timedelta(minutes=5)
    # closes below R.low(97) without qualifying as S (close < pool, not > pool).
    stream.on_bar_close(m5(ts2, 97.5, 97.6, 96.0, 96.5), store)
    stream.step(store.as_of(ts2 + timedelta(minutes=1)))

    [setup] = stream.active_setups()
    assert setup.state == "ZONE_ENGAGED"
    assert setup.r_bar is None
