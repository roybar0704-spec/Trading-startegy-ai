"""AT-3.4 iFVG: Inversion on close only (Wick-through=nothing); not counted before S closes;
first inversion wins; multi-gap in one bar -> highest top.
"""

from datetime import timedelta

from src.entry.setup_stream import SetupStream
from tests.fixtures.setup_stream import IN_WINDOW, m1, m5, seed_store

TOP, BOTTOM = 100.0, 95.0


def _awaiting_ifvg_stream(s_close_ts):
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()
    stream.on_bar_close(m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    stream.step(store.as_of(IN_WINDOW + timedelta(minutes=1)))
    r_ts = IN_WINDOW + timedelta(minutes=5)
    stream.on_bar_close(m5(r_ts, 99.0, 99.8, 97.0, 99.5), store)
    stream.step(store.as_of(r_ts + timedelta(minutes=1)))
    stream.on_bar_close(m5(s_close_ts, 98.0, 98.5, 96.0, 97.5), store)  # S
    stream.step(store.as_of(s_close_ts + timedelta(minutes=1)))
    [candidate] = stream._active.values()
    assert candidate.setup.state == "AWAITING_IFVG"
    return store, stream


def test_wick_through_top_does_not_invert():
    store, stream = _awaiting_ifvg_stream(IN_WINDOW + timedelta(minutes=10))
    base = IN_WINDOW + timedelta(minutes=20)
    # candidate gap: c1.l=97.0 > c3.h=96.5 -> [96.5, 97.0]
    stream.on_bar_close(m1(base, 97.5, 97.6, 97.0, 97.3), store)  # c1
    stream.on_bar_close(m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0), store)  # c2
    stream.on_bar_close(m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3), store)  # c3
    # wick pokes above 97.0 but CLOSES back below -- must not count as Inversion.
    wick_ts = base + timedelta(minutes=3)
    stream.on_bar_close(m1(wick_ts, 96.5, 97.4, 96.4, 96.8), store)
    events = stream.step(store.as_of(wick_ts + timedelta(minutes=1)))
    assert not any(e.kind == "armed" for e in events)
    [candidate] = stream._active.values()
    assert candidate.setup.state == "AWAITING_IFVG"


def test_inversion_before_s_close_is_not_counted():
    # S closes at +30min; iFVG candidate forms and inverts at +10..+13min -- before S closed.
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()
    stream.on_bar_close(m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    stream.step(store.as_of(IN_WINDOW + timedelta(minutes=1)))
    r_ts = IN_WINDOW + timedelta(minutes=5)
    stream.on_bar_close(m5(r_ts, 99.0, 99.8, 97.0, 99.5), store)
    stream.step(store.as_of(r_ts + timedelta(minutes=1)))

    base = IN_WINDOW + timedelta(minutes=10)  # while still REACTION_SEEN (S not yet closed)
    stream.on_bar_close(m1(base, 97.5, 97.6, 97.0, 97.3), store)  # c1
    stream.on_bar_close(m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0), store)  # c2
    stream.on_bar_close(m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3), store)  # c3
    inv_ts = base + timedelta(minutes=3)
    stream.on_bar_close(m1(inv_ts, 96.8, 97.3, 96.7, 97.2), store)  # closes > top -> inverted

    s_ts = IN_WINDOW + timedelta(minutes=30)
    stream.on_bar_close(m5(s_ts, 98.0, 98.5, 96.0, 97.5), store)  # S closes after inversion
    events = stream.step(store.as_of(s_ts + timedelta(minutes=1)))
    assert not any(e.kind == "armed" for e in events)  # that gap was already used up

    [candidate] = stream._active.values()
    assert candidate.setup.state == "AWAITING_IFVG"  # never armed


def test_first_inversion_after_s_close_arms():
    store, stream = _awaiting_ifvg_stream(IN_WINDOW + timedelta(minutes=10))
    base = IN_WINDOW + timedelta(minutes=20)
    stream.on_bar_close(m1(base, 97.5, 97.6, 97.0, 97.3), store)  # c1
    stream.on_bar_close(m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0), store)  # c2
    stream.on_bar_close(m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3), store)  # c3
    inv_ts = base + timedelta(minutes=3)
    stream.on_bar_close(m1(inv_ts, 96.8, 97.3, 96.7, 97.2), store)
    events = stream.step(store.as_of(inv_ts + timedelta(minutes=1)))
    assert any(e.kind == "armed" for e in events)
    [candidate] = stream._active.values()
    assert candidate.setup.state == "ARMED"
    assert candidate.setup.ifvg.top == 97.0
    assert candidate.setup.ifvg.bottom == 96.5


def test_multi_gap_inversion_same_bar_picks_highest_top():
    store, stream = _awaiting_ifvg_stream(IN_WINDOW + timedelta(minutes=10))
    base = IN_WINDOW + timedelta(minutes=20)
    # Gap A: c1.l=97.0 > c3.h=96.5 -> top=97.0
    stream.on_bar_close(m1(base, 97.5, 97.6, 97.0, 97.3), store)
    stream.on_bar_close(m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0), store)
    stream.on_bar_close(m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3), store)  # gap A
    # Gap B, formed later, lower top: c1.l=96.9 > c3.h=96.6 -> top=96.9
    t2 = base + timedelta(minutes=3)
    stream.on_bar_close(m1(t2, 96.9, 97.0, 96.9, 97.0), store)  # c1 for gap B (low=96.9)
    stream.on_bar_close(m1(t2 + timedelta(minutes=1), 96.8, 96.85, 96.7, 96.8), store)  # c2
    stream.on_bar_close(m1(t2 + timedelta(minutes=2), 96.6, 96.6, 96.5, 96.55), store)  # c3
    # One bar closes above BOTH gap tops (97.0 and 96.9) -> highest top (97.0) wins.
    inv_ts = t2 + timedelta(minutes=3)
    stream.on_bar_close(m1(inv_ts, 96.8, 97.5, 96.7, 97.3), store)
    events = stream.step(store.as_of(inv_ts + timedelta(minutes=1)))
    assert any(e.kind == "armed" for e in events)
    [candidate] = stream._active.values()
    assert candidate.setup.ifvg.top == 97.0
