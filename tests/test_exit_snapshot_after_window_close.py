"""D-092 regression: exit context_snapshot must not crash when the Setup's own
session window has already closed before the resulting trade's SL/TP exit fires.

Root cause (T3.4 first-real-run crash, KeyError: 'SETUP-6809'): SetupStream's
``_finished`` is a deliberate single-tick buffer (cleared at the top of every
``step()``, setup_stream.py) -- an ARMED Setup is evicted from ``_active`` the
moment its trading window closes, and is only retrievable through
``_finished`` for exactly one further merged timestamp. An M2 Market entry can
fill well before window close, and the resulting open position can exit
(SL/TP) well after -- ``Orchestrator._close_trade`` still needs the Setup for
its "exit" context_snapshot, and previously called
``setup_stream.get_setup(setup_id)`` directly, raising ``KeyError`` once the
Setup had been evicted.

Fix (D-092): ``Orchestrator`` now caches each ARMED Setup once, at ARM time
(the one moment it is guaranteed still reachable), and ``_record_snapshot``
consults that cache first for the "exit" kind.
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


def _bars_and_ticks_spanning_window_close():
    """Same happy-path R/S/iFVG sequence as test_context_snapshots.py's fixture,
    but the exit tick lands well after the session window (08:30-10:30 ET,
    IN_WINDOW=09:00 ET) has closed, with two intervening ticks in between so
    SetupStream._finished is genuinely cleared before the exit fires -- not
    just the one-tick grace window that would mask the bug.
    """
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
    inversion_ts = bars_1m[-1].close_ts  # ~09:23 ET -- well inside [08:30, 10:30)

    ticks = [
        Tick(ts=inversion_ts + timedelta(seconds=1), bid=97.15, ask=97.25),  # entry fill, in-window
        # Window closes at IN_WINDOW + 90min (10:30 ET). Both ticks below sit
        # strictly between SL(95.95) and TP(100.95) for this arm's geometry,
        # so neither triggers a fill on its own -- they only advance the
        # merged timeline so SetupStream.step() actually clears _finished
        # before the real exit tick arrives.
        Tick(ts=IN_WINDOW + timedelta(minutes=91), bid=98.0, ask=98.1),  # window now closed
        Tick(ts=IN_WINDOW + timedelta(minutes=92), bid=98.0, ask=98.1),  # _finished cleared here
        Tick(ts=IN_WINDOW + timedelta(minutes=93), bid=101.0, ask=101.1),  # TP exit, post-close
    ]
    return bars_1m, bars_5m, ticks


def _run(tmp_path):
    bars_1m, bars_5m, ticks = _bars_and_ticks_spanning_window_close()
    arm = make_arm("M2", "S_wick")
    orch = make_orchestrator(bars_1m=bars_1m, bars_5m=bars_5m, ticks=ticks, arms=[arm])
    db_path = tmp_path / "test.duckdb"
    orch.journal = DuckDBJournal(db_path, SCHEMA_PATH)
    seed_fvg_and_bias(orch, "long", 100.0, 95.0)
    result = orch.run()  # closes the journal itself on success
    return orch, result, db_path


def test_exit_after_window_close_does_not_crash(tmp_path):
    """The actual T3.4 failure mode: must complete without KeyError."""
    orch, result, _db_path = _run(tmp_path)

    assert result.armed == 1
    assert result.orders_placed == 1
    assert result.fills == 2  # entry + exit
    arm = orch.arms[0]
    assert arm.portfolio.realized_equity != arm.portfolio.initial_equity  # KI-006 wiring


def test_exit_snapshot_is_written_not_skipped(tmp_path):
    """D-092: the fix must not drop the exit snapshot -- full fidelity, not a skip."""
    _orch, _result, db_path = _run(tmp_path)

    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    rows = reader.query("SELECT kind FROM context_snapshots ORDER BY ts")
    reader.close()

    assert [r[0] for r in rows] == ["engagement", "armed", "entry", "exit"]


def test_exit_snapshot_payload_matches_pre_eviction_setup_data(tmp_path):
    """The post-window-close exit snapshot's Setup-derived fields must be
    identical to the armed snapshot's (same Setup, D-092 only changes *how*
    it's fetched, never *what* the values are -- nothing mutates a Setup's
    r_bar/s_bar/ifvg/direction/same_zone_reentry after ARMED)."""
    _orch, _result, db_path = _run(tmp_path)

    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    [(armed_raw,)] = reader.query("SELECT payload FROM context_snapshots WHERE kind='armed'")
    [(exit_raw,)] = reader.query("SELECT payload FROM context_snapshots WHERE kind='exit'")
    reader.close()

    armed_payload, exit_payload = json.loads(armed_raw), json.loads(exit_raw)
    for field in ("direction", "r_bar", "s_bar", "ifvg", "same_zone_reentry"):
        assert exit_payload[field] == armed_payload[field]


def test_setup_arm_outcome_reaches_closed_after_window_close_exit(tmp_path):
    """Confirms the code past the former crash point now actually runs:
    _record_arm_outcome(..., "closed", ...) executes right after the exit
    snapshot in _close_trade -- this row only exists if that line was reached."""
    _orch, _result, db_path = _run(tmp_path)

    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    rows = reader.query("SELECT outcome, order_id FROM setup_arm_outcomes")
    reader.close()

    assert rows == [("closed", rows[0][1])]
    assert rows[0][1] is not None
