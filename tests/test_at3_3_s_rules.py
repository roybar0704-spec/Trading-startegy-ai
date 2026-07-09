"""AT-3.3 S rules: low<R.low without close>R.low -> not a Sweep; both -> SWEEP_CONFIRMED."""

from datetime import timedelta

from src.entry.setup_stream import SetupStream
from tests.fixtures.setup_stream import IN_WINDOW, m1, m5, seed_store

TOP, BOTTOM = 100.0, 95.0


def _reaction_seen_stream():
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()
    stream.on_bar_close(m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    stream.step(store.as_of(IN_WINDOW + timedelta(minutes=1)))
    ts = IN_WINDOW + timedelta(minutes=5)
    stream.on_bar_close(m5(ts, 99.0, 99.8, 97.0, 99.5), store)  # R, low=97
    stream.step(store.as_of(ts + timedelta(minutes=1)))
    return store, stream


def test_undercut_without_close_back_above_is_not_a_sweep():
    store, stream = _reaction_seen_stream()
    ts = IN_WINDOW + timedelta(minutes=10)
    # low(96) < R.low(97), but close(96.5) also < 97 -- this is Close-Through, not Sweep.
    stream.on_bar_close(m5(ts, 97.2, 97.3, 96.0, 96.5), store)
    stream.step(store.as_of(ts + timedelta(minutes=1)))
    [candidate] = stream._active.values()
    assert candidate.setup.state == "ZONE_ENGAGED"  # reset, not SWEEP_CONFIRMED


def test_undercut_with_close_back_above_confirms_sweep():
    store, stream = _reaction_seen_stream()
    ts = IN_WINDOW + timedelta(minutes=10)
    # low(96) < R.low(97) and close(97.5) > 97 -- qualifies as S.
    stream.on_bar_close(m5(ts, 98.0, 98.5, 96.0, 97.5), store)
    events = stream.step(store.as_of(ts + timedelta(minutes=1)))
    assert any(e.kind == "sweep_confirmed" for e in events)
    [candidate] = stream._active.values()
    assert candidate.setup.state == "AWAITING_IFVG"
    assert candidate.setup.s_bar.l == 96.0
