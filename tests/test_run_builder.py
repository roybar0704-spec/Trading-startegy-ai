"""KI-016: build_orchestrator must load a fully-wired, runnable Orchestrator directly
from the real frozen config files -- no manual per-caller translation.
"""

from datetime import timedelta

import pytest

from src.backtest.run_builder import build_orchestrator
from src.config.models import load_parameters, load_rules_v1, load_run_config
from src.core.types import FVG, TF, RunIdentity
from src.store.state_store import BiasEvent
from tests.fixtures.orchestrator import IN_WINDOW, SEED_TS, make_identity, warmup_ticks
from tests.fixtures.setup_stream import m1, m5

TOP, BOTTOM = 100.0, 95.0


def _rules_params_run():
    return load_rules_v1(), load_parameters(), load_run_config()


def test_build_orchestrator_wires_all_9_declared_arms(tmp_path):
    rules, params, run_cfg = _rules_params_run()
    orch = build_orchestrator(
        rules, params, run_cfg, identity=make_identity(), bars_1m=[], bars_5m=[],
        bars_4h=[], ticks=[], spread_warmup_ticks=warmup_ticks({h: 0.01 for h in range(24)}),
        registry_path=tmp_path / "runs.jsonl",
    )
    assert len(orch.arms) == 9
    pairs = {(a.arm_id.entry, a.arm_id.sl_anchor) for a in orch.arms}
    assert pairs == {
        (e, s) for e in ("M1", "M2", "M4") for s in ("R_body", "S_body", "S_wick")
    }
    assert orch.symbol == "XAUUSD"


def test_build_orchestrator_matches_declared_config_values(tmp_path):
    rules, params, run_cfg = _rules_params_run()
    orch = build_orchestrator(
        rules, params, run_cfg, identity=make_identity(), bars_1m=[], bars_5m=[],
        bars_4h=[], ticks=[], spread_warmup_ticks=warmup_ticks({h: 0.01 for h in range(24)}),
        registry_path=tmp_path / "runs.jsonl",
    )
    for arm in orch.arms:
        assert arm.portfolio.initial_equity == pytest.approx(10_000.0)  # RA-28
        assert arm.risk.params.sizing_pct == pytest.approx(rules.risk.sizing_pct)
        assert arm.risk.params.min_stop_k_spread == pytest.approx(
            params.min_stop_k_spread.default
        )
        # Calendar now exists (T3.1) -- FillSimulator must no longer be wired to the
        # old always-False news stub; every arm's Blackout check is the run's own.
        assert arm.fill_sim.in_news_checker == orch.calendar.in_blackout
    assert orch.displacement_params == {
        "body_vs_avg_n": params.displacement.d1.body_vs_avg_n,
        "ratio_min": params.displacement.d1.ratio_min.default,
    }
    assert orch.sl_buffer_usd == pytest.approx(params.sl_buffer_usd.default)


def test_build_orchestrator_rejects_undeclared_displacement_model():
    rules, params, run_cfg = _rules_params_run()
    bad_params = params.model_copy(
        update={"displacement": params.displacement.model_copy(
            update={"model": params.displacement.model.model_copy(update={"default": "D2"})}
        )}
    )
    with pytest.raises(NotImplementedError):
        build_orchestrator(
            rules, bad_params, run_cfg, identity=make_identity(),
            bars_1m=[], bars_5m=[], bars_4h=[], ticks=[],
        )


def test_build_orchestrator_rejects_caller_supplied_config_hash():
    rules, params, run_cfg = _rules_params_run()
    ok_identity = make_identity()
    bad_identity = RunIdentity(
        data_version=ok_identity.data_version, split_type=ok_identity.split_type,
        code_version=ok_identity.code_version, config_hash="not-allowed",
    )
    with pytest.raises(ValueError):
        build_orchestrator(
            rules, params, run_cfg, identity=bad_identity,
            bars_1m=[], bars_5m=[], bars_4h=[], ticks=[],
        )


def test_build_orchestrator_runs_end_to_end_from_real_config(tmp_path):
    rules, params, run_cfg = _rules_params_run()
    r_ts = IN_WINDOW + timedelta(minutes=5)
    s_ts = IN_WINDOW + timedelta(minutes=10)
    base = IN_WINDOW + timedelta(minutes=20)
    bars_1m = [
        m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2),
        m1(base, 97.5, 97.6, 97.0, 97.3),
        m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0),
        m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3),
        m1(base + timedelta(minutes=3), 96.8, 97.3, 96.7, 97.2),
    ]
    bars_5m = [m5(r_ts, 99.0, 99.8, 97.0, 99.5), m5(s_ts, 98.0, 98.5, 96.0, 97.5)]

    orch = build_orchestrator(
        rules, params, run_cfg, identity=make_identity(), bars_1m=bars_1m, bars_5m=bars_5m,
        bars_4h=[], ticks=[], spread_warmup_ticks=warmup_ticks({h: 0.01 for h in range(24)}),
        registry_path=tmp_path / "runs.jsonl",
    )
    orch.store.put(
        FVG(
            id="FVG-H4-1", tf=TF.H4, direction="bull", top=TOP, bottom=BOTTOM, level=1,
            created_at=SEED_TS, confirmed_at=SEED_TS, mitigation_pct=0.0,
            invalidated_at=None, bos_link=None, displacement=False,
        )
    )
    orch.store.put(BiasEvent(ts=SEED_TS, state="bullish", trigger_bos=None))

    result = orch.run()
    assert result.armed == 1
    # M4 never fires an intent on "armed" itself (it only starts watching for a later
    # rejection candle, which this scenario doesn't include) -- so only M1's and M2's
    # 3 arms each (6 total) are routed through RiskEngine.approve() here. With the
    # *real* declared geometry (sl_buffer_usd=0.30, min_stop_k_spread=3.0, RA-15/16)
    # rather than a test's artificially tiny values, R_body/S_body genuinely fail
    # geometry for this entry price -- only S_wick passes for each of M1/M2.
    assert result.orders_placed == 2
    assert result.orders_rejected == 4
    assert result.orders_placed + result.orders_rejected == 6
