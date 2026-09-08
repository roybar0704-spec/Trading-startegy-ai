"""Unit tests for src/research/comparison.py -- the strategy-agnostic
Baseline / Comparison layer (Research System, Phase 4).

Journal fixture helpers are duplicated from tests/research/test_validation.py's
established pattern (that file is not a shared fixture module, and this
phase's scope forbids refactoring it).
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.journal.duckdb_writer import DuckDBJournal
from src.research.comparison import (
    BaselineComparisonResult,
    MetricDelta,
    compare_to_baseline,
)
from src.research.validation import LabeledRun

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"
COMPARISON_PATH = REPO_ROOT / "src" / "research" / "comparison.py"

_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)


# -- Journal fixture helpers (duplicated from test_validation.py's pattern) --


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


def _find_delta(deltas: list[MetricDelta], metric_name: str) -> MetricDelta:
    for d in deltas:
        if d.metric_name == metric_name:
            return d
    raise KeyError(metric_name)


# -- 1. baseline vs one candidate ------------------------------------------


def test_baseline_vs_one_candidate_correct_deltas(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, entry_px=2000.0, exit_px=2010.0, result_r=0.2)
    _insert_portfolio(journal, "PORT-CAND", "RUN-CAND")
    _make_closed_trade(journal, "PORT-CAND", "RUN-CAND", 0, entry_px=2000.0, exit_px=2030.0, result_r=0.5)

    result = compare_to_baseline(
        journal,
        baseline=LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample"),
        candidates=[LabeledRun(run_id="RUN-CAND", portfolio_id="PORT-CAND", split_type="in_sample")],
    )
    journal.close()

    assert isinstance(result, BaselineComparisonResult)
    assert result.baseline.run_id == "RUN-BASE"
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.run_id == "RUN-CAND"

    net_pnl_delta = _find_delta(candidate.deltas, "net_pnl")
    assert net_pnl_delta.baseline_value == pytest.approx(10.0)
    assert net_pnl_delta.candidate_value == pytest.approx(30.0)
    assert net_pnl_delta.delta == pytest.approx(20.0)

    average_r_delta = _find_delta(candidate.deltas, "average_r")
    assert average_r_delta.delta == pytest.approx(0.3)

    win_rate_delta = _find_delta(candidate.deltas, "win_rate")
    assert win_rate_delta.delta == pytest.approx(0.0)

    trade_count_delta = _find_delta(candidate.deltas, "closed_trade_count")
    assert trade_count_delta.delta == 0


# -- 2. multiple candidates against one baseline ---------------------------


def test_multiple_candidates_compared_independently_against_baseline(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, entry_px=2000.0, exit_px=2010.0, result_r=0.2)  # net_pnl=10
    _insert_portfolio(journal, "PORT-C1", "RUN-C1")
    _make_closed_trade(journal, "PORT-C1", "RUN-C1", 0, entry_px=2000.0, exit_px=2030.0, result_r=0.5)  # net_pnl=30
    _insert_portfolio(journal, "PORT-C2", "RUN-C2")
    _make_closed_trade(journal, "PORT-C2", "RUN-C2", 0, entry_px=2000.0, exit_px=1995.0, result_r=-0.1)  # net_pnl=-5

    result = compare_to_baseline(
        journal,
        baseline=LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample"),
        candidates=[
            LabeledRun(run_id="RUN-C1", portfolio_id="PORT-C1", split_type="walk_forward_test"),
            LabeledRun(run_id="RUN-C2", portfolio_id="PORT-C2", split_type="walk_forward_test"),
        ],
    )
    journal.close()

    assert len(result.candidates) == 2
    by_run = {c.run_id: c for c in result.candidates}
    assert _find_delta(by_run["RUN-C1"].deltas, "net_pnl").delta == pytest.approx(20.0)  # 30 - 10
    assert _find_delta(by_run["RUN-C2"].deltas, "net_pnl").delta == pytest.approx(-15.0)  # -5 - 10
    # each candidate's deltas are independent of the other candidate
    assert by_run["RUN-C1"].metrics.net_pnl != by_run["RUN-C2"].metrics.net_pnl


# -- 3. portfolio isolation --------------------------------------------------


def test_portfolio_isolation(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, result_r=0.1)
    _insert_portfolio(journal, "PORT-CAND", "RUN-CAND")
    _make_closed_trade(journal, "PORT-CAND", "RUN-CAND", 0, result_r=0.2)
    # unrelated third portfolio -- must never appear in the result
    _insert_portfolio(journal, "PORT-OTHER", "RUN-OTHER")
    _make_closed_trade(journal, "PORT-OTHER", "RUN-OTHER", 0, result_r=999.0, entry_px=2000.0, exit_px=999999.0)

    result = compare_to_baseline(
        journal,
        baseline=LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample"),
        candidates=[LabeledRun(run_id="RUN-CAND", portfolio_id="PORT-CAND", split_type="in_sample")],
    )
    journal.close()

    all_run_ids = {result.baseline.run_id} | {c.run_id for c in result.candidates}
    assert all_run_ids == {"RUN-BASE", "RUN-CAND"}
    assert "RUN-OTHER" not in all_run_ids


# -- 4. different split_type values -----------------------------------------


def test_different_split_types_preserved_without_filtering(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, result_r=0.1)
    _insert_portfolio(journal, "PORT-CAND", "RUN-CAND")
    _make_closed_trade(journal, "PORT-CAND", "RUN-CAND", 0, result_r=0.2)

    result = compare_to_baseline(
        journal,
        baseline=LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample"),
        candidates=[LabeledRun(run_id="RUN-CAND", portfolio_id="PORT-CAND", split_type="holdout")],
    )
    journal.close()

    assert result.baseline.split_type == "in_sample"
    assert result.candidates[0].split_type == "holdout"
    # comparison proceeded despite the mismatched split_type -- no filtering occurred
    assert len(result.candidates) == 1


# -- 5. provenance preservation -----------------------------------------------


def test_provenance_preserved_unaltered(tmp_path):
    journal = _open_journal(tmp_path)
    _ensure_run(journal, "RUN-BASE", config_hash="hash-base", code_version="ver-base", data_version="data-base")
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, result_r=0.1)
    _ensure_run(journal, "RUN-CAND", config_hash="hash-cand", code_version="ver-cand", data_version="data-cand")
    _insert_portfolio(journal, "PORT-CAND", "RUN-CAND")
    _make_closed_trade(journal, "PORT-CAND", "RUN-CAND", 0, result_r=0.2)

    result = compare_to_baseline(
        journal,
        baseline=LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample"),
        candidates=[LabeledRun(run_id="RUN-CAND", portfolio_id="PORT-CAND", split_type="in_sample")],
    )
    journal.close()

    assert result.baseline.config_hash == "hash-base"
    assert result.baseline.code_version == "ver-base"
    assert result.baseline.data_version == "data-base"
    candidate = result.candidates[0]
    assert candidate.run_id == "RUN-CAND"
    assert candidate.portfolio_id == "PORT-CAND"
    assert candidate.split_type == "in_sample"
    assert candidate.config_hash == "hash-cand"
    assert candidate.code_version == "ver-cand"
    assert candidate.data_version == "data-cand"


# -- 6/7. unknown baseline/candidate run -------------------------------------


def test_unknown_baseline_run_raises(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-CAND", "RUN-CAND")
    _make_closed_trade(journal, "PORT-CAND", "RUN-CAND", 0, result_r=0.1)

    with pytest.raises(ValueError, match="unknown run_id"):
        compare_to_baseline(
            journal,
            baseline=LabeledRun(run_id="NO-SUCH-RUN", portfolio_id="PORT-X", split_type="in_sample"),
            candidates=[LabeledRun(run_id="RUN-CAND", portfolio_id="PORT-CAND", split_type="in_sample")],
        )
    journal.close()


def test_unknown_candidate_run_raises(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, result_r=0.1)

    with pytest.raises(ValueError, match="unknown run_id"):
        compare_to_baseline(
            journal,
            baseline=LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample"),
            candidates=[LabeledRun(run_id="NO-SUCH-RUN", portfolio_id="PORT-X", split_type="in_sample")],
        )
    journal.close()


# -- 8. unavailable metrics ----------------------------------------------


def test_unavailable_metrics_delta_stays_none(tmp_path):
    """Baseline has zero closed trades (trades_available=False) -- every
    rate/R/P&L-based MetricsResult field is None there, so those deltas
    must stay None, never a fabricated zero. closed_trade_count, however,
    is always a real int (0) even when unavailable, so its delta IS
    computed normally -- this test verifies both behaviors precisely.
    """
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")  # zero trades
    _insert_portfolio(journal, "PORT-CAND", "RUN-CAND")
    _make_closed_trade(journal, "PORT-CAND", "RUN-CAND", 0, entry_px=2000.0, exit_px=2010.0, result_r=0.2)

    result = compare_to_baseline(
        journal,
        baseline=LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample"),
        candidates=[LabeledRun(run_id="RUN-CAND", portfolio_id="PORT-CAND", split_type="in_sample")],
    )
    journal.close()

    assert result.baseline.metrics.trades_available is False
    candidate = result.candidates[0]

    net_pnl_delta = _find_delta(candidate.deltas, "net_pnl")
    assert net_pnl_delta.baseline_value is None
    assert net_pnl_delta.delta is None

    win_rate_delta = _find_delta(candidate.deltas, "win_rate")
    assert win_rate_delta.baseline_value is None
    assert win_rate_delta.delta is None

    # closed_trade_count is never None -- 0 for an empty portfolio -- so its
    # delta IS computed normally.
    trade_count_delta = _find_delta(candidate.deltas, "closed_trade_count")
    assert trade_count_delta.baseline_value == 0
    assert trade_count_delta.delta == 1


# -- 9. MAE/MFE unavailable -----------------------------------------------


def test_mae_mfe_unavailable_delta_stays_none(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, result_r=0.1)  # mae_r/mfe_r default to None
    _insert_portfolio(journal, "PORT-CAND", "RUN-CAND")
    _make_closed_trade(journal, "PORT-CAND", "RUN-CAND", 0, result_r=0.2)

    result = compare_to_baseline(
        journal,
        baseline=LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample"),
        candidates=[LabeledRun(run_id="RUN-CAND", portfolio_id="PORT-CAND", split_type="in_sample")],
    )
    journal.close()

    candidate = result.candidates[0]
    mae_delta = _find_delta(candidate.deltas, "average_mae_r")
    mfe_delta = _find_delta(candidate.deltas, "average_mfe_r")
    assert mae_delta.baseline_value is None and mae_delta.candidate_value is None and mae_delta.delta is None
    assert mfe_delta.baseline_value is None and mfe_delta.candidate_value is None and mfe_delta.delta is None


# -- 10. profit_factor=None -------------------------------------------------


def test_profit_factor_none_on_baseline_delta_stays_none(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    # all-winners baseline -> profit_factor is None (no losing trades)
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, entry_px=2000.0, exit_px=2010.0, result_r=0.1)
    _insert_portfolio(journal, "PORT-CAND", "RUN-CAND")
    _make_closed_trade(journal, "PORT-CAND", "RUN-CAND", 0, entry_px=2000.0, exit_px=2010.0, result_r=0.1)
    _make_closed_trade(journal, "PORT-CAND", "RUN-CAND", 1, entry_px=2000.0, exit_px=1995.0, result_r=-0.1)

    result = compare_to_baseline(
        journal,
        baseline=LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample"),
        candidates=[LabeledRun(run_id="RUN-CAND", portfolio_id="PORT-CAND", split_type="in_sample")],
    )
    journal.close()

    assert result.baseline.metrics.profit_factor is None
    candidate = result.candidates[0]
    assert candidate.metrics.profit_factor is not None
    pf_delta = _find_delta(candidate.deltas, "profit_factor")
    assert pf_delta.baseline_value is None
    assert pf_delta.candidate_value is not None
    assert pf_delta.delta is None


# -- 11. no automatic baseline discovery -------------------------------------


def _method_call_names(tree: ast.AST) -> set[str]:
    """Names of methods actually CALLED as obj.method(...) anywhere in the
    AST -- i.e. real ast.Call nodes whose function is an attribute access.
    Ignores docstrings/comments/string literals entirely, since those are
    not Call nodes.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def _docstring_string_nodes(tree: ast.AST) -> set[int]:
    """id() of every Constant string node that IS a module/class/function
    docstring -- excluded from the executable-literal scan below."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _executable_string_literals(tree: ast.AST, value: str) -> list[ast.Constant]:
    """Every ast.Constant string node exactly equal to `value` that is NOT
    part of a docstring -- an actual literal in executable code (a
    comparison, an assignment, a call argument, ...), not explanatory
    prose.
    """
    docstring_ids = _docstring_string_nodes(tree)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == value and id(node) not in docstring_ids
    ]


def _comparisons_involving_name(tree: ast.AST, name: str) -> list[ast.Compare]:
    """Every ast.Compare node where an operand is a Name/Attribute called
    `name` -- an actual executable comparison against that identifier/
    field, not a mere field declaration or keyword-argument passthrough
    (neither of which is a Compare node).
    """
    matches: list[ast.Compare] = []
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
                if operand_name == name:
                    matches.append(node)
                    break
    return matches


def test_no_automatic_baseline_discovery():
    """Source guard: comparison.py must make no executable Journal query
    call, no executable comparison against split_type, and no executable
    "baseline" string literal outside its own docstring -- every read
    happens inside the reused validation.compare_runs(), and the baseline
    is always the caller-supplied argument, never discovered/filtered/
    selected here. AST-based (real Call/Compare/Constant nodes), not raw
    text, so the module's own explanatory docstring cannot cause a false
    positive.
    """
    source = COMPARISON_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    called_methods = _method_call_names(tree)
    assert "query" not in called_methods

    split_type_comparisons = _comparisons_involving_name(tree, "split_type")
    assert split_type_comparisons == []

    baseline_literals = _executable_string_literals(tree, "baseline")
    assert baseline_literals == []


# -- 12. no verdict/significance fields --------------------------------------


_FORBIDDEN_VERDICT_FIELD_NAMES = {
    "validation_passed", "candidate", "best", "better", "promising", "rejected", "verdict", "passed",
    "significant", "p_value",
}


def test_no_verdict_fields_in_dataclasses():
    source = COMPARISON_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    field_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_names.add(item.target.id)

    overlap = field_names & _FORBIDDEN_VERDICT_FIELD_NAMES
    assert not overlap, f"comparison.py dataclasses contain verdict-like fields: {overlap}"


# -- 13. strategy-agnostic imports -------------------------------------------


def test_comparison_module_imports_are_strategy_agnostic():
    source = COMPARISON_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    allowed = {"__future__", "dataclasses", "src.research.metrics", "src.research.validation"}
    unexpected = imported_modules - allowed
    assert not unexpected, f"comparison.py has unexpected/strategy-specific imports: {unexpected}"


# -- 14. read-only behavior --------------------------------------------------


def test_comparison_module_never_writes_to_journal():
    """Source guard: comparison.py must never call Journal.record()."""
    source = COMPARISON_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    called_methods = _method_call_names(tree)
    assert "record" not in called_methods
