# XAUUSD Research Platform

A research platform (not a trading indicator) for testing an SMC-based XAUUSD strategy:
realistic backtesting, an anti-bias research protocol, and paired comparison of
entry/stop-loss arms on an identical setup stream.

The project's source of truth is the handoff package at the repo root / `docs/`:
read `CLAUDE.md` first, then follow `docs/HANDOFF_MASTER.md` §2 for the mandatory
reading order. Work proceeds strictly by `docs/PHASE_PLAN.md` phases; each phase
ends in a demoable artifact and requires explicit user approval before the next
phase starts.

## Status

**Phase 0 — Data Pipeline**: complete — 39/39 months of real tick data verified (see `BATCH7_CLOSURE_REPORT.md`).
**Phase 1 — State Store + Structure Engines**: Closed.
**Phase 2 — Execution Layer**: Green-Conditional (2026-07-09).
**Phase 3 — End-to-End (narrow)**: Green-Conditional / code-complete (2026-07-10) — T3.4 (the first real backtest run) is blocked until the Research Readiness Review below reaches GO.
**Stage A (B-1…B-7)**: Closed — see `docs/DECISIONS_LOG.md`.
**Research Readiness Review**: NO-GO — required before T3.4; see `docs/RESEARCH_READINESS_REVIEW.md`.

## Setup

```bash
uv sync --extra dev
# or: pip install -e ".[dev]"
```

## Commands

```bash
pytest -q                     # acceptance tests
ruff check src tests scripts  # lint
scripts/ci.sh                 # full local CI (lint + tests + frozen-config integrity)
python scripts/demo_phase0.py --month 2024-03                     # Phase 0 demo
python scripts/bench_phase0.py                                    # Phase 0 performance benchmark
python scripts/demo_phase1.py --period 2024-01-01:2024-02-01      # Phase 1 demo (chart)
python scripts/bench_phase1.py                                    # Phase 1 performance benchmark
python scripts/demo_phase2.py                                     # Phase 2 demo
python scripts/bench_phase2.py                                    # Phase 2 performance benchmark
python scripts/demo_phase3.py                                     # Phase 3 demo
python scripts/bench_phase3.py                                    # Phase 3 performance benchmark
```

## Known environment constraint

Real historical tick data comes from Dukascopy (`docs/SPEC_V1_FROZEN.md` §1).
Acquiring it requires outbound network access to `datafeed.dukascopy.com`.
See `docs/KNOWN_ISSUES.md` for the current status of live data acquisition in
this environment; the data pipeline itself (downloader, validator, bar builder,
spread report, holdout isolation) is implemented and tested against synthetic
fixtures that reproduce Dukascopy's tick wire format.

## Repo layout

See `CLAUDE.md` §"מבנה הריפו" for the full target tree.
