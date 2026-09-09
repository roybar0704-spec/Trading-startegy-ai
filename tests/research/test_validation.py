"""Unit tests for src/research/validation.py -- the strategy-agnostic
Validation Engine (Research System, Phase 3).

Journal fixture helpers are duplicated from tests/research/test_metrics.py's
established pattern (that file is not a shared fixture module, and this
phase's scope forbids refactoring it).
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.journal.duckdb_writer import DuckDBJournal
from src.research.validation import (
    ComparisonResult,
    LabeledRun,
    Split,
    compare_runs,
    holdout_usage_report,
    split_plan,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"
VALIDATION_PATH = REPO_ROOT / "src" / "research" / "validation.py"

_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)


# -- Journal fixture helpers -------------------------------------------


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


def _ensure_run(
    journal: DuckDBJournal,
    run_id: str,
    *,
    config_hash: str = "test-fixture-hash",
    code_version: str = "test-fixture",
    data_version: str = "test-fixture",
    split_type: str = "fixture",
) -> None:
    if journal.query("SELECT 1 FROM runs WHERE run_id = ?", [run_id]):
        return
    experiment_id = f"{run_id}-EXP"
    _insert_experiment(journal, experiment_id)
    journal.record(
        "runs",
        {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "config_hash": config_hash,
            "code_version": code_version,
            "data_version": data_version,
            "period_start": _BASE_TS.date(),
            "period_end": _BASE_TS.date(),
            "split_type": split_type,
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
            "entry_model": "M2",
            "sl_anchor": "S_body",
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
    journal: DuckDBJournal, order_id: str, setup_id: str, portfolio_id: str, index: int,
    *, units: float = 1.0, side: str = "buy", fill_price: float = 2000.0,
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
            "status": "filled",
            "filled_at": placed_at,
            "fill_price": fill_price,
            "cancel_reason": None,
        },
    )


def _make_closed_trade(
    journal: DuckDBJournal, portfolio_id: str, run_id: str, index: int,
    *, entry_px: float = 2000.0, exit_px: float = 2010.0, units: float = 1.0,
    side: str = "buy", result_r: float = 0.1,
) -> None:
    setup_id = f"SETUP-{portfolio_id}-{index}"
    order_id = f"ORDER-{portfolio_id}-{index}"
    trade_id = f"TRADE-{portfolio_id}-{index}"
    entry_ts = _BASE_TS + timedelta(hours=index)
    exit_ts = entry_ts + timedelta(minutes=30)
    _insert_setup(journal, setup_id, run_id, index)
    _insert_order(journal, order_id, setup_id, portfolio_id, index, units=units, side=side, fill_price=entry_px)
    journal.record(
        "trades",
        {
            "trade_id": trade_id,
            "order_id": order_id,
            "portfolio_id": portfolio_id,
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "entry_px": entry_px,
            "exit_px": exit_px,
            "sl_px": entry_px - 10 if side == "buy" else entry_px + 10,
            "tp_px": entry_px + 10 if side == "buy" else entry_px - 10,
            "exit_kind": "tp",
            "result_r": result_r,
            "mae_r": None,
            "mfe_r": None,
            "duration_min": 30,
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


# -- split_plan ------------------------------------------------------------


def test_split_plan_produces_expected_rolling_windows():
    splits = split_plan(
        datetime(2023, 1, 1, tzinfo=UTC), datetime(2024, 6, 30, tzinfo=UTC),
        train_months=9, test_months=3,
    )

    assert len(splits) == 2
    assert splits[0] == Split(
        train_start=datetime(2023, 1, 1, tzinfo=UTC), train_end=datetime(2023, 10, 1, tzinfo=UTC),
        test_start=datetime(2023, 10, 1, tzinfo=UTC), test_end=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert splits[1] == Split(
        train_start=datetime(2023, 4, 1, tzinfo=UTC), train_end=datetime(2024, 1, 1, tzinfo=UTC),
        test_start=datetime(2024, 1, 1, tzinfo=UTC), test_end=datetime(2024, 4, 1, tzinfo=UTC),
    )


def test_split_plan_returns_empty_when_no_full_window_fits():
    splits = split_plan(
        datetime(2023, 1, 1, tzinfo=UTC), datetime(2023, 6, 1, tzinfo=UTC),
        train_months=9, test_months=3,
    )
    assert splits == []


def test_split_plan_rejects_non_positive_months():
    with pytest.raises(ValueError, match="positive"):
        split_plan(datetime(2023, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC), train_months=0, test_months=3)
    with pytest.raises(ValueError, match="positive"):
        split_plan(datetime(2023, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC), train_months=9, test_months=-1)


def test_split_plan_ignores_day_component_and_month_aligns():
    splits = split_plan(
        datetime(2023, 1, 15, tzinfo=UTC), datetime(2024, 1, 5, tzinfo=UTC),
        train_months=9, test_months=3,
    )
    assert len(splits) == 1
    assert splits[0].train_start == datetime(2023, 1, 1, tzinfo=UTC)
    assert splits[0].train_start.day == 1


def test_split_plan_never_executes_a_backtest():
    """Source guard: split_plan/validation.py must never reference
    Orchestrator or build_orchestrator."""
    source = VALIDATION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "orchestrator" not in node.module.lower()
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "orchestrator" not in alias.name.lower()


# -- compare_runs ------------------------------------------------------


def test_compare_runs_preserves_identity_and_provenance(tmp_path):
    journal = _open_journal(tmp_path)
    _ensure_run(journal, "RUN-A", config_hash="hash-a", code_version="ver-a", data_version="data-a", split_type="in_sample")
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.3)

    result = compare_runs(journal, [LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")])
    journal.close()

    assert isinstance(result, ComparisonResult)
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.run_id == "RUN-A"
    assert entry.portfolio_id == "PORT-A"
    assert entry.split_type == "in_sample"
    assert entry.config_hash == "hash-a"
    assert entry.code_version == "ver-a"
    assert entry.data_version == "data-a"
    assert entry.metrics.closed_trade_count == 1
    assert entry.metrics.win_count == 1
    assert "no validation_passed" in result.note or "no significance" in result.note


def test_compare_runs_multiple_same_split_type_stay_distinguishable(tmp_path):
    journal = _open_journal(tmp_path)
    _ensure_run(journal, "RUN-A", split_type="walk_forward_test")
    _ensure_run(journal, "RUN-B", split_type="walk_forward_test")
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _insert_portfolio(journal, "PORT-B", "RUN-B")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.2)
    _make_closed_trade(journal, "PORT-B", "RUN-B", 0, result_r=-0.2)

    result = compare_runs(
        journal,
        [
            LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="walk_forward_test"),
            LabeledRun(run_id="RUN-B", portfolio_id="PORT-B", split_type="walk_forward_test"),
        ],
    )
    journal.close()

    assert len(result.entries) == 2
    run_ids = {e.run_id for e in result.entries}
    assert run_ids == {"RUN-A", "RUN-B"}
    # not collapsed: each entry keeps its own metrics
    by_run = {e.run_id: e for e in result.entries}
    assert by_run["RUN-A"].metrics.win_count == 1
    assert by_run["RUN-B"].metrics.loss_count == 1


def test_compare_runs_unknown_run_id_raises(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")

    with pytest.raises(ValueError, match="unknown run_id"):
        compare_runs(journal, [LabeledRun(run_id="NO-SUCH-RUN", portfolio_id="PORT-A", split_type="in_sample")])
    journal.close()


def test_compare_runs_unknown_portfolio_id_raises(tmp_path):
    journal = _open_journal(tmp_path)
    _ensure_run(journal, "RUN-A")

    with pytest.raises(ValueError, match="unknown portfolio_id"):
        compare_runs(journal, [LabeledRun(run_id="RUN-A", portfolio_id="NO-SUCH-PORTFOLIO", split_type="in_sample")])
    journal.close()


def test_compare_runs_mismatched_run_id_raises(tmp_path):
    journal = _open_journal(tmp_path)
    _ensure_run(journal, "RUN-A")
    _ensure_run(journal, "RUN-B")
    _insert_portfolio(journal, "PORT-A", "RUN-A")  # PORT-A actually belongs to RUN-A

    with pytest.raises(ValueError, match="not the supplied run_id"):
        compare_runs(journal, [LabeledRun(run_id="RUN-B", portfolio_id="PORT-A", split_type="in_sample")])
    journal.close()


def test_compare_runs_no_automatic_discovery(tmp_path):
    """Only the explicitly supplied run appears in the result, even though
    a second run/portfolio exists in the same Journal."""
    journal = _open_journal(tmp_path)
    _ensure_run(journal, "RUN-A")
    _ensure_run(journal, "RUN-B")
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _insert_portfolio(journal, "PORT-B", "RUN-B")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)
    _make_closed_trade(journal, "PORT-B", "RUN-B", 0, result_r=0.2)

    result = compare_runs(journal, [LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")])
    journal.close()

    assert len(result.entries) == 1
    assert result.entries[0].run_id == "RUN-A"


# -- holdout_usage_report -----------------------------------------------


def test_holdout_usage_report_missing_log(tmp_path):
    report = holdout_usage_report(tmp_path / "does_not_exist.jsonl")
    assert report.log_exists is False
    assert report.access_count == 0
    assert report.accesses == []


def test_holdout_usage_report_holdout_guard_schema(tmp_path):
    log_path = tmp_path / "usage.jsonl"
    entry = {
        "accessed_at": "2026-01-01T00:00:00+00:00",
        "symbol": "XAUUSD",
        "start": "2025-07-01T00:00:00+00:00",
        "end": "2025-08-01T00:00:00+00:00",
        "reason": "T5.2 test",
    }
    log_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    report = holdout_usage_report(log_path)

    assert report.log_exists is True
    assert report.access_count == 1
    assert report.accesses[0].symbol == "XAUUSD"
    assert report.accesses[0].reason == "T5.2 test"
    assert report.accesses[0].detail == {"start": "2025-07-01T00:00:00+00:00", "end": "2025-08-01T00:00:00+00:00"}


def test_holdout_usage_report_tick_store_schema(tmp_path):
    log_path = tmp_path / "usage.jsonl"
    entry = {"accessed_at": "2026-01-01T00:00:00+00:00", "symbol": "XAUUSD", "year": 2025, "month": 7, "reason": "diagnostic"}
    log_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    report = holdout_usage_report(log_path)

    assert report.access_count == 1
    assert report.accesses[0].detail == {"year": 2025, "month": 7}


def test_holdout_usage_report_mixed_schema_multiple_lines(tmp_path):
    log_path = tmp_path / "usage.jsonl"
    entries = [
        {"accessed_at": "t1", "symbol": "XAUUSD", "start": "s1", "end": "e1", "reason": "r1"},
        {"accessed_at": "t2", "symbol": "XAUUSD", "year": 2025, "month": 8, "reason": "r2"},
    ]
    log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    report = holdout_usage_report(log_path)

    assert report.access_count == 2
    assert report.accesses[0].detail == {"start": "s1", "end": "e1"}
    assert report.accesses[1].detail == {"year": 2025, "month": 8}


# -- No-verdict / strategy-agnostic boundary -----------------------------


_FORBIDDEN_VERDICT_FIELD_NAMES = {
    "validation_passed", "candidate", "best", "better", "promising", "rejected", "verdict", "passed",
}


def test_no_verdict_fields_in_dataclasses():
    source = VALIDATION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    field_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_names.add(item.target.id)

    overlap = field_names & _FORBIDDEN_VERDICT_FIELD_NAMES
    assert not overlap, f"validation.py dataclasses contain verdict-like fields: {overlap}"


def test_validation_module_imports_are_strategy_agnostic():
    source = VALIDATION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    allowed = {
        "__future__", "json", "dataclasses", "datetime", "pathlib",
        "src.research.metrics",
    }
    unexpected = imported_modules - allowed
    assert not unexpected, f"validation.py has unexpected/strategy-specific imports: {unexpected}"
