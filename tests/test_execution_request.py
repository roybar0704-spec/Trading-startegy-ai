"""Unit/integration tests for src/backtest/execution_request.py -- the
Phase 8 Strategy-A execution glue (Research System).

Not under tests/research/: this module is Strategy-A-specific execution
glue, not a strategy-agnostic Research Engine component (matching the
module's own documented boundary). Uses lightweight SimpleNamespace
stand-ins for RunConfig in pure plan_execution()-level tests (no
Pydantic validation is exercised by this module's own code -- only
attribute access), and the real, frozen load_rules_v1()/load_parameters()
plus a genuinely constructed minimal RunConfig for the one full
execute_plan() integration test. No new dependency is introduced --
only Python stdlib (types.SimpleNamespace, unittest.mock) plus
already-used project dependencies (polars).
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from src.backtest.execution_request import (
    ExecutionPlan,
    ExecutionRequest,
    execute_plan,
    plan_execution,
)
from src.config.models import (
    Arms,
    Baseline,
    Guards,
    Holdout,
    Period,
    RunConfig,
    WalkForward,
    load_parameters,
    load_rules_v1,
)
from src.data.tick_store import HoldoutRange, TickParquetStore
from src.research.validation import LabeledRun

REPO_ROOT = Path(__file__).resolve().parents[1]
EXECUTION_REQUEST_PATH = REPO_ROOT / "src" / "backtest" / "execution_request.py"


# -- lightweight request builder for plan_execution()-level tests -----------


def _make_request(
    *,
    run_id: str = "test-run",
    period_start: date,
    period_end: date,
    split_type: str = "in_sample",
    holdout_range: HoldoutRange | None = None,
    seed: int = 42,
    ticks_dir: Path | None = None,
) -> ExecutionRequest:
    run_config = SimpleNamespace(period=SimpleNamespace(start=period_start, end=period_end), seed=seed)
    return ExecutionRequest(
        run_id=run_id,
        run_config=run_config,
        ticks_dir=ticks_dir if ticks_dir is not None else Path("unused"),
        holdout_range=holdout_range if holdout_range is not None else HoldoutRange.none(),
        rules=object(),
        parameters=object(),
        split_type=split_type,
    )


# -- 1. valid construction ---------------------------------------------


def test_execution_request_valid_construction():
    request = _make_request(period_start=date(2024, 3, 1), period_end=date(2024, 3, 31))
    assert request.run_id == "test-run"
    assert request.split_type == "in_sample"


# -- 2/3. run_id rejection ------------------------------------------------


def test_empty_run_id_rejected():
    with pytest.raises(ValueError, match="run_id"):
        _make_request(run_id="", period_start=date(2024, 3, 1), period_end=date(2024, 3, 31))


def test_whitespace_only_run_id_rejected():
    with pytest.raises(ValueError, match="run_id"):
        _make_request(run_id="   ", period_start=date(2024, 3, 1), period_end=date(2024, 3, 31))


# -- 4. reversed period rejected ------------------------------------------


def test_reversed_period_rejected():
    with pytest.raises(ValueError, match="period"):
        _make_request(period_start=date(2024, 3, 31), period_end=date(2024, 3, 1))


# -- 5/6. inclusive month resolution, day-of-month irrelevant --------------


def test_plan_execution_inclusive_month_resolution():
    request = _make_request(period_start=date(2024, 1, 1), period_end=date(2024, 3, 1))
    plan = plan_execution(request)
    assert plan.resolved_months == [(2024, 1), (2024, 2), (2024, 3)]


def test_plan_execution_day_of_month_does_not_shrink_range():
    # entirely within one calendar month, at non-boundary days
    request = _make_request(period_start=date(2024, 7, 15), period_end=date(2024, 7, 20))
    plan = plan_execution(request)
    assert plan.resolved_months == [(2024, 7)]


# -- 7/8. holdout overlap at month granularity -----------------------------


def test_holdout_overlap_detected_at_month_granularity():
    holdout_range = HoldoutRange(start=date_to_dt(2025, 7, 1), end=date_to_dt(2025, 12, 31))
    # period ends deep inside a holdout month even though it starts well before
    request = _make_request(
        period_start=date(2025, 6, 15), period_end=date(2025, 7, 5), holdout_range=holdout_range
    )
    plan = plan_execution(request)
    assert plan.holdout_overlap is True


def test_no_overlap_case():
    holdout_range = HoldoutRange(start=date_to_dt(2025, 7, 1), end=date_to_dt(2025, 12, 31))
    request = _make_request(
        period_start=date(2024, 1, 1), period_end=date(2024, 3, 1), holdout_range=holdout_range
    )
    plan = plan_execution(request)
    assert plan.holdout_overlap is False


def date_to_dt(y: int, m: int, d: int):
    from datetime import UTC, datetime

    return datetime(y, m, d, tzinfo=UTC)


# -- split_type is metadata only, never inferred, never a bypass -----------


def test_split_type_holdout_note_when_no_overlap():
    holdout_range = HoldoutRange(start=date_to_dt(2025, 7, 1), end=date_to_dt(2025, 12, 31))
    request = _make_request(
        period_start=date(2024, 1, 1), period_end=date(2024, 3, 1),
        holdout_range=holdout_range, split_type="holdout",
    )
    plan = plan_execution(request)
    assert plan.holdout_overlap is False
    assert any("does not actually overlap" in n for n in plan.notes)


def test_split_type_holdout_does_not_bypass_holdout_guard():
    """split_type='holdout' grants no execution bypass -- overlap without
    holdout_unlock still fails, exactly like any other split_type."""
    holdout_range = HoldoutRange(start=date_to_dt(2025, 7, 1), end=date_to_dt(2025, 12, 31))
    request = _make_request(
        period_start=date(2025, 7, 1), period_end=date(2025, 7, 5),
        holdout_range=holdout_range, split_type="holdout",
    )
    plan = plan_execution(request)
    assert plan.holdout_overlap is True

    with pytest.raises(ValueError, match="holdout_overlap"):
        execute_plan(plan, Path("unused.duckdb"), holdout_unlock=False)


# -- 9. overlap without unlock fails before data loading -------------------


def test_overlap_without_unlock_fails_before_data_loading():
    holdout_range = HoldoutRange(start=date_to_dt(2025, 7, 1), end=date_to_dt(2025, 12, 31))
    request = _make_request(
        period_start=date(2025, 7, 1), period_end=date(2025, 7, 5),
        holdout_range=holdout_range,
        ticks_dir=Path("this-directory-does-not-exist-and-must-never-be-touched"),
    )
    plan = plan_execution(request)
    assert plan.holdout_overlap is True

    with pytest.raises(ValueError, match="holdout_overlap is True but holdout_unlock=False"):
        execute_plan(plan, Path("unused.duckdb"), holdout_unlock=False)


# -- 10/11. TickParquetStore's own validation remains authoritative --------


def test_holdout_unlock_without_usage_log_path_fails():
    request = _make_request(period_start=date(2024, 1, 1), period_end=date(2024, 1, 31))
    plan = plan_execution(request)  # no overlap -- reaches TickParquetStore construction

    with pytest.raises(ValueError, match="usage_log_path"):
        execute_plan(
            plan, Path("unused.duckdb"),
            holdout_unlock=True, usage_log_path=None, unlock_reason="a real reason",
        )


def test_holdout_unlock_with_empty_unlock_reason_fails():
    request = _make_request(period_start=date(2024, 1, 1), period_end=date(2024, 1, 31))
    plan = plan_execution(request)

    with pytest.raises(ValueError, match="unlock_reason"):
        execute_plan(
            plan, Path("unused.duckdb"),
            holdout_unlock=True, usage_log_path=Path("some_log.jsonl"), unlock_reason="   ",
        )


# -- 12. unlock_reason passed through to TickParquetStore unchanged --------


def test_unlock_reason_passed_through_unchanged(tmp_path):
    request = _make_request(period_start=date(2024, 1, 1), period_end=date(2024, 1, 31))
    plan = plan_execution(request)

    mock_store_cls = MagicMock()
    mock_store_cls.return_value.read_month.side_effect = RuntimeError("stop-here-sentinel")

    with patch("src.backtest.execution_request.TickParquetStore", mock_store_cls):
        with pytest.raises(RuntimeError, match="stop-here-sentinel"):
            execute_plan(
                plan, tmp_path / "unused.duckdb",
                holdout_unlock=True,
                usage_log_path=tmp_path / "usage.jsonl",
                unlock_reason="a genuinely specific reason",
            )

    _, kwargs = mock_store_cls.call_args
    assert kwargs["unlock_reason"] == "a genuinely specific reason"
    assert kwargs["holdout_unlock"] is True
    assert kwargs["usage_log_path"] == tmp_path / "usage.jsonl"
    assert kwargs["holdout_range"] is request.holdout_range


# -- 13. real execution returns list[LabeledRun] mapping to real portfolios -


def _write_synthetic_month(store: TickParquetStore, symbol: str, year: int, month: int) -> None:
    """A small, real, valid tick dataset spanning the whole month at a
    coarse cadence -- enough for BarBuilder to produce 1M/5M/4H bars and
    for Orchestrator.run() to complete, without needing to actually
    generate any trades.
    """
    from datetime import UTC, datetime, timedelta

    start = datetime(year, month, 1, tzinfo=UTC)
    rows = []
    ts = start
    end = start + timedelta(days=27)  # stay within the month regardless of length
    price = 2000.0
    i = 0
    while ts < end:
        wobble = 0.05 * ((i % 21) - 10)
        rows.append({"ts": ts, "bid": price + wobble, "ask": price + wobble + 0.30})
        ts += timedelta(minutes=30)
        i += 1
    ticks_df = pl.DataFrame(rows)
    store.write_month(symbol, year, month, ticks_df)


def test_execute_plan_happy_path_returns_labeled_runs(tmp_path):
    ticks_dir = tmp_path / "ticks"
    write_store = TickParquetStore(ticks_dir, holdout_range=HoldoutRange.none())
    _write_synthetic_month(write_store, "XAUUSD", 2024, 3)

    run_config = RunConfig(
        experiment="phase8-test",
        objective="test",
        guards=Guards(p_vs_baseline_max=0.05, pf_min=1.0, min_trades=1, worst_quarter_r_min=-100.0),
        period=Period(start=date(2024, 3, 1), end=date(2024, 3, 31)),
        holdout=Holdout(last_months=6, unlocked=False),
        walk_forward=WalkForward(train_months=9, test_months=3),
        arms=Arms(entry_models=("M2",), sl_anchors=("S_body",)),
        baseline=Baseline(n_sims=10, seed=1),
        seed=42,
    )
    request = ExecutionRequest(
        run_id="phase8-happy-path-test",
        run_config=run_config,
        ticks_dir=ticks_dir,
        holdout_range=HoldoutRange.none(),
        rules=load_rules_v1(),
        parameters=load_parameters(),
        split_type="fixture",
    )
    plan = plan_execution(request)
    assert plan.holdout_overlap is False

    journal_path = tmp_path / "journal.duckdb"
    result = execute_plan(plan, journal_path)

    assert isinstance(result, list)
    assert len(result) >= 1
    for labeled_run in result:
        assert isinstance(labeled_run, LabeledRun)
        assert labeled_run.run_id == "phase8-happy-path-test"
        assert labeled_run.split_type == "fixture"
        assert labeled_run.portfolio_id  # non-empty


# -- 14. execute_plan requires an ExecutionPlan, never a raw Request -------


def test_execute_plan_rejects_raw_execution_request():
    request = _make_request(period_start=date(2024, 1, 1), period_end=date(2024, 1, 31))
    with pytest.raises(AttributeError):
        execute_plan(request, Path("unused.duckdb"))  # type: ignore[arg-type]


# -- source guards: no direct writes, no experiment coupling ---------------


def test_no_direct_journal_record_calls():
    source = EXECUTION_REQUEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_methods = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "record" not in called_methods


def test_no_experiment_module_import():
    source = EXECUTION_REQUEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
    assert "src.research.experiment" not in imported_modules
    assert not any(m.startswith("src.research.experiment") for m in imported_modules)


_FORBIDDEN_VERDICT_FIELD_NAMES = {
    "significant", "verdict", "recommendation", "candidate", "rejected",
    "promising", "best", "promotion", "validation_passed", "approved", "passed",
}


def test_no_verdict_fields_in_dataclasses():
    source = EXECUTION_REQUEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    field_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_names.add(item.target.id)
    overlap = field_names & _FORBIDDEN_VERDICT_FIELD_NAMES
    assert not overlap, f"execution_request.py dataclasses contain verdict-like fields: {overlap}"
