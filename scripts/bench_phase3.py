#!/usr/bin/env python3
"""Phase 3 performance benchmark (docs/QUALITY_GATES.md Performance Gate).

No pre-declared Phase 3 budget exists in docs/QUALITY_GATES.md; per D-032
this establishes the initial measurement for the Orchestrator's merged-timeline
throughput (quiet bars, no signals -- the baseline looping/state-update cost
that dominates a real 3-year run). Results are written to benchmarks/.
"""

from __future__ import annotations

import json
import resource
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.orchestrator import Orchestrator
from src.backtest.portfolio_arm import PortfolioArm
from src.core.types import TF, ArmId, Bar
from src.displacement.d1_body import D1_DEFAULT_PARAMS, D1BodyRatio
from src.entry.m1 import M1EntryModel
from src.entry.m2 import M2EntryModel
from src.entry.m4 import M4EntryModel
from src.execution.cost_model import CostModelParams, StaticCostModel
from src.execution.fill_simulator import FillSimulator
from src.risk.engine import RiskEngine, RiskEngineParams
from src.risk.portfolio import Portfolio
from src.session.calendar_engine import CalendarEngine
from src.session.session_engine import SessionEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION = SessionEngine.from_config(window=("08:30", "10:30"), tz="America/New_York")
NO_BLACKOUT = CalendarEngine.from_config(
    [], currencies=("USD",), impacts=("red",), blackout_before_min=30, blackout_after_min=30,
)
N_DAYS = 20  # 1M+5M quiet bars over N_DAYS full 24h days


def peak_rss_mb() -> float:
    """Peak resident set size so far, in MB (Linux: ru_maxrss is KB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _quiet_bars() -> tuple[list[Bar], list[Bar]]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars_1m, bars_5m = [], []
    ts = start
    end = start + timedelta(days=N_DAYS)
    price = 2000.0
    i = 0
    while ts < end:
        bars_1m.append(Bar(tf=TF.M1, open_ts=ts, close_ts=ts + timedelta(minutes=1),
                            o=price, h=price + 0.1, l=price - 0.1, c=price, tick_volume=1))
        if i % 5 == 0:
            bars_5m.append(Bar(tf=TF.M5, open_ts=ts, close_ts=ts + timedelta(minutes=5),
                                o=price, h=price + 0.1, l=price - 0.1, c=price, tick_volume=5))
        ts += timedelta(minutes=1)
        i += 1
    return bars_1m, bars_5m


def _make_arm() -> PortfolioArm:
    arm_id = ArmId(entry="M2", sl_anchor="S_body")
    portfolio = Portfolio(portfolio_id="P1", arm=arm_id, initial_equity=10_000)
    risk = RiskEngine(portfolio, RiskEngineParams(sizing_pct=0.005, min_stop_k_spread=3.0))
    cost_model = StaticCostModel(
        CostModelParams(slippage_stop_usd=0.10, news_slip_mult=3.0,
                         slippage_market_usd=0.05, commission_per_unit=0.0)
    )
    fill_sim = FillSimulator(cost_model, in_news_checker=lambda ts: False)
    return PortfolioArm(arm_id=arm_id, portfolio=portfolio, risk=risk, fill_sim=fill_sim)


def bench_orchestrator() -> tuple[float, int]:
    bars_1m, bars_5m = _quiet_bars()
    entry_models = {
        "M1": M1EntryModel(session=SESSION, get_setup=None),
        "M2": M2EntryModel(get_setup=None),
        "M4": M4EntryModel(get_setup=None),
    }
    cost_model = StaticCostModel(
        CostModelParams(slippage_stop_usd=0.10, news_slip_mult=3.0,
                         slippage_market_usd=0.05, commission_per_unit=0.0)
    )
    # Quiet bars, no signals -- median_spread() is never queried, so no warm-up
    # ticks are needed here (unlike a real/signal-bearing run, D-049).
    orch = Orchestrator(
        bars_1m=bars_1m, bars_5m=bars_5m, bars_4h=[], ticks=[],
        session=SESSION, calendar=NO_BLACKOUT, arms=[_make_arm()], entry_models=entry_models,
        displacement_model=D1BodyRatio(), displacement_params=D1_DEFAULT_PARAMS,
        cost_model=cost_model, sl_buffer_usd=0.3,
    )

    t0 = time.perf_counter()
    orch.run()
    seconds = time.perf_counter() - t0
    return seconds, len(bars_1m) + len(bars_5m)


def main() -> None:
    seconds, n_bars = bench_orchestrator()

    result = {
        "measured_at": datetime.now(UTC).isoformat(),
        "orchestrator": {
            "days_simulated": N_DAYS,
            "bars_processed": n_bars,
            "seconds": round(seconds, 4),
            "bars_per_second": round(n_bars / seconds, 1) if seconds > 0 else None,
        },
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "note": (
            "No pre-declared Phase 3 budget in QUALITY_GATES.md; establishes D-032's "
            "initial measurement. Quiet bars only (no signals) -- baseline looping cost."
        ),
    }

    bench_dir = REPO_ROOT / "benchmarks"
    bench_dir.mkdir(exist_ok=True)
    out_path = bench_dir / "phase3_bench.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"\nwritten to {out_path}")


if __name__ == "__main__":
    main()
