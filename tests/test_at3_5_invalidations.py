"""AT-3.5 Invalidations: Re-Inversion / S.low break / Mitigation-100% / Bias-flip ->
correct final state + (D-052) correct cascade to per-arm cleanup signal (post_arm flag).

Note: ``step()`` drops a Setup from active tracking the moment it dies (freeing its
fvg_id for same_zone_reentry), so tests grab the ``Setup`` reference (via
``active_setups()``) *before* the invalidating step and inspect that object afterward --
it isn't destroyed, just unlinked.
"""

from datetime import timedelta

from src.entry.setup_stream import SetupStream
from src.store.state_store import BiasEvent
from tests.fixtures.setup_stream import IN_WINDOW, m1, m5, seed_store

TOP, BOTTOM = 100.0, 95.0


def _sweep_confirmed_stream():
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()
    stream.on_bar_close(m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    stream.step(store.as_of(IN_WINDOW + timedelta(minutes=1)))
    r_ts = IN_WINDOW + timedelta(minutes=5)
    stream.on_bar_close(m5(r_ts, 99.0, 99.8, 97.0, 99.5), store)
    stream.step(store.as_of(r_ts + timedelta(minutes=1)))
    s_ts = IN_WINDOW + timedelta(minutes=10)
    stream.on_bar_close(m5(s_ts, 98.0, 98.5, 96.0, 97.5), store)  # S, low=96
    stream.step(store.as_of(s_ts + timedelta(minutes=1)))
    [setup] = stream.active_setups()
    assert setup.state == "AWAITING_IFVG"
    return store, stream, setup


def _armed_stream():
    store, stream, setup = _sweep_confirmed_stream()
    base = IN_WINDOW + timedelta(minutes=20)
    stream.on_bar_close(m1(base, 97.5, 97.6, 97.0, 97.3), store)
    stream.on_bar_close(m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0), store)
    stream.on_bar_close(m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3), store)
    inv_ts = base + timedelta(minutes=3)
    stream.on_bar_close(m1(inv_ts, 96.8, 97.3, 96.7, 97.2), store)
    stream.step(store.as_of(inv_ts + timedelta(minutes=1)))
    assert setup.state == "ARMED"
    return store, stream, setup, inv_ts


def test_s_low_break_before_arm_invalidates():
    store, stream, setup = _sweep_confirmed_stream()
    ts = IN_WINDOW + timedelta(minutes=15)
    # 1M bar dips below S.low (96) -- premise broken.
    stream.on_bar_close(m1(ts, 96.2, 96.3, 95.8, 96.0), store)
    events = stream.step(store.as_of(ts + timedelta(minutes=1)))
    assert any(e.kind == "invalidated" and not e.post_arm for e in events)
    assert setup.outcome == "invalidated"
    assert setup.outcome_reason == "s_low_break"


def test_re_inversion_after_arm_is_post_arm_only():
    store, stream, setup, inv_ts = _armed_stream()
    ts = inv_ts + timedelta(minutes=5)
    # closes back below the chosen iFVG's bottom (96.5) -- Re-Inversion.
    stream.on_bar_close(m1(ts, 96.7, 96.8, 96.3, 96.3), store)
    events = stream.step(store.as_of(ts + timedelta(minutes=1)))
    assert any(
        e.kind == "invalidated" and e.post_arm and e.reason == "re_inversion" for e in events
    )
    assert setup.outcome == "armed"  # unchanged -- model-agnostic story already over


def test_s_low_break_after_arm_is_post_arm_only():
    store, stream, setup, inv_ts = _armed_stream()
    ts = inv_ts + timedelta(minutes=5)
    stream.on_bar_close(m1(ts, 95.9, 96.0, 95.7, 95.8), store)  # below S.low(96)
    events = stream.step(store.as_of(ts + timedelta(minutes=1)))
    assert any(e.kind == "invalidated" and e.post_arm and e.reason == "s_low_break" for e in events)
    assert setup.outcome == "armed"


def test_mitigation_100_invalidates():
    store, stream, setup = _sweep_confirmed_stream()
    mit_ts = IN_WINDOW + timedelta(minutes=15)
    store.invalidate("FVG-H4-1", mit_ts)  # simulates FVGEngine marking 100% mitigation
    events = stream.step(store.as_of(mit_ts + timedelta(minutes=1)))
    assert any(e.kind == "invalidated" and e.reason == "mitigation_100" for e in events)
    assert setup.outcome == "invalidated"


def test_bias_flip_invalidates():
    store, stream, setup = _sweep_confirmed_stream()
    flip_ts = IN_WINDOW + timedelta(minutes=15)
    store.put(BiasEvent(ts=flip_ts, state="bearish", trigger_bos=None))
    events = stream.step(store.as_of(flip_ts + timedelta(minutes=1)))
    assert any(e.kind == "invalidated" and e.reason == "bias_flip" for e in events)
    assert setup.outcome == "invalidated"
