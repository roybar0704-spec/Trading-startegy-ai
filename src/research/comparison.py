"""Strategy-agnostic Baseline / Comparison layer (Research System, Phase 4).

Answers exactly one question: "compared with an explicitly designated
baseline run, how did another explicitly designated run perform?" Nothing
more.

Reuses, unmodified:
    - src.research.validation.LabeledRun / compare_runs() / RunComparisonEntry
      for identity resolution, provenance lookup, and per-run metrics.
    - src.research.metrics.MetricsResult (via compare_runs()) for every
      metric value -- this module performs zero metric calculation of its
      own. It calls compare_runs() exactly once, with [baseline, *candidates],
      and every MetricDelta below is pure subtraction over the two already-
      computed MetricsResult objects compare_runs() returned.

This module makes ZERO Journal calls directly (no .query(), no .record())
-- every database read happens inside the reused, unmodified
validation.compare_runs(). This is a structural guarantee, not just a
convention: there is no code path here that could query for a run by
split_type or any other filter, because there is no query in this module
at all.

Baseline semantics -- critical, confirmed by inspection before this module
was written: the "research baseline" this module compares against is
ALWAYS the caller-supplied `baseline: LabeledRun` argument. It is never
inferred, never auto-discovered, never persisted. In particular:
    - db/schema.sql's `baseline_runs` table (baseline_id, run_id,
      portfolio_arm, n_sims, seed, expectancy_dist, strategy_p_value) is
      the Random Baseline STATISTICAL SIMULATION table (RA-07, T5.3) -- an
      unrelated, later, not-yet-implemented feature. It is never read here.
    - RunIdentity.split_type == "baseline" (docs/INTERFACES.md:63-70) means
      the same Random Baseline simulation concept (see the comment on the
      adjacent `seed` field: "לא-None = Baseline"), NOT "the reference run
      for this comparison." split_type is preserved on every entry here
      exactly as given, but is never read, filtered, or judged by this
      module -- a run with split_type="baseline" is treated identically to
      any other split_type value.
    - The Code Baseline (git tag strategy-a-baseline-v1, commit
      7c03964131cce3abfe2163fb895957f207782a9e) is an unrelated, git-level
      concept, never referenced by this module.

No verdict layer: no validation_passed/candidate/best/better/promising/
rejected field, no p-value, no bootstrap, no significance claim, no
automatic winner selection. Deltas are reported; no judgment is made.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.research.metrics import MetricsResult
from src.research.validation import LabeledRun, RunComparisonEntry, compare_runs

_NO_VERDICT_NOTE = (
    "This comparison contains baseline-relative deltas only -- no "
    "validation_passed, candidate, best, better, promising, or rejected "
    "judgment is computed here, and no significance test is applied. A "
    "positive or negative delta is not evidence of a real effect by "
    "itself. That judgment belongs to a human, or to a future, "
    "separately-approved statistical layer."
)

# Exactly the MetricsResult fields the approved design names -- no
# additional metric is invented.
_COMPARED_METRICS = (
    "closed_trade_count",
    "win_rate",
    "gross_pnl",
    "total_cost",
    "net_pnl",
    "expectancy_r",
    "average_r",
    "median_r",
    "profit_factor",
    "average_duration_min",
    "average_mae_r",
    "average_mfe_r",
    "max_consecutive_wins",
    "max_consecutive_losses",
    "exposure_avg_open_risk_r",
)


@dataclass(frozen=True)
class MetricDelta:
    """One metric's baseline value, candidate value, and their delta.
    ``delta`` is ``candidate_value - baseline_value``, or None if either
    side is None -- never a fabricated zero for an unavailable metric.
    """

    metric_name: str
    baseline_value: float | int | None
    candidate_value: float | int | None
    delta: float | int | None


@dataclass(frozen=True)
class BaselineComparisonEntry:
    """One candidate run's full identity/provenance/metrics plus its
    deltas against the designated baseline. Never collapsed with another
    candidate -- multiple candidates remain independently identifiable by
    run_id, exactly like validation.RunComparisonEntry.
    """

    run_id: str
    portfolio_id: str
    split_type: str
    config_hash: str | None
    code_version: str | None
    data_version: str | None
    metrics: MetricsResult
    deltas: list[MetricDelta]


@dataclass(frozen=True)
class BaselineComparisonResult:
    """The caller-designated baseline plus every candidate's deltas
    against it. No verdict field -- see _NO_VERDICT_NOTE.
    """

    baseline: RunComparisonEntry
    candidates: list[BaselineComparisonEntry]
    note: str


def compare_to_baseline(
    journal, baseline: LabeledRun, candidates: list[LabeledRun]
) -> BaselineComparisonResult:
    """Compare each explicitly supplied candidate against the explicitly
    supplied baseline. Never infers, discovers, or persists a baseline --
    ``baseline`` is used exactly as given.

    Calls validation.compare_runs() exactly once, with
    [baseline, *candidates], reusing all of its existing identity/
    provenance resolution and its ValueError behavior for an unknown
    run_id/portfolio_id or a mismatched portfolio_id/run_id pair (that
    behavior is not duplicated here).
    """
    all_runs = compare_runs(journal, [baseline, *candidates])
    baseline_entry = all_runs.entries[0]
    candidate_entries = all_runs.entries[1:]

    comparisons = [
        BaselineComparisonEntry(
            run_id=entry.run_id,
            portfolio_id=entry.portfolio_id,
            split_type=entry.split_type,
            config_hash=entry.config_hash,
            code_version=entry.code_version,
            data_version=entry.data_version,
            metrics=entry.metrics,
            deltas=_compute_deltas(baseline_entry.metrics, entry.metrics),
        )
        for entry in candidate_entries
    ]

    return BaselineComparisonResult(baseline=baseline_entry, candidates=comparisons, note=_NO_VERDICT_NOTE)


def _compute_deltas(baseline_metrics: MetricsResult, candidate_metrics: MetricsResult) -> list[MetricDelta]:
    deltas = []
    for name in _COMPARED_METRICS:
        baseline_value = getattr(baseline_metrics, name)
        candidate_value = getattr(candidate_metrics, name)
        delta = (
            candidate_value - baseline_value
            if baseline_value is not None and candidate_value is not None
            else None
        )
        deltas.append(
            MetricDelta(
                metric_name=name,
                baseline_value=baseline_value,
                candidate_value=candidate_value,
                delta=delta,
            )
        )
    return deltas
