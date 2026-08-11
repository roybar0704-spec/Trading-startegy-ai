#!/usr/bin/env python3
"""B-3 Real-Data Diagnostic Validation Gate -- Commit 1 (WORK_ORDER_B3.md).

Diagnostic-only. NOT T3.4 (docs/PHASE_PLAN.md). Does not close any
Research Readiness Review checklist item (docs/RESEARCH_READINESS_REVIEW.md).

Runs the existing, unmodified ``build_orchestrator``/``Orchestrator`` against
the one real month ever validated end-to-end (November 2022, D-069/D-070) --
the first time the engine (Structure/FVG/iFVG/SetupStream/Orchestrator) is
exposed to real tick data instead of synthetic Fixtures. Read-only: no
production code is touched by this script regardless of outcome.

Non-Goals (Roy-approved, WORK_ORDER_B3.md S1.5/S6 -- must stay true of every
report this script produces):
  - KI-010 (real news calendar) is not validated here -- the calendar is
    injected empty, so Blackout/news_cross are never exercised.
  - KI-022 (Validator calibration) is not closed here -- this script does not
    run the Validator at all; any anomaly found must be cross-checked against
    D-071's already-flagged gap/spike windows before being treated as new.
  - No research/statistical conclusions are drawn from the printed counters
    (no Win Rate, PnL, R-multiple interpretation) -- this is a pass/fail
    sanity check on whether the engine runs to completion, nothing more.

Usage:
    python scripts/diagnostics/run_b3_real_data_diagnostic.py
"""

from __future__ import annotations

import sys
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.backtest.run_builder import build_orchestrator  # noqa: E402
from src.config.models import (  # noqa: E402
    Arms,
    Baseline,
    Guards,
    Holdout,
    Period,
    RunConfig,
    WalkForward,
    load_parameters,
    load_rules_v1,
)
from src.core.types import TF, NewsEvent, RunIdentity, Tick  # noqa: E402
from src.data.bar_builder import BarBuilder  # noqa: E402
from src.data.holdout import XAUUSD_HOLDOUT_RANGE  # noqa: E402
from src.data.tick_store import TickParquetStore  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "XAUUSD"
YEAR, MONTH = 2022, 11


def log(msg: str) -> None:
    print(msg, flush=True)


def _minimal_run_config() -> RunConfig:
    """Single arm (M2 x S_body) -- WORK_ORDER_B3.md S4 Commit 1's stated
    minimal-scope recommendation. Fields outside `arms` are schema-required
    by RunConfig but not consumed by build_orchestrator's own logic; values
    below are placeholders, not a declared Experiment (this run is not one)."""
    return RunConfig(
        experiment="B3_real_data_diagnostic",
        objective="oos_wf_expectancy_r",
        guards=Guards(p_vs_baseline_max=0.05, pf_min=1.3, min_trades=150, worst_quarter_r_min=-15),
        period=Period(start=date(YEAR, MONTH, 1), end=date(YEAR, MONTH, 30)),
        holdout=Holdout(last_months=6, unlocked=False),
        walk_forward=WalkForward(train_months=9, test_months=3),
        arms=Arms(entry_models=("M2",), sl_anchors=("S_body",)),
        baseline=Baseline(n_sims=1000, seed=42),
        seed=42,
    )


def main() -> int:
    log(f"=== B-3 Real-Data Diagnostic Run -- {SYMBOL} {YEAR}-{MONTH:02d} ===")
    log("Diagnostic-only. NOT T3.4. Does not close RRR. No research conclusions drawn.")
    log("Non-Goals in effect: KI-010 not validated (empty news calendar); "
        "KI-022 not closed (validator not run at all in this script).")
    log("")

    # D-085: B-3 diagnostic uses November 2022 only; no unlock flag.
    store = TickParquetStore(REPO_ROOT / "data" / "ticks", holdout_range=XAUUSD_HOLDOUT_RANGE)
    month_path = store.month_path(SYMBOL, YEAR, MONTH)
    log(f"Loading ticks from {month_path} ...")
    ticks_df = store.read_month(SYMBOL, YEAR, MONTH)
    log(f"  loaded {ticks_df.height:,} ticks")

    builder = BarBuilder()
    log("Building 1M/5M/4H bars (Mid price, BarBuilder, unmodified) ...")
    bars_1m = builder.build(ticks_df, TF.M1)
    bars_5m = builder.build(ticks_df, TF.M5)
    bars_4h = builder.build(ticks_df, TF.H4)
    log(f"  bars: 1M={len(bars_1m):,} 5M={len(bars_5m):,} 4H={len(bars_4h):,}")

    log("Converting tick DataFrame rows to Tick objects ...")
    ticks = [
        Tick(ts=row["ts"], bid=row["bid"], ask=row["ask"])
        for row in ticks_df.iter_rows(named=True)
    ]
    log(f"  converted {len(ticks):,} Tick objects")

    news: list[NewsEvent] = []  # Non-Goal: KI-010 not validated -- empty by design

    log("Loading frozen rules_v1.yaml + parameters.yaml (unmodified loaders) ...")
    rules = load_rules_v1()
    parameters = load_parameters()
    run_config = _minimal_run_config()

    identity = RunIdentity(
        data_version=store.data_version(SYMBOL, [(YEAR, MONTH)]),
        # "fixture": this is not a declared research split (in_sample/wf/holdout/
        # baseline) -- RunIdentity's Literal has no "diagnostic" option, and
        # "fixture" is the closest existing label for "not a real Experiment".
        split_type="fixture",
        seed=None,
    )

    log("")
    log("Building Orchestrator (build_orchestrator, unmodified) -- "
        "arms=M2xS_body, empty news calendar, no Journal (counters only) ...")
    orch = build_orchestrator(
        rules,
        parameters,
        run_config,
        identity=identity,
        bars_1m=bars_1m,
        bars_5m=bars_5m,
        bars_4h=bars_4h,
        ticks=ticks,
        news=news,
        run_id="b3-diagnostic-2022-11",
    )

    log("Running orchestrator.run() over the full real month ...")
    try:
        result = orch.run()
    except Exception:
        log("")
        log("=== DIAGNOSTIC RUN CRASHED ===")
        traceback.print_exc()
        return 1

    log("")
    log("=== DIAGNOSTIC RUN COMPLETE (no crash) ===")
    log(
        f"  engaged={result.engaged} reaction_seen={result.reaction_seen} "
        f"sweep_confirmed={result.sweep_confirmed} armed={result.armed}"
    )
    log(f"  expired={result.expired} invalidated={result.invalidated} no_ifvg={result.no_ifvg}")
    log(
        f"  orders_placed={result.orders_placed} orders_rejected={result.orders_rejected} "
        f"fills={result.fills} orders_cancelled={result.orders_cancelled}"
    )
    log("")
    log(
        "Non-Goals reminder: no research/statistical conclusions drawn from the "
        "counters above; KI-010 not validated (Blackout never exercised); KI-022 "
        "not closed (Validator not invoked by this script at all)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
