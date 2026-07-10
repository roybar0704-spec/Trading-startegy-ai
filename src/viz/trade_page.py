"""T3.5: Basic per-trade Viz (docs/PHASE_PLAN.md "דף עסקה עם כל הסימונים").

One Plotly page per trade: OHLC candles, the 4H FVG zone, the R and S candles,
the armed iFVG zone, entry/SL/TP lines, and entry/exit markers.

Reads facts *only* from the Journal (trades/orders/portfolios/context_snapshots)
-- never from live engine state -- plus the caller-supplied 1M bars for
candlestick rendering (bars themselves aren't journaled). This is exactly the
boundary docs/ARCHITECTURE.md draws for Viz: read-only over what a completed run
already wrote down, same discipline as everything downstream of the Journal.
"""

from __future__ import annotations

import json
from datetime import timedelta

import plotly.graph_objects as go

from src.core.types import Bar
from src.journal.duckdb_writer import DuckDBJournal

_WINDOW_PAD = timedelta(hours=2)


def _load_trade(journal: DuckDBJournal, trade_id: str) -> dict:
    rows = journal.query(
        "SELECT order_id, portfolio_id, entry_ts, exit_ts, entry_px, exit_px, "
        "sl_px, tp_px, exit_kind, result_r FROM trades WHERE trade_id = ?",
        [trade_id],
    )
    if not rows:
        raise ValueError(f"no trade found for trade_id={trade_id!r}")
    keys = (
        "order_id", "portfolio_id", "entry_ts", "exit_ts", "entry_px", "exit_px",
        "sl_px", "tp_px", "exit_kind", "result_r",
    )
    return dict(zip(keys, rows[0], strict=True))


def _load_arm(journal: DuckDBJournal, portfolio_id: str) -> dict:
    [(entry_model, sl_anchor)] = journal.query(
        "SELECT entry_model, sl_anchor FROM portfolios WHERE portfolio_id = ?",
        [portfolio_id],
    )
    return {"entry_model": entry_model, "sl_anchor": sl_anchor}


def _load_setup_id(journal: DuckDBJournal, order_id: str) -> str:
    [(setup_id,)] = journal.query("SELECT setup_id FROM orders WHERE order_id = ?", [order_id])
    return setup_id


def _load_armed_payload(journal: DuckDBJournal, setup_id: str) -> dict:
    rows = journal.query(
        "SELECT payload FROM context_snapshots WHERE setup_id = ? AND kind = 'armed'",
        [setup_id],
    )
    if not rows:
        raise ValueError(f"no 'armed' context_snapshot for setup_id={setup_id!r}")
    return json.loads(rows[0][0])


def _candlestick(bars: list[Bar]) -> go.Candlestick:
    return go.Candlestick(
        x=[b.close_ts for b in bars],
        open=[b.o for b in bars], high=[b.h for b in bars],
        low=[b.l for b in bars], close=[b.c for b in bars],
        name="1M",
    )


def _zone_shape(x0, x1, top: float, bottom: float, color: str, label: str) -> dict:
    return {
        "type": "rect", "xref": "x", "yref": "y",
        "x0": x0, "x1": x1, "y0": bottom, "y1": top,
        "fillcolor": color, "opacity": 0.18, "line_width": 0, "layer": "below",
        "name": label,
    }


def _hline(y: float, color: str, label: str) -> dict:
    return {
        "type": "line", "xref": "paper", "yref": "y",
        "x0": 0, "x1": 1, "y0": y, "y1": y,
        "line": {"color": color, "dash": "dash", "width": 1.5}, "name": label,
    }


def build_trade_page(journal: DuckDBJournal, trade_id: str, bars_1m: list[Bar]) -> go.Figure:
    """Build the T3.5 trade page for ``trade_id`` as a Plotly Figure."""
    trade = _load_trade(journal, trade_id)
    arm = _load_arm(journal, trade["portfolio_id"])
    setup_id = _load_setup_id(journal, trade["order_id"])
    armed = _load_armed_payload(journal, setup_id)

    window_end = trade["exit_ts"] or trade["entry_ts"]
    window_bars = [
        b for b in bars_1m
        if trade["entry_ts"] - _WINDOW_PAD <= b.close_ts <= window_end + _WINDOW_PAD
    ]
    if not window_bars:
        raise ValueError(f"no bars_1m fall inside the display window for {trade_id!r}")

    fig = go.Figure(data=[_candlestick(window_bars)])
    x0, x1 = window_bars[0].close_ts, window_bars[-1].close_ts
    shapes = []

    fvg = armed.get("fvg")
    if fvg is not None:
        shapes.append(_zone_shape(x0, x1, fvg["top"], fvg["bottom"], "blue", "4H FVG"))
    ifvg = armed.get("ifvg")
    if ifvg is not None:
        shapes.append(_zone_shape(x0, x1, ifvg["top"], ifvg["bottom"], "purple", "iFVG"))

    for label, bar_key, color in (("R", "r_bar", "orange"), ("S", "s_bar", "red")):
        bar = armed.get(bar_key)
        if bar is None:
            continue
        shapes.append(
            {
                "type": "rect", "xref": "x", "yref": "paper",
                "x0": bar["open_ts"], "x1": bar["close_ts"], "y0": 0, "y1": 1,
                "fillcolor": color, "opacity": 0.12, "line_width": 0, "layer": "below",
            }
        )
        fig.add_annotation(
            x=bar["close_ts"], y=1, yref="paper", yshift=10, showarrow=False,
            text=label, font={"color": color},
        )

    shapes.append(_hline(trade["entry_px"], "black", "entry"))
    shapes.append(_hline(trade["sl_px"], "red", "SL"))
    shapes.append(_hline(trade["tp_px"], "green", "TP"))
    fig.update_layout(shapes=shapes)

    fig.add_trace(
        go.Scatter(
            x=[trade["entry_ts"]], y=[trade["entry_px"]], mode="markers",
            marker={"symbol": "triangle-up", "size": 14, "color": "black"}, name="entry",
        )
    )
    if trade["exit_ts"] is not None:
        exit_color = "green" if (trade["result_r"] or 0) > 0 else "red"
        fig.add_trace(
            go.Scatter(
                x=[trade["exit_ts"]], y=[trade["exit_px"]], mode="markers",
                marker={"symbol": "triangle-down", "size": 14, "color": exit_color},
                name=f"exit ({trade['exit_kind']})",
            )
        )

    result_r = trade["result_r"]
    result_str = f"{result_r:+.2f}R" if result_r is not None else "open"
    fig.update_layout(
        title=(
            f"{trade_id} -- {arm['entry_model']}/{arm['sl_anchor']} -- {result_str}"
        ),
        xaxis_title="time (UTC)", yaxis_title="price", xaxis_rangeslider_visible=False,
    )
    return fig
