"""Unit tests for src/research/report.py -- the strategy-agnostic Research
Report layer (Research System, Phase 5).

Journal fixture helpers are duplicated from tests/research/test_comparison.py's
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
from src.research.report import ResearchReport, ResearchReportSection, build_report
from src.research.validation import LabeledRun

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"
REPORT_PATH = REPO_ROOT / "src" / "research" / "report.py"

_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)  # a Monday


# -- Journal fixture helpers (duplicated from test_comparison.py's pattern) --


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


# -- 1/2. single/multiple runs -----------------------------------------------


def test_single_run_produces_one_section(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.2)

    report = build_report(journal, [LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")])
    journal.close()

    assert isinstance(report, ResearchReport)
    assert len(report.sections) == 1
    section = report.sections[0]
    assert isinstance(section, ResearchReportSection)
    assert section.run.run_id == "RUN-A"
    assert section.run.portfolio_id == "PORT-A"
    assert section.run.metrics.closed_trade_count == 1


def test_multiple_runs_produce_multiple_sections(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)
    _insert_portfolio(journal, "PORT-B", "RUN-B")
    _make_closed_trade(journal, "PORT-B", "RUN-B", 0, result_r=0.2)

    report = build_report(
        journal,
        [
            LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample"),
            LabeledRun(run_id="RUN-B", portfolio_id="PORT-B", split_type="in_sample"),
        ],
    )
    journal.close()

    assert len(report.sections) == 2
    run_ids = {s.run.run_id for s in report.sections}
    assert run_ids == {"RUN-A", "RUN-B"}


# -- 3. split-type separation -------------------------------------------------


def test_multiple_split_types_preserved_as_separate_sections(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, entry_px=2000.0, exit_px=2010.0, result_r=0.2)
    _insert_portfolio(journal, "PORT-B", "RUN-B")
    _make_closed_trade(journal, "PORT-B", "RUN-B", 0, entry_px=2000.0, exit_px=1990.0, result_r=-0.2)

    report = build_report(
        journal,
        [
            LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample"),
            LabeledRun(run_id="RUN-B", portfolio_id="PORT-B", split_type="holdout"),
        ],
    )
    journal.close()

    by_split = {s.run.split_type: s for s in report.sections}
    assert set(by_split) == {"in_sample", "holdout"}
    # independent, never blended -- distinct net_pnl values, each reflecting
    # only its own section's trade
    assert by_split["in_sample"].run.metrics.net_pnl == pytest.approx(10.0)
    assert by_split["holdout"].run.metrics.net_pnl == pytest.approx(-10.0)


# -- 4/5. baseline -------------------------------------------------------


def test_baseline_with_multiple_candidates(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, entry_px=2000.0, exit_px=2010.0, result_r=0.2)
    _insert_portfolio(journal, "PORT-C1", "RUN-C1")
    _make_closed_trade(journal, "PORT-C1", "RUN-C1", 0, entry_px=2000.0, exit_px=2030.0, result_r=0.5)
    _insert_portfolio(journal, "PORT-C2", "RUN-C2")
    _make_closed_trade(journal, "PORT-C2", "RUN-C2", 0, entry_px=2000.0, exit_px=1995.0, result_r=-0.1)

    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    report = build_report(
        journal,
        [
            LabeledRun(run_id="RUN-C1", portfolio_id="PORT-C1", split_type="walk_forward_test"),
            LabeledRun(run_id="RUN-C2", portfolio_id="PORT-C2", split_type="walk_forward_test"),
        ],
        baseline=baseline,
    )
    journal.close()

    assert report.comparison is not None
    assert len(report.comparison.candidates) == 2
    by_run = {c.run_id: c for c in report.comparison.candidates}
    assert by_run["RUN-C1"].deltas
    assert by_run["RUN-C2"].deltas


def test_baseline_none_produces_comparison_none(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)

    report = build_report(journal, [LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")])
    journal.close()

    assert report.comparison is None
    assert any("no baseline supplied" in n for n in report.notes)


# -- 6/7. holdout usage --------------------------------------------------


def test_holdout_log_absent_produces_holdout_usage_none(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)

    report = build_report(journal, [LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")])
    journal.close()

    assert report.holdout_usage is None
    assert any("no holdout usage log supplied" in n for n in report.notes)


def test_holdout_log_supplied_produces_holdout_usage_report(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)

    log_path = tmp_path / "holdout_usage.jsonl"
    entry = {
        "accessed_at": "2026-01-01T00:00:00+00:00",
        "symbol": "XAUUSD",
        "start": "2025-07-01T00:00:00+00:00",
        "end": "2025-08-01T00:00:00+00:00",
        "reason": "test",
    }
    log_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    report = build_report(
        journal,
        [LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")],
        holdout_usage_log_path=log_path,
    )
    journal.close()

    assert report.holdout_usage is not None
    assert report.holdout_usage.log_exists is True
    assert report.holdout_usage.access_count == 1
    assert not any("no holdout usage log supplied" in n for n in report.notes)


# -- 8/9/10. disclosures visible per section, not duplicated -----------------


def test_multiple_comparison_disclosure_visible_per_section(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)

    report = build_report(
        journal,
        [LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")],
        min_sample_size=1,
    )
    journal.close()

    section = report.sections[0]
    assert section.analysis.dimensions_scanned == 6
    assert section.analysis.buckets_scanned > 0
    # not duplicated into report-level notes
    assert not any("dimensions" in n.lower() or "buckets" in n.lower() for n in report.notes)


def test_insufficient_sample_disclosure_visible_in_section(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    # only 2 trades -- below the default min_sample_size=5
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)
    _make_closed_trade(journal, "PORT-A", "RUN-A", 1, result_r=0.2)

    report = build_report(journal, [LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")])
    journal.close()

    section = report.sections[0]
    monday_bucket = next(b for b in section.analysis.buckets if b.dimension == "day_of_week" and b.bucket_key == "Monday")
    assert monday_bucket.sufficient_sample is False
    assert monday_bucket.trade_count == 2


def test_unavailable_metrics_visible_in_section(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")  # zero trades

    report = build_report(journal, [LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")])
    journal.close()

    assert len(report.sections) == 1
    section = report.sections[0]
    assert section.run.metrics.trades_available is False
    assert section.run.metrics.closed_trade_count == 0


# -- 11. duplicate runs -----------------------------------------------------


def test_duplicate_run_raises_value_error(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    with pytest.raises(ValueError, match="duplicate run"):
        build_report(journal, [run, run])
    journal.close()


# -- 12/13. baseline in/not-in runs -----------------------------------------


def test_baseline_not_in_runs_not_silently_added_to_sections(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, result_r=0.2)

    report = build_report(
        journal,
        [LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")],
        baseline=LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample"),
    )
    journal.close()

    assert len(report.sections) == 1
    assert report.sections[0].run.run_id == "RUN-A"
    assert "RUN-BASE" not in {s.run.run_id for s in report.sections}


def test_baseline_present_in_runs_kept_in_sections_excluded_from_candidates(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-BASE", "RUN-BASE")
    _make_closed_trade(journal, "PORT-BASE", "RUN-BASE", 0, result_r=0.1)
    _insert_portfolio(journal, "PORT-C", "RUN-C")
    _make_closed_trade(journal, "PORT-C", "RUN-C", 0, result_r=0.2)

    baseline = LabeledRun(run_id="RUN-BASE", portfolio_id="PORT-BASE", split_type="in_sample")
    candidate = LabeledRun(run_id="RUN-C", portfolio_id="PORT-C", split_type="in_sample")
    report = build_report(journal, [baseline, candidate], baseline=baseline)
    journal.close()

    # baseline still gets its own section, like any other run
    assert {s.run.run_id for s in report.sections} == {"RUN-BASE", "RUN-C"}
    # but is excluded from the comparison's candidate list
    assert report.comparison is not None
    assert {c.run_id for c in report.comparison.candidates} == {"RUN-C"}


# -- 14. empty runs -----------------------------------------------------


def test_empty_runs_raises_value_error(tmp_path):
    journal = _open_journal(tmp_path)
    with pytest.raises(ValueError, match="runs must not be empty"):
        build_report(journal, [])
    journal.close()


# -- 15/16/17/18. strategy-agnostic / read-only / no-verdict guards ---------


def _method_call_names(tree: ast.AST) -> set[str]:
    """Names of methods actually CALLED as obj.method(...) anywhere in the
    AST -- real ast.Call nodes whose function is an attribute access.
    Ignores docstrings/comments/string literals entirely.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def _bare_call_names(tree: ast.AST) -> set[str]:
    """Names of bare (non-attribute) functions actually CALLED, e.g.
    open(...) -- real ast.Call nodes whose function is a plain Name.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def test_report_module_imports_are_strategy_agnostic():
    source = REPORT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    allowed = {
        "__future__",
        "dataclasses",
        "pathlib",
        "src.research.analysis",
        "src.research.comparison",
        "src.research.validation",
    }
    unexpected = imported_modules - allowed
    assert not unexpected, f"report.py has unexpected/strategy-specific imports: {unexpected}"


def test_report_module_never_writes_to_journal():
    """Source guard: report.py must never make an executable call to
    Journal.record(). AST-based, not raw text.
    """
    source = REPORT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_methods = _method_call_names(tree)
    assert "record" not in called_methods


def test_report_module_makes_no_direct_file_writes():
    """Source guard: report.py must never write to the filesystem itself
    (no open()/write_text()/write_bytes()/write() calls) -- Path is
    imported only for type hints; the one file read in this feature
    (the hold-out log) happens inside the reused holdout_usage_report().
    """
    source = REPORT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_methods = _method_call_names(tree)
    bare_calls = _bare_call_names(tree)
    forbidden_methods = {"write_text", "write_bytes", "write", "open"}
    assert not (called_methods & forbidden_methods)
    assert "open" not in bare_calls


_FORBIDDEN_VERDICT_FIELD_NAMES = {
    "validation_passed", "candidate", "best", "better", "promising", "rejected", "verdict", "passed",
    "significant", "p_value", "approved", "recommendation",
}


def test_no_verdict_fields_in_dataclasses():
    source = REPORT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    field_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_names.add(item.target.id)

    overlap = field_names & _FORBIDDEN_VERDICT_FIELD_NAMES
    assert not overlap, f"report.py dataclasses contain verdict-like fields: {overlap}"
