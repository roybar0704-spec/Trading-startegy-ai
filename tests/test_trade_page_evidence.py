"""AT-3.10 auditability improvement: Engagement->Armed->Entry->Exit timeline,
bias/blackout state, FVG/iFVG/R-bar/S-bar detail, order lifecycle, and the
explicit decision-boundary disclaimer -- all additive to the existing T3.5
trade page (tests/test_trade_page.py), which must keep passing unchanged.
"""

from datetime import timedelta
from pathlib import Path

from src.core.types import Tick
from src.journal.duckdb_writer import DuckDBJournal
from src.viz.trade_page import build_trade_page
from tests.fixtures.orchestrator import IN_WINDOW, make_arm, make_orchestrator, seed_fvg_and_bias
from tests.fixtures.setup_stream import m1, m5

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def _run_end_to_end_scenario(tmp_path):
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
    db_path = tmp_path / "test.duckdb"
    orch = make_orchestrator(bars_1m=bars_1m, bars_5m=bars_5m, ticks=ticks, arms=[arm])
    orch.journal = DuckDBJournal(db_path, SCHEMA_PATH)
    seed_fvg_and_bias(orch, "long", 100.0, 95.0)
    orch.run()
    return db_path, bars_1m


def _build_page(tmp_path):
    db_path, bars_1m = _run_end_to_end_scenario(tmp_path)
    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    [(trade_id,)] = reader.query("SELECT trade_id FROM trades")
    fig = build_trade_page(reader, trade_id, bars_1m)
    return fig, reader, trade_id, db_path


def _shape_names(fig, shape_type):
    return [s.name for s in fig.layout.shapes if s.type == shape_type]


def _all_hovertext(fig):
    return " ".join(t.hovertext for t in fig.data if getattr(t, "hovertext", None))


def test_engagement_marker_present(tmp_path):
    fig, reader, _, _ = _build_page(tmp_path)
    reader.close()
    assert "engagement" in _shape_names(fig, "line")
    ann_texts = [a.text for a in fig.layout.annotations]
    assert any(t == "Engagement" for t in ann_texts)


def test_decision_boundary_present_and_disclaimer_worded_correctly(tmp_path):
    fig, reader, _, _ = _build_page(tmp_path)
    reader.close()
    assert "decision_boundary" in _shape_names(fig, "line")
    ann_texts = [a.text for a in fig.layout.annotations]
    boundary = [t for t in ann_texts if "DECISION BOUNDARY" in t]
    assert len(boundary) == 1
    assert "DECISION BOUNDARY — ARM TIMESTAMP" in boundary[0]
    assert (
        "Information after this timestamp must not be used to justify the decision."
        in boundary[0]
    )
    # must not overclaim that everything *before* the line was actually used
    assert "was used" not in boundary[0].lower()


def test_fvg_hover_metadata_present(tmp_path):
    fig, reader, _, _ = _build_page(tmp_path)
    reader.close()
    hover = _all_hovertext(fig)
    assert "4H FVG" in hover
    for field in ("id=", "level=", "confirmed_at=", "mitigation_pct=", "displacement="):
        assert field in hover


def test_r_and_s_bar_hover_metadata_present(tmp_path):
    fig, reader, _, _ = _build_page(tmp_path)
    reader.close()
    hover = _all_hovertext(fig)
    assert "R bar" in hover
    assert "S bar" in hover
    for field in ("open_ts=", "close_ts=", "O=", "H=", "L=", "C=", "tick_volume="):
        assert hover.count(field) >= 2  # present for both R-bar and S-bar


def test_order_lifecycle_in_entry_hover(tmp_path):
    fig, reader, _, _ = _build_page(tmp_path)
    reader.close()
    entry_trace = [t for t in fig.data if t.name == "entry"][0]
    for field in ("placed_at=", "filled_at=", "otype=", "side=", "status=", "cancel_reason="):
        assert field in entry_trace.hovertext


def test_sl_anchor_label_present(tmp_path):
    fig, reader, _, _ = _build_page(tmp_path)
    reader.close()
    ann_texts = [a.text for a in fig.layout.annotations]
    assert any(t == "SL (S_wick)" for t in ann_texts)


def test_bias_and_blackout_stage_summary_present(tmp_path):
    fig, reader, _, _ = _build_page(tmp_path)
    reader.close()
    ann_texts = [a.text for a in fig.layout.annotations]
    summary = [t for t in ann_texts if "Engagement @" in t]
    assert len(summary) == 1
    for label in ("Engagement @", "Armed @", "Entry @", "Exit @"):
        assert label in summary[0]
    assert "bias=" in summary[0]
    assert "in_window=" in summary[0]
    assert "in_blackout=" in summary[0]


def test_handles_missing_ifvg_gracefully(tmp_path):
    db_path, bars_1m = _run_end_to_end_scenario(tmp_path)
    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    [(trade_id,)] = reader.query("SELECT trade_id FROM trades")

    # Strip the ifvg field from the already-written 'armed' snapshot payload,
    # in this disposable test database only (never the real Journal), to
    # exercise build_trade_page's defensive `if ifvg is not None` branch --
    # a real ARMED setup always has an ifvg (SPEC), so this state is not
    # reachable via the engine itself; it is a unit test of the Viz layer's
    # own robustness, not a claim that this happens in production.
    import json as _json
    [(setup_id,)] = reader.query(
        "SELECT setup_id FROM context_snapshots WHERE kind = 'armed' LIMIT 1"
    )
    [(payload,)] = reader.query(
        "SELECT payload FROM context_snapshots WHERE setup_id = ? AND kind = 'armed'",
        [setup_id],
    )
    data = _json.loads(payload)
    data["ifvg"] = None
    reader._con.execute(
        "UPDATE context_snapshots SET payload = ? WHERE setup_id = ? AND kind = 'armed'",
        [_json.dumps(data), setup_id],
    )

    fig = build_trade_page(reader, trade_id, bars_1m)
    reader.close()

    assert "purple" not in {s.fillcolor for s in fig.layout.shapes if s.type == "rect"}
    assert "iFVG" not in _all_hovertext(fig)


def test_handles_missing_exit_snapshot_gracefully(tmp_path):
    db_path, bars_1m = _run_end_to_end_scenario(tmp_path)
    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    [(trade_id,)] = reader.query("SELECT trade_id FROM trades")

    # Delete the 'exit' context_snapshot row in this disposable test database
    # only, to exercise the `exit_snap is None` branch even though this run's
    # trade did close normally (a real still-open trade never gets a `trades`
    # row at all -- _close_trade writes both together -- so this combination
    # isn't reachable via the engine; this is a unit test of the Viz layer's
    # own defensive handling).
    reader._con.execute("DELETE FROM context_snapshots WHERE kind = 'exit'")

    fig = build_trade_page(reader, trade_id, bars_1m)
    reader.close()

    ann_texts = [a.text for a in fig.layout.annotations]
    summary = [t for t in ann_texts if "Engagement @" in t][0]
    assert "Exit: (no snapshot)" in summary
    # exit marker/vline still render from the `trades` row itself, unaffected
    assert any(t.name and t.name.startswith("exit (") for t in fig.data)


def test_existing_visuals_unchanged(tmp_path):
    """Regression guard (Stability Rule): the pre-existing candlestick,
    FVG/iFVG zones, R/S shading, and entry/SL/TP lines must still be present
    with the same core properties as before this change."""
    fig, reader, trade_id, _ = _build_page(tmp_path)
    reader.close()

    trace_types = {type(t).__name__ for t in fig.data}
    assert "Candlestick" in trace_types
    assert "Scatter" in trace_types

    shape_colors = {s.fillcolor for s in fig.layout.shapes if s.type == "rect"}
    assert "blue" in shape_colors
    assert "purple" in shape_colors

    line_colors = {s.line.color for s in fig.layout.shapes if s.type == "line"}
    assert {"black", "red", "green"} <= line_colors

    assert trade_id in fig.layout.title.text
