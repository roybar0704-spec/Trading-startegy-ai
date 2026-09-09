"""Unit/integration tests for src/backtest/walk_forward.py -- the Phase 9
Walk-Forward / OOS execution driver (Research System).

Not under tests/research/: this module is Strategy-A-specific execution
glue, matching execution_request.py's own established boundary and its
test file's own location. Mocks execute_plan() (patched in
src.backtest.walk_forward's own namespace) for pure request-mapping/
sequencing/fail-fast tests -- plan_execution() itself is left real and
unmocked throughout since it is pure, no-I/O computation, exactly as
test_execution_request.py already does. One real end-to-end integration
test uses genuine split_plan()-generated Splits, real load_rules_v1()/
load_parameters(), and real synthetic ticks written via
TickParquetStore.write_month().
"""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest

from src.backtest.walk_forward import WalkForwardWindowResult, run_walk_forward
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
from src.research.validation import LabeledRun, Split, split_plan

REPO_ROOT = Path(__file__).resolve().parents[1]
WALK_FORWARD_PATH = REPO_ROOT / "src" / "backtest" / "walk_forward.py"


def _dt(y: int, m: int, d: int = 1) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


def _make_split(*, train_start, train_end, test_start, test_end) -> Split:
    return Split(train_start=train_start, train_end=train_end, test_start=test_start, test_end=test_end)


def _make_run_config(seed: int = 42) -> RunConfig:
    return RunConfig(
        experiment="phase9-test",
        objective="test",
        guards=Guards(p_vs_baseline_max=0.05, pf_min=1.0, min_trades=1, worst_quarter_r_min=-100.0),
        period=Period(start=date(2024, 1, 1), end=date(2024, 4, 1)),
        holdout=Holdout(last_months=6, unlocked=False),
        walk_forward=WalkForward(train_months=1, test_months=1),
        arms=Arms(entry_models=("M2",), sl_anchors=("S_body",)),
        baseline=Baseline(n_sims=10, seed=1),
        seed=seed,
    )


def _fake_execute_plan_factory():
    """Returns a MagicMock execute_plan() stand-in that produces one
    LabeledRun per call, echoing the request's run_id/split_type, so
    tests can assert on the ExecutionRequest actually constructed per
    window without touching TickParquetStore/Orchestrator/Journal.
    """

    def _side_effect(plan, journal_path, *, holdout_unlock=False, usage_log_path=None, unlock_reason=""):
        return [
            LabeledRun(run_id=plan.request.run_id, portfolio_id="fake-portfolio", split_type=plan.request.split_type)
        ]

    return MagicMock(side_effect=_side_effect)


# -- 1. deterministic Split -> test-period request mapping -----------------


def test_test_period_derivation_excludes_train_and_next_month(monkeypatch):
    mock_execute = _fake_execute_plan_factory()
    monkeypatch.setattr("src.backtest.walk_forward.execute_plan", mock_execute)

    split = _make_split(
        train_start=_dt(2024, 1), train_end=_dt(2024, 3),
        test_start=_dt(2024, 3), test_end=_dt(2024, 6),
    )
    run_walk_forward(
        [split],
        run_config=_make_run_config(),
        ticks_dir=Path("unused"),
        holdout_range=HoldoutRange.none(),
        rules=object(),
        parameters=object(),
        journal_path=Path("unused.duckdb"),
        run_id_prefix="wf-test",
    )

    plan_used = mock_execute.call_args[0][0]
    assert plan_used.request.run_config.period == Period(start=date(2024, 3, 1), end=date(2024, 5, 31))


# -- 2. split_type is always walk_forward_test ------------------------------


def test_split_type_always_walk_forward_test(monkeypatch):
    mock_execute = _fake_execute_plan_factory()
    monkeypatch.setattr("src.backtest.walk_forward.execute_plan", mock_execute)

    splits = [
        _make_split(train_start=_dt(2024, 1), train_end=_dt(2024, 2), test_start=_dt(2024, 2), test_end=_dt(2024, 3)),
        _make_split(train_start=_dt(2024, 2), train_end=_dt(2024, 3), test_start=_dt(2024, 3), test_end=_dt(2024, 4)),
    ]
    run_walk_forward(
        splits,
        run_config=_make_run_config(),
        ticks_dir=Path("unused"),
        holdout_range=HoldoutRange.none(),
        rules=object(),
        parameters=object(),
        journal_path=Path("unused.duckdb"),
        run_id_prefix="wf-test",
    )

    for c in mock_execute.call_args_list:
        assert c[0][0].request.split_type == "walk_forward_test"


# -- 3. unique, deterministic run IDs ---------------------------------------


def test_run_ids_unique_and_deterministic(monkeypatch):
    mock_execute = _fake_execute_plan_factory()
    monkeypatch.setattr("src.backtest.walk_forward.execute_plan", mock_execute)

    splits = [
        _make_split(train_start=_dt(2024, 1), train_end=_dt(2024, 2), test_start=_dt(2024, 2), test_end=_dt(2024, 3)),
        _make_split(train_start=_dt(2024, 2), train_end=_dt(2024, 3), test_start=_dt(2024, 3), test_end=_dt(2024, 4)),
    ]
    run_walk_forward(
        splits,
        run_config=_make_run_config(),
        ticks_dir=Path("unused"),
        holdout_range=HoldoutRange.none(),
        rules=object(),
        parameters=object(),
        journal_path=Path("unused.duckdb"),
        run_id_prefix="wf-test",
    )

    run_ids = [c[0][0].request.run_id for c in mock_execute.call_args_list]
    assert len(run_ids) == len(set(run_ids))
    assert run_ids == ["wf-test_w000_202402_202402", "wf-test_w001_202403_202403"]


# -- 4. empty splits returns [] without execution ---------------------------


def test_empty_splits_returns_empty_without_execution(monkeypatch):
    mock_execute = _fake_execute_plan_factory()
    monkeypatch.setattr("src.backtest.walk_forward.execute_plan", mock_execute)

    result = run_walk_forward(
        [],
        run_config=_make_run_config(),
        ticks_dir=Path("unused"),
        holdout_range=HoldoutRange.none(),
        rules=object(),
        parameters=object(),
        journal_path=Path("unused.duckdb"),
        run_id_prefix="wf-test",
    )

    assert result == []
    mock_execute.assert_not_called()


# -- 5/10. multiple windows, sequential order --------------------------------


def test_multiple_windows_executed_in_input_order(monkeypatch):
    mock_execute = _fake_execute_plan_factory()
    monkeypatch.setattr("src.backtest.walk_forward.execute_plan", mock_execute)

    splits = [
        _make_split(train_start=_dt(2024, 1), train_end=_dt(2024, 2), test_start=_dt(2024, 2), test_end=_dt(2024, 3)),
        _make_split(train_start=_dt(2024, 2), train_end=_dt(2024, 3), test_start=_dt(2024, 3), test_end=_dt(2024, 4)),
        _make_split(train_start=_dt(2024, 3), train_end=_dt(2024, 4), test_start=_dt(2024, 4), test_end=_dt(2024, 5)),
    ]
    results = run_walk_forward(
        splits,
        run_config=_make_run_config(),
        ticks_dir=Path("unused"),
        holdout_range=HoldoutRange.none(),
        rules=object(),
        parameters=object(),
        journal_path=Path("unused.duckdb"),
        run_id_prefix="wf-test",
    )

    assert len(results) == 3
    assert [r.split.test_start for r in results] == [s.test_start for s in splits]
    for r in results:
        assert isinstance(r, WalkForwardWindowResult)
        assert len(r.labeled_runs) == 1


# -- 6/11. Train metadata / provenance preserved unmodified -----------------


def test_train_metadata_preserved_unmodified(monkeypatch):
    mock_execute = _fake_execute_plan_factory()
    monkeypatch.setattr("src.backtest.walk_forward.execute_plan", mock_execute)

    split = _make_split(
        train_start=_dt(2024, 1), train_end=_dt(2024, 4),
        test_start=_dt(2024, 4), test_end=_dt(2024, 7),
    )
    results = run_walk_forward(
        [split],
        run_config=_make_run_config(),
        ticks_dir=Path("unused"),
        holdout_range=HoldoutRange.none(),
        rules=object(),
        parameters=object(),
        journal_path=Path("unused.duckdb"),
        run_id_prefix="wf-test",
    )

    assert results[0].split == split
    assert results[0].split.train_start == _dt(2024, 1)
    assert results[0].split.train_end == _dt(2024, 4)


# -- 7. holdout fail-closed, fail-fast on overlap ----------------------------


def test_holdout_overlap_without_unlock_stops_before_data_loading():
    holdout_range = HoldoutRange(start=_dt(2025, 7), end=_dt(2025, 12, 31))
    splits = [
        _make_split(train_start=_dt(2025, 5), train_end=_dt(2025, 7), test_start=_dt(2025, 7), test_end=_dt(2025, 8)),
        _make_split(train_start=_dt(2025, 6), train_end=_dt(2025, 8), test_start=_dt(2025, 8), test_end=_dt(2025, 9)),
    ]

    with pytest.raises(ValueError, match="holdout_overlap is True but holdout_unlock=False"):
        run_walk_forward(
            splits,
            run_config=_make_run_config(),
            ticks_dir=Path("this-directory-does-not-exist-and-must-never-be-touched"),
            holdout_range=holdout_range,
            rules=load_rules_v1(),
            parameters=load_parameters(),
            journal_path=Path("unused.duckdb"),
            run_id_prefix="wf-holdout-test",
        )


# -- fail-fast: a later window's exception stops execution of any window after it


def test_fail_fast_stops_remaining_windows(monkeypatch):
    call_count = {"n": 0}

    def _side_effect(plan, journal_path, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("window-2-boom")
        return [LabeledRun(run_id=plan.request.run_id, portfolio_id="p", split_type=plan.request.split_type)]

    mock_execute = MagicMock(side_effect=_side_effect)
    monkeypatch.setattr("src.backtest.walk_forward.execute_plan", mock_execute)

    splits = [
        _make_split(train_start=_dt(2024, 1), train_end=_dt(2024, 2), test_start=_dt(2024, 2), test_end=_dt(2024, 3)),
        _make_split(train_start=_dt(2024, 2), train_end=_dt(2024, 3), test_start=_dt(2024, 3), test_end=_dt(2024, 4)),
        _make_split(train_start=_dt(2024, 3), train_end=_dt(2024, 4), test_start=_dt(2024, 4), test_end=_dt(2024, 5)),
    ]

    with pytest.raises(RuntimeError, match="window-2-boom"):
        run_walk_forward(
            splits,
            run_config=_make_run_config(),
            ticks_dir=Path("unused"),
            holdout_range=HoldoutRange.none(),
            rules=object(),
            parameters=object(),
            journal_path=Path("unused.duckdb"),
            run_id_prefix="wf-test",
        )

    assert call_count["n"] == 2  # third window never attempted


# -- 8. explicit unlock propagation, identical across all windows -----------


def test_unlock_params_propagated_unchanged_to_every_window(monkeypatch):
    mock_execute = _fake_execute_plan_factory()
    monkeypatch.setattr("src.backtest.walk_forward.execute_plan", mock_execute)

    splits = [
        _make_split(train_start=_dt(2024, 1), train_end=_dt(2024, 2), test_start=_dt(2024, 2), test_end=_dt(2024, 3)),
        _make_split(train_start=_dt(2024, 2), train_end=_dt(2024, 3), test_start=_dt(2024, 3), test_end=_dt(2024, 4)),
    ]
    usage_log_path = Path("some_log.jsonl")
    run_walk_forward(
        splits,
        run_config=_make_run_config(),
        ticks_dir=Path("unused"),
        holdout_range=HoldoutRange.none(),
        rules=object(),
        parameters=object(),
        journal_path=Path("unused.duckdb"),
        run_id_prefix="wf-test",
        holdout_unlock=True,
        usage_log_path=usage_log_path,
        unlock_reason="a genuinely specific reason",
    )

    for c in mock_execute.call_args_list:
        assert c.kwargs["holdout_unlock"] is True
        assert c.kwargs["usage_log_path"] == usage_log_path
        assert c.kwargs["unlock_reason"] == "a genuinely specific reason"


# -- 9. journal path reused unchanged across all windows ---------------------


def test_journal_path_reused_across_windows(monkeypatch):
    mock_execute = _fake_execute_plan_factory()
    monkeypatch.setattr("src.backtest.walk_forward.execute_plan", mock_execute)

    splits = [
        _make_split(train_start=_dt(2024, 1), train_end=_dt(2024, 2), test_start=_dt(2024, 2), test_end=_dt(2024, 3)),
        _make_split(train_start=_dt(2024, 2), train_end=_dt(2024, 3), test_start=_dt(2024, 3), test_end=_dt(2024, 4)),
    ]
    journal_path = Path("shared_journal.duckdb")
    run_walk_forward(
        splits,
        run_config=_make_run_config(),
        ticks_dir=Path("unused"),
        holdout_range=HoldoutRange.none(),
        rules=object(),
        parameters=object(),
        journal_path=journal_path,
        run_id_prefix="wf-test",
    )

    journal_paths_used = [c[0][1] for c in mock_execute.call_args_list]
    assert journal_paths_used == [journal_path, journal_path]


# -- source guards: no direct writes, no experiment coupling, no verdicts ---


def test_no_direct_journal_calls():
    source = WALK_FORWARD_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_methods = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "record" not in called_methods
    assert "query" not in called_methods


def test_no_experiment_module_import():
    source = WALK_FORWARD_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
    assert not any(m.startswith("src.research.experiment") for m in imported_modules)


_FORBIDDEN_VERDICT_FIELD_NAMES = {
    "significant", "verdict", "recommendation", "candidate", "rejected",
    "promising", "best", "promotion", "validation_passed", "approved", "passed",
}


def test_no_verdict_fields_in_dataclasses():
    source = WALK_FORWARD_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    field_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_names.add(item.target.id)
    overlap = field_names & _FORBIDDEN_VERDICT_FIELD_NAMES
    assert not overlap, f"walk_forward.py dataclasses contain verdict-like fields: {overlap}"


# -- 15. real synthetic multi-window end-to-end test -------------------------


def _write_synthetic_month(store: TickParquetStore, symbol: str, year: int, month: int) -> None:
    start = datetime(year, month, 1, tzinfo=UTC)
    rows = []
    ts = start
    end = start + timedelta(days=27)
    price = 2000.0
    i = 0
    while ts < end:
        wobble = 0.05 * ((i % 21) - 10)
        rows.append({"ts": ts, "bid": price + wobble, "ask": price + wobble + 0.30})
        ts += timedelta(minutes=30)
        i += 1
    store.write_month(symbol, year, month, pl.DataFrame(rows))


def test_run_walk_forward_real_end_to_end_multi_window(tmp_path):
    ticks_dir = tmp_path / "ticks"
    write_store = TickParquetStore(ticks_dir, holdout_range=HoldoutRange.none())
    _write_synthetic_month(write_store, "XAUUSD", 2024, 2)
    _write_synthetic_month(write_store, "XAUUSD", 2024, 3)

    splits = split_plan(_dt(2024, 1), _dt(2024, 4), train_months=1, test_months=1)
    assert len(splits) == 2  # test windows: Feb, Mar

    run_config = RunConfig(
        experiment="phase9-e2e-test",
        objective="test",
        guards=Guards(p_vs_baseline_max=0.05, pf_min=1.0, min_trades=1, worst_quarter_r_min=-100.0),
        period=Period(start=date(2024, 1, 1), end=date(2024, 4, 1)),
        holdout=Holdout(last_months=6, unlocked=False),
        walk_forward=WalkForward(train_months=1, test_months=1),
        arms=Arms(entry_models=("M2",), sl_anchors=("S_body",)),
        baseline=Baseline(n_sims=10, seed=1),
        seed=42,
    )

    results = run_walk_forward(
        splits,
        run_config=run_config,
        ticks_dir=ticks_dir,
        holdout_range=HoldoutRange.none(),
        rules=load_rules_v1(),
        parameters=load_parameters(),
        journal_path=tmp_path / "journal.duckdb",
        run_id_prefix="phase9-e2e",
    )

    assert len(results) == 2
    seen_run_ids: set[str] = set()
    for window_result in results:
        assert isinstance(window_result, WalkForwardWindowResult)
        assert len(window_result.labeled_runs) >= 1
        for labeled_run in window_result.labeled_runs:
            assert isinstance(labeled_run, LabeledRun)
            assert labeled_run.split_type == "walk_forward_test"
            seen_run_ids.add(labeled_run.run_id)
    assert len(seen_run_ids) == 2  # one distinct run_id per window
