"""Strategy-agnostic Statistical Significance / Bootstrap layer (Research
System, Phase 6).

Answers whether an observed difference (or an observed one-sample mean)
in already-persisted result_r data has statistical evidence behind it,
within the sample actually observed. Nothing more.

Statistical unit -- per-trade result_r (design audit, Phase 6): the
schema's own canonical trade-result field, already the basis for every
existing win/loss/average/median/expectancy computation across
metrics.py/analysis.py/comparison.py. Retrieved read-only, directly via
DuckDBJournal.query(), mirroring analysis.py's own established precedent
of a dedicated trade-fetch query rather than depending on MetricsEngine
internals (metrics.py is not modified by this module).

Independence/exchangeability limitation -- disclosed, not hidden:
standard bootstrap resampling treats observations as approximately
exchangeable/independent. Trading observations can exhibit temporal
dependence, regime clustering, and overlapping/concurrent behavior.
trades.tag_concurrent exists in db/schema.sql as a real column, but is
always written False by Orchestrator today (same placeholder status as
cost_spread/cost_slippage/mae_r/mfe_r, per KI-012/KI-013) -- its presence
is evidence the platform's own design anticipates overlapping trades as
a real possibility, NOT proof that concurrent trades occurred in the
persisted data used by any particular call here. This MVP bootstrap is
therefore an approximation, not a serial-correlation-aware block-
bootstrap procedure -- disclosed on every result via _EXCHANGEABILITY_NOTE.

Comparison kinds:
    - one_sample: is the observed mean result_r for one run distinguishable
      from zero? No pairing question.
    - two_sample_unpaired: general-purpose comparison between two
      arbitrary LabeledRuns. Makes NO assumption that the two runs have
      any trade-for-trade correspondence -- each side is resampled
      independently.
    - two_sample_paired: allowed ONLY when a.run_id == b.run_id and
      a.portfolio_id != b.portfolio_id -- the one currently-justified
      pairing key (RA-09: "Paired Bootstrap on identical Setup Stream"),
      corresponding to two arms/portfolios of the SAME run, which by
      design (D-052) share the identical Setup Stream. Observations are
      paired via the shared setup_id each trade's order belongs to
      (orders.setup_id) -- a real, schema-supported key, NOT positional/
      list-index pairing. If run_id differs, raises ValueError rather
      than inventing another pairing key.

      Uniqueness caveat, verified not assumed: orders/trades carry NO
      database-level uniqueness constraint on (setup_id, portfolio_id) --
      only setup_arm_outcomes' own PRIMARY KEY (setup_id, portfolio_id)
      suggests "at most one terminal outcome per (setup, portfolio)" by
      convention. A SQL JOIN on setup_id alone would silently produce a
      many-to-many/cartesian pairing if that convention were ever
      violated. This module therefore pairs via a Python-side dict keyed
      by setup_id and explicitly raises ValueError if any setup_id
      appears more than once within one portfolio's closed trades --
      never falling back to positional pairing.

      NULL setup_id -- orders.setup_id is TEXT NOT NULL in db/schema.sql,
      so a NULL setup_id should be unreachable through normal insertion.
      This module still treats it as fail-closed defense-in-depth (the
      same posture as DuckDBJournal's own _KNOWN_TABLES check on a value
      that "should never" be wrong): a NULL setup_id is never used as a
      dict key (which could silently pair two unrelated trades across
      portfolios if both happened to carry a NULL), and never silently
      excluded -- it raises ValueError immediately.

Bootstrap method -- nonparametric percentile bootstrap, resampling with
replacement, default n_resamples=10_000, default alpha=0.05 (RA-02, reused
not reinvented), two-sided confidence interval. seed is REQUIRED (no
default) and drives a local random.Random(seed) instance -- the global
`random` module state is never touched, matching CLAUDE.md's "Seed לכל
אקראיות" rule and RA-07's own Baseline(n_sims, seed) precedent (no
default seed there either).

p_value is DEFERRED in this MVP (always None, on EVERY result including
unavailable ones) -- a statistical-correctness finding, not an
oversight: the percentile-bootstrap distribution used for the confidence
interval above is built by resampling the OBSERVED data, so it is
centered near the observed statistic, not generated under a null
hypothesis (statistic=0). Reading P(D<=0)/P(D>=0) off that distribution
as if it were a rigorous null-hypothesis-consistent p-value is not
statistically defensible. A correct null-centered/shifted bootstrap test
(and, for the two-sample case, a correct pooled-under-H0 resampling
scheme) is real additional complexity deferred to a future, separately-
designed iteration. The confidence interval is this module's sole
primary, statistically defensible output. _P_VALUE_DEFERRED_NOTE is
included by _base_notes() -- called unconditionally, before any
availability branching -- so it appears on every result, making
p_value=None unambiguously an intentional design choice rather than a
failed calculation.

Sample-size policy -- min_sample_size (default 10) is a conservative
availability floor, mirroring analysis.py's AnalysisEngine's own
already-approved pattern (an explicit, overridable, documented-as-a-floor
parameter, not a claim of adequate statistical power). n=0, n=1, and
n < min_sample_size all produce available=False with every statistical
field None -- trade counts are still shown (mirroring MetricsResult's own
"counts always shown, only derived statistics withheld" philosophy).
Constant (zero-variance) observations are NOT specially blocked: the
bootstrap runs naturally (every resample of constant data reproduces the
same constant, so the CI mechanically collapses to a point) -- this is
detected and disclosed via a note, not silently presented as unusually
strong evidence.

Missing values -- None result_r values are excluded, never coerced to
zero; the excluded count is disclosed in a note whenever exclusions occur.

No verdict layer: no significant/verdict/recommendation/candidate/
rejected/promising/best/promotion/validation_passed field anywhere.

Multiple comparisons: comparison_count is accepted for DISCLOSURE ONLY --
it never adjusts alpha, the confidence interval, or anything else. No
Bonferroni/Holm/FDR or any other automatic correction is applied.

Anti-overfitting interpretation: mandatory on every result via
_ANTI_OVERFITTING_NOTE -- a bootstrap result here establishes nothing
about out-of-sample edge, future performance, robustness, tradability,
causality, strategy quality, or promotion/candidacy.

Independent of comparison.py by design (Phase 6 scope decision): this
module does not import from or get consumed by comparison.py in this
phase, to avoid prematurely mixing descriptive and statistical concerns.
Read-only throughout: only DuckDBJournal.query() is ever called, never
.record(); no file is ever written by this module.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

from src.research.validation import LabeledRun

_MULTIPLE_COMPARISON_NOTE = (
    "This result may be one of multiple comparisons performed. No "
    "multiple-comparison correction (Bonferroni, Holm, FDR, or otherwise) "
    "is applied here -- alpha and the confidence interval are computed "
    "exactly as if this were the only comparison. If comparison_count is "
    "supplied it is recorded for disclosure only, never used to adjust "
    "any statistical field."
)
_ANTI_OVERFITTING_NOTE = (
    "This bootstrap evaluates uncertainty within the observed sample "
    "only. It does NOT establish out-of-sample edge, future performance, "
    "robustness, tradability, causality, strategy quality, or promotion/"
    "candidacy -- those require separate, human-reviewed research steps."
)
_EXCHANGEABILITY_NOTE = (
    "Standard bootstrap resampling treats observations as approximately "
    "exchangeable/independent. Trading observations can exhibit temporal "
    "dependence, regime clustering, and overlapping/concurrent behavior "
    "(trades.tag_concurrent exists in the schema as a design signal that "
    "overlapping trades are anticipated by the platform -- this does not "
    "by itself prove concurrent trades occurred in the persisted data "
    "used here). This MVP bootstrap is therefore an approximation, not a "
    "serial-correlation-aware block-bootstrap procedure."
)
_P_VALUE_DEFERRED_NOTE = (
    "p_value is deferred in this MVP and is always None -- this is "
    "intentional design, not a failed calculation. The confidence-"
    "interval bootstrap distribution is built by resampling the observed "
    "data, so it is centered near the observed statistic, not generated "
    "under a null hypothesis; reading a p-value off it would not be a "
    "statistically defensible null-hypothesis test. The confidence "
    "interval is this module's primary output."
)
_DEGENERATE_NOTE = (
    "All resampled observations are identical (zero variance) -- the "
    "resulting confidence interval collapses to a point. This is not "
    "evidence of unusually strong statistical significance; it is a "
    "mechanical consequence of constant input data."
)
_UNAVAILABLE_NO_OBSERVATIONS_NOTE = "no closed-trade result_r observations are available"
_UNAVAILABLE_BELOW_FLOOR_NOTE_TMPL = (
    "sample size {n} is below the configured min_sample_size={floor} -- "
    "statistical fields withheld (this floor is a conservative "
    "availability threshold, not a claim of adequate statistical power)"
)


@dataclass(frozen=True)
class BootstrapComparisonResult:
    """One bootstrap procedure's result. Measurements and their
    provenance only -- no verdict, no automatic interpretation.
    """

    comparison_kind: str
    statistic_name: str
    sample_size_a: int
    sample_size_b: int | None
    available: bool
    observed_statistic: float | None
    confidence_level: float
    ci_low: float | None
    ci_high: float | None
    p_value: float | None
    alpha: float
    n_resamples: int
    seed: int
    comparison_count: int | None
    notes: list[str]


def bootstrap_one_sample(
    journal,
    run: LabeledRun,
    *,
    alpha: float = 0.05,
    n_resamples: int = 10_000,
    seed: int,
    min_sample_size: int = 10,
    comparison_count: int | None = None,
) -> BootstrapComparisonResult:
    """Is the observed mean result_r for `run` distinguishable from zero?
    No pairing required.
    """
    _validate_params(alpha, n_resamples, min_sample_size, comparison_count)
    _resolve_and_verify(journal, run)
    values, excluded = _fetch_result_r_values(journal, run.portfolio_id)
    notes = _base_notes(comparison_count)
    if excluded:
        notes.append(f"{excluded} trade(s) with missing result_r were excluded, not coerced to zero")

    n = len(values)
    if n < min_sample_size:
        return _unavailable_result(
            "one_sample", "mean_result_r", n, None, alpha, n_resamples, seed, comparison_count,
            notes, n, min_sample_size,
        )

    rng = random.Random(seed)
    observed = statistics.mean(values)
    resampled = _bootstrap_mean_distribution(values, rng, n_resamples)
    ci_low, ci_high = _percentile_ci(resampled, alpha)
    if len(set(values)) == 1:
        notes.append(_DEGENERATE_NOTE)

    return BootstrapComparisonResult(
        comparison_kind="one_sample",
        statistic_name="mean_result_r",
        sample_size_a=n,
        sample_size_b=None,
        available=True,
        observed_statistic=observed,
        confidence_level=1 - alpha,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=None,
        alpha=alpha,
        n_resamples=n_resamples,
        seed=seed,
        comparison_count=comparison_count,
        notes=notes,
    )


def bootstrap_two_sample_unpaired(
    journal,
    a: LabeledRun,
    b: LabeledRun,
    *,
    alpha: float = 0.05,
    n_resamples: int = 10_000,
    seed: int,
    min_sample_size: int = 10,
    comparison_count: int | None = None,
) -> BootstrapComparisonResult:
    """General-purpose comparison between two arbitrary LabeledRuns.
    Makes NO assumption that `a` and `b` have any trade-for-trade
    correspondence -- each side is resampled independently. statistic =
    mean(b) - mean(a).
    """
    _validate_params(alpha, n_resamples, min_sample_size, comparison_count)
    _resolve_and_verify(journal, a)
    _resolve_and_verify(journal, b)
    values_a, excluded_a = _fetch_result_r_values(journal, a.portfolio_id)
    values_b, excluded_b = _fetch_result_r_values(journal, b.portfolio_id)
    notes = _base_notes(comparison_count)
    if excluded_a or excluded_b:
        notes.append(
            f"{excluded_a} trade(s) excluded from a, {excluded_b} trade(s) excluded from b "
            "(missing result_r, not coerced to zero)"
        )

    n_a, n_b = len(values_a), len(values_b)
    if n_a < min_sample_size or n_b < min_sample_size:
        notes.append(
            f"sample_size_a={n_a}, sample_size_b={n_b}; both must be >= "
            f"min_sample_size={min_sample_size} for an available result"
        )
        return _unavailable_result(
            "two_sample_unpaired", "mean_result_r_difference", n_a, n_b, alpha, n_resamples,
            seed, comparison_count, notes, None, None,
        )

    rng = random.Random(seed)
    observed = statistics.mean(values_b) - statistics.mean(values_a)
    resampled = _bootstrap_unpaired_diff_distribution(values_a, values_b, rng, n_resamples)
    ci_low, ci_high = _percentile_ci(resampled, alpha)
    if len(set(values_a)) == 1 and len(set(values_b)) == 1:
        notes.append(_DEGENERATE_NOTE)

    return BootstrapComparisonResult(
        comparison_kind="two_sample_unpaired",
        statistic_name="mean_result_r_difference",
        sample_size_a=n_a,
        sample_size_b=n_b,
        available=True,
        observed_statistic=observed,
        confidence_level=1 - alpha,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=None,
        alpha=alpha,
        n_resamples=n_resamples,
        seed=seed,
        comparison_count=comparison_count,
        notes=notes,
    )


def bootstrap_two_sample_paired(
    journal,
    a: LabeledRun,
    b: LabeledRun,
    *,
    alpha: float = 0.05,
    n_resamples: int = 10_000,
    seed: int,
    min_sample_size: int = 10,
    comparison_count: int | None = None,
) -> BootstrapComparisonResult:
    """Paired comparison between two arms/portfolios of the SAME run
    (RA-09: "Paired Bootstrap on identical Setup Stream"). Requires
    a.run_id == b.run_id and a.portfolio_id != b.portfolio_id -- the one
    currently-justified pairing key. Raises ValueError otherwise; no
    other pairing key is invented.

    Observations are paired via a Python-side dict keyed by setup_id
    (never positional/list-index pairing). Raises ValueError if any
    setup_id appears more than once, or is NULL, within one portfolio's
    closed trades (see module docstring's uniqueness/NULL caveats)
    rather than silently producing an invalid pairing.
    """
    _validate_params(alpha, n_resamples, min_sample_size, comparison_count)
    _resolve_and_verify(journal, a)
    _resolve_and_verify(journal, b)
    if a.run_id != b.run_id:
        raise ValueError(
            f"paired bootstrap requires a.run_id == b.run_id (got {a.run_id!r} vs {b.run_id!r}) "
            "-- two arbitrary runs are not assumed pairable; no other pairing key is invented"
        )
    if a.portfolio_id == b.portfolio_id:
        raise ValueError(
            f"paired bootstrap requires distinct portfolio_id (both are {a.portfolio_id!r})"
        )

    values_a, values_b, raw_n_a, raw_n_b, excluded = _fetch_paired_result_r_values(
        journal, a.portfolio_id, b.portfolio_id
    )
    notes = _base_notes(comparison_count)
    n = len(values_a)
    notes.append(
        f"portfolio {a.portfolio_id!r} had {raw_n_a} closed trade(s), "
        f"portfolio {b.portfolio_id!r} had {raw_n_b} closed trade(s); "
        f"{n} were pairable via shared setup_id"
    )
    if excluded:
        notes.append(f"{excluded} paired observation(s) excluded (missing result_r on either side)")

    if n < min_sample_size:
        return _unavailable_result(
            "two_sample_paired", "mean_result_r_difference", n, n, alpha, n_resamples,
            seed, comparison_count, notes, n, min_sample_size,
        )

    rng = random.Random(seed)
    observed = statistics.mean(values_b) - statistics.mean(values_a)
    resampled = _bootstrap_paired_diff_distribution(values_a, values_b, rng, n_resamples)
    ci_low, ci_high = _percentile_ci(resampled, alpha)
    diffs = [vb - va for va, vb in zip(values_a, values_b)]
    if len(set(diffs)) == 1:
        notes.append(_DEGENERATE_NOTE)

    return BootstrapComparisonResult(
        comparison_kind="two_sample_paired",
        statistic_name="mean_result_r_difference",
        sample_size_a=n,
        sample_size_b=n,
        available=True,
        observed_statistic=observed,
        confidence_level=1 - alpha,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=None,
        alpha=alpha,
        n_resamples=n_resamples,
        seed=seed,
        comparison_count=comparison_count,
        notes=notes,
    )


# -- internals -----------------------------------------------------------


def _validate_params(alpha: float, n_resamples: int, min_sample_size: int, comparison_count: int | None) -> None:
    if not (0 < alpha < 1):
        raise ValueError(f"alpha must satisfy 0 < alpha < 1, got {alpha!r}")
    if n_resamples <= 0:
        raise ValueError(f"n_resamples must be > 0, got {n_resamples!r}")
    if min_sample_size < 1:
        raise ValueError(f"min_sample_size must be >= 1, got {min_sample_size!r}")
    if comparison_count is not None and comparison_count < 1:
        raise ValueError(f"comparison_count must be None or >= 1, got {comparison_count!r}")


def _base_notes(comparison_count: int | None) -> list[str]:
    """Always included, before any availability branching -- guarantees
    the anti-overfitting/exchangeability/p-value-deferred/multiple-
    comparison disclosures appear on EVERY result, available or not.
    """
    notes = [_ANTI_OVERFITTING_NOTE, _EXCHANGEABILITY_NOTE, _P_VALUE_DEFERRED_NOTE, _MULTIPLE_COMPARISON_NOTE]
    if comparison_count is not None:
        notes.append(f"comparison_count={comparison_count} (disclosure only; does not alter alpha/CI)")
    return notes


def _unavailable_result(
    comparison_kind: str,
    statistic_name: str,
    sample_size_a: int,
    sample_size_b: int | None,
    alpha: float,
    n_resamples: int,
    seed: int,
    comparison_count: int | None,
    notes: list[str],
    n_for_note: int | None,
    floor_for_note: int | None,
) -> BootstrapComparisonResult:
    if n_for_note is not None and floor_for_note is not None:
        if n_for_note == 0:
            notes = [*notes, _UNAVAILABLE_NO_OBSERVATIONS_NOTE]
        else:
            notes = [*notes, _UNAVAILABLE_BELOW_FLOOR_NOTE_TMPL.format(n=n_for_note, floor=floor_for_note)]
    return BootstrapComparisonResult(
        comparison_kind=comparison_kind,
        statistic_name=statistic_name,
        sample_size_a=sample_size_a,
        sample_size_b=sample_size_b,
        available=False,
        observed_statistic=None,
        confidence_level=1 - alpha,
        ci_low=None,
        ci_high=None,
        p_value=None,
        alpha=alpha,
        n_resamples=n_resamples,
        seed=seed,
        comparison_count=comparison_count,
        notes=notes,
    )


def _resolve_and_verify(journal, run: LabeledRun) -> None:
    rows = journal.query("SELECT run_id FROM portfolios WHERE portfolio_id = ?", [run.portfolio_id])
    if not rows:
        raise ValueError(f"unknown portfolio_id {run.portfolio_id!r} -- no row in portfolios")
    actual_run_id = rows[0][0]
    if actual_run_id != run.run_id:
        raise ValueError(
            f"portfolio_id {run.portfolio_id!r} belongs to run_id {actual_run_id!r}, "
            f"not the supplied run_id {run.run_id!r}"
        )


def _fetch_result_r_values(journal, portfolio_id: str) -> tuple[list[float], int]:
    rows = journal.query(
        "SELECT result_r FROM trades WHERE portfolio_id = ? AND exit_ts IS NOT NULL",
        [portfolio_id],
    )
    values: list[float] = []
    excluded = 0
    for (r,) in rows:
        if r is None:
            excluded += 1
        else:
            values.append(r)
    return values, excluded


def _fetch_setup_keyed_result_r(journal, portfolio_id: str) -> dict[str, float | None]:
    """Maps setup_id -> result_r for one portfolio's closed trades.

    Raises ValueError if any setup_id appears more than once (orders/
    trades carry no database-level uniqueness constraint on
    (setup_id, portfolio_id), so this is verified, not assumed) or if any
    setup_id is NULL (orders.setup_id is schema-NOT-NULL, so this should
    be unreachable -- checked anyway as fail-closed defense-in-depth,
    never used as a dict key and never silently excluded).
    """
    rows = journal.query(
        """
        SELECT o.setup_id, t.result_r
        FROM trades t JOIN orders o ON t.order_id = o.order_id
        WHERE t.portfolio_id = ? AND t.exit_ts IS NOT NULL
        """,
        [portfolio_id],
    )
    keyed: dict[str, float | None] = {}
    for setup_id, result_r in rows:
        if setup_id is None:
            raise ValueError(
                f"portfolio {portfolio_id!r} has a closed trade with a NULL setup_id -- "
                "paired bootstrap requires a non-null, defensible setup_id pairing key; "
                "refusing rather than silently excluding it or falling back to positional pairing"
            )
        if setup_id in keyed:
            raise ValueError(
                f"duplicate setup_id {setup_id!r} found among portfolio {portfolio_id!r}'s "
                "closed trades -- cannot establish a one-to-one paired-bootstrap key. "
                "orders/trades do not enforce uniqueness of (setup_id, portfolio_id) at the "
                "database level; this must be resolved before a paired comparison can proceed."
            )
        keyed[setup_id] = result_r
    return keyed


def _fetch_paired_result_r_values(
    journal, portfolio_id_a: str, portfolio_id_b: str
) -> tuple[list[float], list[float], int, int, int]:
    """Pairs observations via a Python-side dict keyed by setup_id (see
    _fetch_setup_keyed_result_r's uniqueness/NULL guards). Returns
    (values_a, values_b, raw_count_a, raw_count_b, excluded_count).
    """
    keyed_a = _fetch_setup_keyed_result_r(journal, portfolio_id_a)
    keyed_b = _fetch_setup_keyed_result_r(journal, portfolio_id_b)
    shared_setup_ids = sorted(set(keyed_a) & set(keyed_b))

    values_a: list[float] = []
    values_b: list[float] = []
    excluded = 0
    for setup_id in shared_setup_ids:
        ra, rb = keyed_a[setup_id], keyed_b[setup_id]
        if ra is None or rb is None:
            excluded += 1
            continue
        values_a.append(ra)
        values_b.append(rb)
    return values_a, values_b, len(keyed_a), len(keyed_b), excluded


def _bootstrap_mean_distribution(values: list[float], rng: random.Random, n_resamples: int) -> list[float]:
    n = len(values)
    means = []
    for _ in range(n_resamples):
        resample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.mean(resample))
    return means


def _bootstrap_unpaired_diff_distribution(
    values_a: list[float], values_b: list[float], rng: random.Random, n_resamples: int
) -> list[float]:
    n_a, n_b = len(values_a), len(values_b)
    diffs = []
    for _ in range(n_resamples):
        resample_a = [values_a[rng.randrange(n_a)] for _ in range(n_a)]
        resample_b = [values_b[rng.randrange(n_b)] for _ in range(n_b)]
        diffs.append(statistics.mean(resample_b) - statistics.mean(resample_a))
    return diffs


def _bootstrap_paired_diff_distribution(
    values_a: list[float], values_b: list[float], rng: random.Random, n_resamples: int
) -> list[float]:
    n = len(values_a)
    diffs = []
    for _ in range(n_resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        resample_a = [values_a[i] for i in idx]
        resample_b = [values_b[i] for i in idx]
        diffs.append(statistics.mean(resample_b) - statistics.mean(resample_a))
    return diffs


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (matches numpy's default 'linear'
    method), 0 <= pct <= 100. No numpy dependency is introduced."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def _percentile_ci(resampled: list[float], alpha: float) -> tuple[float, float]:
    ordered = sorted(resampled)
    low = _percentile(ordered, 100 * (alpha / 2))
    high = _percentile(ordered, 100 * (1 - alpha / 2))
    return low, high
