"""Unit tests for src/research/metrics.py -- the strategy-agnostic Metrics
Engine (Research System, Phase 1).

Uses small, deterministic Journal rows inserted directly via
DuckDBJournal.record() (the existing, documented write path) rather than
running a full Orchestrator/backtest -- no existing test in this repository
builds Journal state this way, but every existing test already establishes
the DuckDBJournal(db_path, SCHEMA_PATH) construction convention (see e.g.
tests/test_context_snapshots.py), which is reused here unchanged.

Never imports Strategy A, SetupStream, EntryModel, or any FVG/structure
module -- see test_metrics_module_imports_are_strategy_agnostic below,
which enforces this on src/research/metrics.py itself via AST inspection.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.journal.duckdb_writer import DuckDBJournal
from src.research.metrics import MetricsEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"
METRICS_PATH = REPO_ROOT / "src" / "research" / "metrics.py"

_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)


# -- Journal fixture helpers -------------------------------------------
#
# Minimal direct inserts satisfying db/schema.sql's own FK/CHECK
# constraints (portfolios -> setups -> orders -> trades). entry_model/
# sl_anchor are schema-mandated CHECK values with no other legal
# placeholder -- MetricsEngine itself never reads either column (verified
# in test_metrics_module_imports_are_strategy_agnostic's whitelist and by
# inspection of every SELECT in metrics.py).


def _open_journal(tmp_path: Path, name: str = "test.duckdb") -> DuckDBJournal:
    return DuckDBJournal(tmp_path / name, SCHEMA_PATH)


def _insert_experiment(journal: DuckDBJournal, experiment_id: str) -> None:
    journal.record(
        "experiments",
        {
            "experiment_id": experiment_id,
            "name": experiment_id,
            "hypothesis": "test fixture -- not a real research hypothesis",
            "objective_fn": "n/a",
            "declared_grid": "{}",
            "holdout_range": "{}",
            "created_at": _BASE_TS,
        },
    )


def _ensure_run(journal: DuckDBJournal, run_id: str) -> None:
    """Idempotent: portfolios.run_id REFERENCES runs(run_id), and
    runs.experiment_id REFERENCES experiments(experiment_id) (db/schema.sql:29,16)
    -- both must exist before a portfolio can be inserted. Safe to call once
    per unique run_id per test, including tests that share one run_id across
    multiple portfolios.
    """
    if journal.query("SELECT 1 FROM runs WHERE run_id = ?", [run_id]):
        return
    experiment_id = f"{run_id}-EXP"
    _insert_experiment(journal, experiment_id)
    journal.record(
        "runs",
        {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "config_hash": "test-fixture-hash",
            "code_version": "test-fixture",
            "data_version": "test-fixture",
            "period_start": _BASE_TS.date(),
            "period_end": _BASE_TS.date(),
            "split_type": "fixture",
            "seed": None,
            "created_at": _BASE_TS,
        },
    )


def _insert_portfolio(journal: DuckDBJournal, portfolio_id: str, run_id: str) -> None:
    _ensure_run(journal, run_id)
    journal.record(
        "portfolios",
        {
            "portfolio_id": portfolio_id,
            "run_id": run_id,
            "entry_model": "M2",  # placeholder to satisfy CHECK; unread by MetricsEngine
            "sl_anchor": "S_body",  # placeholder to satisfy CHECK; unread by MetricsEngine
            "initial_equity": 10_000.0,
        },
    )


def _insert_setup(journal: DuckDBJournal, setup_id: str, run_id: str, index: int, outcome: str = "armed") -> None:
    journal.record(
        "setups",
        {
            "setup_id": setup_id,
            "run_id": run_id,
            "direction": "long",
            "fvg_id": f"FVG-{index}",
            "engagement_ts": _BASE_TS + timedelta(hours=index),
            "r_bar": None,
            "s_bar": None,
            "ifvg": None,
            "ts_flag": False,
            "same_zone_reentry": False,
            "score": None,
            "outcome": outcome,
            "outcome_reason": None,
            "state_log": "[]",
        },
    )


def _insert_order(
    journal: DuckDBJournal,
    order_id: str,
    setup_id: str,
    portfolio_id: str,
    index: int,
    *,
    units: float = 1.0,
    side: str = "buy",
    status: str = "filled",
    fill_price: float | None = 2000.0,
) -> None:
    placed_at = _BASE_TS + timedelta(hours=index)
    journal.record(
        "orders",
        {
            "order_id": order_id,
            "setup_id": setup_id,
            "portfolio_id": portfolio_id,
            "otype": "limit",
            "side": side,
            "price": fill_price,
            "sl": 1990.0,
            "tp": 2010.0,
            "units": units,
            "placed_at": placed_at,
            "valid_until": placed_at + timedelta(minutes=30),
            "status": status,
            "filled_at": placed_at if status == "filled" else None,
            "fill_price": fill_price if status == "filled" else None,
            "cancel_reason": "blocked_quota" if status == "cancelled" else None,
        },
    )


def _insert_trade_row(
    journal: DuckDBJournal,
    trade_id: str,
    order_id: str,
    portfolio_id: str,
    *,
    entry_ts: datetime,
    exit_ts: datetime | None,
    entry_px: float,
    exit_px: float | None,
    units: float,
    side: str,
    result_r: float | None,
    cost_spread: float = 0.0,
    cost_slippage: float = 0.0,
    cost_commission: float = 0.0,
    mae_r: float | None = None,
    mfe_r: float | None = None,
    exit_kind: str = "tp",
) -> None:
    closed = exit_ts is not None
    duration_min = int((exit_ts - entry_ts).total_seconds() / 60) if closed else None
    journal.record(
        "trades",
        {
            "trade_id": trade_id,
            "order_id": order_id,
            "portfolio_id": portfolio_id,
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "entry_px": entry_px,
            "exit_px": exit_px if closed else None,
            "sl_px": entry_px - 10 if side == "buy" else entry_px + 10,
            "tp_px": entry_px + 10 if side == "buy" else entry_px - 10,
            "exit_kind": exit_kind if closed else None,
            "result_r": result_r if closed else None,
            "mae_r": mae_r,
            "mfe_r": mfe_r,
            "duration_min": duration_min,
            "cost_spread": cost_spread,
            "cost_slippage": cost_slippage,
            "cost_commission": cost_commission,
            "tag_overnight": False,
            "tag_weekend": False,
            "tag_news_cross": False,
            "tag_concurrent": False,
            "tag_bias_flip": False,
            "hour_bucket_et": entry_ts.hour,
        },
    )


def _insert_arm_outcome(
    journal: DuckDBJournal, setup_id: str, portfolio_id: str, outcome: str, order_id: str | None = None
) -> None:
    journal.record(
        "setup_arm_outcomes",
        {
            "setup_id": setup_id,
            "portfolio_id": portfolio_id,
            "outcome": outcome,
            "outcome_reason": None,
            "order_id": order_id,
            "state_log": "[]",
        },
    )


def _insert_equity_point(journal: DuckDBJournal, portfolio_id: str, ts: datetime, open_risk_r: float) -> None:
    journal.record(
        "equity_curve",
        {"portfolio_id": portfolio_id, "ts": ts, "balance_r": 0.0, "open_risk_r": open_risk_r},
    )


def _make_closed_trade(
    journal: DuckDBJournal,
    portfolio_id: str,
    run_id: str,
    index: int,
    *,
    entry_px: float = 2000.0,
    exit_px: float = 2010.0,
    units: float = 1.0,
    side: str = "buy",
    result_r: float = 0.1,
    cost_spread: float = 0.0,
    cost_slippage: float = 0.0,
    cost_commission: float = 0.0,
    mae_r: float | None = None,
    mfe_r: float | None = None,
    duration_minutes: int = 30,
    setup_outcome: str = "armed",
    record_closed_arm_outcome: bool = False,
) -> tuple[str, str, str]:
    """Insert a full setup->order->trade chain for one closed trade.

    Returns (setup_id, order_id, trade_id).
    """
    setup_id = f"SETUP-{portfolio_id}-{index}"
    order_id = f"ORDER-{portfolio_id}-{index}"
    trade_id = f"TRADE-{portfolio_id}-{index}"
    entry_ts = _BASE_TS + timedelta(hours=index)
    exit_ts = entry_ts + timedelta(minutes=duration_minutes)

    _insert_setup(journal, setup_id, run_id, index, outcome=setup_outcome)
    _insert_order(journal, order_id, setup_id, portfolio_id, index, units=units, side=side, fill_price=entry_px)
    _insert_trade_row(
        journal,
        trade_id,
        order_id,
        portfolio_id,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        entry_px=entry_px,
        exit_px=exit_px,
        units=units,
        side=side,
        result_r=result_r,
        cost_spread=cost_spread,
        cost_slippage=cost_slippage,
        cost_commission=cost_commission,
        mae_r=mae_r,
        mfe_r=mfe_r,
    )
    if record_closed_arm_outcome:
        _insert_arm_outcome(journal, setup_id, portfolio_id, "closed", order_id=order_id)
    return setup_id, order_id, trade_id


# -- Core classification / win-rate / R statistics ----------------------


def test_mixed_wins_losses_scratches_core_metrics(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    # 2 wins (+0.2, +0.4), 2 losses (-0.3, -0.1), 1 scratch (0.0)
    for i, r in enumerate([0.2, 0.4, -0.3, -0.1, 0.0]):
        _make_closed_trade(journal, "PORT-1", "RUN-1", i, result_r=r)

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.trades_available is True
    assert result.closed_trade_count == 5
    assert result.win_count == 2
    assert result.loss_count == 2
    assert result.scratch_count == 1
    # win_rate denominator is ALL closed trades (including the scratch), not win+loss only
    assert result.win_rate == pytest.approx(2 / 5)
    assert result.average_r == pytest.approx((0.2 + 0.4 - 0.3 - 0.1 + 0.0) / 5)
    assert result.median_r == pytest.approx(0.0)
    # expectancy_r is documented as identical to average_r
    assert result.expectancy_r == result.average_r


def test_all_winners_profit_factor_is_none(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    for i, r in enumerate([0.1, 0.2, 0.3]):
        _make_closed_trade(journal, "PORT-1", "RUN-1", i, result_r=r, exit_px=2000.0 + 10 * (i + 1))

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.loss_count == 0
    assert result.profit_factor is None
    assert result.profit_factor_note is not None
    assert "undefined" in result.profit_factor_note


def test_all_losers_profit_factor_is_zero(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    for i, r in enumerate([-0.1, -0.2, -0.3]):
        _make_closed_trade(journal, "PORT-1", "RUN-1", i, result_r=r, exit_px=2000.0 - 10 * (i + 1))

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.win_count == 0
    # all-losers is a legitimate, computable profit factor (0.0) -- not undefined
    assert result.profit_factor == pytest.approx(0.0)
    assert result.profit_factor is not None


# -- Empty / open-trade handling ----------------------------------------


def test_zero_closed_trades_returns_unavailable_not_zero(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.trades_available is False
    assert result.closed_trade_count == 0
    # every performance field must be None (unavailable), never a fabricated 0
    assert result.win_count is None
    assert result.win_rate is None
    assert result.net_pnl is None
    assert result.average_r is None
    assert result.profit_factor is None


def test_open_trades_excluded_from_closed_trade_metrics(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_closed_trade(journal, "PORT-1", "RUN-1", 0, result_r=0.2)

    # a second setup/order with an OPEN trade (exit_ts=None)
    setup_id = "SETUP-PORT-1-open"
    order_id = "ORDER-PORT-1-open"
    _insert_setup(journal, setup_id, "RUN-1", 1)
    _insert_order(journal, order_id, setup_id, "PORT-1", 1, fill_price=2000.0)
    _insert_trade_row(
        journal,
        "TRADE-PORT-1-open",
        order_id,
        "PORT-1",
        entry_ts=_BASE_TS + timedelta(hours=1),
        exit_ts=None,
        entry_px=2000.0,
        exit_px=None,
        units=1.0,
        side="buy",
        result_r=None,
    )

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.closed_trade_count == 1
    assert result.open_trade_count == 1


# -- P&L / cost accounting ------------------------------------------------


def test_gross_pnl_matches_manual_price_pnl_sum_long_and_short(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    # long: units=2, 2000 -> 2010 => price_pnl = 2*(2010-2000) = 20
    _make_closed_trade(journal, "PORT-1", "RUN-1", 0, entry_px=2000.0, exit_px=2010.0, units=2.0, side="buy", result_r=0.2)
    # short: units=3, 2000 -> 1990 => price_pnl = 3*(2000-1990) = 30
    _make_closed_trade(journal, "PORT-1", "RUN-1", 1, entry_px=2000.0, exit_px=1990.0, units=3.0, side="sell", result_r=0.3)

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.gross_pnl == pytest.approx(20.0 + 30.0)


def test_cost_components_summed_once_and_net_pnl_consistent(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    # trade 1: price_pnl = 1*(2100-2000) = 100
    _make_closed_trade(
        journal, "PORT-1", "RUN-1", 0,
        entry_px=2000.0, exit_px=2100.0, units=1.0, side="buy", result_r=0.5,
        cost_spread=1.0, cost_slippage=2.0, cost_commission=3.0,
    )
    # trade 2: price_pnl = 1*(2050-2000) = 50
    _make_closed_trade(
        journal, "PORT-1", "RUN-1", 1,
        entry_px=2000.0, exit_px=2050.0, units=1.0, side="buy", result_r=0.25,
        cost_spread=0.5, cost_slippage=1.5, cost_commission=2.5,
    )

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.gross_pnl == pytest.approx(150.0)
    assert result.total_cost_spread == pytest.approx(1.5)
    assert result.total_cost_slippage == pytest.approx(3.5)
    assert result.total_cost_commission == pytest.approx(5.5)
    # each of the three cost fields must be counted exactly once
    assert result.total_cost == pytest.approx(1.5 + 3.5 + 5.5)
    assert result.total_cost == pytest.approx(10.5)
    assert result.net_pnl == pytest.approx(result.gross_pnl - result.total_cost)
    assert result.net_pnl == pytest.approx(139.5)


def test_profit_factor_uses_net_dollar_pnl_not_result_r(tmp_path):
    """The required divergence test: a small-R win eaten by commission becomes
    a net-dollar loss. win_count (result_r-based) must still count it as a
    win, while profit_factor (net-$-based) must treat it as a loss -- proving
    the two computations are independent, per _PROFIT_FACTOR_BASIS_NOTE.
    """
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    # Trade A: result_r=+0.1 (R-win), price_pnl = 10*(2000.5-2000) = 5.0,
    # commission=8.0 => net_pnl = 5.0 - 8.0 = -3.0 (a NET LOSS caused by cost)
    _make_closed_trade(
        journal, "PORT-1", "RUN-1", 0,
        entry_px=2000.0, exit_px=2000.5, units=10.0, side="buy", result_r=0.1,
        cost_commission=8.0,
    )
    # Trade B: result_r=+0.3 (R-win), price_pnl = 10*(2010-2000) = 100.0,
    # commission=2.0 => net_pnl = 98.0 (a clean net win)
    _make_closed_trade(
        journal, "PORT-1", "RUN-1", 1,
        entry_px=2000.0, exit_px=2010.0, units=10.0, side="buy", result_r=0.3,
        cost_commission=2.0,
    )

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    # result_r classification: BOTH trades are wins
    assert result.win_count == 2
    assert result.loss_count == 0

    # profit_factor: net-$ basis => win-dollars=98.0, loss-dollars=-3.0
    assert result.profit_factor == pytest.approx(98.0 / 3.0)
    assert "net_pnl" in result.profit_factor_note or "net monetary" in result.profit_factor_note


# -- Duration / MAE / MFE -------------------------------------------------


def test_average_duration_min(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_closed_trade(journal, "PORT-1", "RUN-1", 0, result_r=0.1, duration_minutes=20)
    _make_closed_trade(journal, "PORT-1", "RUN-1", 1, result_r=0.1, duration_minutes=40)

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.average_duration_min == pytest.approx(30.0)


def test_mae_mfe_null_handling_matches_ki013_reality(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_closed_trade(journal, "PORT-1", "RUN-1", 0, result_r=0.1, mae_r=None, mfe_r=None)
    _make_closed_trade(journal, "PORT-1", "RUN-1", 1, result_r=0.2, mae_r=None, mfe_r=None)

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.average_mae_r is None
    assert result.median_mae_r is None
    assert result.average_mfe_r is None
    assert result.median_mfe_r is None
    assert result.mae_mfe_note is not None


def test_mae_mfe_computed_when_present(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_closed_trade(journal, "PORT-1", "RUN-1", 0, result_r=0.1, mae_r=-0.5, mfe_r=0.8)
    _make_closed_trade(journal, "PORT-1", "RUN-1", 1, result_r=0.2, mae_r=-0.3, mfe_r=0.6)

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.average_mae_r == pytest.approx((-0.5 - 0.3) / 2)
    assert result.average_mfe_r == pytest.approx((0.8 + 0.6) / 2)
    assert result.mae_mfe_note is None


# -- Streaks ---------------------------------------------------------------


def test_max_consecutive_wins_and_losses(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    # chronological (entry_ts order via index): W,W,L,W,W,W,L,L
    sequence = [0.1, 0.1, -0.1, 0.1, 0.1, 0.1, -0.1, -0.1]
    for i, r in enumerate(sequence):
        _make_closed_trade(journal, "PORT-1", "RUN-1", i, result_r=r)

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.max_consecutive_wins == 3
    assert result.max_consecutive_losses == 2


def test_scratch_breaks_streaks(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    # W,W,scratch,W,W,W -- scratch must break the streak, so max should be 3, not 5
    sequence = [0.1, 0.1, 0.0, 0.1, 0.1, 0.1]
    for i, r in enumerate(sequence):
        _make_closed_trade(journal, "PORT-1", "RUN-1", i, result_r=r)

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.max_consecutive_wins == 3


# -- Exposure / equity_curve ------------------------------------------------


def test_exposure_unavailable_when_equity_curve_empty(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_closed_trade(journal, "PORT-1", "RUN-1", 0, result_r=0.1)

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.exposure_avg_open_risk_r is None
    assert "equity_curve" in result.exposure_note


def test_exposure_computed_when_equity_curve_present(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_closed_trade(journal, "PORT-1", "RUN-1", 0, result_r=0.1)
    _insert_equity_point(journal, "PORT-1", _BASE_TS, open_risk_r=1.0)
    _insert_equity_point(journal, "PORT-1", _BASE_TS + timedelta(hours=1), open_risk_r=2.0)

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    assert result.exposure_avg_open_risk_r == pytest.approx(1.5)


# -- Opportunity/execution funnel -------------------------------------------


def test_opportunity_execution_funnel(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")

    # setup A: created by _make_closed_trade itself (outcome="armed" by default),
    # becomes the 1 closed trade -- its own arm outcome is recorded against it.
    setup_id_a, order_id_a, _trade_id_a = _make_closed_trade(
        journal, "PORT-1", "RUN-1", 0, result_r=0.1, setup_outcome="armed",
    )
    _insert_arm_outcome(journal, setup_id_a, "PORT-1", "closed", order_id=order_id_a)

    # setup B: expired, gets a cancelled order for this portfolio (no trade)
    _insert_setup(journal, "SETUP-EXTRA-1", "RUN-1", 1, outcome="expired")
    cancelled_order_id = "ORDER-PORT-1-cancelled"
    _insert_order(journal, cancelled_order_id, "SETUP-EXTRA-1", "PORT-1", 1, status="cancelled")

    # setup C: invalidated, rejected before an order existed (RiskEngine rejection)
    _insert_setup(journal, "SETUP-EXTRA-2", "RUN-1", 2, outcome="invalidated")
    _insert_arm_outcome(journal, "SETUP-EXTRA-2", "PORT-1", "blocked_quota", order_id=None)

    # total engaged setups for RUN-1: setup A + B + C = 3

    result = MetricsEngine(journal).compute("PORT-1")
    journal.close()

    funnel = result.funnel
    assert funnel.engaged == 3  # all setups for RUN-1, model-agnostic
    assert funnel.armed == 1
    assert funnel.orders_placed == 2  # 1 filled + 1 cancelled
    assert funnel.orders_filled == 1
    assert funnel.orders_cancelled == 1
    assert funnel.closed_trades == 1
    assert funnel.arm_outcomes.get("closed") == 1
    assert funnel.arm_outcomes.get("blocked_quota") == 1
    # a cancelled/rejected order must never appear as a losing trade
    assert result.closed_trade_count == 1
    assert result.loss_count == 0


# -- Portfolio isolation -----------------------------------------------------


def test_portfolio_isolation(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-SHARED")
    _insert_portfolio(journal, "PORT-B", "RUN-SHARED")

    # 2 shared, run-scoped setups (both portfolios see the same engaged/armed counts)
    _insert_setup(journal, "SETUP-SHARED-0", "RUN-SHARED", 0, outcome="armed")
    _insert_setup(journal, "SETUP-SHARED-1", "RUN-SHARED", 1, outcome="expired")

    # PORT-A gets 2 closed trades
    _make_closed_trade(journal, "PORT-A", "RUN-SHARED", 10, result_r=0.1, entry_px=2000.0, exit_px=2010.0)
    _make_closed_trade(journal, "PORT-A", "RUN-SHARED", 11, result_r=0.2, entry_px=2000.0, exit_px=2020.0)
    # PORT-B gets 1 closed trade with very different economics
    _make_closed_trade(journal, "PORT-B", "RUN-SHARED", 20, result_r=-0.5, entry_px=2000.0, exit_px=1950.0)

    result_a = MetricsEngine(journal).compute("PORT-A")
    result_b = MetricsEngine(journal).compute("PORT-B")
    journal.close()

    assert result_a.closed_trade_count == 2
    assert result_b.closed_trade_count == 1
    # no cross-contamination of P&L
    assert result_a.loss_count == 0
    assert result_b.loss_count == 1
    assert result_a.gross_pnl != pytest.approx(result_b.gross_pnl)
    # run-scoped funnel counts are intentionally identical across portfolios of the same run
    # (2 explicit setups + 3 created by the _make_closed_trade calls above, indices 10/11/20)
    assert result_a.funnel.engaged == result_b.funnel.engaged == 5
    # but portfolio-scoped funnel counts correctly differ
    assert result_a.funnel.closed_trades == 2
    assert result_b.funnel.closed_trades == 1


def test_unknown_portfolio_id_raises(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")

    with pytest.raises(ValueError, match="unknown portfolio_id"):
        MetricsEngine(journal).compute("NO-SUCH-PORTFOLIO")
    journal.close()


# -- Strategy-agnostic boundary ------------------------------------------


def test_metrics_module_imports_are_strategy_agnostic():
    """Source guard (mirrors the existing repo pattern in
    test_duckdb_writer_encoding.py): metrics.py must import only generic
    infrastructure, never Strategy A / SetupStream / EntryModel / FVG /
    structure / displacement / Orchestrator modules.
    """
    source = METRICS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    allowed = {"__future__", "statistics", "dataclasses", "src.journal.duckdb_writer"}
    unexpected = imported_modules - allowed
    assert not unexpected, f"metrics.py has unexpected/strategy-specific imports: {unexpected}"
