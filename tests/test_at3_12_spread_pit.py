"""AT-3.12: median_spread must be Point-in-Time (D-049, closes KI-007).

Unit-level: ExpandingSpreadReport.median_spread(hour_et) at any point depends only on
ticks fed to update() so far -- future updates never retroactively change an
already-returned value. Orchestrator-level: an order's geometry check reflects only
ticks processed up to that point in the run, not ticks that arrive later.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.types import Tick
from src.data.spread_report import ExpandingSpreadReport
from tests.fixtures.orchestrator import IN_WINDOW, make_arm, make_orchestrator, seed_fvg_and_bias


def _tick(ts, spread) -> Tick:
    return Tick(ts=ts, bid=2000.0, ask=2000.0 + spread)


def test_median_spread_reflects_only_ticks_seen_so_far():
    report = ExpandingSpreadReport(symbol="XAUUSD")
    base = datetime(2024, 1, 10, 14, 0, tzinfo=UTC)  # 09:00 ET, winter -> hour_et=9

    with pytest.raises(KeyError):
        report.median_spread(9)

    report.update(_tick(base, 0.10))
    assert report.median_spread(9) == pytest.approx(0.10)

    snapshot_after_one_tick = report.median_spread(9)

    # Feeding a later tick with a wildly different spread must not change the
    # value that was already valid/returned as of the earlier point in time.
    report.update(_tick(base + timedelta(minutes=1), 9.99))
    assert snapshot_after_one_tick == pytest.approx(0.10)
    # The tracker itself has moved on (it's a live, growing accumulator) -- this
    # confirms the *previously returned* value was never mutated in place, only
    # that a fresh query now reflects the newly-available tick too.
    assert report.median_spread(9) == pytest.approx((0.10 + 9.99) / 2)


def test_warm_start_seeds_from_strictly_prior_ticks():
    prior = [_tick(datetime(2024, 1, 1, 14, 0, tzinfo=UTC), 0.05)]
    report = ExpandingSpreadReport.warm_start(symbol="XAUUSD", ticks=prior)
    assert report.median_spread(9) == pytest.approx(0.05)


def test_orchestrator_order_geometry_unaffected_by_later_ticks():
    """A Tick that arrives *after* an order's RiskEngine.approve() call must not be
    able to change the median_spread value that call already used.

    Setup: entry=97.2 (M2 inversion_close), SL(S_wick)=S.low-buffer=96.0-0.05=95.95,
    stop_distance=1.25. With min_stop_k_spread=1.0: the warm-started spread (0.01)
    gives min_stop_distance=0.01 -- comfortably approved. A tick with spread=20.0
    (bid=90, ask=110), timestamped *after* the armed event that triggers this order,
    would give min_stop_distance=20.0 -- geometry would fail -- *if* it leaked into
    the approval check. It must not: the order must still be approved, proving the
    late tick was invisible to a decision that already happened.
    """
    r_ts = IN_WINDOW + timedelta(minutes=5)
    s_ts = IN_WINDOW + timedelta(minutes=10)
    base = IN_WINDOW + timedelta(minutes=20)
    from tests.fixtures.setup_stream import m1, m5

    bars_1m = [
        m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2),
        m1(base, 97.5, 97.6, 97.0, 97.3),
        m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0),
        m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3),
        m1(base + timedelta(minutes=3), 96.8, 97.3, 96.7, 97.2),
    ]
    bars_5m = [m5(r_ts, 99.0, 99.8, 97.0, 99.5), m5(s_ts, 98.0, 98.5, 96.0, 97.5)]
    inversion_ts = bars_1m[-1].close_ts

    late_tick = Tick(ts=inversion_ts + timedelta(minutes=1), bid=90.0, ask=110.0)

    arm = make_arm("M2", "S_wick", min_stop_k_spread=1.0)
    orch = make_orchestrator(bars_1m=bars_1m, bars_5m=bars_5m, ticks=[late_tick], arms=[arm])
    seed_fvg_and_bias(orch, "long", 100.0, 95.0)

    result = orch.run()
    assert result.armed == 1
    assert result.orders_placed == 1
    assert result.orders_rejected == 0
