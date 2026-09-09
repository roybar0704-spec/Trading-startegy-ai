"""Strategy-A-specific execution glue (Research System, Phase 8).

Deliberately lives under src/backtest/, NOT src/research/: this module
depends on Strategy-A-shaped types (RulesV1, Parameters, RunConfig) to
call the existing, unmodified build_orchestrator() -- placing it under
src/research/ would leak those types into the strategy-agnostic package
every prior research-layer module (Phases 1-7) has kept clean, enforced
by each of their own AST import-whitelist tests. No src/research/*
module imports this one -- the dependency runs one way only.

Automates exactly the proven sequence already demonstrated by
scripts/run_t3_4_in_sample.py: TickParquetStore -> months_between() ->
BarBuilder -> RunIdentity -> build_orchestrator() -> Orchestrator.run() ->
post-run Journal query for resulting portfolio_ids. No new data-loading
path, no new execution path -- every step below calls an existing,
unmodified function in the same order that script already proves works.

Two-step plan/execute split (not a dry_run flag): execute_plan() requires
an ExecutionPlan object, never a raw ExecutionRequest -- there is no code
path to execution that skips producing a reviewable Plan first, and the
exact object reviewed is the exact object executed (no re-derivation).

ExecutionRequest holds only the fields not already covered by the
existing RunConfig (which already bundles period/holdout(declared)/
arms/guards/baseline/seed/experiment/objective) -- reused whole, never
decomposed into duplicate top-level fields that could diverge from it.
config_hash/code_version remain resolved exclusively inside the existing
build_orchestrator(), unchanged; data_version is computed here from the
months actually read, never caller-supplied.

Period semantics (config.models.Period, reused verbatim via
request.run_config.period): a month-selection descriptor. The effective
execution range is the inclusive set of calendar months from
period.start.year/month through period.end.year/month -- day-of-month is
not an execution boundary, matching months_between()'s own existing,
unmodified behavior exactly (it reads only .year/.month off both
arguments -- verified by inspection, not assumed).

Holdout governance -- fails closed, never bypasses or duplicates the
existing TickParquetStore/HoldoutGuard enforcement:
    - plan_execution() computes holdout_overlap via month-set
      intersection (reusing months_between() a second time on the
      holdout range itself), not a raw datetime overlaps() call, to stay
      exactly consistent with month-granular reading. HoldoutRange
      itself performs no start/end validation (verified by inspection --
      no __post_init__ exists); a degenerate/reversed range is treated
      as containing zero holdout months, mirroring HoldoutRange.overlaps()'s
      own existing handling of start >= end, not a new rule.
    - execute_plan() raises ValueError BEFORE constructing
      TickParquetStore or reading any tick data if plan.holdout_overlap
      and not holdout_unlock -- an early, defense-in-depth refusal on
      top of, never instead of, TickParquetStore's own unmodified
      per-month fail-closed check (_check_holdout, called inside
      read_month()).
    - holdout_unlock/unlock_reason/usage_log_path are passed straight
      through to TickParquetStore.__init__() unchanged and without
      reinterpretation -- its own existing validation (non-empty
      unlock_reason, non-None usage_log_path whenever
      holdout_unlock=True) remains authoritative and is never
      duplicated or weakened here.
    - A missing month's Parquet file is not specially handled: read_month()
      lets pl.read_parquet's own exception propagate, exactly as
      scripts/run_t3_4_in_sample.py's identical [store.read_month(...) for
      ...] + pl.concat(...).sort("ts") pattern already does -- no new
      execution behavior is introduced here.

split_type/holdout: no existing invariant links them anywhere in this
codebase (verified by inspection before this module was written, not
assumed) -- this module does not invent one. split_type is caller-
declared metadata only, never inferred. A semantically surprising
combination (e.g. split_type declared "in_sample" while the period
overlaps the holdout range) is disclosed as a plain ExecutionPlan.notes
entry, never blocked by it -- notes are informational only and never
change execution behavior. in_sample/walk_forward_train/
walk_forward_test periods that overlap holdout still require the same
explicit holdout_unlock as any other overlapping period; a declared
split_type of "holdout" grants no bypass of TickParquetStore's own
enforcement.

Return value: list[LabeledRun], one per resulting portfolio, built by
querying the Journal for portfolio_id rows belonging to the just-
executed run_id -- Orchestrator.run() itself returns only aggregate
counters (no portfolio identity), and closes the Journal connection it
was given on the success path, so this module reopens journal_path
after a successful run to read the result back, mirroring exactly how
scripts/run_t3_4_in_sample.py already does this (it reopens its own
`reader = DuckDBJournal(journal_path, SCHEMA_PATH)` after orch.run()).

Idempotency: no new duplicate-prevention mechanism. runs.run_id is
already a database PRIMARY KEY; executing the same run_id twice
propagates that existing constraint violation unchanged.

Experiment boundary: this module never imports src.research.experiment
and knows nothing of Experiment/ExperimentResult/changed_variables/
fixed_variables -- LabeledRun is the sole handoff point to the research
layer, unchanged.

No verdict layer, no optimization, no ML, no automatic candidate
generation, no automatic experiment declaration, no Strategy interface/
Protocol (no second strategy exists to validate one against), no
persistent execution registry, no schema change, no Runner class (plain
functions, matching every other Research System module's own
established convention).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import polars as pl

from src.backtest.run_builder import build_orchestrator
from src.config.models import Parameters, RulesV1, RunConfig
from src.core.types import TF, RunIdentity, Tick
from src.data.bar_builder import BarBuilder
from src.data.tick_store import HoldoutRange, TickParquetStore, months_between
from src.journal.duckdb_writer import DuckDBJournal
from src.research.validation import LabeledRun

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


@dataclass(frozen=True)
class ExecutionRequest:
    """Declarative execution intent. In-memory only -- no I/O performed
    by this class itself.
    """

    run_id: str
    run_config: RunConfig
    ticks_dir: Path
    holdout_range: HoldoutRange
    rules: RulesV1
    parameters: Parameters
    split_type: Literal[
        "in_sample", "walk_forward_train", "walk_forward_test",
        "holdout", "baseline", "fixture",
    ]
    symbol: str = "XAUUSD"
    news: tuple = ()

    def __post_init__(self) -> None:
        if not self.run_id or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if self.run_config.period.start > self.run_config.period.end:
            raise ValueError("run_config.period.start must be <= run_config.period.end")


@dataclass(frozen=True)
class ExecutionPlan:
    """A resolved, human-reviewable preview. Pure computation -- no tick
    data read, no Journal opened, no backtest executed.
    """

    request: ExecutionRequest
    resolved_months: list[tuple[int, int]]
    holdout_overlap: bool
    notes: list[str]


def _to_utc_datetime(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def plan_execution(request: ExecutionRequest) -> ExecutionPlan:
    """Resolve the months this request would read and whether they
    overlap the declared holdout range. Read-only: no tick data is read,
    no Journal is opened, no Orchestrator is constructed.
    """
    period = request.run_config.period
    resolved_months = months_between(_to_utc_datetime(period.start), _to_utc_datetime(period.end))

    holdout_range = request.holdout_range
    if holdout_range.start < holdout_range.end:
        holdout_months = set(months_between(holdout_range.start, holdout_range.end))
    else:
        holdout_months = set()
    holdout_overlap = bool(set(resolved_months) & holdout_months)

    notes: list[str] = []
    if request.split_type != "holdout" and holdout_overlap:
        notes.append(
            f"split_type={request.split_type!r} declared but the requested period "
            "overlaps the configured holdout range -- disclosure only, execution "
            "remains governed solely by holdout_unlock."
        )
    if request.split_type == "holdout" and not holdout_overlap:
        notes.append(
            "split_type='holdout' declared but the requested period does not "
            "actually overlap the configured holdout range -- disclosure only."
        )

    return ExecutionPlan(
        request=request,
        resolved_months=resolved_months,
        holdout_overlap=holdout_overlap,
        notes=notes,
    )


def execute_plan(
    plan: ExecutionPlan,
    journal_path: Path,
    *,
    holdout_unlock: bool = False,
    usage_log_path: Path | None = None,
    unlock_reason: str = "",
) -> list[LabeledRun]:
    """Load ticks (TickParquetStore, unmodified, fail-closed), build bars
    (BarBuilder, unmodified), call build_orchestrator()/Orchestrator.run()
    (unmodified), then query the Journal for the resulting portfolios.

    Raises ValueError if plan.holdout_overlap and not holdout_unlock --
    before any tick data is read. holdout_unlock/usage_log_path/
    unlock_reason are passed straight through to TickParquetStore's own
    unmodified constructor, without reinterpretation -- its own
    validation (non-empty unlock_reason, non-None usage_log_path
    whenever holdout_unlock=True) remains authoritative and is never
    duplicated or weakened here. Propagates whatever
    build_orchestrator()/Orchestrator.run() already raise, unchanged.
    """
    if plan.holdout_overlap and not holdout_unlock:
        raise ValueError(
            "plan.holdout_overlap is True but holdout_unlock=False -- refusing "
            "before loading any tick data"
        )

    request = plan.request
    store = TickParquetStore(
        request.ticks_dir,
        holdout_range=request.holdout_range,
        holdout_unlock=holdout_unlock,
        unlock_reason=unlock_reason,
        usage_log_path=usage_log_path,
    )

    month_frames = [store.read_month(request.symbol, y, m) for y, m in plan.resolved_months]
    ticks_df = pl.concat(month_frames).sort("ts")

    builder = BarBuilder()
    bars_1m = builder.build(ticks_df, TF.M1)
    bars_5m = builder.build(ticks_df, TF.M5)
    bars_4h = builder.build(ticks_df, TF.H4)
    ticks = [
        Tick(ts=row["ts"], bid=row["bid"], ask=row["ask"]) for row in ticks_df.iter_rows(named=True)
    ]

    identity = RunIdentity(
        data_version=store.data_version(request.symbol, plan.resolved_months),
        split_type=request.split_type,
        seed=request.run_config.seed,
    )

    journal = DuckDBJournal(journal_path, _SCHEMA_PATH)
    orch = build_orchestrator(
        request.rules,
        request.parameters,
        request.run_config,
        identity=identity,
        bars_1m=bars_1m,
        bars_5m=bars_5m,
        bars_4h=bars_4h,
        ticks=ticks,
        news=list(request.news),
        journal=journal,
        run_id=request.run_id,
    )
    orch.run()

    reader = DuckDBJournal(journal_path, _SCHEMA_PATH)
    try:
        rows = reader.query("SELECT portfolio_id FROM portfolios WHERE run_id = ?", [request.run_id])
    finally:
        reader.close()

    return [
        LabeledRun(run_id=request.run_id, portfolio_id=row[0], split_type=request.split_type)
        for row in rows
    ]
