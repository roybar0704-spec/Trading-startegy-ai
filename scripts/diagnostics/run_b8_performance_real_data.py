#!/usr/bin/env python3
"""B-8 Performance Gate -- real-data diagnostic (docs/QUALITY_GATES.md S2).

Diagnostic-only. NOT T3.4 (docs/PHASE_PLAN.md) -- does not close any Research
Readiness Review checklist item, does not create a declared Experiment, does
not write to ``data/registry/runs.jsonl``. Its only purpose is to measure the
Phase-3 performance budget ("backtest 3 months, one arm <= 5 min",
QUALITY_GATES.md S2) against real tick data instead of the synthetic Fixture
``bench_phase3.py`` uses (that budget has never been measured against real
data -- see B-8 Pre-Flight SS1/PREFLIGHT_B8.md).

Mirrors the existing, unmodified real-data pattern already proven in
``scripts/diagnostics/run_b3_real_data_diagnostic.py`` (B-3): the same
``TickParquetStore`` -> ``BarBuilder`` -> ``build_orchestrator`` pipeline, one
arm (M2 x S_body), no news calendar (KI-010 is not exercised here -- Non-Goal,
same as B-3). The only structural difference is 3 consecutive real months
instead of 1, and ``journal=None`` explicitly enforced (no ``--journal``
CLI flag exists at all, by design -- there is no way to make this script
write a Journal or a registry record).

Holdout guard (D-073 pattern, mirrors ``run_full_spread_report.py``): two
independent checks refuse any month at or after 2025-07 -- this script must
never read the Hold-Out window (2025-07..2025-12).

Writes ``benchmarks/phase3_bench_real.json`` -- a new file, never overwrites
the existing synthetic ``benchmarks/phase3_bench.json``.

Usage (must run where the requested months' Parquet files actually exist --
this Sandbox only has 2022-11; see PREFLIGHT_B8.md SS a.10):
    python scripts/diagnostics/run_b8_performance_real_data.py \
        --start 2024-01 --end 2024-03 \
        --arm M2 --sl-anchor S_body \
        --output benchmarks/phase3_bench_real.json
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
import traceback
from datetime import UTC, date, datetime
from pathlib import Path

if sys.platform != "win32":
    import resource

import polars as pl

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
from src.data.tick_store import TickParquetStore, months_between  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "XAUUSD"

# D-073 pattern (mirrors run_full_spread_report.py, B-4): last calendar month
# this script is ever allowed to load. Hardcoded, not read from config --
# deliberately cannot be loosened by editing config/run_default.yaml.
_LAST_ALLOWED_MONTH = (2025, 6)

# Phase-3 Performance Gate budget (docs/QUALITY_GATES.md S2): "backtest 3
# months, one arm <= 5 min".
_BUDGET_SECONDS = 5 * 60

_PERF_BUDGET_TARGET_YEARS = (2022, 2025)  # informational only, not enforced


def log(msg: str) -> None:
    print(msg, flush=True)


class _ProcessMemoryCounters(ctypes.Structure):
    """Mirrors Windows' PROCESS_MEMORY_COUNTERS (psapi.h) -- only the fields
    up to and including PeakWorkingSetSize are used, but the struct's `cb`
    size must match the real layout for GetProcessMemoryInfo to fill it in."""

    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _peak_rss_mb_windows() -> float:
    """Windows' analog of POSIX maxrss: PeakWorkingSetSize via GetProcessMemoryInfo
    (psapi.dll) -- the peak physical-memory working set of this process, not an
    arbitrary substitute. Bytes -> MB."""
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    if not ok:
        raise OSError("GetProcessMemoryInfo failed (Windows peak RSS measurement)")
    return counters.PeakWorkingSetSize / (1024 * 1024)


def peak_rss_mb() -> float:
    """Peak resident set size so far, in MB.

    POSIX: resource.getrusage().ru_maxrss (Linux: KB -- matches bench_phase0.py's
    existing convention, unchanged). Windows: PeakWorkingSetSize (bytes), the
    platform's own equivalent of maxrss -- not a placeholder or arbitrary stand-in.
    """
    if sys.platform == "win32":
        return _peak_rss_mb_windows()
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _parse_year_month(s: str) -> tuple[int, int]:
    dt = datetime.strptime(s, "%Y-%m")
    return dt.year, dt.month


def _refuse_if_holdout(year: int, month: int) -> str | None:
    """Guard 1/2 shared check: None if (year, month) is allowed, else a refusal message."""
    if (year, month) > _LAST_ALLOWED_MONTH:
        return (
            f"{year:04d}-{month:02d} is at/after the Hold-Out boundary "
            f"({_LAST_ALLOWED_MONTH[0]:04d}-{_LAST_ALLOWED_MONTH[1]:02d} is the last "
            "allowed month, D-073). This script must never read 2025-07 onward."
        )
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--start", default="2024-01", help="YYYY-MM, inclusive")
    p.add_argument("--end", default="2024-03", help="YYYY-MM, inclusive")
    p.add_argument("--arm", default="M2", choices=["M1", "M2", "M4"])
    p.add_argument("--sl-anchor", default="S_body", choices=["R_body", "S_body", "S_wick"])
    p.add_argument("--ticks-dir", default=str(REPO_ROOT / "data" / "ticks"))
    p.add_argument("--output", default=str(REPO_ROOT / "benchmarks" / "phase3_bench_real.json"))
    return p


def _minimal_run_config(arm: str, sl_anchor: str, start: date, end: date) -> RunConfig:
    """Single arm, mirrors run_b3_real_data_diagnostic.py's `_minimal_run_config`
    (WORK_ORDER_B3.md S4 Commit 1 precedent). Fields outside `arms` are
    schema-required by RunConfig but not consumed by build_orchestrator's own
    logic -- placeholders, not a declared Experiment (this run is not one)."""
    return RunConfig(
        experiment="B8_performance_diagnostic",
        objective="oos_wf_expectancy_r",
        guards=Guards(p_vs_baseline_max=0.05, pf_min=1.3, min_trades=150, worst_quarter_r_min=-15),
        period=Period(start=start, end=end),
        holdout=Holdout(last_months=6, unlocked=False),
        walk_forward=WalkForward(train_months=9, test_months=3),
        arms=Arms(entry_models=(arm,), sl_anchors=(sl_anchor,)),
        baseline=Baseline(n_sims=1000, seed=42),
        seed=42,
    )


def main() -> int:
    args = build_arg_parser().parse_args()
    start_year, start_month = _parse_year_month(args.start)
    end_year, end_month = _parse_year_month(args.end)

    log(f"=== B-8 Performance Diagnostic -- {SYMBOL} {args.start}..{args.end} "
        f"({args.arm}x{args.sl_anchor}) ===")
    log("Diagnostic-only. NOT T3.4. No Journal. No Registry write. Does not close RRR.")

    # Guard 1 (CLI-level): reject before touching the filesystem at all.
    for label, y, m in (("--start", start_year, start_month), ("--end", end_year, end_month)):
        refusal = _refuse_if_holdout(y, m)
        if refusal:
            print(f"REFUSING TO RUN: {label} {refusal} No data was read.", file=sys.stderr)
            return 1
    if (start_year, start_month) > (end_year, end_month):
        print(f"ERROR: --start ({args.start}) must be <= --end ({args.end}).", file=sys.stderr)
        return 1

    store = TickParquetStore(Path(args.ticks_dir))
    months = months_between(
        datetime(start_year, start_month, 1, tzinfo=UTC),
        datetime(end_year, end_month, 1, tzinfo=UTC),
    )

    # Guard 2 (post-resolution): re-check every resolved (year, month) tuple
    # independently of Guard 1 -- catches any future bug in date arithmetic.
    for year, month in months:
        refusal = _refuse_if_holdout(year, month)
        if refusal:
            print(f"REFUSING TO RUN: resolved month {refusal} No data was read.", file=sys.stderr)
            return 1

    log(f"Months to load: {[f'{y:04d}-{m:02d}' for y, m in months]}")
    log("")

    log("Loading real ticks (TickParquetStore.read_month, unmodified) ...")
    try:
        month_frames = [store.read_month(SYMBOL, y, m) for y, m in months]
    except FileNotFoundError as exc:
        print(
            f"REFUSING TO RUN: real Parquet data missing for one or more requested "
            f"months ({exc}). This script must be run where the data actually exists "
            "-- see PREFLIGHT_B8.md SS a.10 (this Sandbox only has 2022-11).",
            file=sys.stderr,
        )
        return 1
    ticks_df = pl.concat(month_frames).sort("ts")
    log(f"  loaded {ticks_df.height:,} ticks across {len(months)} month(s)")

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

    news: list[NewsEvent] = []  # Non-Goal, same as B-3: KI-010 not exercised here.

    log("Loading frozen rules_v1.yaml + parameters.yaml (unmodified loaders) ...")
    rules = load_rules_v1()
    parameters = load_parameters()
    run_config = _minimal_run_config(
        args.arm, args.sl_anchor, date(start_year, start_month, 1), date(end_year, end_month, 28)
    )

    identity = RunIdentity(
        data_version=store.data_version(SYMBOL, months),
        # "fixture": not a declared research split -- mirrors B-3's own choice
        # (RunIdentity's Literal has no "diagnostic" option).
        split_type="fixture",
        seed=None,
    )

    log("")
    log(f"Building Orchestrator (build_orchestrator, unmodified) -- "
        f"arms={args.arm}x{args.sl_anchor}, empty news calendar, "
        "journal=None (no Journal, no Registry write) ...")
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
        journal=None,  # hardcoded -- no CLI flag can change this (Scope Lock)
        registry_path=None,
        run_id=f"b8-perf-diagnostic-{args.start}-{args.end}",
    )

    log("Running orchestrator.run() over the real 3-month window (timed) ...")
    t0 = time.perf_counter()
    try:
        result = orch.run()
    except Exception:
        log("")
        log("=== DIAGNOSTIC RUN CRASHED ===")
        traceback.print_exc()
        return 1
    elapsed_seconds = time.perf_counter() - t0
    rss_mb = peak_rss_mb()

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
    log(f"  elapsed: {elapsed_seconds:.4f}s (budget: {_BUDGET_SECONDS}s)")
    log(f"  peak RSS: {rss_mb:.1f} MB")
    log(
        "Non-Goals reminder: no research/statistical conclusions drawn from the "
        "counters above; KI-010 not exercised (empty news calendar); this run is "
        "not a declared Experiment and wrote nothing to data/registry/runs.jsonl "
        "(journal=None); this is NOT T3.4."
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "measured_at": datetime.now(UTC).isoformat(),
        "data_source": "real (TickParquetStore, D-073-guarded, excludes Hold-Out)",
        "months": [f"{y:04d}-{m:02d}" for y, m in months],
        "arm": f"{args.arm}x{args.sl_anchor}",
        "tick_count": ticks_df.height,
        "bar_counts": {"1M": len(bars_1m), "5M": len(bars_5m), "4H": len(bars_4h)},
        "seconds": round(elapsed_seconds, 4),
        "budget_seconds": _BUDGET_SECONDS,
        "within_budget": elapsed_seconds <= _BUDGET_SECONDS,
        "peak_rss_mb": round(rss_mb, 1),
        "counters": {
            "engaged": result.engaged, "reaction_seen": result.reaction_seen,
            "sweep_confirmed": result.sweep_confirmed, "armed": result.armed,
            "expired": result.expired, "invalidated": result.invalidated,
            "no_ifvg": result.no_ifvg, "orders_placed": result.orders_placed,
            "orders_rejected": result.orders_rejected, "fills": result.fills,
            "orders_cancelled": result.orders_cancelled,
        },
        "note": (
            "Diagnostic-only (B-8 Pre-Flight). NOT T3.4, not a declared Experiment, "
            "journal=None (no data/registry/runs.jsonl write). Does not close any "
            "Research Readiness Review checklist item on its own."
        ),
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n")
    log("")
    log(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
