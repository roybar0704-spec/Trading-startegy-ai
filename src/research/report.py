"""Strategy-agnostic Research Report layer (Research System, Phase 5).

Assembles the already-approved, unmodified research engines into one
coherent, typed result:

    Research Run(s) -> Metrics -> Analysis -> [Baseline Comparison] ->
    [Holdout Usage] -> ResearchReport

This module performs zero metric/analysis/comparison calculation of its
own. Every number in a ResearchReport comes from calling:
    - validation.compare_runs() (itself reusing metrics.MetricsEngine)
      for identity, provenance, and per-run metrics
    - analysis.AnalysisEngine.analyze() for the dimensional breakdown
    - comparison.compare_to_baseline() (itself reusing compare_runs())
      for baseline-relative deltas, when a baseline is supplied
    - validation.holdout_usage_report() for hold-out access disclosure,
      when a log path is supplied

Provenance -- ResearchReportSection carries a RunComparisonEntry (not a
bare LabeledRun/MetricsResult pair): RunComparisonEntry already bundles
run_id/portfolio_id/split_type/config_hash/code_version/data_version/
metrics, all resolved by the reused, unmodified compare_runs(). This is
why build_report() calls compare_runs() once for ALL supplied runs (not
only when a baseline is given) -- provenance must be preserved
unconditionally, not only in the baseline-comparison path.

Split separation -- sections is a flat list, one entry per supplied
(run_id, portfolio_id, split_type). Nothing in build_report() sums,
averages, or otherwise combines two sections' metrics; the only
aggregation-shaped operation is list construction. An in_sample and a
holdout run passed together therefore remain two independent sections,
never one blended number. This guarantee is structural in this module;
any future renderer must iterate sections individually to preserve it.

Baseline semantics -- identical to comparison.py's: the baseline is
always the caller-supplied `baseline: LabeledRun` argument, never
inferred/discovered/persisted. If `baseline` also appears in `runs`, it
still gets its own section (like any other run) but is excluded from the
comparison's candidate list (by exact (run_id, portfolio_id) match) --
comparing a run against itself would only ever produce all-zero deltas.

Notes -- ResearchReport.notes is report-level only. It never duplicates
information already visible on a nested object (a section's own
sufficient_sample/trades_available/dimensions_scanned, or a comparison's
own no-verdict note all remain exactly where they already live). It
carries at most three fixed strings: a split-separation reminder (always
present), a no-baseline-supplied note, and a no-holdout-log-supplied
note.

No verdict layer: no validation_passed/candidate/best/better/promising/
rejected/verdict field anywhere. Measurements and their provenance only.

Read-only: no Journal write, no file write, no backtest execution, no
persistence of the returned ResearchReport. This module only reads via
the already-approved research APIs listed above.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.research.analysis import AnalysisEngine, AnalysisResult
from src.research.comparison import BaselineComparisonResult, compare_to_baseline
from src.research.validation import (
    HoldoutUsageReport,
    LabeledRun,
    RunComparisonEntry,
    compare_runs,
    holdout_usage_report,
)

_SPLIT_SEPARATION_NOTE = (
    "Each section below is one independent (run_id, portfolio_id, split_type) "
    "result. Sections are never merged or averaged -- an in_sample, "
    "walk_forward_train, walk_forward_test, holdout, or baseline (Random "
    "Baseline simulation, per split_type's own meaning) run always remains "
    "its own separate result."
)
_NO_BASELINE_NOTE = "no baseline supplied -- no comparison performed."
_NO_HOLDOUT_LOG_NOTE = "no holdout usage log supplied -- holdout access unknown."


@dataclass(frozen=True)
class ResearchReportSection:
    """One supplied run's identity, provenance, metrics, and dimensional
    analysis. Never merged with another section.
    """

    run: RunComparisonEntry
    analysis: AnalysisResult


@dataclass(frozen=True)
class ResearchReport:
    """The assembled result for a caller-supplied set of runs. No verdict
    field -- see module docstring.
    """

    sections: list[ResearchReportSection]
    comparison: BaselineComparisonResult | None
    holdout_usage: HoldoutUsageReport | None
    notes: list[str]


def build_report(
    journal,
    runs: list[LabeledRun],
    *,
    baseline: LabeledRun | None = None,
    holdout_usage_log_path: Path | None = None,
    min_sample_size: int = 5,
) -> ResearchReport:
    """Assemble a ResearchReport from explicit, caller-supplied runs.

    Raises ValueError if `runs` is empty, or if `runs` contains a
    duplicate (run_id, portfolio_id) pair. Raises ValueError (propagated
    from compare_runs()/compare_to_baseline(), not duplicated here) for
    an unknown run_id/portfolio_id or a mismatched portfolio_id/run_id
    pair, in either `runs` or `baseline`.
    """
    if not runs:
        raise ValueError("runs must not be empty")

    seen: set[tuple[str, str]] = set()
    for r in runs:
        key = (r.run_id, r.portfolio_id)
        if key in seen:
            raise ValueError(f"duplicate run in `runs`: {key}")
        seen.add(key)

    resolved = compare_runs(journal, runs)
    sections = [
        ResearchReportSection(
            run=entry,
            analysis=AnalysisEngine(journal, min_sample_size=min_sample_size).analyze(
                entry.portfolio_id
            ),
        )
        for entry in resolved.entries
    ]

    comparison: BaselineComparisonResult | None = None
    if baseline is not None:
        excluded = (baseline.run_id, baseline.portfolio_id)
        candidates = [r for r in runs if (r.run_id, r.portfolio_id) != excluded]
        comparison = compare_to_baseline(journal, baseline, candidates)

    holdout_usage: HoldoutUsageReport | None = None
    if holdout_usage_log_path is not None:
        holdout_usage = holdout_usage_report(holdout_usage_log_path)

    notes = [_SPLIT_SEPARATION_NOTE]
    if baseline is None:
        notes.append(_NO_BASELINE_NOTE)
    if holdout_usage_log_path is None:
        notes.append(_NO_HOLDOUT_LOG_NOTE)

    return ResearchReport(
        sections=sections, comparison=comparison, holdout_usage=holdout_usage, notes=notes
    )
