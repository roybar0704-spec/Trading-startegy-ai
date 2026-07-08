#!/usr/bin/env python3
"""Phase 1 demo (docs/PHASE_PLAN.md working-software table).

Runs the Structure + FVG engines over a synthetic sample period and
renders an interactive chart: candlesticks, confirmed Swings, BOS/Sweep
markers, a Bias axis, and FVG boxes colored by L1/L2/L3.

Per D-037 (data-source independence), this script drives the exact same
engine code Phase 3+ will drive on real Dukascopy-derived bars — only the
bar source (a synthetic generator here) differs.

Usage:
    python scripts/demo_phase1.py --period 2024-01-01:2024-02-01
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.graph_objects as go

from src.core.types import TF, Bar
from src.displacement.d1_body import D1BodyRatio
from src.fvg.engine import FVGEngine
from src.store.state_store import StateStore
from src.structure.engine import StructureEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
LEVEL_COLOR = {1: "rgba(120,120,120,0.25)", 2: "rgba(255,165,0,0.35)", 3: "rgba(220,20,60,0.4)"}
BIAS_Y = {"bearish": -1, "neutral": 0, "bullish": 1}


def synthetic_4h_bars(start: datetime, end: datetime, seed: int = 11) -> list[Bar]:
    """[SYNTHETIC] A deterministic 4H random-walk sample period (no real network needed)."""
    rng = random.Random(seed)
    bars = []
    price = 2000.0
    ts = start
    interval = timedelta(hours=4)
    while ts < end:
        o = price
        c = o + rng.uniform(-4.0, 4.0)
        h = max(o, c) + rng.uniform(0.0, 2.0)
        low = min(o, c) - rng.uniform(0.0, 2.0)
        bars.append(
            Bar(tf=TF.H4, open_ts=ts, close_ts=ts + interval, o=o, h=h, l=low, c=c, tick_volume=1)
        )
        price = c
        ts += interval
    return bars


def run_engines(bars: list[Bar]) -> tuple[StateStore, list, list[Bar]]:
    """Run Structure+FVG over ``bars``; return (store, bos_sweep_events, bars)."""
    store = StateStore()
    structure = StructureEngine(TF.H4, is_bias_source=True)
    fvg_engine = FVGEngine(TF.H4, displacement_model=D1BodyRatio(), displacement_params={})
    events = []
    for bar in bars:
        events.extend(structure.step(bar, store))
        fvg_engine.step_bar_close(bar, store)
    return store, events, bars


def build_chart(
    store: StateStore, events: list, bars: list[Bar], period_start: datetime
) -> go.Figure:
    """Assemble the interactive Plotly chart."""
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=[b.open_ts for b in bars],
            open=[b.o for b in bars],
            high=[b.h for b in bars],
            low=[b.l for b in bars],
            close=[b.c for b in bars],
            name="4H",
        )
    )

    swings = store.all_swings(TF.H4)
    highs = [s for s in swings if s.kind == "H"]
    lows = [s for s in swings if s.kind == "L"]
    fig.add_trace(
        go.Scatter(
            x=[s.confirmed_at for s in highs],
            y=[s.price for s in highs],
            mode="markers",
            marker={"symbol": "triangle-down", "size": 10, "color": "blue"},
            name="Swing High",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[s.confirmed_at for s in lows],
            y=[s.price for s in lows],
            mode="markers",
            marker={"symbol": "triangle-up", "size": 10, "color": "purple"},
            name="Swing Low",
        )
    )

    bos = [e for e in events if e.kind == "BOS"]
    sweep = [e for e in events if e.kind == "SWEEP"]
    fig.add_trace(
        go.Scatter(
            x=[e.ts for e in bos],
            y=[e.swing.price for e in bos],
            mode="markers",
            marker={"symbol": "x", "size": 12, "color": "black"},
            name="BOS",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[e.ts for e in sweep],
            y=[e.swing.price for e in sweep],
            mode="markers",
            marker={"symbol": "star", "size": 12, "color": "gold"},
            name="Sweep",
        )
    )

    for fvg in store.all_fvgs(TF.H4):
        fig.add_shape(
            type="rect",
            x0=fvg.confirmed_at,
            x1=fvg.invalidated_at or bars[-1].close_ts,
            y0=fvg.bottom,
            y1=fvg.top,
            fillcolor=LEVEL_COLOR[fvg.level],
            line={"width": 0},
            layer="below",
        )

    bias_ts = [period_start] + [e.ts for e in store._bias_events]  # noqa: SLF001
    bias_state = ["neutral"] + [e.state for e in store._bias_events]  # noqa: SLF001
    fig.add_trace(
        go.Scatter(
            x=bias_ts,
            y=[BIAS_Y[s] for s in bias_state],
            mode="lines",
            line={"shape": "hv", "color": "green"},
            name="Bias",
            yaxis="y2",
        )
    )

    fig.update_layout(
        title="Phase 1 Demo — Structure + FVG (L1/L2/L3) + Bias",
        xaxis_rangeslider_visible=False,
        yaxis2={"overlaying": "y", "side": "right", "range": [-1.5, 1.5], "title": "Bias"},
    )
    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="2024-01-01:2024-02-01", help="YYYY-MM-DD:YYYY-MM-DD")
    args = parser.parse_args()
    start_s, end_s = args.period.split(":")
    start = datetime.strptime(start_s, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(end_s, "%Y-%m-%d").replace(tzinfo=UTC)

    print(f"[SYNTHETIC] generating 4H sample bars for {args.period} (Phase 1 tests real data "
          "access separately; this demo is engine-logic-only, per D-037 data-source independence)")
    bars = synthetic_4h_bars(start, end)
    print(f"bars: {len(bars)}")

    store, events, bars = run_engines(bars)

    swings = store.all_swings(TF.H4)
    fvgs = store.all_fvgs(TF.H4)
    print(f"swings confirmed: {len(swings)} ({sum(1 for s in swings if s.kind == 'H')} H / "
          f"{sum(1 for s in swings if s.kind == 'L')} L)")
    bos_count = sum(1 for e in events if e.kind == "BOS")
    sweep_count = sum(1 for e in events if e.kind == "SWEEP")
    print(f"BOS: {bos_count}   Sweep: {sweep_count}")
    print(f"FVGs: {len(fvgs)}  (L1={sum(1 for f in fvgs if f.level == 1)}, "
          f"L2={sum(1 for f in fvgs if f.level == 2)}, L3={sum(1 for f in fvgs if f.level == 3)})")
    print(f"bias transitions: {len(store._bias_events)}")  # noqa: SLF001
    for e in store._bias_events:  # noqa: SLF001
        print(f"  {e.ts.isoformat()} -> {e.state}")

    fig = build_chart(store, events, bars, start)
    out_dir = REPO_ROOT / "data" / "demo"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "phase1_chart.html"
    fig.write_html(out_path)
    print(f"\nchart written to {out_path}")
    print("Phase 1 demo complete.")


if __name__ == "__main__":
    main()
