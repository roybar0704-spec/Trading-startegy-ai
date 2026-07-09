"""T3.3 Orchestrator: end-to-end wiring (Engagement->R->S->Armed->Order->Fill->Trade),
AT-3.7 (Race-09:00 determinism), AT-3.9 (Blackout cancels pending orders),
AT-3.11 (per-arm quota admission).
"""

from datetime import timedelta

from src.core.types import NewsEvent, Tick
from src.session.calendar_engine import CalendarEngine
from tests.fixtures.orchestrator import (
    IN_WINDOW,
    make_arm,
    make_orchestrator,
    seed_fvg_and_bias,
)
from tests.fixtures.setup_stream import m1, m5

TOP, BOTTOM = 100.0, 95.0


def _happy_path_bars():
    r_ts = IN_WINDOW + timedelta(minutes=5)
    s_ts = IN_WINDOW + timedelta(minutes=10)
    base = IN_WINDOW + timedelta(minutes=20)
    bars_1m = [
        m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2),  # engagement
        m1(base, 97.5, 97.6, 97.0, 97.3),  # c1
        m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0),  # c2
        m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3),  # c3 -> candidate [96.5,97.0]
        m1(base + timedelta(minutes=3), 96.8, 97.3, 96.7, 97.2),  # inversion, closes 97.2
    ]
    bars_5m = [
        m5(r_ts, 99.0, 99.8, 97.0, 99.5),  # R, low=97
        m5(s_ts, 98.0, 98.5, 96.0, 97.5),  # S, low=96
    ]
    return bars_1m, bars_5m


def test_end_to_end_armed_setup_fills_and_closes_trade_updates_equity():
    arm = make_arm("M2", "S_wick")
    bars_1m, bars_5m = _happy_path_bars()
    inversion_ts = bars_1m[-1].close_ts

    entry_tick = Tick(ts=inversion_ts + timedelta(seconds=1), bid=97.15, ask=97.25)
    exit_tick = Tick(ts=inversion_ts + timedelta(minutes=5), bid=101.0, ask=101.1)

    orch = make_orchestrator(
        bars_1m=bars_1m, bars_5m=bars_5m, ticks=[entry_tick, exit_tick], arms=[arm],
    )
    seed_fvg_and_bias(orch, "long", TOP, BOTTOM)
    result = orch.run()

    assert result.engaged == 1
    assert result.reaction_seen == 1
    assert result.sweep_confirmed == 1
    assert result.armed == 1
    assert result.orders_placed == 1
    assert result.orders_rejected == 0

    # SL = S.low(96) - buffer(0.05) = 95.95; TP = 97.2 + 3*(97.2-95.95) = 100.95.
    # exit_tick.bid(101.0) >= TP -> fills the trade at exactly order.tp (conservative, D-018).
    assert arm.portfolio.realized_equity != arm.portfolio.initial_equity  # KI-006 wiring


def test_at3_11_quota_blocks_one_arm_but_not_another_on_the_same_setup():
    bars_1m, bars_5m = _happy_path_bars()
    # Same (entry, sl_anchor) -- S_wick is the only anchor whose geometry is valid for this
    # fixture's numbers (R_body/S_body both land the SL above the entry, invalid_geometry
    # rejects those before quota is even checked, D-047 ordering) -- two separate Portfolio
    # instances isolate quota independently of that, which is exactly what AT-3.11 tests.
    quota_full_arm = make_arm("M2", "S_wick")
    quota_free_arm = make_arm("M2", "S_wick")
    quota_full_arm.portfolio.record_fill(IN_WINDOW.date())
    quota_full_arm.portfolio.record_fill(IN_WINDOW.date())  # 2/2 used up before this Setup

    orch = make_orchestrator(
        bars_1m=bars_1m, bars_5m=bars_5m, arms=[quota_full_arm, quota_free_arm],
    )
    seed_fvg_and_bias(orch, "long", TOP, BOTTOM)
    result = orch.run()

    assert result.armed == 1
    assert result.orders_placed == 1  # only the free arm
    assert result.orders_rejected == 1  # only the full arm
    assert quota_full_arm.portfolio.quota_remaining(IN_WINDOW.date()) == 0
    # Order was only *placed* (approved), not filled (no ticks in this test) -- quota only
    # decrements on an actual fill (Portfolio.record_fill), so this stays untouched at 2.
    assert quota_free_arm.portfolio.quota_remaining(IN_WINDOW.date()) == 2


def test_at3_9_blackout_onset_cancels_pending_limit_order():
    arm = make_arm("M1", "S_wick")
    bars_1m, bars_5m = _happy_path_bars()
    inversion_ts = bars_1m[-1].close_ts
    blackout_ts = inversion_ts + timedelta(minutes=1)

    blackout = CalendarEngine.from_config(
        [NewsEvent(ts_utc=blackout_ts, currency="USD", impact="red", title="x", source="test")],
        currencies=("USD",), impacts=("red",), blackout_before_min=0, blackout_after_min=30,
    )
    # a late 1M bar keeps the merged timeline alive past blackout_ts so the Orchestrator's
    # loop actually visits a tick at/after the blackout boundary.
    trailing_bar = m1(blackout_ts + timedelta(minutes=1), 97.2, 97.3, 97.1, 97.2)

    orch = make_orchestrator(
        bars_1m=[*bars_1m, trailing_bar], bars_5m=bars_5m, arms=[arm], calendar=blackout,
    )
    seed_fvg_and_bias(orch, "long", TOP, BOTTOM)
    result = orch.run()

    assert result.orders_placed == 1  # M1 Limit placed at Armed, still pending (no fill tick)
    [order] = arm.fill_sim.orders()
    assert order.status == "cancelled"
    assert order.cancel_reason == "blocked_news"


def test_at3_7_race_09_00_deterministic_across_repeated_runs():
    # 1M and 5M bars sharing the identical close_ts -- H2 requires 1M->5M->4H ordering to
    # resolve this deterministically regardless of list order.
    race_ts = IN_WINDOW + timedelta(minutes=5)
    bars_1m = [m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), m1(race_ts, 99.9, 100.0, 99.7, 99.8)]
    bars_5m = [m5(race_ts, 99.0, 99.8, 97.0, 99.5)]  # R, same instant as the 2nd 1M bar

    results = []
    for _ in range(3):
        orch = make_orchestrator(bars_1m=bars_1m, bars_5m=bars_5m, arms=[make_arm("M2", "S_wick")])
        seed_fvg_and_bias(orch, "long", TOP, BOTTOM)
        results.append(orch.run())

    assert results[0] == results[1] == results[2]
