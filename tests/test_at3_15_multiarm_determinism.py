"""AT-3.15 (Stage A / B-2 Commit 1, closes part of KI-015): two from-scratch runs of
the D-062 multi-arm fixture (tests/test_full_pipeline_9_arms.py::_scenario -- 3 arms
fill, one per entry model, 6 stay untouched) must produce a byte-identical canonical
export of every Journal table.

AT-3.14 (B-1) already proved two-run determinism, but only on a single-fill fixture
(D-064). This extends the guarantee to a genuine multi-fill scenario -- the gap
PREFLIGHT_B2.md identified as still open.

Per WORK_ORDER_B2.md rule 5 (Stability Rule, D-026): `_scenario` is imported, never
modified, from the already-closed test_full_pipeline_9_arms.py. The canonical-export
function below is an independent, local copy of the one in test_at3_14_determinism.py
(WORK_ORDER_B1.md's own file, also not to be touched) -- not a cross-file import.
"""

import hashlib
from pathlib import Path

from src.journal.duckdb_writer import DuckDBJournal
from tests.test_full_pipeline_9_arms import _scenario

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

# Same fixed table list + PKs as test_at3_14_determinism.py -- independent copy per
# rule 5, not an import. No wall-clock columns excluded: this fixture's bars/ticks
# are always non-empty, so Orchestrator._write_run_identity_rows' datetime.now(UTC)
# fallback (only reached when bars_1m/5m/4h are all empty) never fires here either.
_TABLE_PKS = {
    "experiments": ["experiment_id"],
    "runs": ["run_id"],
    "portfolios": ["portfolio_id"],
    "sessions": ["run_id", "ny_date"],
    "bias_history": ["run_id", "ts"],
    "fvg_registry": ["fvg_id"],
    "setups": ["setup_id"],
    "orders": ["order_id"],
    "setup_arm_outcomes": ["setup_id", "portfolio_id"],
    "trades": ["trade_id"],
    "equity_curve": ["portfolio_id", "ts"],
    "news_events": ["ts_utc", "title"],
    "scores": ["setup_id"],
    "ai_annotations": ["annotation_id"],
    "baseline_runs": ["baseline_id"],
    "feature_registry": ["feature"],
    "trade_features": ["trade_id", "feature"],
    "context_snapshots": ["snapshot_id"],
}


def _canonical_export(db_path: Path) -> str:
    """SHA256 over a CSV-ish serialization of every known table, each ordered by
    its own PK -- byte-identical iff the two runs' Journal contents are identical.
    """
    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    lines = []
    for table in sorted(_TABLE_PKS):
        order_by = ", ".join(_TABLE_PKS[table])
        rows = reader.query(f"SELECT * FROM {table} ORDER BY {order_by}")  # noqa: S608
        lines.append(f"--{table}--")
        for row in rows:
            lines.append(",".join("" if v is None else str(v) for v in row))
    reader.close()
    canonical = "\n".join(lines)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _run_once(tmp_path: Path, label: str):
    """Fresh Orchestrator from _scenario() (unmodified, imported) + a real Journal
    attached post-construction -- the same orch.journal = journal pattern already
    used by tests/test_context_snapshots.py and tests/test_trade_page.py, so
    test_full_pipeline_9_arms.py itself needs no changes (rule 5).
    """
    run_dir = tmp_path / label
    run_dir.mkdir()
    db_path = run_dir / "test.duckdb"
    journal = DuckDBJournal(db_path, SCHEMA_PATH)
    orch = _scenario()
    orch.journal = journal
    result = orch.run()  # closes `journal`
    filled_arms = {
        arm.arm_id.entry for arm in orch.arms if arm.portfolio.realized_equity != 10_000.0
    }
    return result, filled_arms, _canonical_export(db_path)


def test_at3_15_two_from_scratch_multiarm_runs_produce_identical_canonical_export(tmp_path):
    result_1, filled_arms_1, hash_1 = _run_once(tmp_path, "run1")
    result_2, filled_arms_2, hash_2 = _run_once(tmp_path, "run2")

    assert hash_1 == hash_2

    # Sanity (not a new AC): the scenario itself didn't silently change between runs --
    # still exactly 3 filling arms (one per entry model), 6 untouched, in both runs.
    assert filled_arms_1 == filled_arms_2 == {"M1", "M2", "M4"}
    assert result_1.fills == result_2.fills == 6
