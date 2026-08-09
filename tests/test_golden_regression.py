"""Golden Regression (Stage A / B-8, closes KI-024, QUALITY_GATES.md S6).

Re-runs the same D-064 fixture pipeline used by AT-3.14
(tests/test_full_pipeline_from_raw_4h_bars.py::_scenario) and asserts its
canonical Journal export (tests/test_at3_14_determinism.py::_canonical_export,
imported unchanged -- no src/ extraction, per B-8 Pre-Flight Scope Lock) is
byte-identical to the frozen baseline hash in tests/golden/at3_14_baseline.sha256.

This differs from AT-3.14 in kind, not in mechanism: AT-3.14 proves two
from-scratch runs agree with *each other*; this test proves today's run still
agrees with a *frozen historical baseline* -- the actual guarantee
QUALITY_GATES.md S6 asks for ("sample-period journal identical bit-for-bit;
a deliberate change requires an explanation + a new Golden, user-approved").

An intentional logic change that legitimately changes the fixture's output
must NOT silently update the baseline file -- regenerating it requires
explicit user approval and a separate, documented commit (B-8 Pre-Flight SS4).
"""

from pathlib import Path

from src.journal.duckdb_writer import DuckDBJournal
from tests.test_at3_14_determinism import _canonical_export
from tests.test_full_pipeline_from_raw_4h_bars import SCHEMA_PATH, _scenario

_BASELINE_PATH = Path(__file__).parent / "golden" / "at3_14_baseline.sha256"


def test_d064_scenario_matches_frozen_golden_baseline(tmp_path):
    frozen_hash = _BASELINE_PATH.read_text().strip()

    db_path = tmp_path / "golden_run.duckdb"
    registry_path = tmp_path / "runs.jsonl"
    journal = DuckDBJournal(db_path, SCHEMA_PATH)
    _scenario(journal=journal, registry_path=registry_path).orch.run()  # closes `journal`

    computed_hash = _canonical_export(db_path)

    assert computed_hash == frozen_hash, (
        "Golden Regression mismatch: today's canonical Journal export no longer "
        "matches the frozen baseline (tests/golden/at3_14_baseline.sha256). If "
        "this change is intentional, it requires explicit user approval and a "
        "separate, documented commit that regenerates the baseline -- not a "
        "silent update here."
    )
