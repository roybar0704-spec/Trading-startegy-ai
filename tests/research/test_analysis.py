"""Unit tests for src/research/analysis.py -- the strategy-agnostic
Analysis Engine (Research System, Phase 2).

Uses small, deterministic Journal rows inserted directly via
DuckDBJournal.record(), following the same convention established in
tests/research/test_metrics.py (that file's helpers are duplicated here
rather than imported, since it is not designed as a shared fixture
module and this phase's scope forbids refactoring it).
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.journal.duckdb_writer import DuckDBJournal
from src.research.analysis import AnalysisEngine, BucketResult

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"
ANALYSIS_PATH = REPO_ROOT / "src" / "research" / "analysis.py"

_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)  # a Monday


# -- Journal fixture helpers (duplicated from test_metrics.py's pattern) ----


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
            "entry_model": "M2",  # placeholder to satisfy CHECK; unread by AnalysisEngine
            "sl_anchor": "S_body",  # placeholder to satisfy CHECK; unread by AnalysisEngine
            "initial_equity": 10_000.0,
        },
    )


def _insert_setup(journal: DuckDBJournal, setup_id: str, run_id: str, index: int) -> None:
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
            "outcome": "armed",
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
            "cancel_reason": None,
        },
    )


def _make_trade(
    journal: DuckDBJournal,
    portfolio_id: str,
    run_id: str,
    index: int,
    *,
    entry_ts: datetime,
    result_r: float = 0.1,
    side: str = "buy",
    entry_px: float = 2000.0,
    exit_px: float = 2010.0,
    units: float = 1.0,
    duration_min: int | None = 30,
    hour_bucket_et: int | None = 9,
    cost_spread: float = 0.0,
    cost_slippage: float = 0.0,
    cost_commission: float = 0.0,
    exit_ts: datetime | None = None,
) -> str:
    """Insert a full setup->order->trade chain. Returns trade_id.

    exit_ts=None (default) means "closed trade" -- computed from entry_ts +
    duration_min. Pass an explicit exit_ts=False-like sentinel is not
    supported; to build an OPEN trade, use _make_open_trade instead.
    """
    setup_id = f"SETUP-{portfolio_id}-{index}"
    order_id = f"ORDER-{portfolio_id}-{index}"
    trade_id = f"TRADE-{portfolio_id}-{index}"
    _insert_setup(journal, setup_id, run_id, index)
    _insert_order(journal, order_id, setup_id, portfolio_id, index, units=units, side=side, fill_price=entry_px)

    resolved_exit_ts = exit_ts if exit_ts is not None else entry_ts + timedelta(minutes=duration_min or 0)
    journal.record(
        "trades",
        {
            "trade_id": trade_id,
            "order_id": order_id,
            "portfolio_id": portfolio_id,
            "entry_ts": entry_ts,
            "exit_ts": resolved_exit_ts,
            "entry_px": entry_px,
            "exit_px": exit_px,
            "sl_px": entry_px - 10 if side == "buy" else entry_px + 10,
            "tp_px": entry_px + 10 if side == "buy" else entry_px - 10,
            "exit_kind": "tp",
            "result_r": result_r,
            "mae_r": None,
            "mfe_r": None,
            "duration_min": duration_min,
            "cost_spread": cost_spread,
            "cost_slippage": cost_slippage,
            "cost_commission": cost_commission,
            "tag_overnight": False,
            "tag_weekend": False,
            "tag_news_cross": False,
            "tag_concurrent": False,
            "tag_bias_flip": False,
            "hour_bucket_et": hour_bucket_et,
        },
    )
    return trade_id


def _make_open_trade(journal: DuckDBJournal, portfolio_id: str, run_id: str, index: int, entry_ts: datetime) -> str:
    setup_id = f"SETUP-{portfolio_id}-{index}"
    order_id = f"ORDER-{portfolio_id}-{index}"
    trade_id = f"TRADE-{portfolio_id}-{index}"
    _insert_setup(journal, setup_id, run_id, index)
    _insert_order(journal, order_id, setup_id, portfolio_id, index, fill_price=2000.0)
    journal.record(
        "trades",
        {
            "trade_id": trade_id,
            "order_id": order_id,
            "portfolio_id": portfolio_id,
            "entry_ts": entry_ts,
            "exit_ts": None,
            "entry_px": 2000.0,
            "exit_px": None,
            "sl_px": 1990.0,
            "tp_px": 2010.0,
            "exit_kind": None,
            "result_r": None,
            "mae_r": None,
            "mfe_r": None,
            "duration_min": None,
            "cost_spread": 0.0,
            "cost_slippage": 0.0,
            "cost_commission": 0.0,
            "tag_overnight": False,
            "tag_weekend": False,
            "tag_news_cross": False,
            "tag_concurrent": False,
            "tag_bias_flip": False,
            "hour_bucket_et": entry_ts.hour,
        },
    )
    return trade_id


def _find_bucket(result, dimension: str, key: str) -> BucketResult | None:
    for b in result.buckets:
        if b.dimension == dimension and b.bucket_key == key:
            return b
    return None


# -- Empty / open-trade handling ------------------------------------------


def test_zero_closed_trades_returns_unavailable(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")

    result = AnalysisEngine(journal).analyze("PORT-1")
    journal.close()

    assert result.trades_available is False
    assert result.closed_trade_count == 0
    assert result.buckets == []


def test_open_trades_excluded(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_trade(journal, "PORT-1", "RUN-1", 0, entry_ts=_BASE_TS, result_r=0.1)
    _make_open_trade(journal, "PORT-1", "RUN-1", 1, entry_ts=_BASE_TS + timedelta(hours=1))

    result = AnalysisEngine(journal, min_sample_size=1).analyze("PORT-1")
    journal.close()

    assert result.closed_trade_count == 1


# -- Day of week -------------------------------------------------------------


def test_day_of_week_grouping(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    # 2024-01-01 = Monday, 2024-01-02 = Tuesday
    _make_trade(journal, "PORT-1", "RUN-1", 0, entry_ts=_BASE_TS, result_r=0.1)
    _make_trade(journal, "PORT-1", "RUN-1", 1, entry_ts=_BASE_TS + timedelta(days=1), result_r=0.2)

    result = AnalysisEngine(journal, min_sample_size=1).analyze("PORT-1")
    journal.close()

    monday = _find_bucket(result, "day_of_week", "Monday")
    tuesday = _find_bucket(result, "day_of_week", "Tuesday")
    assert monday is not None and monday.trade_count == 1
    assert tuesday is not None and tuesday.trade_count == 1
    # canonical ordering: Monday must appear before Tuesday in the buckets list
    dow_keys = [b.bucket_key for b in result.buckets if b.dimension == "day_of_week"]
    assert dow_keys.index("Monday") < dow_keys.index("Tuesday")


# -- Hour (ET) -----------------------------------------------------------


def test_hour_grouping_uses_hour_bucket_et_column(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_trade(journal, "PORT-1", "RUN-1", 0, entry_ts=_BASE_TS, result_r=0.1, hour_bucket_et=9)
    _make_trade(journal, "PORT-1", "RUN-1", 1, entry_ts=_BASE_TS + timedelta(hours=5), result_r=0.2, hour_bucket_et=14)

    result = AnalysisEngine(journal, min_sample_size=1).analyze("PORT-1")
    journal.close()

    nine = _find_bucket(result, "hour_et", "09")
    fourteen = _find_bucket(result, "hour_et", "14")
    assert nine is not None and nine.trade_count == 1
    assert fourteen is not None and fourteen.trade_count == 1


# -- Month / Quarter -------------------------------------------------------


def test_month_and_quarter_grouping_pools_across_years(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_trade(journal, "PORT-1", "RUN-1", 0, entry_ts=datetime(2023, 1, 15, tzinfo=UTC), result_r=0.1)
    _make_trade(journal, "PORT-1", "RUN-1", 1, entry_ts=datetime(2024, 1, 20, tzinfo=UTC), result_r=0.2)
    _make_trade(journal, "PORT-1", "RUN-1", 2, entry_ts=datetime(2023, 7, 5, tzinfo=UTC), result_r=-0.1)

    result = AnalysisEngine(journal, min_sample_size=1).analyze("PORT-1")
    journal.close()

    january = _find_bucket(result, "month", "01")
    july = _find_bucket(result, "month", "07")
    assert january is not None and january.trade_count == 2  # pooled across 2023 and 2024
    assert july is not None and july.trade_count == 1

    q1 = _find_bucket(result, "quarter", "Q1")
    q3 = _find_bucket(result, "quarter", "Q3")
    assert q1 is not None and q1.trade_count == 2
    assert q3 is not None and q3.trade_count == 1


# -- Side (long/short) -----------------------------------------------------


def test_side_grouping(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_trade(journal, "PORT-1", "RUN-1", 0, entry_ts=_BASE_TS, side="buy", result_r=0.1)
    _make_trade(journal, "PORT-1", "RUN-1", 1, entry_ts=_BASE_TS + timedelta(hours=1), side="sell", result_r=0.2)
    _make_trade(journal, "PORT-1", "RUN-1", 2, entry_ts=_BASE_TS + timedelta(hours=2), side="buy", result_r=-0.1)

    result = AnalysisEngine(journal, min_sample_size=1).analyze("PORT-1")
    journal.close()

    buy = _find_bucket(result, "side", "buy")
    sell = _find_bucket(result, "side", "sell")
    assert buy is not None and buy.trade_count == 2
    assert sell is not None and sell.trade_count == 1


# -- Duration bucket ---------------------------------------------------------


def test_duration_bucket_grouping(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    durations = {
        "under_15m": 10,
        "15m_to_1h": 30,
        "1h_to_4h": 120,
        "4h_to_24h": 600,
        "over_24h": 2000,
    }
    for i, (_label, minutes) in enumerate(durations.items()):
        _make_trade(
            journal, "PORT-1", "RUN-1", i,
            entry_ts=_BASE_TS + timedelta(hours=i), result_r=0.1, duration_min=minutes,
        )

    result = AnalysisEngine(journal, min_sample_size=1).analyze("PORT-1")
    journal.close()

    for label in durations:
        bucket = _find_bucket(result, "duration_bucket", label)
        assert bucket is not None and bucket.trade_count == 1, f"missing/miscounted bucket {label}"


# -- Win/loss/scratch + net P&L + average R correctness ---------------------


def test_bucket_win_loss_scratch_and_net_pnl_average_r(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    # all on the same weekday (Monday) so they land in one bucket together
    _make_trade(journal, "PORT-1", "RUN-1", 0, entry_ts=_BASE_TS, side="buy", entry_px=2000.0, exit_px=2010.0, units=1.0, result_r=0.2)
    _make_trade(journal, "PORT-1", "RUN-1", 1, entry_ts=_BASE_TS + timedelta(hours=1), side="buy", entry_px=2000.0, exit_px=1990.0, units=1.0, result_r=-0.2)
    _make_trade(journal, "PORT-1", "RUN-1", 2, entry_ts=_BASE_TS + timedelta(hours=2), side="buy", entry_px=2000.0, exit_px=2000.0, units=1.0, result_r=0.0)

    result = AnalysisEngine(journal, min_sample_size=1).analyze("PORT-1")
    journal.close()

    monday = _find_bucket(result, "day_of_week", "Monday")
    assert monday.trade_count == 3
    assert monday.win_count == 1
    assert monday.loss_count == 1
    assert monday.scratch_count == 1
    assert monday.win_rate == pytest.approx(1 / 3)
    # net_pnl: (2010-2000) + (1990-2000) + (2000-2000) = 10 - 10 + 0 = 0.0
    assert monday.net_pnl == pytest.approx(0.0)
    assert monday.average_r == pytest.approx((0.2 - 0.2 + 0.0) / 3)


# -- Insufficient sample -----------------------------------------------------


def test_insufficient_sample_withholds_performance_fields(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    # only 2 trades on Monday, well below the default min_sample_size=5
    _make_trade(journal, "PORT-1", "RUN-1", 0, entry_ts=_BASE_TS, result_r=0.1)
    _make_trade(journal, "PORT-1", "RUN-1", 1, entry_ts=_BASE_TS + timedelta(hours=1), result_r=0.2)

    result = AnalysisEngine(journal).analyze("PORT-1")  # default min_sample_size=5
    journal.close()

    monday = _find_bucket(result, "day_of_week", "Monday")
    assert monday is not None
    assert monday.trade_count == 2  # raw count is always shown
    assert monday.sufficient_sample is False
    assert monday.insufficient_sample_note is not None
    assert monday.win_rate is None
    assert monday.net_pnl is None
    assert monday.average_r is None
    assert monday.profit_factor is None


# -- Portfolio isolation ------------------------------------------------------


def test_portfolio_isolation(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-SHARED")
    _insert_portfolio(journal, "PORT-B", "RUN-SHARED")
    _make_trade(journal, "PORT-A", "RUN-SHARED", 0, entry_ts=_BASE_TS, result_r=0.5, entry_px=2000.0, exit_px=2050.0)
    _make_trade(journal, "PORT-B", "RUN-SHARED", 1, entry_ts=_BASE_TS, result_r=-0.5, entry_px=2000.0, exit_px=1950.0)

    result_a = AnalysisEngine(journal, min_sample_size=1).analyze("PORT-A")
    result_b = AnalysisEngine(journal, min_sample_size=1).analyze("PORT-B")
    journal.close()

    monday_a = _find_bucket(result_a, "day_of_week", "Monday")
    monday_b = _find_bucket(result_b, "day_of_week", "Monday")
    assert monday_a.trade_count == 1
    assert monday_b.trade_count == 1
    assert monday_a.win_count == 1 and monday_a.loss_count == 0
    assert monday_b.win_count == 0 and monday_b.loss_count == 1
    assert monday_a.net_pnl != pytest.approx(monday_b.net_pnl)


# -- Multiple-comparison disclosure ------------------------------------------


def test_multiple_comparison_disclosure_counts(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-1", "RUN-1")
    _make_trade(journal, "PORT-1", "RUN-1", 0, entry_ts=_BASE_TS, result_r=0.1)

    result = AnalysisEngine(journal, min_sample_size=1).analyze("PORT-1")
    journal.close()

    assert result.dimensions_scanned == 6
    assert result.buckets_scanned == len(result.buckets)
    assert result.buckets_scanned > 0
    assert result.multiple_comparison_note  # non-empty disclosure string


# -- Strategy-agnostic boundary ------------------------------------------


def test_analysis_module_imports_are_strategy_agnostic():
    """Source guard (mirrors test_metrics.py's identical guard):
    analysis.py must import only generic infrastructure, never Strategy A /
    SetupStream / EntryModel / FVG / structure / displacement / Orchestrator.
    """
    source = ANALYSIS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    allowed = {
        "__future__", "statistics", "collections", "dataclasses", "datetime",
        "src.journal.duckdb_writer",
    }
    unexpected = imported_modules - allowed
    assert not unexpected, f"analysis.py has unexpected/strategy-specific imports: {unexpected}"
