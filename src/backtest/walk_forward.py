"""Walk-Forward / OOS execution driver (Research System, Phase 9).

Lives under src/backtest/, not src/research/: same reason as
execution_request.py (Phase 8) -- this module depends on Strategy-A-shaped
types (RulesV1, Parameters, RunConfig) to construct ExecutionRequest
objects, and placing it under src/research/ would leak those types into
the strategy-agnostic package every prior research-layer module keeps
clean.

Test-only execution: Strategy A is currently non-adaptive (no parameter
fitting, no optimization, no threshold calibration, no candidate
selection, no strategy mutation based on Train data -- config/rules_v1.yaml
is frozen). Executing a Split's Train window would therefore only produce
another ordinary backtest, not contribute to any fitting process. This
module executes ONLY each Split's Test window, always labelled
split_type="walk_forward_test" -- an existing, first-class RunIdentity/
ExecutionRequest split_type value (see execution_request.py), not a new
one. The Train window is preserved unmodified on WalkForwardWindowResult
for provenance/auditability/future adaptive strategies, but is never
turned into an ExecutionRequest.

Reuses split_plan()/Split (src/research/validation.py, Phase 3) for
window boundaries without modification -- this module accepts
already-generated Split objects, it never generates them. Reuses
plan_execution()/execute_plan() (src/backtest/execution_request.py,
Phase 8) for all execution -- this module never reimplements
TickParquetStore, HoldoutGuard, bar construction, Orchestrator execution,
or Journal writes; it only maps each Split's test window onto one
ExecutionRequest per window and delegates.

Period derivation: Split.test_end is exclusive and always the first of a
month (validation.py's _month_start()), while Period.end's month is
inclusive under months_between()'s own existing day-of-month-irrelevant
semantics (see execution_request.py). Subtracting one day from
test_end always lands in the correct last test month regardless of
day-of-month, so:
    Period(start=split.test_start.date(), end=(split.test_end - 1 day).date())
is the exact test-period boundary, with no new date-arithmetic rule
invented beyond what months_between()/Period already define.

RunConfig per window: one caller-supplied RunConfig template is reused
via Pydantic's own model_copy(update={"period": ...}) (frozen models
support this without mutating the original) -- only .period varies per
window; every other field (arms, guards, baseline, seed, experiment,
objective) is identical across all windows, including seed (no
per-window seed variation is introduced).

Provenance: LabeledRun (src/research/validation.py) is exactly
{run_id, portfolio_id, split_type} -- reused unmodified since Phase 3
and unchanged here, so it cannot carry Split provenance. This module
introduces the smallest wrapper that can: WalkForwardWindowResult pairs
the original, unmodified Split with the LabeledRuns produced by
executing its test window. Callers who only need the flat list (e.g. to
feed compare_runs()/declare_experiment(candidates=...) exactly as any
other list[LabeledRun] today) can flatten it trivially -- no new
aggregation type is introduced beyond this pairing.

run_id: derived deterministically from a caller-supplied prefix, the
window's index, and its test boundaries -- unique by construction, with
runs.run_id's existing database PRIMARY KEY as the sole, sufficient
backstop (matching execute_plan()'s own existing idempotency story; no
new duplicate-prevention mechanism is added here).

Failure semantics: fail-fast. If any window's plan_execution() or
execute_plan() raises, the exception propagates immediately and
run_walk_forward() stops -- no try/except suppresses or transforms it,
no partial result list is returned as if it were a complete Walk-Forward
result. Matches the project's standing rule against silently swallowed
anomalies.

Holdout governance: no per-window special-casing and no new bypass path.
holdout_unlock/usage_log_path/unlock_reason are passed through unchanged
to every window's execute_plan() call, which in turn passes them through
unchanged to TickParquetStore's own unmodified, authoritative validation
-- exactly as execute_plan() already does for a single window. A window
whose test period overlaps holdout without an unlock fails exactly like
any single-window execute_plan() call would, stopping the whole driver
under fail-fast.

Journal reuse: the same journal_path is passed unchanged to every
window's execute_plan() call -- safe by construction, since execute_plan()
already opens and closes two fresh DuckDBJournal connections within a
single call; sequential reuse across windows is the same access pattern
repeated, not a new one.

Experiment boundary: this module never imports src.research.experiment
and never calls declare_experiment() -- it returns plain data for the
caller to hand to the research layer exactly as any other execution
result today.

No verdict layer, no optimization, no grid search, no ML, no automatic
candidate generation, no ranking/winner-selection, no promotion, no
Experiment Tracker persistence, no schema change, no Strategy B/Strategy
interface, no modification to split_plan()/Split/LabeledRun/RunConfig or
to any protected file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from src.backtest.execution_request import ExecutionRequest, execute_plan, plan_execution
from src.config.models import Parameters, Period, RulesV1, RunConfig
from src.data.tick_store import HoldoutRange
from src.research.validation import LabeledRun, Split


@dataclass(frozen=True)
class WalkForwardWindowResult:
    """One executed window: the Split it came from (full train+test
    boundaries, preserved verbatim for provenance) plus the LabeledRuns
    produced by executing only its test period. In-memory only -- no
    persistence, no verdict field.
    """

    split: Split
    labeled_runs: list[LabeledRun]


def _test_period_for(split: Split) -> Period:
    return Period(
        start=split.test_start.date(),
        end=(split.test_end - timedelta(days=1)).date(),
    )


def _run_id_for(prefix: str, index: int, split: Split) -> str:
    end_month = split.test_end - timedelta(days=1)
    return f"{prefix}_w{index:03d}_{split.test_start:%Y%m}_{end_month:%Y%m}"


def run_walk_forward(
    splits: list[Split],
    *,
    run_config: RunConfig,
    ticks_dir: Path,
    holdout_range: HoldoutRange,
    rules: RulesV1,
    parameters: Parameters,
    journal_path: Path,
    run_id_prefix: str,
    symbol: str = "XAUUSD",
    news: tuple = (),
    holdout_unlock: bool = False,
    usage_log_path: Path | None = None,
    unlock_reason: str = "",
) -> list[WalkForwardWindowResult]:
    """Execute only each Split's test window, in input order, fail-fast.

    Returns [] immediately for empty `splits`, without constructing any
    ExecutionRequest or calling plan_execution()/execute_plan(). On any
    window's failure, the original exception propagates immediately --
    no later window is attempted and no partial result list is returned.
    """
    results: list[WalkForwardWindowResult] = []

    for index, split in enumerate(splits):
        window_run_config = run_config.model_copy(update={"period": _test_period_for(split)})
        request = ExecutionRequest(
            run_id=_run_id_for(run_id_prefix, index, split),
            run_config=window_run_config,
            ticks_dir=ticks_dir,
            holdout_range=holdout_range,
            rules=rules,
            parameters=parameters,
            split_type="walk_forward_test",
            symbol=symbol,
            news=news,
        )
        plan = plan_execution(request)
        labeled_runs = execute_plan(
            plan,
            journal_path,
            holdout_unlock=holdout_unlock,
            usage_log_path=usage_log_path,
            unlock_reason=unlock_reason,
        )
        results.append(WalkForwardWindowResult(split=split, labeled_runs=labeled_runs))

    return results
