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

**Phase 0 — Data Pipeline** (see `docs/PHASE_PLAN.md`).

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
python scripts/demo_phase0.py --month 2024-03   # Phase 0 demo
python scripts/bench_phase0.py                  # Phase 0 performance benchmark
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
