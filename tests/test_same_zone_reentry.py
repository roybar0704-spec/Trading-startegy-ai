"""SPEC S10 same_zone_reentry: a second Setup engaging the same 4H FVG after the first
one terminates must be tagged; a first-ever engagement, and one on a *different* zone,
must not be. Found with zero test coverage during the Phase 3 Critical Review despite
being SPEC-mandated and already implemented (_ever_engaged_fvg_ids tracking).
"""

from datetime import timedelta

from src.core.types import FVG, TF
from src.entry.setup_stream import SetupStream
from src.store.state_store import BiasEvent
from tests.fixtures.setup_stream import IN_WINDOW, m1, seed_store

TOP, BOTTOM = 100.0, 95.0


def test_first_engagement_is_not_tagged_reentry():
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()
    stream.on_bar_close(m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    stream.step(store.as_of(IN_WINDOW + timedelta(minutes=1)))
    [setup] = stream.active_setups()
    assert setup.same_zone_reentry is False


def test_second_engagement_of_same_zone_after_invalidation_is_tagged():
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()

    stream.on_bar_close(m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    stream.step(store.as_of(IN_WINDOW + timedelta(minutes=1)))
    [first] = stream.active_setups()
    assert first.same_zone_reentry is False

    # Mitigate the FVG to terminate the first Setup, then un-mitigate (a fresh FVG version
    # with mitigation reset) and re-touch it -- simulating a stop-out and a later re-test
    # of the same structural zone, which the model-agnostic Setup Stream can still see
    # because it re-checks store.as_of() fresh each time.
    mit_ts = IN_WINDOW + timedelta(minutes=2)
    store.invalidate("FVG-H4-1", mit_ts)
    events = stream.step(store.as_of(mit_ts + timedelta(minutes=1)))
    assert any(e.kind == "invalidated" for e in events)
    assert not stream.active_setups()

    reentry_ts = IN_WINDOW + timedelta(minutes=5)
    store.put(
        FVG(
            id="FVG-H4-1", tf=TF.H4, direction="bull", top=TOP, bottom=BOTTOM, level=1,
            created_at=reentry_ts, confirmed_at=reentry_ts, mitigation_pct=0.0,
            invalidated_at=None, bos_link=None, displacement=False,
        )
    )
    store.put(BiasEvent(ts=reentry_ts, state="bullish", trigger_bos=None))
    stream.on_bar_close(m1(reentry_ts, 100.5, 100.6, 99.5, 100.2), store)
    events = stream.step(store.as_of(reentry_ts + timedelta(minutes=1)))
    assert any(e.kind == "engaged" for e in events)
    [second] = stream.active_setups()
    assert second.same_zone_reentry is True


def test_engagement_of_a_different_zone_is_not_tagged():
    store = seed_store("long", TOP, BOTTOM, fvg_id="FVG-H4-1")
    stream = SetupStream()
    stream.on_bar_close(m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    stream.step(store.as_of(IN_WINDOW + timedelta(minutes=1)))

    store.put(
        FVG(
            id="FVG-H4-2", tf=TF.H4, direction="bull", top=90.0, bottom=85.0, level=1,
            created_at=IN_WINDOW, confirmed_at=IN_WINDOW, mitigation_pct=0.0,
            invalidated_at=None, bos_link=None, displacement=False,
        )
    )
    ts2 = IN_WINDOW + timedelta(minutes=1)
    stream.on_bar_close(m1(ts2, 90.5, 90.6, 89.5, 90.2), store)
    stream.step(store.as_of(ts2 + timedelta(minutes=1)))

    setups = {s.fvg_id: s for s in stream.active_setups()}
    assert setups["FVG-H4-2"].same_zone_reentry is False
