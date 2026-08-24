# XAUUSD Research Platform

A research platform (not a trading indicator) for testing an SMC-based XAUUSD strategy:
realistic backtesting, an anti-bias research protocol, and paired comparison of
entry/stop-loss arms on an identical setup stream.

Authority order: Git/Code → Tests/Evidence → `docs/DECISIONS_LOG.md` →
`docs/KNOWN_ISSUES.md` · `docs/RESEARCH_READINESS_REVIEW.md` → ARCHIVAL documents.
Read `CLAUDE.md` first, then `docs/PHASE_PLAN.md` and `docs/ACCEPTANCE_TESTS.md`.
`HANDOFF_MASTER.md` (repo root) is ARCHIVAL. Work proceeds strictly by phases; each phase
ends in a demoable artifact and requires explicit user approval before the next
phase starts.

## Status

**Phase 0 — Data Pipeline**: complete — 39/39 months of real tick data acquired and
verified (2022-10..2025-12). KI-001 (network access) closed by D-069; KI-002
(point_value) closed by D-070. Data is physically split: 33 research months in
`data/ticks`, 6 hold-out months (2025-07..12) in `data/holdout` (B-9 / D-086).
**Phase 1 — State Store + Structure Engines**: Closed.
**Phase 2 — Execution Layer**: Green-Conditional (2026-07-09).
**Phase 3 — End-to-End (narrow)**: Green-Conditional / code-complete (2026-07-10) — T3.4 (the first real backtest run) is blocked until the Research Readiness Review below reaches GO.
**Stage A (B-1…B-7)**: Closed. **B-8**: merged; Performance and Documentation gates
not yet green. **B-9 (Track B)**: Closed — physical hold-out separation (D-085/D-086).
See `docs/DECISIONS_LOG.md`.
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
Network access was resolved in D-069 (browser-like transport); all 39 months have
been downloaded and verified. The pipeline is tested against synthetic fixtures and
has also been run against real data (D-072, D-075).

**Open limitation — KI-010 (news coverage):** the real economic calendar covers
CPI and Employment Situation only (2 of 7 high-impact USD event types). Core PCE,
GDP, FOMC, ISM PMI and Retail Sales are not yet covered. See `docs/KNOWN_ISSUES.md`.

## Repo layout

See `CLAUDE.md` §"מבנה הריפו" for the full target tree.
