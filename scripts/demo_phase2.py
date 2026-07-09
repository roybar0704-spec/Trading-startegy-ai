#!/usr/bin/env python3
"""Phase 2 demo (docs/PHASE_PLAN.md working-software table).

Fill-scenario report: Limit / Market / SL-First / Gap-Through / Sizing,
each printed against its hand-calculated expected value.

Usage:
    python scripts/demo_phase2.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.types import TF, ArmId, Bar, Order, OrderIntent, Tick
from src.data.spread_report import HourSpreadStats, SpreadReport
from src.execution.cost_model import CostModelParams, StaticCostModel
from src.execution.fill_simulator import FillSimulator
from src.risk.engine import RiskEngine, RiskEngineParams
from src.risk.portfolio import Portfolio
from src.risk.sizing import size_units
from src.store.state_store import StateStore

NY = ZoneInfo("America/New_York")
COST_MODEL = StaticCostModel(
    CostModelParams(
        slippage_stop_usd=0.10,
        news_slip_mult=3.0,
        slippage_market_usd=0.05,
        commission_per_unit=0.0,
    )
)


def _order(**overrides) -> Order:
    base = {
        "order_id": "DEMO",
        "setup_id": "S1",
        "portfolio_id": "P1",
        "otype": "limit",
        "side": "buy",
        "price": 2000.0,
        "sl": 1998.0,
        "tp": 2006.0,
        "units": 10.0,
        "placed_at": datetime(2024, 1, 1, tzinfo=UTC),
        "valid_until": datetime(2024, 1, 1, 12, tzinfo=UTC),
    }
    base.update(overrides)
    return Order(**base)


def report_line(label: str, expected: float, actual: float) -> None:
    ok = "OK" if abs(expected - actual) < 1e-9 else "MISMATCH"
    print(f"  {label:<28} expected={expected:<12} actual={actual:<12} [{ok}]")


def demo_limit_fill() -> None:
    print("\n== Limit fill (AT-2.1): buy Limit at P, fills only when Ask <= P, at P ==")
    sim = FillSimulator(COST_MODEL, in_news_checker=lambda ts: False)
    order = _order(otype="limit", side="buy", price=2000.0)
    sim.place(order, "P1")
    sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, tzinfo=UTC), bid=2000.3, ask=2000.5))
    print("  tick ask=2000.5 (> 2000.0): no fill expected ->", order.status)
    fills = sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, 1, tzinfo=UTC), bid=1999.7, ask=1999.9))
    report_line("fill price (hand: 2000.0)", 2000.0, fills[0].price)


def demo_market_fill() -> None:
    print("\n== Market fill: Ask + market_slippage (buy side) ==")
    sim = FillSimulator(COST_MODEL, in_news_checker=lambda ts: False)
    order = _order(otype="market", side="buy", price=None)
    sim.place(order, "P1")
    fills = sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, tzinfo=UTC), bid=2000.0, ask=2000.2))
    report_line("fill price (hand: 2000.2+0.05)", 2000.25, fills[0].price)


def demo_sl_first_fallback() -> None:
    print("\n== SL-First fallback (AT-2.3): 1M bar touches both SL and TP -> SL ==")
    sim = FillSimulator(COST_MODEL, in_news_checker=lambda ts: False)
    order = _order(otype="market", side="buy", price=None, sl=1998.0, tp=2004.0)
    sim.place(order, "P1")
    sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, tzinfo=UTC), bid=2000.0, ask=2000.2))
    bar = Bar(
        tf=TF.M1,
        open_ts=datetime(2024, 1, 1, 2, tzinfo=UTC),
        close_ts=datetime(2024, 1, 1, 2, 1, tzinfo=UTC),
        o=2000.0, h=2005.0, l=1997.0, c=2001.0, tick_volume=1,
    )
    fills = sim.on_bar_1m(bar)
    print(f"  bar range [1997, 2005] spans SL(1998) and TP(2004) -> kind={fills[0].kind}")
    report_line("fill price (hand: 1998.0-0.10)", 1997.90, fills[0].price)


def demo_gap_through() -> None:
    print("\n== Gap-Through (AT-2.4): bar opens beyond SL -> fill at open, never at SL ==")
    sim = FillSimulator(COST_MODEL, in_news_checker=lambda ts: False)
    order = _order(otype="market", side="buy", price=None, sl=1998.0, tp=2010.0)
    sim.place(order, "P1")
    sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, tzinfo=UTC), bid=2000.0, ask=2000.2))
    bar = Bar(
        tf=TF.M1,
        open_ts=datetime(2024, 1, 1, 6, tzinfo=UTC),
        close_ts=datetime(2024, 1, 1, 6, 1, tzinfo=UTC),
        o=1995.0, h=1995.5, l=1994.0, c=1994.5, tick_volume=1,
    )
    fills = sim.on_bar_1m(bar)
    print(f"  bar opens at 1995.0 (< SL 1998.0) -> kind={fills[0].kind}")
    report_line("fill price (hand: 1995.0-0.10)", 1994.90, fills[0].price)
    print(f"  fill price != SL price (1998.0)? {fills[0].price != order.sl}")


def demo_sizing() -> None:
    print("\n== Sizing (AT-2.5): 0.5% of realized equity / stop distance, no rounding (RA-26) ==")
    units = size_units(equity=10_000, sizing_pct=0.005, stop_distance_usd=2.00)
    report_line("units (hand: 50/2.00)", 25.0, units)

    now = datetime(2024, 1, 1, 14, 0, tzinfo=UTC)
    spread_report = SpreadReport(
        symbol="XAUUSD",
        by_hour={
            9: HourSpreadStats(
                hour_et=9, tick_count=100, mean_spread=0.10, p25_spread=0.10,
                median_spread=0.10, p75_spread=0.10, p95_spread=0.10,
            )
        },
    )
    store = StateStore(spread_report=spread_report)
    ctx = store.as_of(now)
    arm = ArmId(entry="M2", sl_anchor="S_body")
    portfolio = Portfolio(portfolio_id="P1", arm=arm, initial_equity=10_000)
    engine = RiskEngine(portfolio, RiskEngineParams(sizing_pct=0.005, min_stop_k_spread=3.0))
    intent = OrderIntent(
        setup_id="S1", arm=arm, side="long", otype="market",
        price=2000.00, sl=1998.00, tp=2006.00, valid_until=now,
    )
    order = engine.approve(intent, ctx)
    print(f"  RiskEngine.approve() -> Order, units={order.units}")


def main() -> None:
    print("Phase 2 demo: fill scenarios vs. hand calculation")
    demo_limit_fill()
    demo_market_fill()
    demo_sl_first_fallback()
    demo_gap_through()
    demo_sizing()
    print("\nPhase 2 demo complete.")


if __name__ == "__main__":
    main()
