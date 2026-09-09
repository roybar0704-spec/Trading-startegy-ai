"""Unit tests for src/research/significance.py -- the strategy-agnostic
Statistical Significance / Bootstrap layer (Research System, Phase 6).

Journal fixture helpers are duplicated from tests/research/test_comparison.py's
established pattern (that file is not a shared fixture module, and this
phase's scope forbids refactoring it).
"""

from __future__ import annotations

import ast
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.journal.duckdb_writer import DuckDBJournal
from src.research.significance import (
    BootstrapComparisonResult,
    bootstrap_one_sample,
    bootstrap_two_sample_paired,
    bootstrap_two_sample_unpaired,
)
from src.research.validation import LabeledRun

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"
SIGNIFICANCE_PATH = REPO_ROOT / "src" / "research" / "significance.py"

_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)


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


def _ensure_run(journal: DuckDBJournal, run_id: str, *, split_type: str = "fixture") -> None:
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


def _insert_setup_if_missing(journal: DuckDBJournal, setup_id: str, run_id: str, index: int) -> None:
    if journal.query("SELECT 1 FROM setups WHERE setup_id = ?", [setup_id]):
        return
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


def _make_closed_trade_for_setup(
    journal: DuckDBJournal, portfolio_id: str, run_id: str, index: int, setup_id: str,
    *, result_r: float = 0.1, entry_px: float = 2000.0, exit_px: float = 2010.0,
    units: float = 1.0, side: str = "buy",
) -> None:
    order_id = f"ORDER-{portfolio_id}-{index}"
    trade_id = f"TRADE-{portfolio_id}-{index}"
    entry_ts = _BASE_TS + timedelta(hours=index)
    exit_ts = entry_ts + timedelta(minutes=30)
    _insert_setup_if_missing(journal, setup_id, run_id, index)
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


def _make_closed_trade(
    journal: DuckDBJournal, portfolio_id: str, run_id: str, index: int,
    *, result_r: float = 0.1, entry_px: float = 2000.0, exit_px: float = 2010.0,
    units: float = 1.0, side: str = "buy",
) -> None:
    _make_closed_trade_for_setup(
        journal, portfolio_id, run_id, index, f"SETUP-{portfolio_id}-{index}",
        result_r=result_r, entry_px=entry_px, exit_px=exit_px, units=units, side=side,
    )


def _make_n_trades(journal: DuckDBJournal, portfolio_id: str, run_id: str, result_r_values: list[float]) -> None:
    for i, r in enumerate(result_r_values):
        _make_closed_trade(journal, portfolio_id, run_id, i, result_r=r)


# -- A tiny stub journal for the NULL-setup_id case, which cannot be
# constructed via real inserts (orders.setup_id is schema NOT NULL) ------


class _NullSetupIdStubJournal:
    """Returns a NULL setup_id for the paired-fetch query only; answers
    the portfolio/run identity-check query normally. Used solely to
    exercise significance.py's own fail-closed defensive check, since the
    real schema's NOT NULL constraint makes this state unreachable via
    genuine inserts.
    """

    def __init__(self, run_id: str, portfolio_a: str, portfolio_b: str):
        self._run_id = run_id
        self._portfolio_a = portfolio_a
        self._portfolio_b = portfolio_b

    def query(self, sql: str, params: list | None = None):
        if "FROM portfolios" in sql:
            return [(self._run_id,)]
        if "FROM trades t JOIN orders o" in sql:
            portfolio_id = params[0]
            if portfolio_id == self._portfolio_a:
                return [(None, 0.1), ("SETUP-OK", 0.2)]
            return [("SETUP-OK", 0.3)]
        raise AssertionError(f"unexpected query in stub: {sql}")


def _find_note_containing(result: BootstrapComparisonResult, substring: str) -> bool:
    return any(substring in n for n in result.notes)


# -- 1/8/9/22. deterministic bootstrap, known statistic, CI validity, reproducibility --


def test_one_sample_deterministic_with_fixed_seed(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [1.0, 2.0, 3.0, -1.0, 0.5, 1.5, -0.5, 2.5, 0.0, 1.0])

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    r1 = bootstrap_one_sample(journal, run, seed=42, n_resamples=500)
    r2 = bootstrap_one_sample(journal, run, seed=42, n_resamples=500)
    journal.close()

    assert r1.ci_low == r2.ci_low
    assert r1.ci_high == r2.ci_high
    assert r1.observed_statistic == r2.observed_statistic


def test_known_synthetic_observations_produce_correct_observed_statistic(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [1.0] * 10 + [2.0] * 10 + [3.0] * 10)  # mean == 2.0

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result = bootstrap_one_sample(journal, run, seed=1, n_resamples=500)
    journal.close()

    assert result.observed_statistic == pytest.approx(2.0)


def test_non_degenerate_ci_contains_observed_statistic(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [0.5, -0.3, 1.2, -0.8, 0.1, 0.9, -0.2, 0.4, 1.0, -0.6, 0.3, 0.7])

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result = bootstrap_one_sample(journal, run, seed=7, n_resamples=1000)
    journal.close()

    assert result.available is True
    assert result.ci_low <= result.observed_statistic <= result.ci_high


# -- 2. different seeds ------------------------------------------------


def test_different_seeds_accepted_and_not_forced_identical(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [0.5, -0.3, 1.2, -0.8, 0.1, 0.9, -0.2, 0.4, 1.0, -0.6])

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    r1 = bootstrap_one_sample(journal, run, seed=1, n_resamples=500)
    r2 = bootstrap_one_sample(journal, run, seed=2, n_resamples=500)
    journal.close()

    assert r1.seed == 1
    assert r2.seed == 2
    # not asserting they MUST differ (not guaranteed in principle), but in
    # practice with this data they do -- proves seed actually drives the RNG
    assert (r1.ci_low, r1.ci_high) != (r2.ci_low, r2.ci_high)


# -- 3/4/5. n=0 / n=1 / below floor -----------------------------------


def test_one_sample_n_zero_unavailable(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result = bootstrap_one_sample(journal, run, seed=1)
    journal.close()

    assert result.available is False
    assert result.sample_size_a == 0
    assert result.observed_statistic is None
    assert result.ci_low is None and result.ci_high is None
    assert _find_note_containing(result, "no closed-trade result_r observations")


def test_one_sample_n_one_unavailable(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.5)

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result = bootstrap_one_sample(journal, run, seed=1)
    journal.close()

    assert result.available is False
    assert result.sample_size_a == 1


def test_below_min_sample_size_unavailable(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [0.1, 0.2, 0.3])  # n=3, default floor=10

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result = bootstrap_one_sample(journal, run, seed=1)
    journal.close()

    assert result.available is False
    assert result.sample_size_a == 3
    assert _find_note_containing(result, "below the configured min_sample_size=10")


# -- 6. constant observations / degenerate CI ----------------------------


def test_constant_observations_degenerate_ci_disclosed(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [1.0] * 12)

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result = bootstrap_one_sample(journal, run, seed=1, n_resamples=200)
    journal.close()

    assert result.available is True
    assert result.ci_low == result.ci_high == pytest.approx(1.0)
    assert _find_note_containing(result, "zero variance")


# -- 7. missing result_r exclusion ----------------------------------------


def test_missing_result_r_excluded_not_coerced_to_zero(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [1.0] * 10)
    # one more trade with a NULL result_r (simulates an edge case; excluded, not zeroed)
    _make_closed_trade_for_setup(journal, "PORT-A", "RUN-A", 10, "SETUP-PORT-A-10", result_r=None)

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result = bootstrap_one_sample(journal, run, seed=1, n_resamples=200)
    journal.close()

    assert result.sample_size_a == 10  # NULL excluded, not counted
    assert result.observed_statistic == pytest.approx(1.0)  # unaffected by the excluded NULL
    assert _find_note_containing(result, "1 trade(s) with missing result_r were excluded")


# -- 10/11. unpaired comparison + direction ------------------------------


def test_unpaired_comparison_direction(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [0.1] * 10)  # mean 0.1
    _insert_portfolio(journal, "PORT-B", "RUN-B")
    _make_n_trades(journal, "PORT-B", "RUN-B", [0.5] * 10)  # mean 0.5

    a = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    b = LabeledRun(run_id="RUN-B", portfolio_id="PORT-B", split_type="in_sample")
    result = bootstrap_two_sample_unpaired(journal, a, b, seed=1, n_resamples=500)
    journal.close()

    assert result.available is True
    assert result.comparison_kind == "two_sample_unpaired"
    # statistic = mean(b) - mean(a) = 0.5 - 0.1 = 0.4
    assert result.observed_statistic == pytest.approx(0.4)
    assert result.sample_size_a == 10
    assert result.sample_size_b == 10


# -- 12. paired comparison success ----------------------------------------


def test_paired_comparison_same_run_id_success(tmp_path):
    journal = _open_journal(tmp_path)
    _ensure_run(journal, "RUN-A")
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _insert_portfolio(journal, "PORT-B", "RUN-A")
    for i in range(10):
        setup_id = f"SETUP-SHARED-{i}"
        _make_closed_trade_for_setup(journal, "PORT-A", "RUN-A", i, setup_id, result_r=0.1)
        _make_closed_trade_for_setup(journal, "PORT-B", "RUN-A", i + 100, setup_id, result_r=0.3)

    a = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    b = LabeledRun(run_id="RUN-A", portfolio_id="PORT-B", split_type="in_sample")
    result = bootstrap_two_sample_paired(journal, a, b, seed=1, n_resamples=500)
    journal.close()

    assert result.available is True
    assert result.comparison_kind == "two_sample_paired"
    assert result.sample_size_a == 10
    assert result.sample_size_b == 10
    assert result.observed_statistic == pytest.approx(0.2)  # mean(b) - mean(a) = 0.3 - 0.1


# -- 13/14. paired rejection cases -----------------------------------------


def test_paired_run_id_mismatch_raises(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _insert_portfolio(journal, "PORT-B", "RUN-B")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)
    _make_closed_trade(journal, "PORT-B", "RUN-B", 0, result_r=0.2)

    a = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    b = LabeledRun(run_id="RUN-B", portfolio_id="PORT-B", split_type="in_sample")
    with pytest.raises(ValueError, match="run_id"):
        bootstrap_two_sample_paired(journal, a, b, seed=1)
    journal.close()


def test_paired_same_portfolio_raises(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_closed_trade(journal, "PORT-A", "RUN-A", 0, result_r=0.1)

    a = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    b = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    with pytest.raises(ValueError, match="distinct portfolio_id"):
        bootstrap_two_sample_paired(journal, a, b, seed=1)
    journal.close()


# -- 15. duplicate setup_id -------------------------------------------------


def test_paired_duplicate_setup_id_raises(tmp_path):
    journal = _open_journal(tmp_path)
    _ensure_run(journal, "RUN-A")
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _insert_portfolio(journal, "PORT-B", "RUN-A")
    # PORT-A has TWO closed trades referencing the SAME setup_id (simulates
    # an ambiguous state the schema does not prevent at the DB level)
    _make_closed_trade_for_setup(journal, "PORT-A", "RUN-A", 0, "SETUP-DUP", result_r=0.1)
    _make_closed_trade_for_setup(journal, "PORT-A", "RUN-A", 1, "SETUP-DUP", result_r=0.2)
    _make_closed_trade_for_setup(journal, "PORT-B", "RUN-A", 2, "SETUP-DUP", result_r=0.3)

    a = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    b = LabeledRun(run_id="RUN-A", portfolio_id="PORT-B", split_type="in_sample")
    with pytest.raises(ValueError, match="duplicate setup_id"):
        bootstrap_two_sample_paired(journal, a, b, seed=1)
    journal.close()


# -- 16. NULL setup_id ----------------------------------------------------


def test_paired_null_setup_id_raises():
    journal = _NullSetupIdStubJournal("RUN-A", "PORT-A", "PORT-B")
    a = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    b = LabeledRun(run_id="RUN-A", portfolio_id="PORT-B", split_type="in_sample")
    with pytest.raises(ValueError, match="NULL setup_id"):
        bootstrap_two_sample_paired(journal, a, b, seed=1)


# -- 17. no positional pairing ----------------------------------------------


def test_paired_uses_setup_id_not_positional_pairing(tmp_path):
    """Portfolio A has 3 closed trades (setups X, Y, Z); portfolio B has 3
    closed trades (setups Y, Z, W) -- only Y and Z are actually shared.
    A positional/list-index pairing would either error or (via naive
    zip-truncation) produce 3 "pairs"; the correct setup_id-keyed
    intersection produces exactly 2.
    """
    journal = _open_journal(tmp_path)
    _ensure_run(journal, "RUN-A")
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _insert_portfolio(journal, "PORT-B", "RUN-A")
    _make_closed_trade_for_setup(journal, "PORT-A", "RUN-A", 0, "SETUP-X", result_r=0.1)
    _make_closed_trade_for_setup(journal, "PORT-A", "RUN-A", 1, "SETUP-Y", result_r=0.2)
    _make_closed_trade_for_setup(journal, "PORT-A", "RUN-A", 2, "SETUP-Z", result_r=0.3)
    _make_closed_trade_for_setup(journal, "PORT-B", "RUN-A", 3, "SETUP-Y", result_r=0.4)
    _make_closed_trade_for_setup(journal, "PORT-B", "RUN-A", 4, "SETUP-Z", result_r=0.5)
    _make_closed_trade_for_setup(journal, "PORT-B", "RUN-A", 5, "SETUP-W", result_r=0.6)

    a = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    b = LabeledRun(run_id="RUN-A", portfolio_id="PORT-B", split_type="in_sample")
    result = bootstrap_two_sample_paired(journal, a, b, seed=1, n_resamples=200, min_sample_size=1)
    journal.close()

    assert result.sample_size_a == 2
    assert result.sample_size_b == 2
    assert _find_note_containing(result, "had 3 closed trade(s)")
    assert _find_note_containing(result, "2 were pairable via shared setup_id")


# -- 18/19/20. p_value deferred, on available AND unavailable results ------


def test_p_value_always_none_available_result(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [0.1] * 12)

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result = bootstrap_one_sample(journal, run, seed=1, n_resamples=200)
    journal.close()

    assert result.p_value is None
    assert _find_note_containing(result, "p_value is deferred in this MVP")


def test_p_value_deferred_disclosure_on_unavailable_result(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")  # zero trades

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result = bootstrap_one_sample(journal, run, seed=1)
    journal.close()

    assert result.available is False
    assert result.p_value is None
    assert _find_note_containing(result, "p_value is deferred in this MVP")


# -- 21. parameter validation -----------------------------------------------


def test_parameter_validation_alpha(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    with pytest.raises(ValueError, match="alpha"):
        bootstrap_one_sample(journal, run, seed=1, alpha=0.0)
    with pytest.raises(ValueError, match="alpha"):
        bootstrap_one_sample(journal, run, seed=1, alpha=1.0)
    journal.close()


def test_parameter_validation_n_resamples(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    with pytest.raises(ValueError, match="n_resamples"):
        bootstrap_one_sample(journal, run, seed=1, n_resamples=0)
    journal.close()


def test_parameter_validation_min_sample_size(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    with pytest.raises(ValueError, match="min_sample_size"):
        bootstrap_one_sample(journal, run, seed=1, min_sample_size=0)
    journal.close()


def test_parameter_validation_comparison_count(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    with pytest.raises(ValueError, match="comparison_count"):
        bootstrap_one_sample(journal, run, seed=1, comparison_count=0)
    journal.close()


# -- 23. global RNG not mutated ---------------------------------------------


def test_global_random_state_not_mutated(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [0.1] * 12)

    state_before = random.getstate()
    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    bootstrap_one_sample(journal, run, seed=1, n_resamples=200)
    state_after = random.getstate()
    journal.close()

    assert state_before == state_after


# -- 27. multiple-comparison disclosure -------------------------------------


def test_comparison_count_disclosure_only(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [0.1] * 12)

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result_with = bootstrap_one_sample(journal, run, seed=1, n_resamples=200, comparison_count=5)
    result_without = bootstrap_one_sample(journal, run, seed=1, n_resamples=200)
    journal.close()

    assert result_with.comparison_count == 5
    assert _find_note_containing(result_with, "comparison_count=5")
    # disclosure-only: identical CI regardless of comparison_count
    assert result_with.ci_low == result_without.ci_low
    assert result_with.ci_high == result_without.ci_high
    assert result_with.alpha == result_without.alpha


# -- 28/29. anti-overfitting + exchangeability disclosures ------------------


def test_anti_overfitting_and_exchangeability_disclosures_present(tmp_path):
    journal = _open_journal(tmp_path)
    _insert_portfolio(journal, "PORT-A", "RUN-A")
    _make_n_trades(journal, "PORT-A", "RUN-A", [0.1] * 12)

    run = LabeledRun(run_id="RUN-A", portfolio_id="PORT-A", split_type="in_sample")
    result = bootstrap_one_sample(journal, run, seed=1, n_resamples=200)
    journal.close()

    assert _find_note_containing(result, "does NOT establish out-of-sample edge")
    assert _find_note_containing(result, "exchangeable/independent")


# -- 30. identity integrity --------------------------------------------------


def test_unknown_portfolio_id_raises(tmp_path):
    journal = _open_journal(tmp_path)
    run = LabeledRun(run_id="RUN-A", portfolio_id="NO-SUCH-PORTFOLIO", split_type="in_sample")
    with pytest.raises(ValueError, match="unknown portfolio_id"):
        bootstrap_one_sample(journal, run, seed=1)
    journal.close()


# -- 24/25/26/31. AST/source guards -----------------------------------------


def _method_call_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def test_no_verdict_fields_in_dataclass():
    source = SIGNIFICANCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden = {
        "significant", "verdict", "recommendation", "candidate", "rejected",
        "promising", "best", "promotion", "validation_passed", "approved", "passed",
    }
    field_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_names.add(item.target.id)

    overlap = field_names & forbidden
    assert not overlap, f"significance.py dataclass contains verdict-like fields: {overlap}"


def test_significance_module_imports_are_strategy_agnostic():
    source = SIGNIFICANCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    allowed = {"__future__", "random", "statistics", "dataclasses", "src.research.validation"}
    unexpected = imported_modules - allowed
    assert not unexpected, f"significance.py has unexpected/strategy-specific imports: {unexpected}"


def test_significance_module_never_writes_to_journal():
    source = SIGNIFICANCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_methods = _method_call_names(tree)
    assert "record" not in called_methods


def test_significance_module_makes_no_direct_file_writes():
    source = SIGNIFICANCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_methods = _method_call_names(tree)
    forbidden_methods = {"write_text", "write_bytes", "write", "open"}
    assert not (called_methods & forbidden_methods)


def test_significance_module_never_seeds_global_random():
    """Source guard: significance.py must never call random.seed() at the
    module level (global RNG mutation) -- only random.Random(seed) local
    instances are permitted.
    """
    source = SIGNIFICANCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "seed":
                # allow random.Random(...).seed style is not used here at all;
                # this specifically guards against a bare `random.seed(...)` call
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "random":
                    pytest.fail("significance.py must not call random.seed() (global RNG mutation)")
