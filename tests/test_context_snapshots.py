"""T3.6: Context Snapshots (docs/FEATURE_SPEC_V1.md) -- point-in-time capture at
engagement/armed/entry/exit, written through the real DuckDBJournal (first test to
exercise Journal + Orchestrator together end-to-end).
"""

import json
from datetime import timedelta
from pathlib import Path

from src.core.types import Tick
from src.journal.duckdb_writer import DuckDBJournal
from tests.fixtures.orchestrator import IN_WINDOW, make_arm, make_orchestrator, seed_fvg_and_bias
from tests.fixtures.setup_stream import m1, m5

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def _run_end_to_end_scenario(journal):
    r_ts = IN_WINDOW + timedelta(minutes=5)
    s_ts = IN_WINDOW + timedelta(minutes=10)
    base = IN_WINDOW + timedelta(minutes=20)
    bars_1m = [
        m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2),
        m1(base, 97.5, 97.6, 97.0, 97.3),
        m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0),
        m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3),
        m1(base + timedelta(minutes=3), 96.8, 97.3, 96.7, 97.2),
    ]
    bars_5m = [m5(r_ts, 99.0, 99.8, 97.0, 99.5), m5(s_ts, 98.0, 98.5, 96.0, 97.5)]
    inversion_ts = bars_1m[-1].close_ts
    ticks = [
        Tick(ts=inversion_ts + timedelta(seconds=1), bid=97.15, ask=97.25),  # entry fill
        Tick(ts=inversion_ts + timedelta(minutes=5), bid=101.0, ask=101.1),  # TP exit
    ]
    arm = make_arm("M2", "S_wick")
    orch = make_orchestrator(bars_1m=bars_1m, bars_5m=bars_5m, ticks=ticks, arms=[arm])
    orch.journal = journal
    seed_fvg_and_bias(orch, "long", 100.0, 95.0)
    orch.run()  # closes `journal` itself when journal is not None
    return orch


def _run_and_reopen(tmp_path):
    """Orchestrator.run() closes the Journal connection it was given -- reopen a
    fresh read-only view afterwards rather than reusing the closed instance.
    """
    db_path = tmp_path / "test.duckdb"
    _run_end_to_end_scenario(DuckDBJournal(db_path, SCHEMA_PATH))
    return DuckDBJournal(db_path, SCHEMA_PATH)


def test_context_snapshots_captured_at_all_four_kinds(tmp_path):
    reader = _run_and_reopen(tmp_path)
    rows = reader.query("SELECT kind FROM context_snapshots ORDER BY ts")
    reader.close()

    assert [r[0] for r in rows] == ["engagement", "armed", "entry", "exit"]


def test_engagement_and_armed_snapshots_are_model_agnostic(tmp_path):
    reader = _run_and_reopen(tmp_path)
    rows = reader.query(
        "SELECT kind, order_id FROM context_snapshots WHERE kind IN ('engagement','armed')"
    )
    reader.close()

    assert len(rows) == 2
    for _kind, order_id in rows:
        assert order_id is None  # D-058: shared across all 9 arms, no per-arm order


def test_entry_and_exit_snapshots_are_keyed_to_their_order(tmp_path):
    reader = _run_and_reopen(tmp_path)
    rows = reader.query(
        "SELECT kind, order_id FROM context_snapshots WHERE kind IN ('entry','exit')"
    )
    reader.close()

    assert len(rows) == 2
    order_ids = {order_id for _kind, order_id in rows}
    assert len(order_ids) == 1  # same order -- entry and exit of the one trade
    assert None not in order_ids


def test_snapshot_payload_reflects_setup_state_at_capture_time(tmp_path):
    reader = _run_and_reopen(tmp_path)
    [(armed_raw,)] = reader.query("SELECT payload FROM context_snapshots WHERE kind = 'armed'")
    [(engagement_raw,)] = reader.query(
        "SELECT payload FROM context_snapshots WHERE kind = 'engagement'"
    )
    reader.close()
    armed_payload, engagement_payload = json.loads(armed_raw), json.loads(engagement_raw)

    # At engagement, R/S/iFVG haven't formed yet -- must not be back-filled with
    # hindsight (No-Lookahead by Construction, same discipline as MarketContext.as_of).
    assert engagement_payload["r_bar"] is None
    assert engagement_payload["s_bar"] is None
    assert engagement_payload["ifvg"] is None
    # By armed, the full R->S->iFVG sequence is known.
    assert armed_payload["r_bar"] is not None
    assert armed_payload["s_bar"] is not None
    assert armed_payload["ifvg"] is not None
    assert armed_payload["bias"] == "bullish"


def test_entry_payload_carries_order_detail(tmp_path):
    reader = _run_and_reopen(tmp_path)
    [(entry_raw,)] = reader.query("SELECT payload FROM context_snapshots WHERE kind = 'entry'")
    reader.close()
    entry_payload = json.loads(entry_raw)

    assert entry_payload["order"]["side"] == "buy"
    assert entry_payload["order"]["otype"] == "market"
    assert entry_payload["order"]["price"] is None  # M2 is Market -- no Limit price


def test_setup_arm_outcome_written_once_as_closed_not_pending(tmp_path):
    """D-060: no interim 'pending' row is ever persisted -- setup_arm_outcomes is
    written exactly once, at the arm's true terminal state (closed here)."""
    reader = _run_and_reopen(tmp_path)
    rows = reader.query("SELECT outcome, order_id FROM setup_arm_outcomes")
    reader.close()

    assert rows == [("closed", rows[0][1])]
    assert rows[0][1] is not None


def test_no_journal_means_no_snapshots_and_no_crash():
    orch = _run_end_to_end_scenario(None)
    assert orch is not None  # ran to completion with journal=None (default)
