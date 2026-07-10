#!/usr/bin/env python3
"""Phase 3 demo (docs/PHASE_PLAN.md working-software table).

End-to-end scenario report: Session/Calendar Engines, Setup Stream
(Engagement -> R -> S -> Armed), and the full Orchestrator wiring
(Order placed -> Market fill -> TP exit -> realized equity updated),
each printed against its hand-calculated expected value.

Usage:
    python scripts/demo_phase3.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.orchestrator import Orchestrator
from src.backtest.portfolio_arm import PortfolioArm
from src.core.types import FVG, TF, ArmId, Bar, NewsEvent, Tick
from src.displacement.d1_body import D1_DEFAULT_PARAMS, D1BodyRatio
from src.entry.m1 import M1EntryModel
from src.entry.m2 import M2EntryModel
from src.entry.m4 import M4EntryModel
from src.execution.cost_model import CostModelParams, StaticCostModel
from src.execution.fill_simulator import FillSimulator
from src.journal.duckdb_writer import DuckDBJournal
from src.risk.engine import RiskEngine, RiskEngineParams
from src.risk.portfolio import Portfolio
from src.session.calendar_engine import CalendarEngine
from src.session.session_engine import SessionEngine
from src.store.state_store import BiasEvent
from src.viz.trade_page import build_trade_page

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

SESSION = SessionEngine.from_config(window=("08:30", "10:30"), tz="America/New_York")
NO_BLACKOUT = CalendarEngine.from_config(
    [], currencies=("USD",), impacts=("red",), blackout_before_min=30, blackout_after_min=30,
)
SEED_TS = datetime(2024, 1, 10, 12, 0, tzinfo=UTC)
IN_WINDOW = datetime(2024, 1, 10, 14, 0, tzinfo=UTC)  # 09:00 ET, winter
TOP, BOTTOM = 100.0, 95.0
COST_MODEL = StaticCostModel(
    CostModelParams(
        slippage_stop_usd=0.10, news_slip_mult=3.0, slippage_market_usd=0.05,
        commission_per_unit=0.0,
    )
)


def _m1(ts, o, h, low, c) -> Bar:
    return Bar(
        tf=TF.M1, open_ts=ts, close_ts=ts + timedelta(minutes=1),
        o=o, h=h, l=low, c=c, tick_volume=1,
    )


def _m5(ts, o, h, low, c) -> Bar:
    return Bar(
        tf=TF.M5, open_ts=ts, close_ts=ts + timedelta(minutes=5),
        o=o, h=h, l=low, c=c, tick_volume=1,
    )


def report_line(label: str, expected, actual) -> None:
    ok = "OK" if expected == actual else "MISMATCH"
    print(f"  {label:<32} expected={expected!s:<10} actual={actual!s:<10} [{ok}]")


def demo_session_calendar() -> None:
    print("\n== Session + Calendar Engines (T3.1) ==")
    print(f"  09:00 ET in window? -> {SESSION.in_window(IN_WINDOW)}")
    report_line("in_window(09:00 ET)", True, SESSION.in_window(IN_WINDOW))
    outside = IN_WINDOW.replace(hour=20)  # 15:00 ET
    report_line("in_window(15:00 ET)", False, SESSION.in_window(outside))

    news = [NewsEvent(ts_utc=IN_WINDOW, currency="USD", impact="red", title="NFP", source="demo")]
    cal = CalendarEngine.from_config(
        news, currencies=("USD",), impacts=("red",), blackout_before_min=30, blackout_after_min=30,
    )
    report_line("in_blackout(at NFP)", True, cal.in_blackout(IN_WINDOW))
    report_line("in_blackout(+45min)", False, cal.in_blackout(IN_WINDOW + timedelta(minutes=45)))


def _make_arm(entry: str, sl_anchor: str) -> PortfolioArm:
    arm_id = ArmId(entry=entry, sl_anchor=sl_anchor)
    portfolio = Portfolio(portfolio_id=f"P-{entry}-{sl_anchor}", arm=arm_id, initial_equity=10_000)
    risk = RiskEngine(portfolio, RiskEngineParams(sizing_pct=0.005, min_stop_k_spread=0.01))
    fill_sim = FillSimulator(COST_MODEL, in_news_checker=lambda ts: False)
    return PortfolioArm(arm_id=arm_id, portfolio=portfolio, risk=risk, fill_sim=fill_sim)


def _warmup_ticks() -> list[Tick]:
    """Pre-run ticks (D-049): one per ET hour, strictly before SEED_TS, so
    median_spread() has data before anything on the demo's own timeline."""
    et = ZoneInfo("America/New_York")
    return [
        Tick(ts=datetime(2024, 1, 1, h, 0, tzinfo=et).astimezone(UTC), bid=2000.0, ask=2000.01)
        for h in range(24)
    ]


def _make_orchestrator(bars_1m, bars_5m, ticks, arms, journal=None) -> Orchestrator:
    entry_models = {
        "M1": M1EntryModel(session=SESSION, get_setup=None),
        "M2": M2EntryModel(get_setup=None),
        "M4": M4EntryModel(get_setup=None),
    }
    orch = Orchestrator(
        bars_1m=bars_1m, bars_5m=bars_5m, bars_4h=[], ticks=ticks,
        session=SESSION, calendar=NO_BLACKOUT, arms=arms, entry_models=entry_models,
        displacement_model=D1BodyRatio(), displacement_params=D1_DEFAULT_PARAMS,
        cost_model=COST_MODEL, sl_buffer_usd=0.05, spread_warmup_ticks=_warmup_ticks(),
        journal=journal,
    )
    orch.store.put(
        FVG(
            id="FVG-H4-1", tf=TF.H4, direction="bull", top=TOP, bottom=BOTTOM, level=1,
            created_at=SEED_TS, confirmed_at=SEED_TS, mitigation_pct=0.0, invalidated_at=None,
            bos_link=None, displacement=False,
        )
    )
    orch.store.put(BiasEvent(ts=SEED_TS, state="bullish", trigger_bos=None))
    return orch


def demo_setup_stream_progression() -> None:
    print("\n== Setup Stream progression (T3.2): Engagement -> R -> S -> Armed ==")
    r_ts = IN_WINDOW + timedelta(minutes=5)
    s_ts = IN_WINDOW + timedelta(minutes=10)
    base = IN_WINDOW + timedelta(minutes=20)
    bars_1m = [
        _m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2),
        _m1(base, 97.5, 97.6, 97.0, 97.3),
        _m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0),
        _m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3),
        _m1(base + timedelta(minutes=3), 96.8, 97.3, 96.7, 97.2),  # inversion, closes 97.2
    ]
    bars_5m = [_m5(r_ts, 99.0, 99.8, 97.0, 99.5), _m5(s_ts, 98.0, 98.5, 96.0, 97.5)]
    orch = _make_orchestrator(bars_1m, bars_5m, ticks=[], arms=[_make_arm("M2", "S_wick")])
    result = orch.run()
    report_line("engaged events", 1, result.engaged)
    report_line("reaction_seen events", 1, result.reaction_seen)
    report_line("sweep_confirmed events", 1, result.sweep_confirmed)
    report_line("armed events", 1, result.armed)
    report_line("orders placed (M2, no ticks yet)", 1, result.orders_placed)


def demo_orchestrator_end_to_end() -> None:
    print("\n== Orchestrator end-to-end (T3.3): Order -> Fill -> Exit -> Equity ==")
    r_ts = IN_WINDOW + timedelta(minutes=5)
    s_ts = IN_WINDOW + timedelta(minutes=10)
    base = IN_WINDOW + timedelta(minutes=20)
    bars_1m = [
        _m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2),
        _m1(base, 97.5, 97.6, 97.0, 97.3),
        _m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0),
        _m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3),
        _m1(base + timedelta(minutes=3), 96.8, 97.3, 96.7, 97.2),
    ]
    bars_5m = [_m5(r_ts, 99.0, 99.8, 97.0, 99.5), _m5(s_ts, 98.0, 98.5, 96.0, 97.5)]
    inversion_ts = bars_1m[-1].close_ts
    ticks = [
        Tick(ts=inversion_ts + timedelta(seconds=1), bid=97.15, ask=97.25),  # entry fill
        Tick(ts=inversion_ts + timedelta(minutes=5), bid=101.0, ask=101.1),  # TP exit
    ]
    arm = _make_arm("M2", "S_wick")
    orch = _make_orchestrator(bars_1m, bars_5m, ticks, arms=[arm])
    orch.run()
    print(f"  realized_equity before: 10000.0, after: {arm.portfolio.realized_equity}")
    report_line("equity changed (KI-006 wiring)", True, arm.portfolio.realized_equity != 10_000.0)


def demo_context_snapshots_and_viz() -> None:
    print("\n== Context Snapshots (T3.6) + Trade Page Viz (T3.5) ==")
    r_ts = IN_WINDOW + timedelta(minutes=5)
    s_ts = IN_WINDOW + timedelta(minutes=10)
    base = IN_WINDOW + timedelta(minutes=20)
    bars_1m = [
        _m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2),
        _m1(base, 97.5, 97.6, 97.0, 97.3),
        _m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0),
        _m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3),
        _m1(base + timedelta(minutes=3), 96.8, 97.3, 96.7, 97.2),
    ]
    bars_5m = [_m5(r_ts, 99.0, 99.8, 97.0, 99.5), _m5(s_ts, 98.0, 98.5, 96.0, 97.5)]
    inversion_ts = bars_1m[-1].close_ts
    ticks = [
        Tick(ts=inversion_ts + timedelta(seconds=1), bid=97.15, ask=97.25),
        Tick(ts=inversion_ts + timedelta(minutes=5), bid=101.0, ask=101.1),
    ]
    arm = _make_arm("M2", "S_wick")
    out_dir = REPO_ROOT / "data" / "demo"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "phase3_demo.duckdb"
    db_path.unlink(missing_ok=True)
    journal = DuckDBJournal(db_path, SCHEMA_PATH)
    orch = _make_orchestrator(bars_1m, bars_5m, ticks, arms=[arm], journal=journal)
    orch.run()  # closes `journal`

    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    snapshot_kinds = reader.query("SELECT kind FROM context_snapshots ORDER BY ts")
    report_line(
        "context_snapshots kinds", ["engagement", "armed", "entry", "exit"],
        [k for (k,) in snapshot_kinds],
    )
    [(trade_id,)] = reader.query("SELECT trade_id FROM trades")
    fig = build_trade_page(reader, trade_id, bars_1m)
    reader.close()

    out_path = out_dir / "phase3_trade_page.html"
    fig.write_html(out_path)
    print(f"  trade page written to {out_path}")


def main() -> None:
    print("Phase 3 demo: Session/Calendar/Setup Stream/Orchestrator vs. hand calculation")
    demo_session_calendar()
    demo_setup_stream_progression()
    demo_orchestrator_end_to_end()
    demo_context_snapshots_and_viz()
    print("\nPhase 3 demo complete.")


if __name__ == "__main__":
    main()
