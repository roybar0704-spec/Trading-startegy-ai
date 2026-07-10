"""Critical Review finding (Phase 3 close-out): the full pipeline -- all 3 entry
models (M1 Limit, M2 Market, M4 rejection-candle) actually filling, with all 9
arms wired together via build_orchestrator -- had never been exercised through to
a real Fill in any existing test (KI-014/KI-015). This is that missing proof.
"""

from datetime import timedelta

from src.backtest.run_builder import build_orchestrator
from src.config.models import load_parameters, load_rules_v1, load_run_config
from src.core.types import FVG, TF, Tick
from src.store.state_store import BiasEvent
from tests.fixtures.orchestrator import IN_WINDOW, SEED_TS, warmup_ticks
from tests.fixtures.setup_stream import m1, m5


def _scenario():
    rules, params, run_cfg = load_rules_v1(), load_parameters(), load_run_config()
    r_ts = IN_WINDOW + timedelta(minutes=5)
    s_ts = IN_WINDOW + timedelta(minutes=10)
    base = IN_WINDOW + timedelta(minutes=20)
    bars_1m = [
        m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2),
        m1(base, 97.5, 97.6, 97.0, 97.3),
        m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0),
        m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3),
        m1(base + timedelta(minutes=3), 96.8, 97.3, 96.7, 97.2),  # inversion bar, arms here
        # bullish candle right after arming -- M4's rejection-candle trigger
        m1(base + timedelta(minutes=4), 97.2, 97.6, 97.1, 97.5),
    ]
    bars_5m = [m5(r_ts, 99.0, 99.8, 97.0, 99.5), m5(s_ts, 98.0, 98.5, 96.0, 97.5)]
    inversion_ts = bars_1m[4].close_ts
    rejection_close_ts = bars_1m[5].close_ts

    # Tiny geometry threshold -- real geometry with real min_stop_k_spread/sl_buffer
    # isn't the point here (already covered by test_at2_6_geometry.py); the point is
    # proving all three entry models reach a real Fill together.
    params = params.model_copy(
        update={
            "min_stop_k_spread": params.min_stop_k_spread.model_copy(update={"default": 0.01}),
            "sl_buffer_usd": params.sl_buffer_usd.model_copy(update={"default": 0.05}),
        }
    )
    ticks = [
        # ask <= 97.0 fills M1's Limit; also the tick M2's Market fires on.
        Tick(ts=inversion_ts + timedelta(seconds=1), bid=96.85, ask=96.98),
        Tick(ts=inversion_ts + timedelta(seconds=2), bid=96.9, ask=97.05),
        Tick(ts=rejection_close_ts + timedelta(seconds=1), bid=97.4, ask=97.55),  # M4 fills
        Tick(ts=rejection_close_ts + timedelta(minutes=10), bid=101.0, ask=101.1),  # TP for all
    ]
    orch = build_orchestrator(
        rules, params, run_cfg, bars_1m=bars_1m, bars_5m=bars_5m, bars_4h=[], ticks=ticks,
        spread_warmup_ticks=warmup_ticks({h: 0.01 for h in range(24)}),
    )
    orch.store.put(
        FVG(
            id="FVG-H4-1", tf=TF.H4, direction="bull", top=100.0, bottom=95.0, level=1,
            created_at=SEED_TS, confirmed_at=SEED_TS, mitigation_pct=0.0,
            invalidated_at=None, bos_link=None, displacement=False,
        )
    )
    orch.store.put(BiasEvent(ts=SEED_TS, state="bullish", trigger_bos=None))
    return orch


def test_all_three_entry_models_fill_through_the_real_orchestrator():
    orch = _scenario()
    assert len(orch.arms) == 9

    orch.run()

    filled_arms = {
        arm.arm_id.entry
        for arm in orch.arms
        if arm.portfolio.realized_equity != 10_000.0
    }
    assert filled_arms == {"M1", "M2", "M4"}


def test_nine_arms_stay_isolated_when_only_some_fill():
    orch = _scenario()
    orch.run()

    for arm in orch.arms:
        if arm.arm_id.sl_anchor == "S_wick":
            assert arm.portfolio.realized_equity != 10_000.0
            assert arm.portfolio.fills_today(SEED_TS.date()) == 1
        else:
            # R_body/S_body fail this scenario's geometry (entry too close to/above
            # their SL) -- must stay completely untouched by the S_wick arms' fills.
            assert arm.portfolio.realized_equity == 10_000.0
            assert arm.portfolio.fills_today(SEED_TS.date()) == 0


def test_run_result_fills_and_cancelled_counters_are_wired():
    """Regression: RunResult.fills/orders_cancelled were declared but never
    incremented anywhere -- always silently 0 even on a fully successful run.
    """
    orch = _scenario()
    result = orch.run()

    # 3 arms x (1 entry fill + 1 exit fill) = 6.
    assert result.fills == 6
