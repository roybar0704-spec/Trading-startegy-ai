"""T3.5: basic per-trade Viz -- build_trade_page over a real Journal."""

from datetime import timedelta
from pathlib import Path

import plotly.graph_objects as go

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


def test_build_trade_page_returns_a_figure_with_all_markings(tmp_path):
    db_path, bars_1m = _run_end_to_end_scenario(tmp_path)
    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    [(trade_id,)] = reader.query("SELECT trade_id FROM trades")
    [(order_id,)] = reader.query("SELECT order_id FROM trades WHERE trade_id = ?", [trade_id])

    fig = build_trade_page(reader, trade_id, bars_1m)
    reader.close()

    assert isinstance(fig, go.Figure)
    trace_types = {type(t).__name__ for t in fig.data}
    assert "Candlestick" in trace_types
    assert "Scatter" in trace_types  # entry/exit markers

    shape_colors = {s.fillcolor for s in fig.layout.shapes if s.type == "rect"}
    assert "blue" in shape_colors  # 4H FVG zone
    assert "purple" in shape_colors  # iFVG zone

    line_colors = {s.line.color for s in fig.layout.shapes if s.type == "line"}
    assert {"black", "red", "green"} <= line_colors  # entry/SL/TP

    assert order_id  # sanity: the trade really has an order behind it
    assert trade_id in fig.layout.title.text


def test_build_trade_page_raises_clearly_for_unknown_trade(tmp_path):
    db_path, bars_1m = _run_end_to_end_scenario(tmp_path)
    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    try:
        raised = False
        try:
            build_trade_page(reader, "TRADE-does-not-exist", bars_1m)
        except ValueError:
            raised = True
        assert raised
    finally:
        reader.close()
