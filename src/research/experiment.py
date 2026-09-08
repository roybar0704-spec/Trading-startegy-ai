"""Strategy-agnostic Experiment Model (Research System, Phase 7).

A declared research hypothesis and its exact intended comparison, fixed
BEFORE any run/result is examined. This module has NO Journal access at
all -- Experiment/declare_experiment take no `journal` parameter and
perform no database interaction whatsoever, the first Research System
component with zero database interaction (stricter than every prior
phase, which were all read-only-via-query rather than no-access).

Model only, not a Tracker: this module deliberately does not persist
anything to the Journal. A real, persistent, cross-session Experiment
Tracker (a "research ledger" recording how many experiments were run,
with what hypotheses, how many touched holdout) would require either a
new write-capable module -- the first one in the entire research layer,
a categorically different risk class -- or modifying the protected
Orchestrator (the sole current writer of `experiments` rows, which it
always populates with a KI-018 placeholder hypothesis, never a real
one). Neither is in scope here; this is the Experiment Model only,
explicitly deferred Tracker persistence to a separately-authorized
future phase (Phase 7 design audit, Section C).

Objective locking: declare_experiment() requires non-empty hypothesis
and objective at construction time, before baseline/candidate results
are examined -- a small, real, enforced check (not just documentation),
serving the anti-overfitting objective-locking principle for the first
time anywhere in the Research System.

Changed/fixed variables: explicit, caller-supplied dict[str, str]
fields -- closes the gap identified during the Phase 4 design audit (no
declared_changed_variables field exists anywhere in the schema),
in-memory only, no schema change.

Baseline semantics -- identical to comparison.py's and report.py's:
Experiment.baseline is always the caller-supplied LabeledRun argument,
reusing that exact type verbatim. It is never confused with:
    - RunIdentity.split_type == "baseline" (the Random Baseline
      statistical simulation concept, RA-07/T5.3 -- unrelated)
    - db/schema.sql's baseline_runs table (same unrelated concept)
    - the Code Baseline (git tag strategy-a-baseline-v1) -- a git-level
      concept, never referenced here
Experiment never assigns or infers split_type for any LabeledRun it
carries -- each LabeledRun's split_type was already assigned wherever it
was originally produced (matching report.py's own "never infer" rule).
This means Experiment cannot bypass validation/holdout governance: it
has no mechanism to select or relabel a split, only to carry references
to already-labeled runs.

ExperimentResult is a pure bundling container, not an orchestrator: it
NEVER computes a report/comparison/significance result itself. The
caller runs build_report()/compare_to_baseline()/bootstrap_*() exactly
as they already do today (unchanged, unmodified), and only then attaches
those already-computed results here for one coherent record. Zero
duplicated orchestration logic, zero new metric/statistic calculation.

No verdict layer: no significant/verdict/recommendation/candidate/
rejected/promising/best/promotion/validation_passed field anywhere on
either dataclass.

Read-only/no-access: no Journal query or record call anywhere in this
module; no file is ever written.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.research.comparison import BaselineComparisonResult
from src.research.report import ResearchReport
from src.research.significance import BootstrapComparisonResult
from src.research.validation import LabeledRun


@dataclass(frozen=True)
class Experiment:
    """A declared research hypothesis and its exact intended comparison.
    In-memory only -- no Journal access, no persistence.
    """

    hypothesis: str
    objective: str
    baseline: LabeledRun
    candidates: list[LabeledRun]
    changed_variables: dict[str, str]
    fixed_variables: dict[str, str]


def declare_experiment(
    hypothesis: str,
    objective: str,
    baseline: LabeledRun,
    candidates: list[LabeledRun],
    *,
    changed_variables: dict[str, str],
    fixed_variables: dict[str, str],
) -> Experiment:
    """Validate and construct an Experiment. Requires non-empty
    hypothesis and objective -- explicit objective-locking, not merely
    documented convention. No Journal access.
    """
    if not hypothesis or not hypothesis.strip():
        raise ValueError("hypothesis must be a non-empty string")
    if not objective or not objective.strip():
        raise ValueError("objective must be a non-empty string")

    return Experiment(
        hypothesis=hypothesis,
        objective=objective,
        baseline=baseline,
        candidates=candidates,
        changed_variables=changed_variables,
        fixed_variables=fixed_variables,
    )


@dataclass(frozen=True)
class ExperimentResult:
    """The declared Experiment plus whichever already-existing engine
    outputs the caller chose to attach. Never computed internally -- see
    module docstring. No verdict field.
    """

    experiment: Experiment
    report: ResearchReport | None
    comparison: BaselineComparisonResult | None
    significance: list[BootstrapComparisonResult]
    notes: list[str]
