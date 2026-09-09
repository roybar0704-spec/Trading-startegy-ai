#!/usr/bin/env python3
"""AT-3.10 Population-Observation Run -- M2 x S_body over the full available
Research pool (2022-10..2025-06), NOT a modification of T3.4.

Purpose (Owner-approved direction, Gate 1/2/2.1; write-only approval -- NOT
yet approved to execute): T3.4 (docs/PHASE_PLAN.md) is locked to
2024-01..2024-03, M2xS_body, and was proven (prior investigation, this
project) to contain only 5 ARMED setups and 2 closed trades in that window --
structurally incapable of reaching AT-3.10's 20-sample-trade requirement.
This runner does NOT change T3.4, does NOT change the arm, session window,
entry/exit logic, risk rules, cost model, or config -- it ONLY widens the
observation window to the entirety of the already-existing, already-verified
Research data pool (2022-10..2025-06), stopping strictly before the Hold-Out
boundary (2025-07). The resulting trade count is an OBSERVED RESULT to be
reported honestly -- this script contains no loop, retry, or stopping
condition tied to reaching any particular trade count.

LOCKED SCOPE (Owner-approved; write-only approval, NOT yet approved to run):
    start=2022-10 end=2025-06 arm=M2 sl_anchor=S_body split_type=in_sample
    ticks_dir=data/ticks news_path=data/news/bls_calendar.csv
This range's boundary predates this investigation: 2022-10 is the first
month ever backfilled into this project; 2025-06 is fixed by the existing,
independent Hold-Out carve-out (D-073/D-085/D-086), not by any trade-count
consideration.

Deliberately separate identity from T3.4: run_id prefix, and the Journal
file, are both distinct from scripts/run_t3_4_in_sample.py's own identity --
see module-level constants below. The Registry (data/registry/runs.jsonl) is
intentionally the SAME append-only file T3.4 already uses (Owner-approved,
Gate 2.1) -- distinct run_id values prevent any collision or ambiguity.
src/entry/setup_stream.py, src/backtest/orchestrator.py, src/risk/engine.py,
config/rules_v1.yaml, config/parameters.yaml, and
scripts/run_t3_4_in_sample.py itself are NOT touched by this file's
existence.

Hold-Out guard (identical pattern to run_t3_4_in_sample.py, reused verbatim):
two independent script-level checks plus the engine's own TickParquetStore
guard refuse any month at or after 2025-07.

Frozen-config guard: verify_frozen_rules() runs first, exactly as in T3.4's
own runner. As confirmed in the Gate 2.1 design audit: this guard verifies
ONLY config/rules_v1.yaml's byte integrity against its recorded hash -- it
does NOT verify config/parameters.yaml (which has no frozen-hash mechanism
anywhere in this codebase today), src/ code integrity, or news-calendar
content. This is a pre-existing, known characteristic of the project, not
something this script changes or compensates for (Owner decision, Gate 2.1
review: document as known, do not fix as part of this run).

Runtime (ESTIMATE ONLY, NOT a benchmark -- no measurement has been taken for
any range beyond T3.4's own 3 months): the 33-month Research pool is
approximately 17.5x the total tick-data volume of T3.4's 3-month run (by
file size: ~797MB vs ~45.7MB), scaled against T3.4's own measured real-run
time (526.24s, with a real Journal) gives a rough linear-scaling estimate of
approximately 2.5 HOURS. This assumes roughly linear scaling of runtime with
data volume, which is NOT verified and may be wrong in either direction. A
dedicated Preflight (not this file) must assess actual resource budget
before any execution is approved.

Viz policy (Owner decision, Gate 2.1 review): render a trade page for EVERY
trade in the Journal by default (no arbitrary cap), ordered deterministically
by entry_ts (chronological) -- NOT an arbitrary/unordered subset. An explicit
--viz-limit override remains available (e.g. if resource limits demand
capping later), but the DEFAULT is "all trades," decided in advance, not
chosen after seeing the result count.

STATUS AT TIME OF WRITING: file created per explicit Owner approval to WRITE
ONLY. NOT approved to run. Order that remains binding: Draft -> write to
disk -> Review of the written file against the approved Draft -> Preflight
-> separate run approval -> Run -> Post-Run Review.

Usage (if and when a separate run-approval is given):
    uv run python scripts/run_at3_10_population_observation.py \\
        --journal-path data/journal/at3_10_population_2022_10_2025_06.duckdb \\
        --registry-path data/registry/runs.jsonl \\
        --viz-dir data/journal/at3_10_population_viz
"""

from __future__ import annotations

import argparse
import calendar
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
from src.core.types import TF, RunIdentity  # noqa: E402
from src.data.bar_builder import BarBuilder  # noqa: E402
from src.data.holdout import XAUUSD_HOLDOUT_RANGE  # noqa: E402
from src.data.news_loader import load_bls_csv  # noqa: E402
from src.data.tick_store import TickParquetStore, months_between  # noqa: E402
from src.journal.duckdb_writer import DuckDBJournal  # noqa: E402
from src.viz.trade_page import build_trade_page  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "XAUUSD"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

# AT-3.10 POPULATION-OBSERVATION LOCKED SCOPE (Owner-approved direction,
# Gate 1/2/2.1; write-only approval, NOT yet approved to execute).
# Deliberately NOT exposed as CLI arguments -- same discipline as
# scripts/run_t3_4_in_sample.py. This range is fixed by pre-existing
# decisions (D-073/D-085/D-086), not chosen to hit any particular trade
# count -- see module docstring.
_LOCKED_START = "2022-10"
_LOCKED_END = "2025-06"
_LOCKED_ARM = "M2"
_LOCKED_SL_ANCHOR = "S_body"
_LOCKED_TICKS_DIR = REPO_ROOT / "data" / "ticks"
_LOCKED_NEWS_PATH = REPO_ROOT / "data" / "news" / "bls_calendar.csv"
_LOCKED_SEED = 42

# D-073 pattern, identical to run_t3_4_in_sample.py: last calendar month this
# script is ever allowed to load. Hardcoded, not config-driven.
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
    """Only OUTPUT destinations are configurable. Scope (dates, arm, SL
    anchor, tick-data source, news calendar) is locked as module constants
    above, exactly mirroring run_t3_4_in_sample.py's own discipline."""
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--journal-path",
        default=str(REPO_ROOT / "data" / "journal" / "at3_10_population_2022_10_2025_06.duckdb"),
    )
    p.add_argument("--registry-path", default=str(REPO_ROOT / "data" / "registry" / "runs.jsonl"))
    p.add_argument("--viz-dir", default=str(REPO_ROOT / "data" / "journal" / "at3_10_population_viz"))
    p.add_argument(
        "--viz-limit",
        type=int,
        default=None,
        help=(
            "Optional cap on the number of trade pages rendered, chosen "
            "chronologically (ORDER BY entry_ts). Default: no cap -- every "
            "trade in the Journal gets a Viz page (Owner-approved policy, "
            "Gate 2.1: decided in advance, not chosen after seeing the "
            "result count)."
        ),
    )
    return p


def _true_month_end(year: int, month: int) -> int:
    """Last calendar day of (year, month) -- cosmetic only, does not affect
    which data is loaded (months_between()/read_month() are day-agnostic;
    see Gate 2.1 review). Used only so RunConfig.period.end reads correctly,
    since Period is otherwise unused by build_orchestrator (confirmed)."""
    return calendar.monthrange(year, month)[1]


def _minimal_run_config(arm: str, sl_anchor: str, start: date, end: date, seed: int) -> RunConfig:
    """Identical shape/precedent to run_t3_4_in_sample.py's own helper --
    fields outside `arms` are schema-required by RunConfig but not consumed
    by build_orchestrator's own logic."""
    return RunConfig(
        experiment="AT3_10_population_observation",
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

    log(f"=== AT-3.10 POPULATION OBSERVATION -- {SYMBOL} {_LOCKED_START}..{_LOCKED_END} "
        f"({_LOCKED_ARM}x{_LOCKED_SL_ANCHOR}) [LOCKED SCOPE, NOT T3.4] ===")
    log("journal != None. registry_path is real. split_type=in_sample. "
        "This is a SEPARATE declared Experiment from T3.4.")
    log("NOTE: estimated runtime ~2.5 hours (ESTIMATE ONLY, NOT a benchmark -- "
        "see module docstring). Requires a dedicated Preflight before execution.")

    # Guard 0: frozen-config integrity, before anything else.
    digest = verify_frozen_rules()
    log(f"frozen-config OK: rules_v1.yaml hash = {digest}")

    # Guard 1 (constant-level): reject before touching the filesystem at all.
    for label, y, m in (("_LOCKED_START", start_year, start_month), ("_LOCKED_END", end_year, end_month)):
        refusal = _refuse_if_holdout(y, m)
        if refusal:
            print(f"REFUSING TO RUN: {label} {refusal} No data was read.", file=sys.stderr)
            return 1
    if (start_year, start_month) > (end_year, end_month):
        print(f"ERROR: _LOCKED_START ({_LOCKED_START}) must be <= _LOCKED_END ({_LOCKED_END}).", file=sys.stderr)
        return 1

    # Pre-Flight: refuse to reuse an existing journal path.
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

    log(f"Months to load: {len(months)} total, "
        f"{months[0][0]:04d}-{months[0][1]:02d} .. {months[-1][0]:04d}-{months[-1][1]:02d}")

    log("Building bars (1M/5M/4H) from real ticks -- bars stay fully in memory "
        "(small); only the tick population itself is streamed, never materialized "
        f"in full, across {len(months)} months (Gate 3.6/3.7 streaming design) ...")
    month_frames = [store.read_month(SYMBOL, y, m) for y, m in months]
    ticks_df = pl.concat(month_frames).sort("ts")
    log(f"  {ticks_df.height:,} ticks across {len(months)} month(s) (used only to build bars)")

    builder = BarBuilder()
    bars_1m = builder.build(ticks_df, TF.M1)
    bars_5m = builder.build(ticks_df, TF.M5)
    bars_4h = builder.build(ticks_df, TF.H4)
    log(f"  bars: 1M={len(bars_1m):,} 5M={len(bars_5m):,} 4H={len(bars_4h):,}")
    del ticks_df, month_frames  # no longer needed -- ticks stream separately, bars are built

    log(f"Loading real news calendar from {_LOCKED_NEWS_PATH} (load_bls_csv, unmodified) ...")
    news = load_bls_csv(_LOCKED_NEWS_PATH)
    log(f"  loaded {len(news)} real news event(s) (CPI + Employment Situation, D-077/RA-23)")

    rules = load_rules_v1()
    parameters = load_parameters()
    period_end_day = _true_month_end(end_year, end_month)
    run_config = _minimal_run_config(
        _LOCKED_ARM, _LOCKED_SL_ANCHOR,
        date(start_year, start_month, 1), date(end_year, end_month, period_end_day),
        _LOCKED_SEED,
    )

    # Deterministic, fully derived from the locked scope -- no CLI override
    # exists. Distinct prefix from T3.4's own run_id -- cannot collide.
    run_id = f"at3.10-population-{_LOCKED_START}-{_LOCKED_END}-{_LOCKED_ARM}x{_LOCKED_SL_ANCHOR}"

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
        ticks=[], news=news,
        journal=journal,
        registry_path=Path(args.registry_path),
        run_id=run_id,
    )

    log("Running orchestrator.run_streaming() -- 33-month population observation, "
        "streaming ticks in bounded batches (Gate 3.6/3.7), unmodified decision engine "
        "(timed; ESTIMATE ~2.5h, not a benchmark -- see module docstring) ...")
    t0 = time.perf_counter()
    try:
        result = orch.run_streaming(store.stream_ticks(SYMBOL, months, batch_size=100_000))
    except Exception:
        log("")
        log("=== RUN CRASHED ===")
        traceback.print_exc()
        try:
            journal.close()
        except Exception:
            pass
        return 1
    elapsed_seconds = time.perf_counter() - t0

    log("")
    log("=== RUN COMPLETE (no crash) ===")
    log(f"  run_id={run_id} experiment_id={run_id}-exp")
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
    log("  NOTE: the trade count above is an OBSERVED RESULT of the pre-defined "
        "2022-10..2025-06 scope -- it was not targeted or adjusted to reach any number.")

    # Viz policy (Owner decision, Gate 2.1): every trade gets a page by
    # default, chosen deterministically and chronologically (ORDER BY
    # entry_ts) -- not an arbitrary/unordered subset. --viz-limit, if
    # explicitly given, caps this the same way, still chronologically.
    reader = DuckDBJournal(journal_path, SCHEMA_PATH)
    trade_rows: list[tuple] = []
    viz_dir = Path(args.viz_dir)
    try:
        query = "SELECT trade_id FROM trades ORDER BY entry_ts"
        if args.viz_limit is not None:
            query += f" LIMIT {args.viz_limit}"
        trade_rows = reader.query(query)
        viz_dir.mkdir(parents=True, exist_ok=True)
        for (trade_id,) in trade_rows:
            fig = build_trade_page(reader, trade_id, bars_1m)
            fig.write_html(viz_dir / f"{trade_id}.html")
    except Exception:
        log("")
        log("=== VIZ GENERATION FAILED (run + Journal + Registry already completed "
            "successfully before this point; only Viz failed) ===")
        traceback.print_exc()
        return 1
    finally:
        try:
            reader.close()
        except Exception:
            pass
    log(f"  {len(trade_rows)} trade-page(s) written to {viz_dir} "
        f"({'all trades, no cap' if args.viz_limit is None else f'capped at {args.viz_limit}'})")
    log("")
    log("This run is a SEPARATE declared Experiment from T3.4, over the full "
        "2022-10..2025-06 Research pool. It does not itself constitute AT-3.10 "
        "closure -- that requires your separate, manual review.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
