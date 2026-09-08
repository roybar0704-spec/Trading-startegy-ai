"""Unit tests for src/research/experiment.py -- the strategy-agnostic
Experiment Model (Research System, Phase 7).

No Journal fixture helpers are needed here: Experiment/declare_experiment/
ExperimentResult take no `journal` parameter and make no database
interaction at all -- unlike every prior research-layer test file, these
tests construct plain Python objects only.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.research.comparison import BaselineComparisonEntry, BaselineComparisonResult
from src.research.experiment import Experiment, ExperimentResult, declare_experiment
from src.research.metrics import FunnelCounts, MetricsResult
from src.research.report import ResearchReport
from src.research.significance import BootstrapComparisonResult
from src.research.validation import LabeledRun, RunComparisonEntry

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_PATH = REPO_ROOT / "src" / "research" / "experiment.py"


# -- minimal, valid instance builders (no Journal involved anywhere) -------


def _minimal_funnel_counts() -> FunnelCounts:
    return FunnelCounts(
        engaged=0, armed=0, orders_placed=0, orders_filled=0, orders_cancelled=0,
        arm_outcomes={}, closed_trades=0,
    )


def _minimal_metrics_result(portfolio_id: str, run_id: str) -> MetricsResult:
    return MetricsResult(
        portfolio_id=portfolio_id,
        run_id=run_id,
        closed_trade_count=0,
        open_trade_count=0,
        trades_available=False,
        win_count=None,
        loss_count=None,
        scratch_count=None,
        win_rate=None,
        gross_pnl=None,
        total_cost_spread=None,
        total_cost_slippage=None,
        total_cost_commission=None,
        total_cost=None,
        net_pnl=None,
        cost_data_note="test fixture",
        expectancy_r=None,
        average_r=None,
        median_r=None,
        profit_factor=None,
        profit_factor_note="test fixture",
        average_duration_min=None,
        average_mae_r=None,
        median_mae_r=None,
        average_mfe_r=None,
        median_mfe_r=None,
        mae_mfe_note="test fixture",
        max_consecutive_wins=None,
        max_consecutive_losses=None,
        exposure_avg_open_risk_r=None,
        exposure_note="test fixture",
        funnel=_minimal_funnel_counts(),
    )


def _minimal_run_comparison_entry(run_id: str, portfolio_id: str, split_type: str) -> RunComparisonEntry:
    return RunComparisonEntry(
        run_id=run_id,
        portfolio_id=portfolio_id,
        split_type=split_type,
        config_hash="test-hash",
        code_version="test-version",
        data_version="test-data",
        metrics=_minimal_metrics_result(portfolio_id, run_id),
    )


def _minimal_report() -> ResearchReport:
    return ResearchReport(sections=[], comparison=None, holdout_usage=None, notes=["test fixture"])


def _minimal_comparison_result() -> BaselineComparisonResult:
    baseline_entry = _minimal_run_comparison_entry("RUN-BASE", "PORT-BASE", "in_sample")
    candidate_entry = BaselineComparisonEntry(
        run_id="RUN-CAND",
        portfolio_id="PORT-CAND",
        split_type="in_sample",
        config_hash="test-hash",
        code_version="test-version",
        data_version="test-data",
        metrics=_minimal_metrics_result("PORT-CAND", "RUN-CAND"),
        deltas=[],
    )
    return BaselineComparisonResult(baseline=baseline_entry, candidates=[candidate_entry], note="test fixture")


def _minimal_significance_result() -> BootstrapComparisonResult:
    return BootstrapComparisonResult(
        comparison_kind="one_sample",
        statistic_name="mean_result_r",
        sample_size_a=0,
        sample_size_b=None,
        available=False,
        observed_statistic=None,
        confidence_level=0.95,
        ci_low=None,
        ci_high=None,
        p_value=None,
        alpha=0.05,
        n_resamples=10_000,
        seed=1,
        comparison_count=None,
        notes=["test fixture"],
    )


# -- 1. valid construction --------------------------------------------------


def test_valid_experiment_construction():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    candidate = LabeledRun(run_id="RUN-CAND", portfolio_id="PORT-CAND", split_type="walk_forward_test")

    experiment = declare_experiment(
        "does condition X improve expectancy?",
        "average_r",
        baseline,
        [candidate],
        changed_variables={"filter": "added session window filter"},
        fixed_variables={"entry_model": "M2", "sl_anchor": "S_body"},
    )

    assert isinstance(experiment, Experiment)
    assert experiment.hypothesis == "does condition X improve expectancy?"
    assert experiment.objective == "average_r"


# -- 2/3. hypothesis rejection -----------------------------------------


def test_empty_hypothesis_rejected():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    with pytest.raises(ValueError, match="hypothesis"):
        declare_experiment("", "average_r", baseline, [], changed_variables={}, fixed_variables={})


def test_whitespace_only_hypothesis_rejected():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    with pytest.raises(ValueError, match="hypothesis"):
        declare_experiment("   ", "average_r", baseline, [], changed_variables={}, fixed_variables={})


# -- 4/5. objective rejection --------------------------------------------


def test_empty_objective_rejected():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    with pytest.raises(ValueError, match="objective"):
        declare_experiment("a real hypothesis", "", baseline, [], changed_variables={}, fixed_variables={})


def test_whitespace_only_objective_rejected():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    with pytest.raises(ValueError, match="objective"):
        declare_experiment("a real hypothesis", "  \t ", baseline, [], changed_variables={}, fixed_variables={})


# -- 6/7. baseline and candidates carried exactly ---------------------------


def test_baseline_reused_exactly_as_supplied():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    experiment = declare_experiment(
        "h", "o", baseline, [], changed_variables={}, fixed_variables={}
    )
    assert experiment.baseline is baseline


def test_candidates_carried_exactly_as_supplied():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    c1 = LabeledRun(run_id="RUN-C1", portfolio_id="PORT-C1", split_type="walk_forward_test")
    c2 = LabeledRun(run_id="RUN-C2", portfolio_id="PORT-C2", split_type="holdout")
    candidates = [c1, c2]

    experiment = declare_experiment(
        "h", "o", baseline, candidates, changed_variables={}, fixed_variables={}
    )

    assert experiment.candidates is candidates
    assert experiment.candidates == [c1, c2]


# -- 8/9. changed/fixed variables carried exactly ----------------------------


def test_changed_variables_carried_exactly_as_supplied():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    changed = {"stop_loss_anchor": "S_body -> R_body"}

    experiment = declare_experiment(
        "h", "o", baseline, [], changed_variables=changed, fixed_variables={}
    )

    assert experiment.changed_variables is changed
    assert experiment.changed_variables == {"stop_loss_anchor": "S_body -> R_body"}


def test_fixed_variables_carried_exactly_as_supplied():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    fixed = {"entry_model": "M2", "symbol": "XAUUSD"}

    experiment = declare_experiment(
        "h", "o", baseline, [], changed_variables={}, fixed_variables=fixed
    )

    assert experiment.fixed_variables is fixed
    assert experiment.fixed_variables == {"entry_model": "M2", "symbol": "XAUUSD"}


# -- 10/11. ExperimentResult bundling ----------------------------------------


def test_experiment_result_with_all_outputs():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    experiment = declare_experiment("h", "o", baseline, [], changed_variables={}, fixed_variables={})

    report = _minimal_report()
    comparison = _minimal_comparison_result()
    significance = [_minimal_significance_result()]

    result = ExperimentResult(
        experiment=experiment, report=report, comparison=comparison,
        significance=significance, notes=["bundled for review"],
    )

    assert result.experiment is experiment
    assert result.report is report
    assert result.comparison is comparison
    assert result.significance is significance
    assert result.notes == ["bundled for review"]


def test_experiment_result_with_report_and_comparison_absent():
    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    experiment = declare_experiment("h", "o", baseline, [], changed_variables={}, fixed_variables={})

    result = ExperimentResult(
        experiment=experiment, report=None, comparison=None, significance=[], notes=[],
    )

    assert result.report is None
    assert result.comparison is None
    assert result.significance == []


# -- 12. no verdict fields ---------------------------------------------------


_FORBIDDEN_VERDICT_FIELD_NAMES = {
    "significant", "verdict", "recommendation", "candidate", "rejected",
    "promising", "best", "promotion", "validation_passed", "approved", "passed",
}


def test_no_verdict_fields_in_dataclasses():
    source = EXPERIMENT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    field_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_names.add(item.target.id)

    overlap = field_names & _FORBIDDEN_VERDICT_FIELD_NAMES
    assert not overlap, f"experiment.py dataclasses contain verdict-like fields: {overlap}"


def test_experiment_module_imports_are_strategy_agnostic():
    source = EXPERIMENT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    allowed = {
        "__future__", "dataclasses",
        "src.research.comparison", "src.research.report",
        "src.research.significance", "src.research.validation",
    }
    unexpected = imported_modules - allowed
    assert not unexpected, f"experiment.py has unexpected/strategy-specific imports: {unexpected}"


# -- 13/14. no Journal access, no filesystem writes --------------------------


def _method_call_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def test_no_journal_access():
    source = EXPERIMENT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_methods = _method_call_names(tree)
    assert "query" not in called_methods
    assert "record" not in called_methods
    # stronger check specific to this module: no `journal` parameter exists
    # anywhere in its function signatures
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            arg_names = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
            assert "journal" not in arg_names, f"{node.name} unexpectedly takes a journal parameter"


def test_no_filesystem_writes():
    source = EXPERIMENT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_methods = _method_call_names(tree)
    forbidden_methods = {"write_text", "write_bytes", "write", "open"}
    assert not (called_methods & forbidden_methods)


# -- 15. no split_type inference/relabeling ----------------------------------


def test_no_split_type_inference_or_relabeling():
    """Source guard: experiment.py must never compare against or branch
    on split_type -- it only carries already-labeled LabeledRun objects
    through opaquely, never inspecting or relabeling their split_type.
    """
    source = EXPERIMENT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for operand in (node.left, *node.comparators):
                operand_name = (
                    operand.id
                    if isinstance(operand, ast.Name)
                    else operand.attr
                    if isinstance(operand, ast.Attribute)
                    else None
                )
                assert operand_name != "split_type", (
                    "experiment.py must never compare against split_type"
                )
