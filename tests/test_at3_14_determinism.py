"""AT-3.14 (Stage A / B-1 Commit 4, D-067, closes KI-018): two from-scratch runs of
the D-064 fixture pipeline (tests/test_full_pipeline_from_raw_4h_bars.py::_scenario),
with the same RunIdentity (data_version derived from the fixture's own ticks --
D-037; code_version fixed via tests/fixtures/orchestrator.py::TEST_CODE_VERSION),
must produce a byte-identical canonical export of every Journal table.

Scoped pull-forward of AT-5.3 (real-scale determinism, Phase 5) -- CLAUDE.md's
determinism rule ("same (config_hash, data_version, code_version) -> same journal,
bit-for-bit") is verified here at fixture scale, through the real orchestration
wiring (D-064), not asserted by inspection.

The canonical export function lives here, not in src -- it's a test-only concern
(WORK_ORDER_B1.md S4 Commit 4), not a product feature.
"""

import hashlib
import json
from pathlib import Path

from src.config.models import config_hash as compute_config_hash
from src.journal.duckdb_writer import DuckDBJournal
from tests.test_full_pipeline_from_raw_4h_bars import SCHEMA_PATH, _scenario

# Fixed table list from db/schema.sql (Pre-Flight A7/A9) + each table's PK, so
# every row order is deterministic regardless of insertion order. No wall-clock
# columns are excluded -- Pre-Flight A10 confirmed none of these tables' ts/at
# columns are ever populated from datetime.now() in this fixture (the one
# datetime.now() fallback in Orchestrator._write_run_identity_rows only fires
# when bars_1m/5m/4h are all empty, which never happens here).
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
    run_dir = tmp_path / label
    run_dir.mkdir()
    db_path = run_dir / "test.duckdb"
    registry_path = run_dir / "runs.jsonl"
    journal = DuckDBJournal(db_path, SCHEMA_PATH)
    scenario = _scenario(journal=journal, registry_path=registry_path)
    scenario.orch.run()  # closes `journal`
    return scenario, db_path, registry_path, _canonical_export(db_path)


def test_at3_14_two_from_scratch_runs_produce_identical_canonical_export(tmp_path):
    scenario_1, db_path_1, registry_path_1, hash_1 = _run_once(tmp_path, "run1")
    _scenario_2, _db_path_2, registry_path_2, hash_2 = _run_once(tmp_path, "run2")

    assert hash_1 == hash_2

    reader = DuckDBJournal(db_path_1, SCHEMA_PATH)
    [(config_hash, code_version, data_version, split_type, seed)] = reader.query(
        "SELECT config_hash, code_version, data_version, split_type, seed FROM runs"
    )
    reader.close()
    assert "unknown" not in (config_hash, code_version, data_version, split_type)
    assert seed is None

    # Independent recomputation -- not just "not unknown", but the exact same
    # value config_hash() would produce from the scenario's own resolved config.
    expected_hash = compute_config_hash(
        scenario_1.rules, scenario_1.parameters, scenario_1.run_config,
        data_version=scenario_1.identity.data_version, code_version=code_version,
    )
    assert config_hash == expected_hash

    for registry_path in (registry_path_1, registry_path_2):
        record = json.loads(registry_path.read_text().strip().splitlines()[0])
        assert record["config_hash"] == config_hash
        assert record["code_version"] == code_version
        assert record["data_version"] == data_version
        assert record["seed"] is None
