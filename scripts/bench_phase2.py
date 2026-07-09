#!/usr/bin/env python3
"""Phase 2 performance benchmark (docs/QUALITY_GATES.md Performance Gate).

No pre-declared Phase 2 budget exists in docs/QUALITY_GATES.md; per D-032
this establishes the initial measurement for RiskEngine.approve() and
FillSimulator.on_tick() throughput. Results are written to benchmarks/.
"""

from __future__ import annotations

import json
import random
import resource
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.types import ArmId, Order, OrderIntent, Tick
from src.data.spread_report import HourSpreadStats, SpreadReport
from src.execution.cost_model import CostModelParams, StaticCostModel
from src.execution.fill_simulator import FillSimulator
from src.risk.engine import RiskEngine, RiskEngineParams
from src.risk.portfolio import Portfolio
from src.store.state_store import StateStore

REPO_ROOT = Path(__file__).resolve().parents[1]
N_INTENTS = 50_000
N_TICKS = 50_000


def peak_rss_mb() -> float:
    """Peak resident set size so far, in MB (Linux: ru_maxrss is KB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def bench_risk_engine() -> float:
    spread_report = SpreadReport(
        symbol="XAUUSD",
        by_hour={
            h: HourSpreadStats(
                hour_et=h, tick_count=100, mean_spread=0.20, p25_spread=0.20,
                median_spread=0.20, p75_spread=0.20, p95_spread=0.20,
            )
            for h in range(24)
        },
    )
    store = StateStore(spread_report=spread_report)
    arm = ArmId(entry="M2", sl_anchor="S_body")
    portfolio = Portfolio(portfolio_id="P1", arm=arm, initial_equity=10_000)
    engine = RiskEngine(portfolio, RiskEngineParams(sizing_pct=0.005, min_stop_k_spread=3.0))

    now = datetime(2024, 1, 1, 14, 0, tzinfo=UTC)
    ctx = store.as_of(now)
    t0 = time.perf_counter()
    for i in range(N_INTENTS):
        intent = OrderIntent(
            setup_id=f"S{i}", arm=arm, side="long", otype="market",
            price=2000.00, sl=1998.00, tp=2006.00, valid_until=now,
        )
        engine.approve(intent, ctx)
    return time.perf_counter() - t0


def bench_fill_simulator() -> float:
    cost_model = StaticCostModel(
        CostModelParams(
            slippage_stop_usd=0.10, news_slip_mult=3.0, slippage_market_usd=0.05,
            commission_per_unit=0.0,
        )
    )
    sim = FillSimulator(cost_model, in_news_checker=lambda ts: False)
    rng = random.Random(5)
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(200):
        order = Order(
            order_id=f"O{i}", setup_id=f"S{i}", portfolio_id="P1", otype="limit", side="buy",
            price=2000.0, sl=1998.0, tp=2006.0, units=1.0,
            placed_at=ts, valid_until=ts + timedelta(hours=1),
        )
        sim.place(order, "P1")

    t0 = time.perf_counter()
    price = 2000.0
    for _ in range(N_TICKS):
        price += rng.uniform(-0.05, 0.05)
        sim.on_tick(Tick(ts=ts, bid=price, ask=price + 0.2))
        ts += timedelta(seconds=1)
    return time.perf_counter() - t0


def main() -> None:
    risk_seconds = bench_risk_engine()
    fill_seconds = bench_fill_simulator()

    result = {
        "measured_at": datetime.now(UTC).isoformat(),
        "risk_engine": {
            "intents": N_INTENTS,
            "seconds": round(risk_seconds, 4),
            "per_second": round(N_INTENTS / risk_seconds, 1) if risk_seconds > 0 else None,
        },
        "fill_simulator": {
            "ticks": N_TICKS,
            "seconds": round(fill_seconds, 4),
            "per_second": round(N_TICKS / fill_seconds, 1) if fill_seconds > 0 else None,
        },
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "note": (
            "No pre-declared Phase 2 budget in QUALITY_GATES.md; "
            "establishes D-032's initial measurement."
        ),
    }

    bench_dir = REPO_ROOT / "benchmarks"
    bench_dir.mkdir(exist_ok=True)
    out_path = bench_dir / "phase2_bench.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"\nwritten to {out_path}")


if __name__ == "__main__":
    main()
