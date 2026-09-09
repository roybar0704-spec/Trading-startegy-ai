#!/usr/bin/env python3
"""T3.4 -- first real declared Experiment (docs/PHASE_PLAN.md).

This is a Declared Experiment Runner for ONE specific, Roy-approved scope --
NOT a generic backtest runner. The scope is LOCKED as module-level constants
(see below), not exposed as CLI arguments: this script cannot be invoked
against any other date range, arm, SL anchor, tick-data source, or news
calendar. Runs the SMC strategy for real, against real XAUUSD tick data,
for the single arm M2 x S_body over an In-Sample window -- the first
backtest run in this project's history to be a genuinely declared
Experiment: a real DuckDBJournal (not None), a real registry_path (not
None), and split_type="in_sample" (not "fixture"). This is NOT a
diagnostic.

LOCKED SCOPE (Roy-approved, immutable -- see _LOCKED_* constants below):
    start=2024-01 end=2024-03 arm=M2 sl_anchor=S_body split_type=in_sample
    ticks_dir=data/ticks news_path=data/news/bls_calendar.csv
Changing any of these is a scope change requiring a new explicit decision,
not a CLI flag -- there is deliberately no way to override them at runtime.

News Calendar (approved Option A, LOCKED): the real BLS calendar
(data/news/bls_calendar.csv, CPI + Employment Situation, D-077/RA-23) is
loaded via the existing, unmodified src/data/news_loader.py::load_bls_csv()
and passed to build_orchestrator as-is -- no filtering/conversion in this
script beyond the direct load call (CalendarEngine.from_config already does
its own currency/impact filtering). Blackout logic is therefore LIVE for
this run, not disabled. Coverage remains Phase 1 only (CPI + Employment
Situation, 2 of 7 known High-Impact-USD event types) -- KI-010's documented
limitation is unchanged and is not being extended by this run.

Hold-Out guard (D-073/D-085 pattern, mirrors run_b8_performance_real_data.py):
two independent checks refuse any month at or after 2025-07 -- this script
must never read the Hold-Out window (2025-07..2025-12). Since the date
range is now a locked constant rather than a CLI input, these checks guard
against the constant ever being edited to an out-of-scope value, not
against user-supplied input.

Frozen-config guard: verify_frozen_rules() is called before anything else;
any drift in config/rules_v1.yaml aborts immediately.

Only the OUTPUT destinations remain configurable (they affect where
evidence is written, not what Experiment is declared or what data is read).

Usage:
    uv run python scripts/run_t3_4_in_sample.py \\
        --journal-path data/journal/t3_4_in_sample.duckdb \\
        --registry-path data/registry/runs.jsonl \\
        --viz-dir data/journal/t3_4_in_sample_viz
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.run_builder import build_orchestrator  # noqa: E402
from src.config.frozen_guard import verify_frozen_rules  # noqa: E402
from src.config.models import (  # noqa: E402
    Arms, Baseline, Guards, Holdout, Period, RunConfig, WalkForward,
    load_parameters, load_rules_v1,
)
from src.core.types import TF, RunIdentity, Tick  # noqa: E402
from src.data.bar_builder import BarBuilder  # noqa: E402
from src.data.holdout import XAUUSD_HOLDOUT_RANGE  # noqa: E402
from src.data.news_loader import load_bls_csv  # noqa: E402
from src.data.tick_store import TickParquetStore, months_between  # noqa: E402
from src.journal.duckdb_writer import DuckDBJournal  # noqa: E402
from src.viz.trade_page import build_trade_page  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "XAUUSD"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

# T3.4 LOCKED SCOPE (Roy-approved, immutable). Deliberately NOT exposed as
# CLI arguments -- this is a Declared Experiment Runner for exactly this
# scope, not a generic backtest runner. Changing any of these values is a
# scope change requiring a new explicit decision, not a runtime flag.
_LOCKED_START = "2024-01"
_LOCKED_END = "2024-03"
_LOCKED_ARM = "M2"
_LOCKED_SL_ANCHOR = "S_body"
_LOCKED_TICKS_DIR = REPO_ROOT / "data" / "ticks"
_LOCKED_NEWS_PATH = REPO_ROOT / "data" / "news" / "bls_calendar.csv"
_LOCKED_SEED = 42

# D-073 pattern: last calendar month this script is ever allowed to load.
# Hardcoded, not read from config -- cannot be loosened by editing config/run_default.yaml.
_LAST_ALLOWED_MONTH = (2025, 6)


def log(msg: str) -> None:
    print(msg, flush=True)


def _parse_year_month(s: str) -> tuple[int, int]:
    dt = datetime.strptime(s, "%Y-%m")
    return dt.year, dt.month


def _refuse_if_holdout(year: int, month: int) -> str | None:
    if (year, month) > _LAST_ALLOWED_MONTH:
        return (
            f"{year:04d}-{month:02d} is at/after the Hold-Out boundary "
            f"({_LAST_ALLOWED_MONTH[0]:04d}-{_LAST_ALLOWED_MONTH[1]:02d} is the last "
            "allowed month, D-073). This script must never read 2025-07 onward."
        )
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    """Only OUTPUT destinations are configurable. Experiment scope (dates,
    arm, SL anchor, tick-data source, news calendar) is locked as module
    constants above and is deliberately NOT exposed here."""
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--journal-path", default=str(REPO_ROOT / "data" / "journal" / "t3_4_in_sample.duckdb"))
    p.add_argument("--registry-path", default=str(REPO_ROOT / "data" / "registry" / "runs.jsonl"))
    p.add_argument("--viz-dir", default=str(REPO_ROOT / "data" / "journal" / "t3_4_in_sample_viz"))
    p.add_argument("--viz-limit", type=int, default=20, help="Max trade pages rendered for AT-3.10")
    return p


def _minimal_run_config(arm: str, sl_anchor: str, start: date, end: date, seed: int) -> RunConfig:
    """Single arm, mirrors run_b3/run_b8's `_minimal_run_config` precedent. Fields
    outside `arms` are schema-required by RunConfig but not consumed by
    build_orchestrator's own logic for this narrow, single-arm In-Sample run."""
    return RunConfig(
        experiment="T3_4_in_sample_first_real_run",
        objective="oos_wf_expectancy_r",
        guards=Guards(p_vs_baseline_max=0.05, pf_min=1.3, min_trades=150, worst_quarter_r_min=-15),
        period=Period(start=start, end=end),
        holdout=Holdout(last_months=6, unlocked=False),
        walk_forward=WalkForward(train_months=9, test_months=3),
        arms=Arms(entry_models=(arm,), sl_anchors=(sl_anchor,)),
        baseline=Baseline(n_sims=1000, seed=seed),
        seed=seed,
    )


def main() -> int:
    args = build_arg_parser().parse_args()
    start_year, start_month = _parse_year_month(_LOCKED_START)
    end_year, end_month = _parse_year_month(_LOCKED_END)

    log(f"=== T3.4 -- FIRST REAL DECLARED EXPERIMENT -- {SYMBOL} {_LOCKED_START}..{_LOCKED_END} "
        f"({_LOCKED_ARM}x{_LOCKED_SL_ANCHOR}) [LOCKED SCOPE] ===")
    log("journal != None. registry_path is real. split_type=in_sample. THIS IS T3.4.")

    # Guard 0: frozen-config integrity, before anything else.
    digest = verify_frozen_rules()
    log(f"frozen-config OK: rules_v1.yaml hash = {digest}")

    # Guard 1 (constant-level): reject before touching the filesystem at all.
    # There is no CLI input to validate here -- start/end are locked module
    # constants; this guards against the constants themselves ever being
    # edited to an out-of-scope value.
    for label, y, m in (("_LOCKED_START", start_year, start_month), ("_LOCKED_END", end_year, end_month)):
        refusal = _refuse_if_holdout(y, m)
        if refusal:
            print(f"REFUSING TO RUN: {label} {refusal} No data was read.", file=sys.stderr)
            return 1
    if (start_year, start_month) > (end_year, end_month):
        print(f"ERROR: _LOCKED_START ({_LOCKED_START}) must be <= _LOCKED_END ({_LOCKED_END}).", file=sys.stderr)
        return 1

    # Pre-Flight: refuse to reuse an existing journal path (avoid ambiguous
    # append-vs-overwrite semantics -- mirrors run_separate_holdout.py's
    # "refuse if destination already exists" pattern).
    journal_path = Path(args.journal_path)
    if journal_path.exists():
        print(
            f"REFUSING TO RUN: {journal_path} already exists -- refusing to risk "
            "ambiguous reuse of a prior/partial run. Delete deliberately or choose "
            "a new --journal-path.",
            file=sys.stderr,
        )
        return 1

    store = TickParquetStore(_LOCKED_TICKS_DIR, holdout_range=XAUUSD_HOLDOUT_RANGE)
    months = months_between(
        datetime(start_year, start_month, 1, tzinfo=UTC),
        datetime(end_year, end_month, 1, tzinfo=UTC),
    )

    # Guard 2 (post-resolution): re-check every resolved (year, month) tuple.
    for year, month in months:
        refusal = _refuse_if_holdout(year, month)
        if refusal:
            print(f"REFUSING TO RUN: resolved month {refusal} No data was read.", file=sys.stderr)
            return 1

    log(f"Months to load: {[f'{y:04d}-{m:02d}' for y, m in months]}")

    log("Loading real ticks (TickParquetStore.read_month, unmodified) ...")
    month_frames = [store.read_month(SYMBOL, y, m) for y, m in months]
    ticks_df = pl.concat(month_frames).sort("ts")
    log(f"  loaded {ticks_df.height:,} ticks across {len(months)} month(s)")

    builder = BarBuilder()
    bars_1m = builder.build(ticks_df, TF.M1)
    bars_5m = builder.build(ticks_df, TF.M5)
    bars_4h = builder.build(ticks_df, TF.H4)
    log(f"  bars: 1M={len(bars_1m):,} 5M={len(bars_5m):,} 4H={len(bars_4h):,}")

    ticks = [
        Tick(ts=row["ts"], bid=row["bid"], ask=row["ask"])
        for row in ticks_df.iter_rows(named=True)
    ]

    # News Calendar (approved Option A): real BLS calendar, unmodified loader,
    # no filtering/conversion here -- CalendarEngine.from_config (called inside
    # build_orchestrator) does its own currency/impact filtering, and events
    # outside this run's window simply never match in_blackout(ts). Coverage
    # is Phase 1 only (CPI + Employment Situation) -- KI-010's documented
    # limitation, not extended by this run.
    log(f"Loading real news calendar from {_LOCKED_NEWS_PATH} (load_bls_csv, unmodified) ...")
    news = load_bls_csv(_LOCKED_NEWS_PATH)
    log(f"  loaded {len(news)} real news event(s) (CPI + Employment Situation, D-077/RA-23)")

    rules = load_rules_v1()
    parameters = load_parameters()
    run_config = _minimal_run_config(
        _LOCKED_ARM, _LOCKED_SL_ANCHOR, date(start_year, start_month, 1), date(end_year, end_month, 28), _LOCKED_SEED,
    )

    # Deterministic, fully derived from the locked scope -- no CLI override
    # exists, so a Run ID mismatched with the declared T3.4 scope is not
    # reachable.
    run_id = f"t3.4-in_sample-{_LOCKED_START}-{_LOCKED_END}-{_LOCKED_ARM}x{_LOCKED_SL_ANCHOR}"

    identity = RunIdentity(
        data_version=store.data_version(SYMBOL, months),
        split_type="in_sample",
        seed=_LOCKED_SEED,
    )

    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal = DuckDBJournal(journal_path, SCHEMA_PATH)

    log("")
    log(f"Building Orchestrator (build_orchestrator, unmodified) -- "
        f"arms={_LOCKED_ARM}x{_LOCKED_SL_ANCHOR}, LIVE news blackout ({len(news)} events), "
        f"journal=REAL ({journal_path}), registry=REAL ({args.registry_path}) ...")
    orch = build_orchestrator(
        rules, parameters, run_config,
        identity=identity,
        bars_1m=bars_1m, bars_5m=bars_5m, bars_4h=bars_4h,
        ticks=ticks, news=news,
        journal=journal,
        registry_path=Path(args.registry_path),
        run_id=run_id,
    )

    log("Running orchestrator.run() -- REAL declared Experiment (timed) ...")
    t0 = time.perf_counter()
    try:
        result = orch.run()
    except Exception:
        log("")
        log("=== T3.4 RUN CRASHED ===")
        traceback.print_exc()
        # Defensive cleanup only -- orch.run() closes the journal itself on the
        # success path (src/backtest/orchestrator.py:247), but NOT inside a
        # try/finally, so a mid-run exception leaves it open (finding reported
        # to Roy, approved script-level mitigation, no src/ change). Closing
        # here is additive, script-level cleanup only.
        try:
            journal.close()
        except Exception:
            pass
        return 1
    elapsed_seconds = time.perf_counter() - t0

    log("")
    log("=== T3.4 RUN COMPLETE (no crash) ===")
    log(f"  run_id={run_id} experiment_id={run_id}-exp")
    log(f"  config_hash / data_version / code_version / seed are recorded in the "
        f"journal's `runs` table and in {args.registry_path}")
    log(
        f"  engaged={result.engaged} reaction_seen={result.reaction_seen} "
        f"sweep_confirmed={result.sweep_confirmed} armed={result.armed}"
    )
    log(f"  expired={result.expired} invalidated={result.invalidated} no_ifvg={result.no_ifvg}")
    log(
        f"  orders_placed={result.orders_placed} orders_rejected={result.orders_rejected} "
        f"fills={result.fills} orders_cancelled={result.orders_cancelled}"
    )
    log(f"  elapsed: {elapsed_seconds:.2f}s")
    log(f"  Journal written to {journal_path}")

    # Build trade-page Viz for up to --viz-limit trades (AT-3.10 evidence).
    # Run + Journal + Registry are already fully written by this point --
    # a Viz-generation failure here must still close `reader` (defensive,
    # script-level only; src/viz/trade_page.py and src/journal/duckdb_writer.py
    # are not touched).
    reader = DuckDBJournal(journal_path, SCHEMA_PATH)
    trade_rows: list[tuple] = []
    viz_dir = Path(args.viz_dir)
    try:
        trade_rows = reader.query(f"SELECT trade_id FROM trades LIMIT {args.viz_limit}")
        viz_dir.mkdir(parents=True, exist_ok=True)
        for (trade_id,) in trade_rows:
            fig = build_trade_page(reader, trade_id, bars_1m)
            fig.write_html(viz_dir / f"{trade_id}.html")
    except Exception:
        log("")
        log("=== T3.4 VIZ GENERATION FAILED (Experiment run + Journal + Registry "
            "already completed successfully before this point; only Viz failed) ===")
        traceback.print_exc()
        return 1
    finally:
        try:
            reader.close()
        except Exception:
            pass
    log(f"  {len(trade_rows)} trade-page(s) written to {viz_dir} (for your AT-3.10 manual review)")
    log("")
    log("This run is a REAL declared Experiment, with LIVE news blackout "
        "(data/news/bls_calendar.csv, Phase 1 coverage: CPI + Employment Situation). "
        "It does NOT itself close AT-3.10 -- that requires your separate, manual "
        "review of the trade pages above.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
