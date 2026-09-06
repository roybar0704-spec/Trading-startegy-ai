"""Differential/regression tests for D-095: bisect-based ``MarketContext.bias()`` lookup.

These test the *internal* algorithm swap only (linear scan over ``_bias_events`` ->
``StateStore._bias_state_as_of``, a bisect lookup). The behavioral contract itself
(point-in-time correctness, transition-table semantics) is already covered by
``tests/test_at1_3_bias_transitions.py``, deliberately left unmodified -- it must
keep passing unchanged as the primary regression gate.
"""

import random
from datetime import UTC, datetime, timedelta

import pytest

from src.store.state_store import BiasEvent, StateStore, _OutOfOrderIndexWrite

_BASE = datetime(2024, 1, 10, 9, 0, tzinfo=UTC)


def _linear_scan_reference(events: list[BiasEvent], ts: datetime) -> str:
    """Independent reference implementation -- the exact pre-D-095 logic,
    reimplemented here (not imported) so a bug in the production bisect path
    can't accidentally match a bug in a shared helper."""
    visible = [e for e in events if e.ts <= ts]
    return visible[-1].state if visible else "neutral"


def test_bias_empty_history_is_neutral():
    store = StateStore()
    assert store.as_of(_BASE).bias() == "neutral"


def test_bias_one_event_before_now():
    store = StateStore()
    store.put(BiasEvent(ts=_BASE, state="bullish", trigger_bos=None))
    assert store.as_of(_BASE + timedelta(hours=1)).bias() == "bullish"


def test_bias_one_event_exactly_equal_to_now():
    store = StateStore()
    store.put(BiasEvent(ts=_BASE, state="bullish", trigger_bos=None))
    assert store.as_of(_BASE).bias() == "bullish"


def test_bias_future_event_excluded():
    store = StateStore()
    store.put(BiasEvent(ts=_BASE + timedelta(hours=4), state="bullish", trigger_bos=None))
    assert store.as_of(_BASE).bias() == "neutral"


def test_bias_no_qualifying_event_is_neutral():
    store = StateStore()
    store.put(BiasEvent(ts=_BASE + timedelta(hours=4), state="bearish", trigger_bos=None))
    assert store.as_of(_BASE).bias() == "neutral"


def test_bias_multiple_chronological_events():
    store = StateStore()
    events = [
        BiasEvent(ts=_BASE, state="bullish", trigger_bos=None),
        BiasEvent(ts=_BASE + timedelta(hours=4), state="bearish", trigger_bos=None),
        BiasEvent(ts=_BASE + timedelta(hours=8), state="bullish", trigger_bos=None),
    ]
    for e in events:
        store.put(e)
    assert store.as_of(_BASE - timedelta(minutes=1)).bias() == "neutral"
    assert store.as_of(_BASE).bias() == "bullish"
    assert store.as_of(_BASE + timedelta(hours=2)).bias() == "bullish"
    assert store.as_of(_BASE + timedelta(hours=4)).bias() == "bearish"
    assert store.as_of(_BASE + timedelta(hours=6)).bias() == "bearish"
    assert store.as_of(_BASE + timedelta(hours=8)).bias() == "bullish"
    assert store.as_of(_BASE + timedelta(hours=100)).bias() == "bullish"


def test_bias_duplicate_timestamps_last_appended_wins():
    """Two transitions recorded at the exact same ts (e.g. two BOS events resolving
    at the same bar close) -- the last one put() must win, matching the pre-D-095
    linear scan's visible[-1] semantics exactly."""
    store = StateStore()
    store.put(BiasEvent(ts=_BASE, state="bullish", trigger_bos=None))
    store.put(BiasEvent(ts=_BASE, state="bearish", trigger_bos=None))
    store.put(BiasEvent(ts=_BASE, state="neutral", trigger_bos=None))
    assert store.as_of(_BASE).bias() == "neutral"
    assert store.as_of(_BASE + timedelta(seconds=1)).bias() == "neutral"


def test_bias_equal_timestamp_writes_accepted_not_rejected():
    """The out-of-order guard must accept obj.ts == last-recorded ts (only strictly
    LESS-than is rejected), since equal-ts writes are a legitimate, tested scenario
    above -- not treated as an ordering violation."""
    store = StateStore()
    store.put(BiasEvent(ts=_BASE, state="bullish", trigger_bos=None))
    store.put(BiasEvent(ts=_BASE, state="bearish", trigger_bos=None))  # must not raise
    assert store.as_of(_BASE).bias() == "bearish"


def test_bias_out_of_order_write_raises():
    store = StateStore()
    store.put(BiasEvent(ts=_BASE, state="bullish", trigger_bos=None))
    with pytest.raises(_OutOfOrderIndexWrite):
        store.put(BiasEvent(ts=_BASE - timedelta(seconds=1), state="bearish", trigger_bos=None))


def test_bias_large_n_exercises_indexed_lookup():
    """1,001 chronological transitions (alternating states), far more than any real
    9-month run's 4H-bar-bounded bias-event count -- exercises the bisect path over
    a non-trivial N, sampled every 37th event (plus a +1min offset each) against
    the reference; the smaller tests above already cover every boundary type
    exhaustively at low N."""
    store = StateStore()
    events: list[BiasEvent] = []
    states = ["bullish", "bearish"]
    for i in range(1001):
        ts = _BASE + timedelta(hours=4 * i)
        ev = BiasEvent(ts=ts, state=states[i % 2], trigger_bos=None)
        store.put(ev)
        events.append(ev)

    for i in range(0, 1001, 37):  # sample every 37th event's ts, plus offsets
        ts = events[i].ts
        assert store.as_of(ts).bias() == _linear_scan_reference(events, ts)
        assert store.as_of(ts + timedelta(minutes=1)).bias() == _linear_scan_reference(
            events, ts + timedelta(minutes=1)
        )
    assert store.as_of(events[-1].ts + timedelta(hours=1)).bias() == events[-1].state


def test_bias_randomized_differential_against_linear_scan():
    """Feed a randomized-but-chronological sequence of transitions (including some
    duplicate timestamps), then compare the indexed lookup against the independent
    linear-scan reference at many query points spanning before/at/between/after
    every event -- exact equality, not pytest.approx."""
    rng = random.Random(2026)
    store = StateStore()
    events: list[BiasEvent] = []
    ts = _BASE
    states = ["bullish", "bearish", "neutral"]
    for i in range(300):
        if rng.random() < 0.15:
            pass  # duplicate timestamp: don't advance ts this iteration
        else:
            ts = ts + timedelta(minutes=rng.randint(1, 240))
        ev = BiasEvent(ts=ts, state=states[i % 3], trigger_bos=None)
        store.put(ev)
        events.append(ev)

    query_points = [events[0].ts - timedelta(minutes=5)]
    for e in events:
        query_points.append(e.ts)
        query_points.append(e.ts + timedelta(seconds=30))
    query_points.append(events[-1].ts + timedelta(days=1))

    for q in query_points:
        assert store.as_of(q).bias() == _linear_scan_reference(events, q)


def test_bias_history_still_returns_fresh_independent_list():
    """bias_history() must be completely unchanged: same fresh-copy behavior, same
    return type, unaffected by the new indexed bias() lookup existing alongside it."""
    store = StateStore()
    store.put(BiasEvent(ts=_BASE, state="bullish", trigger_bos=None))

    history_1 = store.bias_history()
    history_2 = store.bias_history()
    assert history_1 == history_2
    assert history_1 is not history_2  # independent list objects each call

    history_1.append(BiasEvent(ts=_BASE + timedelta(hours=1), state="bearish", trigger_bos=None))
    assert len(store.bias_history()) == 1  # mutating the returned list must not affect the store
    assert store.as_of(_BASE + timedelta(hours=1)).bias() == "bullish"
