"""Strategy-agnostic Validation Engine (Research System, Phase 3).

Strictly read-only/computational, per the approved Phase 3 design:
    - split_plan() computes walk-forward split BOUNDARIES only -- pure date
      arithmetic, no database access.
    - compare_runs() compares already-executed Research Runs only, given an
      explicit caller-supplied list of exact (run_id, portfolio_id,
      split_type) triples. No automatic run discovery: this module never
      queries the Journal to select runs by experiment/split_type/date/
      similarity on its own initiative.
    - holdout_usage_report() reads an existing hold-out access log at a
      caller-supplied path. No canonical/default path is invented (none
      exists in this repository -- confirmed by inspection: two scripts use
      Path(args.ticks_dir).parent / "holdout_access_log.jsonl", a test uses
      a tmp-dir path; the path is always caller-supplied, never hardcoded).

This module NEVER executes a backtest and NEVER imports/invokes
Orchestrator or build_orchestrator. It never calls Journal.record() --
only DuckDBJournal.query() (via the reused MetricsEngine) and plain
Path.read_text() for the hold-out log. It never modifies
HoldoutGuard/TickParquetStore behavior -- both are only read about in this
docstring, never imported.

No verdict layer: this module produces no validation_passed/candidate/
best/better/promising/rejected field, no p-value, no bootstrap test, no
significance claim, no Random Baseline, no Sensitivity, no optimization,
no ML. Those are later, separate, explicitly-not-yet-approved items
(RA-02/RA-07/RA-08/RA-09 have no implemented statistical runner yet --
confirmed by inspection before this module was written).

Reuses existing infrastructure rather than reinventing it:
    - compare_runs() reuses src.research.metrics.MetricsEngine (unmodified)
      for each run's performance measurement -- the same, single definition
      of every metric, not a third duplicate (unlike analysis.py, which had
      to duplicate metrics.py's per-trade formulas because it operates on
      bucketed subsets MetricsEngine can't directly produce; compare_runs()
      operates on whole portfolios, exactly what MetricsEngine.compute()
      already returns).
    - split_plan()'s rolling-window arithmetic mirrors the existing
      (year, month) whole-month convention in src/data/tick_store.py's
      months_between() (line 246) and src/data/holdout.py's
      compute_holdout_range(), without importing either -- keeping this
      module dependency-free of the data layer, matching metrics.py/
      analysis.py's own minimal-import convention. The day component of any
      supplied period_start/period_end is ignored; every Split boundary is
      month-aligned to day 1, exactly like months_between()'s domain.
    - split_plan()'s train_months/test_months parameters mirror
      config/models.py's WalkForward(train_months, test_months) (RA-05)
      without importing that Pydantic class, for the same dependency-
      minimalism reason.

Provenance: compare_runs() surfaces each run's existing config_hash/
code_version/data_version (read verbatim from the `runs` table) without
recomputing or altering any of them -- identical in spirit to how
metrics.py/analysis.py carry run_id through without recomputing identity.

Run identity is never collapsed: ComparisonResult.entries is a flat list,
one RunComparisonEntry per supplied run, each carrying its own run_id/
portfolio_id/split_type -- multiple runs sharing one split_type remain
individually distinguishable by run_id, never merged into a single
split_type-keyed result.

Hold-out log format note: the two existing writers of a hold-out usage
log use DIFFERENT JSON shapes -- src/data/holdout.py's
HoldoutGuard._log_usage writes {accessed_at, symbol, start, end, reason},
while src/data/tick_store.py's _log_holdout_usage (line 192-202) writes
{accessed_at, symbol, year, month, reason} instead (no start/end).
holdout_usage_report() does not assume either shape: accessed_at/symbol/
reason are read as common fields, and every other key is preserved
verbatim in HoldoutAccessEntry.detail rather than guessed at.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.research.metrics import MetricsEngine, MetricsResult

_NO_VERDICT_NOTE = (
    "This comparison contains measurements only -- no validation_passed, "
    "candidate, best, better, promising, or rejected judgment is computed "
    "here, and no significance test is applied. That judgment belongs to a "
    "human, or to a future, separately-approved statistical layer."
)


@dataclass(frozen=True)
class Split:
    """One rolling walk-forward window's boundaries. Pure data -- computed
    by split_plan(), never itself run against a backtest by this module.
    """

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime


def split_plan(
    period_start: datetime, period_end: datetime, *, train_months: int, test_months: int
) -> list[Split]:
    """Compute rolling walk-forward split boundaries -- pure date
    arithmetic, no database access, no backtest execution.

    Each window is [train_start, train_end) train + [test_start, test_end)
    test, month-aligned (day component of period_start/period_end is
    ignored). Successive windows slide forward by test_months. Stops once
    a window's test period would end after period_end; returns [] if not
    even one full window fits.

    Mirrors config/models.py's WalkForward(train_months, test_months)
    (RA-05) field names without importing that class -- see module
    docstring.
    """
    if train_months <= 0 or test_months <= 0:
        raise ValueError("train_months and test_months must both be positive")

    splits: list[Split] = []
    year, month = period_start.year, period_start.month
    while True:
        train_start = _month_start(year, month)
        ty, tm = _add_months(year, month, train_months)
        train_end = _month_start(ty, tm)
        test_start = train_end
        ey, em = _add_months(ty, tm, test_months)
        test_end = _month_start(ey, em)

        if test_end > period_end:
            break

        splits.append(Split(train_start=train_start, train_end=train_end, test_start=test_start, test_end=test_end))
        year, month = _add_months(year, month, test_months)

    return splits


@dataclass(frozen=True)
class LabeledRun:
    """One exact, caller-identified run to compare. No field here is ever
    inferred or auto-discovered by this module.
    """

    run_id: str
    portfolio_id: str
    split_type: str


@dataclass(frozen=True)
class RunComparisonEntry:
    """One labeled run's identity, provenance, and measured performance.
    Never collapsed with another entry -- see module docstring.
    """

    run_id: str
    portfolio_id: str
    split_type: str
    config_hash: str | None
    code_version: str | None
    data_version: str | None
    metrics: MetricsResult


@dataclass(frozen=True)
class ComparisonResult:
    """A flat, caller-scoped comparison. No verdict field -- see
    _NO_VERDICT_NOTE.
    """

    entries: list[RunComparisonEntry]
    note: str


def compare_runs(journal, runs: list[LabeledRun]) -> ComparisonResult:
    """Compare an explicit, caller-supplied list of already-executed runs.

    Never queries the Journal to select runs on its own initiative -- every
    (run_id, portfolio_id, split_type) must be supplied by the caller.
    Raises ValueError if a supplied run_id/portfolio_id does not exist, or
    if a supplied portfolio_id does not actually belong to the supplied
    run_id (an identity-integrity guard, not a judgment).
    """
    entries: list[RunComparisonEntry] = []
    for labeled in runs:
        run_rows = journal.query(
            "SELECT config_hash, code_version, data_version FROM runs WHERE run_id = ?",
            [labeled.run_id],
        )
        if not run_rows:
            raise ValueError(f"unknown run_id {labeled.run_id!r} -- no row in runs")
        config_hash, code_version, data_version = run_rows[0]

        portfolio_rows = journal.query(
            "SELECT run_id FROM portfolios WHERE portfolio_id = ?", [labeled.portfolio_id]
        )
        if not portfolio_rows:
            raise ValueError(f"unknown portfolio_id {labeled.portfolio_id!r} -- no row in portfolios")
        actual_run_id = portfolio_rows[0][0]
        if actual_run_id != labeled.run_id:
            raise ValueError(
                f"portfolio_id {labeled.portfolio_id!r} belongs to run_id {actual_run_id!r}, "
                f"not the supplied run_id {labeled.run_id!r} -- refusing to compare "
                "mismatched identity"
            )

        metrics = MetricsEngine(journal).compute(labeled.portfolio_id)
        entries.append(
            RunComparisonEntry(
                run_id=labeled.run_id,
                portfolio_id=labeled.portfolio_id,
                split_type=labeled.split_type,
                config_hash=config_hash,
                code_version=code_version,
                data_version=data_version,
                metrics=metrics,
            )
        )

    return ComparisonResult(entries=entries, note=_NO_VERDICT_NOTE)


@dataclass(frozen=True)
class HoldoutAccessEntry:
    """One logged hold-out access. ``detail`` preserves whatever
    additional fields the actual writer logged (see module docstring for
    the two known, differing schemas) rather than assuming one shape.
    """

    accessed_at: str
    symbol: str
    reason: str
    detail: dict


@dataclass(frozen=True)
class HoldoutUsageReport:
    """A read-only summary of an existing hold-out access log. An
    ``access_count`` of 0 with ``log_exists=False`` means the hold-out has
    never been touched (a legitimate, expected state) -- distinct from
    ``log_exists=True`` with 0 entries (an empty but existing log).
    """

    usage_log_path: str
    log_exists: bool
    access_count: int
    accesses: list[HoldoutAccessEntry]


def holdout_usage_report(usage_log_path: Path) -> HoldoutUsageReport:
    """Parse an existing hold-out access log. Requires an explicit path --
    no canonical/default path is invented (see module docstring). Never
    writes; never modifies HoldoutGuard/TickParquetStore behavior.
    """
    if not usage_log_path.exists():
        return HoldoutUsageReport(
            usage_log_path=str(usage_log_path), log_exists=False, access_count=0, accesses=[]
        )

    accesses: list[HoldoutAccessEntry] = []
    for line in usage_log_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        entry = json.loads(stripped)
        accessed_at = entry.pop("accessed_at", "")
        symbol = entry.pop("symbol", "")
        reason = entry.pop("reason", "")
        accesses.append(
            HoldoutAccessEntry(accessed_at=accessed_at, symbol=symbol, reason=reason, detail=entry)
        )

    return HoldoutUsageReport(
        usage_log_path=str(usage_log_path),
        log_exists=True,
        access_count=len(accesses),
        accesses=accesses,
    )


# -- date arithmetic (pure; mirrors tick_store.py's months_between/
# holdout.py's compute_holdout_range whole-month convention without
# importing either -- see module docstring) -----------------------------


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    y, m = divmod(total, 12)
    return y, m + 1


def _month_start(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=UTC)
