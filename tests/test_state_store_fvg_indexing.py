"""D-093 (perf): equivalence proof for StateStore's FVG confirm/invalidate
indexes -- MarketContext.active_fvgs()/StateStore.fvgs_as_of() must return
byte-identical results (including exact iteration order) to the pre-D-093
full-scan algorithm, for every access pattern including retroactive/as-of
queries (the D-041/AT-1.6 concern) and out-of-order writes (must fail loud,
never silently sorted/coerced).

The pre-D-093 algorithm is reproduced verbatim below as `_naive_*` reference
functions -- the behavioral oracle this whole file measures against. These
functions are never touched/optimized; they exist only as ground truth.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from src.core.types import TF, Bar
from src.store.state_store import StateStore, _OutOfOrderIndexWrite
from tests.fixtures.bars import make_bars
from tests.fixtures.pipeline import run_pipeline

START = datetime(2024, 1, 1, tzinfo=UTC)


# ============================================================================
# Naive reference oracle -- verbatim copy of the pre-D-093 algorithm.
# ============================================================================


def _fvg_effective_ts(fvg):
    return fvg.invalidated_at if fvg.invalidated_at is not None else fvg.confirmed_at


def _naive_fvgs_as_of(store: StateStore, ts: datetime, tf: TF | None = None) -> list:
    result = []
    for versions in store._fvg_versions.values():
        visible = [v for v in versions if _fvg_effective_ts(v) <= ts]
        if visible and (tf is None or visible[-1].tf is tf):
            result.append(visible[-1])
    return result


def _naive_active_fvgs(store: StateStore, ts: datetime, tf: TF, direction: str) -> list:
    return [
        f
        for f in _naive_fvgs_as_of(store, ts, tf)
        if f.direction == direction
        and f.confirmed_at <= ts
        and (f.invalidated_at is None or f.invalidated_at > ts)
    ]


# ============================================================================
# FVG construction helper
# ============================================================================


def _fvg(id_, tf, direction, top, bottom, confirmed_at, level=1, mitigation_pct=0.0,
         invalidated_at=None, displacement=False, bos_link=None, created_at=None):
    from src.core.types import FVG

    return FVG(
        id=id_, tf=tf, direction=direction, top=top, bottom=bottom, level=level,
        created_at=created_at or confirmed_at, confirmed_at=confirmed_at,
        mitigation_pct=mitigation_pct, invalidated_at=invalidated_at,
        bos_link=bos_link, displacement=displacement,
    )


def _dt(minutes: int) -> datetime:
    return START + timedelta(minutes=minutes)


# ============================================================================
# 1. Old-vs-new equivalence: many ids, many versions per id, both directions,
#    both tfs, systematic + boundary ts sweep.
# ============================================================================


def _build_multi_version_store() -> StateStore:
    """Many FVG ids, several with multiple mitigation-style versions, mixed
    directions/tfs, some invalidated, some not -- built via put() only, in
    chronological order (the real engines' own write pattern)."""
    store = StateStore()
    specs = [
        # (id, tf, direction, confirmed_at_minute,
        #  versions: list of (ts_minute, mitigation_pct, invalidated))
        (
            "FVG-A", TF.H4, "bull", 0,
            [(0, 0.0, False), (10, 25.0, False), (20, 60.0, False), (30, 100.0, True)],
        ),
        ("FVG-B", TF.H4, "bear", 5, [(5, 0.0, False)]),
        ("FVG-C", TF.H4, "bull", 8, [(8, 0.0, False), (40, 100.0, True)]),
        ("FVG-D", TF.M1, "bull", 2, [(2, 0.0, False), (15, 50.0, False)]),
        ("FVG-E", TF.M1, "bear", 12, [(12, 0.0, False), (18, 30.0, False), (60, 100.0, True)]),
        ("FVG-F", TF.H4, "bear", 25, [(25, 0.0, False)]),
    ]
    for fvg_id, tf, direction, confirmed_min, versions in specs:
        confirmed_at = _dt(confirmed_min)
        for ts_min, pct, invalidated in versions:
            ts = _dt(ts_min)
            inv_at = ts if invalidated else None
            store.put(
                _fvg(fvg_id, tf, direction, 100.0, 90.0, confirmed_at,
                     mitigation_pct=pct, invalidated_at=inv_at)
            )
    return store


@pytest.mark.parametrize("tf", [TF.H4, TF.M1])
@pytest.mark.parametrize("direction", ["bull", "bear"])
def test_active_fvgs_matches_naive_across_ts_sweep(tf, direction):
    store = _build_multi_version_store()
    for minute in range(-5, 70):
        ts = _dt(minute)
        expected = _naive_active_fvgs(store, ts, tf, direction)
        actual = store._active_fvgs_indexed(ts, tf, direction)
        assert actual == expected, f"mismatch at ts={ts.isoformat()} tf={tf} dir={direction}"


@pytest.mark.parametrize("tf", [TF.H4, TF.M1])
def test_fvgs_as_of_matches_naive_across_ts_sweep(tf):
    store = _build_multi_version_store()
    for minute in range(-5, 70):
        ts = _dt(minute)
        expected = _naive_fvgs_as_of(store, ts, tf)
        actual = store.fvgs_as_of(ts, tf)
        assert actual == expected, f"mismatch at ts={ts.isoformat()} tf={tf}"


def test_fvgs_as_of_tf_none_falls_back_to_full_scan_and_matches_naive():
    store = _build_multi_version_store()
    for minute in (-1, 0, 9, 26, 41, 61, 100):
        ts = _dt(minute)
        assert store.fvgs_as_of(ts, tf=None) == _naive_fvgs_as_of(store, ts, tf=None)


# ============================================================================
# 2. Retroactive / as-of queries -- the D-041/AT-1.6 concern directly.
# ============================================================================


def test_retroactive_query_after_later_writes_matches_naive():
    """Write straight through to a LATE ts, then query an EARLIER ts on the
    same, already-fully-written store -- exactly AT-1.6's own access pattern
    (test_at1_6_prefix_consistency.py: `_snapshot(full_store, ts)` re-queried
    at every earlier bar boundary of an already-fully-processed store)."""
    store = _build_multi_version_store()  # already fully written through minute 60
    for minute in (0, 3, 9, 15, 22, 29, 35, 50):
        ts = _dt(minute)
        for tf in (TF.H4, TF.M1):
            for direction in ("bull", "bear"):
                assert store._active_fvgs_indexed(ts, tf, direction) == _naive_active_fvgs(
                    store, ts, tf, direction
                )
            assert store.fvgs_as_of(ts, tf) == _naive_fvgs_as_of(store, ts, tf)


def test_retroactive_query_before_any_confirmation():
    store = _build_multi_version_store()
    ts = START - timedelta(minutes=100)
    assert store._active_fvgs_indexed(ts, TF.H4, "bull") == []
    assert store.fvgs_as_of(ts, TF.H4) == []


# ============================================================================
# 3. Invalidation permanence
# ============================================================================


def test_invalidated_fvg_never_reappears_in_active_fvgs_for_any_later_ts():
    store = StateStore()
    confirmed_at = _dt(0)
    store.put(_fvg("FVG-X", TF.H4, "bull", 100.0, 90.0, confirmed_at))
    invalidated_at = _dt(10)
    store.put(_fvg("FVG-X", TF.H4, "bull", 100.0, 90.0, confirmed_at, mitigation_pct=100.0,
                    invalidated_at=invalidated_at))
    for minute in range(10, 100, 5):
        ts = _dt(minute)
        assert store._active_fvgs_indexed(ts, TF.H4, "bull") == []
        # but fvgs_as_of must still surface the (invalidated) version -- unchanged contract
        assert store.fvgs_as_of(ts, TF.H4) == [store._fvg_versions["FVG-X"][-1]]


def test_active_fvgs_before_invalidation_still_shows_it():
    store = StateStore()
    confirmed_at = _dt(0)
    store.put(_fvg("FVG-X", TF.H4, "bull", 100.0, 90.0, confirmed_at))
    invalidated_at = _dt(10)
    store.put(_fvg("FVG-X", TF.H4, "bull", 100.0, 90.0, confirmed_at, mitigation_pct=100.0,
                    invalidated_at=invalidated_at))
    ts = _dt(5)  # before invalidation
    result = store._active_fvgs_indexed(ts, TF.H4, "bull")
    assert len(result) == 1
    assert result[0].id == "FVG-X"
    assert result[0].invalidated_at is None  # the pre-invalidation version


# ============================================================================
# 4. Direction/timeframe filtering, isolated (previously-untested gap)
# ============================================================================


def test_direction_filtering_isolated():
    store = StateStore()
    store.put(_fvg("FVG-BULL", TF.H4, "bull", 100.0, 90.0, _dt(0)))
    store.put(_fvg("FVG-BEAR", TF.H4, "bear", 100.0, 90.0, _dt(0)))
    ts = _dt(5)
    bulls = store._active_fvgs_indexed(ts, TF.H4, "bull")
    bears = store._active_fvgs_indexed(ts, TF.H4, "bear")
    assert [f.id for f in bulls] == ["FVG-BULL"]
    assert [f.id for f in bears] == ["FVG-BEAR"]


def test_tf_filtering_isolated():
    store = StateStore()
    store.put(_fvg("FVG-H4", TF.H4, "bull", 100.0, 90.0, _dt(0)))
    store.put(_fvg("FVG-M1", TF.M1, "bull", 100.0, 90.0, _dt(0)))
    ts = _dt(5)
    h4 = store._active_fvgs_indexed(ts, TF.H4, "bull")
    m1 = store._active_fvgs_indexed(ts, TF.M1, "bull")
    assert [f.id for f in h4] == ["FVG-H4"]
    assert [f.id for f in m1] == ["FVG-M1"]


# ============================================================================
# 5. Exact iteration order -- the highest-priority invariant (constraint #5).
# ============================================================================


def test_active_fvgs_order_matches_naive_exactly_not_just_as_a_set():
    """SetupStream engages the FIRST qualifying FVG (setup_stream.py
    _on_1m_close: `for fvg in ctx_now.active_fvgs(...): ... if touched: ...`)
    -- order, not just set membership, must match the pre-D-093 algorithm."""
    store = StateStore()
    # Deliberately confirm in a specific, non-alphabetical creation order.
    order = ["FVG-3", "FVG-1", "FVG-4", "FVG-2", "FVG-5"]
    for i, fvg_id in enumerate(order):
        store.put(_fvg(fvg_id, TF.H4, "bull", 100.0, 90.0, _dt(i)))
    ts = _dt(100)
    naive_order = [f.id for f in _naive_active_fvgs(store, ts, TF.H4, "bull")]
    new_order = [f.id for f in store._active_fvgs_indexed(ts, TF.H4, "bull")]
    assert new_order == naive_order == order


def test_active_fvgs_order_preserved_when_some_ids_invalidated():
    store = StateStore()
    order = ["FVG-3", "FVG-1", "FVG-4", "FVG-2", "FVG-5"]
    for i, fvg_id in enumerate(order):
        store.put(_fvg(fvg_id, TF.H4, "bull", 100.0, 90.0, _dt(i)))
    # Invalidate the 2nd and 4th (by creation order) -- FVG-1 and FVG-2.
    store.put(_fvg("FVG-1", TF.H4, "bull", 100.0, 90.0, _dt(1), mitigation_pct=100.0,
                    invalidated_at=_dt(50)))
    store.put(_fvg("FVG-2", TF.H4, "bull", 100.0, 90.0, _dt(3), mitigation_pct=100.0,
                    invalidated_at=_dt(51)))
    ts = _dt(100)
    naive_order = [f.id for f in _naive_active_fvgs(store, ts, TF.H4, "bull")]
    new_order = [f.id for f in store._active_fvgs_indexed(ts, TF.H4, "bull")]
    expected = ["FVG-3", "FVG-4", "FVG-5"]  # order preserved, invalidated ones removed
    assert new_order == naive_order == expected


def test_fvgs_as_of_order_matches_naive_exactly():
    store = _build_multi_version_store()
    ts = _dt(65)
    assert [f.id for f in store.fvgs_as_of(ts, TF.H4)] == [
        f.id for f in _naive_fvgs_as_of(store, ts, TF.H4)
    ]


# ============================================================================
# 5b. Same-ID reentry (D-093 v2 fix): confirm -> invalidate -> reconfirm ->
#     invalidate -> ... for the SAME id -- the exact case test_same_zone_
#     reentry.py exercises via the real StateStore public API.
# ============================================================================


def test_single_reentry_cycle_matches_naive_at_every_stage():
    """confirm(T0) -> invalidate(T1) -> reconfirm(T2), queried before T0,
    in [T0,T1), in [T1,T2), and >= T2 -- must match the naive oracle at
    every stage, both fvgs_as_of and active_fvgs."""
    store = StateStore()
    t0, t1, t2 = _dt(0), _dt(10), _dt(20)
    store.put(_fvg("FVG-R", TF.H4, "bull", 100.0, 90.0, t0))
    store.invalidate("FVG-R", t1)
    store.put(_fvg("FVG-R", TF.H4, "bull", 100.0, 90.0, t2))  # reconfirm, invalidated_at=None

    for minute in range(-5, 30):
        ts = _dt(minute)
        assert store.fvgs_as_of(ts, TF.H4) == _naive_fvgs_as_of(store, ts, TF.H4), f"ts={ts}"
        assert store._active_fvgs_indexed(ts, TF.H4, "bull") == _naive_active_fvgs(
            store, ts, TF.H4, "bull"
        ), f"ts={ts}"

    # Explicit stage checks, not just equality-with-oracle (the oracle could
    # theoretically be wrong too, though it's unmodified and pre-existing).
    assert store._active_fvgs_indexed(_dt(-1), TF.H4, "bull") == []
    assert [f.id for f in store._active_fvgs_indexed(_dt(5), TF.H4, "bull")] == ["FVG-R"]
    assert store._active_fvgs_indexed(_dt(15), TF.H4, "bull") == []  # invalidated epoch
    # reactive
    assert [f.id for f in store._active_fvgs_indexed(_dt(25), TF.H4, "bull")] == ["FVG-R"]


def test_multiple_reentry_cycles_match_naive():
    """confirm -> invalidate -> reconfirm -> invalidate -> reconfirm ->
    invalidate: three full epochs for one id."""
    store = StateStore()
    boundaries = [_dt(m) for m in (0, 10, 20, 30, 40, 50)]
    t0, t1, t2, t3, t4, t5 = boundaries
    store.put(_fvg("FVG-R", TF.H4, "bull", 100.0, 90.0, t0))
    store.invalidate("FVG-R", t1)
    store.put(_fvg("FVG-R", TF.H4, "bull", 100.0, 90.0, t2))
    store.invalidate("FVG-R", t3)
    store.put(_fvg("FVG-R", TF.H4, "bull", 100.0, 90.0, t4))
    store.invalidate("FVG-R", t5)

    for minute in range(-5, 60):
        ts = _dt(minute)
        assert store.fvgs_as_of(ts, TF.H4) == _naive_fvgs_as_of(store, ts, TF.H4), f"ts={ts}"
        assert store._active_fvgs_indexed(ts, TF.H4, "bull") == _naive_active_fvgs(
            store, ts, TF.H4, "bull"
        ), f"ts={ts}"

    # active in [t0,t1), [t2,t3), [t4,t5); invalidated in [t1,t2), [t3,t4), [t5,inf)
    assert [f.id for f in store._active_fvgs_indexed(_dt(5), TF.H4, "bull")] == ["FVG-R"]
    assert store._active_fvgs_indexed(_dt(15), TF.H4, "bull") == []
    assert [f.id for f in store._active_fvgs_indexed(_dt(25), TF.H4, "bull")] == ["FVG-R"]
    assert store._active_fvgs_indexed(_dt(35), TF.H4, "bull") == []
    assert [f.id for f in store._active_fvgs_indexed(_dt(45), TF.H4, "bull")] == ["FVG-R"]
    assert store._active_fvgs_indexed(_dt(55), TF.H4, "bull") == []


def test_reentry_with_multiple_mitigation_style_versions_within_each_epoch():
    """Real mitigation.py-style repeated put()s (mitigation_pct climbing)
    WITHIN each active epoch, not just one put() per epoch."""
    store = StateStore()
    t0 = _dt(0)
    store.put(_fvg("FVG-R", TF.H4, "bull", 100.0, 90.0, t0, mitigation_pct=0.0))
    store.put(_fvg("FVG-R", TF.H4, "bull", 100.0, 90.0, t0, mitigation_pct=30.0))
    store.put(_fvg("FVG-R", TF.H4, "bull", 100.0, 90.0, t0, mitigation_pct=60.0))
    t_inv = _dt(10)
    store.invalidate("FVG-R", t_inv)  # 100% mitigation, terminal for epoch 1

    t_re = _dt(20)
    store.put(_fvg("FVG-R", TF.H4, "bull", 100.0, 90.0, t_re, mitigation_pct=0.0))
    store.put(_fvg("FVG-R", TF.H4, "bull", 100.0, 90.0, t_re, mitigation_pct=45.0))

    for minute in range(-2, 30):
        ts = _dt(minute)
        assert store.fvgs_as_of(ts, TF.H4) == _naive_fvgs_as_of(store, ts, TF.H4), f"ts={ts}"
        assert store._active_fvgs_indexed(ts, TF.H4, "bull") == _naive_active_fvgs(
            store, ts, TF.H4, "bull"
        ), f"ts={ts}"

    active_late = store._active_fvgs_indexed(_dt(25), TF.H4, "bull")
    assert len(active_late) == 1
    assert active_late[0].mitigation_pct == 45.0  # latest version of the reactivated epoch


def test_reentry_preserves_original_creation_order_position():
    """A reactivated id must reappear at its ORIGINAL creation-order slot
    among other, never-invalidated ids -- not moved to the end -- matching
    the oracle's dict-iteration-order semantics exactly."""
    store = StateStore()
    store.put(_fvg("FVG-1", TF.H4, "bull", 100.0, 90.0, _dt(0)))
    store.put(_fvg("FVG-2", TF.H4, "bull", 100.0, 90.0, _dt(1)))  # will be invalidated+reactivated
    store.put(_fvg("FVG-3", TF.H4, "bull", 100.0, 90.0, _dt(2)))
    store.invalidate("FVG-2", _dt(10))
    store.put(_fvg("FVG-2", TF.H4, "bull", 100.0, 90.0, _dt(20)))  # reconfirm

    ts = _dt(30)
    naive_order = [f.id for f in _naive_active_fvgs(store, ts, TF.H4, "bull")]
    new_order = [f.id for f in store._active_fvgs_indexed(ts, TF.H4, "bull")]
    assert new_order == naive_order == ["FVG-1", "FVG-2", "FVG-3"]


def test_randomized_equivalence_sweep_with_reentry_cycles():
    """Extends the base randomized sweep: some ids get MULTIPLE
    confirm/invalidate/reconfirm epochs, not just one-directional
    invalidation."""
    rng = random.Random(54321)
    for trial in range(50):
        store = StateStore()
        n_ids = rng.randint(1, 10)
        t = 0
        # (ts_min, fvg_id, tf, direction, is_reconfirm_epoch_start, mitigation_pct, invalidated)
        all_writes = []
        for i in range(n_ids):
            fvg_id = f"FVG-RR{trial}-{i}"
            tf = rng.choice([TF.H4, TF.M1])
            direction = rng.choice(["bull", "bear"])
            n_epochs = rng.randint(1, 3)
            for epoch in range(n_epochs):
                t += rng.randint(1, 4)
                confirmed_at = _dt(t)
                n_versions = rng.randint(1, 3)
                for v in range(n_versions):
                    t += rng.randint(1, 4)
                    will_invalidate = (v == n_versions - 1) and (
                        rng.random() < 0.7 or epoch < n_epochs - 1
                    )
                    pct = 100.0 if will_invalidate else rng.uniform(0, 90)
                    all_writes.append(
                        (t, fvg_id, tf, direction, confirmed_at, pct, will_invalidate)
                    )
                if not all_writes[-1][6]:
                    break  # this epoch never got invalidated -- no further epochs possible

        all_writes.sort(key=lambda w: w[0])
        for ts_min, fvg_id, tf, direction, confirmed_at, pct, invalidated in all_writes:
            ts = _dt(ts_min)
            inv_at = ts if invalidated else None
            store.put(_fvg(fvg_id, tf, direction, 100.0, 90.0, confirmed_at,
                            mitigation_pct=pct, invalidated_at=inv_at))

        max_t = max((w[0] for w in all_writes), default=0)
        for query_min in range(-2, max_t + 5, max(1, (max_t + 7) // 12)):
            ts = _dt(query_min)
            for tf in (TF.H4, TF.M1):
                assert store.fvgs_as_of(ts, tf) == _naive_fvgs_as_of(store, ts, tf), (
                    f"trial={trial} ts={ts} tf={tf}"
                )
                for direction in ("bull", "bear"):
                    assert store._active_fvgs_indexed(ts, tf, direction) == _naive_active_fvgs(
                        store, ts, tf, direction
                    ), f"trial={trial} ts={ts} tf={tf} dir={direction}"


# ============================================================================
# 6. Randomized equivalence sweep
# ============================================================================


def test_randomized_equivalence_sweep():
    rng = random.Random(12345)
    for trial in range(50):
        store = StateStore()
        n_ids = rng.randint(1, 15)
        t = 0
        specs = []
        for i in range(n_ids):
            t += rng.randint(1, 5)
            tf = rng.choice([TF.H4, TF.M1])
            direction = rng.choice(["bull", "bear"])
            confirmed_at = _dt(t)
            n_versions = rng.randint(1, 4)
            versions = []
            last_t = t
            for v in range(n_versions):
                last_t += rng.randint(1, 5)
                will_invalidate = (v == n_versions - 1) and rng.random() < 0.6
                versions.append(
                    (last_t, 100.0 if will_invalidate else rng.uniform(0, 90), will_invalidate)
                )
            specs.append((f"FVG-R{trial}-{i}", tf, direction, confirmed_at, versions))
            t = last_t

        # Apply in strict chronological write order across ALL ids (mirrors
        # real engines interleaving multiple FVGs' updates as bars close).
        all_writes = []
        for fvg_id, tf, direction, confirmed_at, versions in specs:
            for ts_min, pct, invalidated in versions:
                all_writes.append((ts_min, fvg_id, tf, direction, confirmed_at, pct, invalidated))
        all_writes.sort(key=lambda w: w[0])
        for ts_min, fvg_id, tf, direction, confirmed_at, pct, invalidated in all_writes:
            ts = _dt(ts_min)
            inv_at = ts if invalidated else None
            store.put(_fvg(fvg_id, tf, direction, 100.0, 90.0, confirmed_at,
                            mitigation_pct=pct, invalidated_at=inv_at))

        max_t = max(w[0] for w in all_writes) if all_writes else 0
        for query_min in range(-2, max_t + 5, max(1, (max_t + 7) // 10)):
            ts = _dt(query_min)
            for tf in (TF.H4, TF.M1):
                assert store.fvgs_as_of(ts, tf) == _naive_fvgs_as_of(store, ts, tf), (
                    f"trial={trial} ts={ts} tf={tf}"
                )
                for direction in ("bull", "bear"):
                    assert store._active_fvgs_indexed(ts, tf, direction) == _naive_active_fvgs(
                        store, ts, tf, direction
                    ), f"trial={trial} ts={ts} tf={tf} dir={direction}"


# ============================================================================
# 7. Write-order invariant must fail loud, never silently sort/coerce.
# ============================================================================


def test_out_of_order_confirmed_at_fails_loud():
    store = StateStore()
    store.put(_fvg("FVG-1", TF.H4, "bull", 100.0, 90.0, _dt(10)))
    with pytest.raises(_OutOfOrderIndexWrite):
        store.put(_fvg("FVG-2", TF.H4, "bull", 100.0, 90.0, _dt(5)))  # earlier than FVG-1


def test_double_invalidation_without_reconfirmation_fails_loud():
    """D-093 v2: invalidation is tracked per-id (an interval list), not a
    single shared cross-id-ordered structure -- cross-id invalidation
    timestamp ordering is not a correctness requirement (see the v2 design
    reassessment: _fvg_invalidated_at only ever consults one id's own
    interval list). What MUST still fail loud: invalidating the SAME id
    twice in a row with no intervening reconfirmation -- an impossible
    state given the was_invalidated_before guard at every real call site."""
    store = StateStore()
    store.put(_fvg("FVG-1", TF.H4, "bull", 100.0, 90.0, _dt(0)))
    store.invalidate("FVG-1", _dt(10))
    with pytest.raises(_OutOfOrderIndexWrite):
        # Bypass the was_invalidated_before guard directly to prove the
        # index itself still refuses this, not just the caller-side guard.
        store._open_invalidation_interval("FVG-1", _dt(20))


def test_reactivation_before_own_invalidation_fails_loud():
    """A reconfirmation ts earlier than the invalidation it supposedly
    reactivates from is nonsensical -- must fail loud, not silently
    coerced."""
    store = StateStore()
    store.put(_fvg("FVG-1", TF.H4, "bull", 100.0, 90.0, _dt(10)))
    store.invalidate("FVG-1", _dt(20))
    with pytest.raises(_OutOfOrderIndexWrite):
        store._close_invalidation_interval("FVG-1", _dt(15))  # before _dt(20)


def test_cross_id_invalidation_order_is_not_restricted():
    """Unlike the confirm index (a shared, cross-id-ordered structure that
    must stay chronological), invalidation is tracked independently per id
    -- two different ids may be invalidated in any relative order without
    raising, matching the oracle (_fvg_versions has no cross-id ordering
    relationship either)."""
    store = StateStore()
    store.put(_fvg("FVG-1", TF.H4, "bull", 100.0, 90.0, _dt(0)))
    store.put(_fvg("FVG-2", TF.H4, "bull", 100.0, 90.0, _dt(1)))
    store.invalidate("FVG-1", _dt(20))
    store.invalidate("FVG-2", _dt(10))  # earlier than FVG-1's invalidation -- must NOT raise
    assert store._fvg_invalidated_at("FVG-1", _dt(25))
    assert store._fvg_invalidated_at("FVG-2", _dt(25))


def test_equal_timestamps_are_allowed_not_treated_as_out_of_order():
    """Two different FVGs can legitimately confirm at the exact same instant
    (e.g. bull+bear on the same 4H bar close) -- must not raise."""
    store = StateStore()
    ts = _dt(10)
    store.put(_fvg("FVG-1", TF.H4, "bull", 100.0, 90.0, ts))
    store.put(_fvg("FVG-2", TF.H4, "bear", 100.0, 90.0, ts))  # same ts, must not raise
    result = store.fvgs_as_of(_dt(20), TF.H4)
    assert [f.id for f in result] == ["FVG-1", "FVG-2"]


def test_out_of_order_write_does_not_corrupt_source_of_truth():
    """Even when the index append fails loud, _fvg_versions (source of
    truth) already received the write -- confirm this doesn't leave the
    store in a state where source-of-truth and index silently disagree in
    a way that could be mistaken for correct."""
    store = StateStore()
    store.put(_fvg("FVG-1", TF.H4, "bull", 100.0, 90.0, _dt(10)))
    with pytest.raises(_OutOfOrderIndexWrite):
        store.put(_fvg("FVG-2", TF.H4, "bull", 100.0, 90.0, _dt(5)))
    # FVG-2 IS in _fvg_versions (put() appends before indexing) -- the raise
    # is a loud signal to the caller that the index is now untrustworthy for
    # FVG-2's tf, not a rollback. This is documented, intended behavior: the
    # invariant violation itself is the bug to fix upstream, not something
    # this store should paper over.
    assert "FVG-2" in store._fvg_versions


# ============================================================================
# 8. Full-pipeline equivalence via the existing real engines (structure+fvg),
#    reusing AT-1.6's own fixture-building helpers -- exercises put()/
#    invalidate() exactly as the real engines call them, not just this
#    file's hand-built scenarios.
# ============================================================================


def _generate_fixture(seed: int, n_bars: int) -> list[Bar]:
    rng = random.Random(seed)
    price = 2000.0
    ohlc = []
    for _ in range(n_bars):
        o = price
        c = o + rng.uniform(-3.0, 3.0)
        h = max(o, c) + rng.uniform(0.0, 1.5)
        low = min(o, c) - rng.uniform(0.0, 1.5)
        ohlc.append((o, h, low, c))
        price = c
    return make_bars(TF.H4, START, timedelta(hours=4), ohlc)


def _pipeline_snapshot(store: StateStore, ts: datetime) -> dict:
    ctx = store.as_of(ts)
    return {
        "fvgs_bull_ordered": [
            (f.id, f.top, f.bottom, f.level, f.mitigation_pct)
            for f in ctx.active_fvgs(TF.H4, "bull")
        ],
        "fvgs_bear_ordered": [
            (f.id, f.top, f.bottom, f.level, f.mitigation_pct)
            for f in ctx.active_fvgs(TF.H4, "bear")
        ],
    }


def test_real_pipeline_indexed_matches_naive_including_order():
    """Runs the REAL StructureEngine+FVGEngine pipeline (same helper AT-1.6
    itself uses) to build a StateStore through genuine put()/invalidate()
    call patterns, then compares the (already-optimized) real
    active_fvgs()/fvgs_as_of() against the naive reference -- at every bar
    boundary, retroactively, on the SAME already-fully-processed store,
    exactly like AT-1.6 -- but WITHOUT sorting first, so an order
    regression (which AT-1.6 itself would not catch, since it sorts) is
    caught here."""
    bars = _generate_fixture(seed=99, n_bars=40)
    store = run_pipeline(bars)

    for k in range(3, len(bars) + 1):
        ts = bars[k - 1].close_ts
        for direction in ("bull", "bear"):
            actual = store.as_of(ts).active_fvgs(TF.H4, direction)
            expected = _naive_active_fvgs(store, ts, TF.H4, direction)
            assert [f.id for f in actual] == [f.id for f in expected], (
                f"order mismatch at bar {k} ts={ts.isoformat()} direction={direction}"
            )
            assert actual == expected


# ============================================================================
# 9. Full Orchestrator+Journal canonical-hash equivalence: old (naive,
#    monkeypatched) vs. new (real, indexed) implementation, same scenario --
#    proves no downstream trade/setup/Journal output changed, reusing the
#    exact _canonical_export() technique already established and accepted
#    for the Gate 3.7 streaming-path equivalence proof this session.
# ============================================================================


def test_orchestrator_canonical_journal_hash_unchanged_old_vs_new(tmp_path, monkeypatch):
    from datetime import timedelta as _td

    from src.core.types import Tick
    from src.journal.duckdb_writer import DuckDBJournal
    from tests.fixtures.orchestrator import (
        IN_WINDOW,
        make_arm,
        make_orchestrator,
        seed_fvg_and_bias,
    )
    from tests.fixtures.setup_stream import m1, m5
    from tests.test_at3_14_determinism import SCHEMA_PATH, _canonical_export

    def _run(db_path, use_naive: bool):
        r_ts = IN_WINDOW + _td(minutes=5)
        s_ts = IN_WINDOW + _td(minutes=10)
        base = IN_WINDOW + _td(minutes=20)
        bars_1m = [
            m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2),
            m1(base, 97.5, 97.6, 97.0, 97.3),
            m1(base + _td(minutes=1), 97.2, 97.3, 96.8, 97.0),
            m1(base + _td(minutes=2), 96.4, 96.5, 96.2, 96.3),
            m1(base + _td(minutes=3), 96.8, 97.3, 96.7, 97.2),
        ]
        bars_5m = [m5(r_ts, 99.0, 99.8, 97.0, 99.5), m5(s_ts, 98.0, 98.5, 96.0, 97.5)]
        inversion_ts = bars_1m[-1].close_ts
        ticks = [
            Tick(ts=inversion_ts + _td(seconds=1), bid=97.15, ask=97.25),
            Tick(ts=inversion_ts + _td(minutes=5), bid=101.0, ask=101.1),
        ]
        arm = make_arm("M2", "S_wick")
        orch = make_orchestrator(bars_1m=bars_1m, bars_5m=bars_5m, ticks=ticks, arms=[arm])
        orch.journal = DuckDBJournal(db_path, SCHEMA_PATH)
        seed_fvg_and_bias(orch, "long", 100.0, 95.0)
        with monkeypatch.context() as m:
            if use_naive:
                m.setattr(
                    "src.store.state_store.MarketContext.active_fvgs",
                    lambda self, tf, direction: _naive_active_fvgs(
                        self._store, self.now, tf, direction
                    ),
                )
            orch.run()
        return _canonical_export(db_path)

    hash_old = _run(tmp_path / "old.duckdb", use_naive=True)
    hash_new = _run(tmp_path / "new.duckdb", use_naive=False)
    assert hash_old == hash_new
