"""Pydantic v2 config models (docs/CONFIG_SCHEMA.md, T3.3 prerequisite).

``extra="forbid"`` everywhere: an unknown field is a hard error, never a
silent ignore (CONFIG_SCHEMA.md's own stated principle, already applied to
Displacement params in Phase 1, D-043/KI-004).

``RulesV1`` mirrors ``config/rules_v1.yaml`` field-for-field (FROZEN;
loading it re-verifies the hash via ``frozen_guard`` first, so tampering
is caught at the point of use, not only in CI). ``Parameters`` mirrors
``config/parameters.yaml``. ``RunConfig`` mirrors ``config/run_default.yaml``
(or any run-specific override of it).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from src.config.frozen_guard import verify_frozen_rules

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---- RulesV1 (config/rules_v1.yaml) ----------------------------------


class SessionRules(_Strict):
    """Trading window and day-roll behavior."""

    tz: str
    window: tuple[str, str]
    sequence_scope: str
    cancel_pending_at_close: bool


class BiasOnFlip(_Strict):
    """What happens to open positions vs. pending orders on a Bias flip."""

    open_position: str
    pending_orders: str


class BiasRules(_Strict):
    """4H Bias state machine configuration."""

    source_tf: str
    neutral_policy: str
    on_flip: BiasOnFlip


class FVG4HRules(_Strict):
    """4H FVG validity and ranking rules."""

    min_size: float | None
    valid_until: str
    age_limit: float | None
    ranking: tuple[str, ...]


class ReactionRRule(_Strict):
    """R-candle qualification rule (Reaction, 5M)."""

    in_zone: bool
    body_direction: str
    lower_wick_required: bool


class SweepSRule(_Strict):
    """S-candle qualification rule (Sweep, 5M)."""

    low_below_r_low: bool
    close_back_above_r_low: bool


class IFVGRule(_Strict):
    """iFVG candidate/inversion/selection rule (1M)."""

    candidate: str
    inversion: str
    after_s_close_only: bool
    selection: str
    rearm: bool


class TriggerRules(_Strict):
    """The locked R -> S -> iFVG trigger sequence (SPEC S6-S7)."""

    reaction_r: ReactionRRule
    r_replacement: str
    r_reset_on_close_through: bool
    sweep_s: SweepSRule
    ifvg: IFVGRule
    no_ifvg_outcome: str


class RiskRules(_Strict):
    """Sizing, TP, and quota rules (SPEC S10)."""

    sizing_pct: float
    equity_base: str
    tp_rr: float
    quota_fills_per_day: int
    same_zone_reentry: str


class BlackoutMinutes(_Strict):
    """News blackout window, minutes before/after the event."""

    before: int
    after: int


class NewsFilterRules(_Strict):
    """News blackout scope and behavior (SPEC S11)."""

    currency: tuple[str, ...]
    impact: tuple[str, ...]
    blackout_min: BlackoutMinutes
    pending_on_blackout: str
    open_position_on_news: str


class HoldingRules(_Strict):
    """Overnight/weekend holding policy."""

    overnight: str
    weekend: str


class ExecutionRules(_Strict):
    """Fill semantics (SPEC S12)."""

    limit_fill: str
    fallback_no_ticks: str
    gap_through: str


class RulesV1(_Strict):
    """Mirrors config/rules_v1.yaml -- FROZEN strategy rules."""

    spec_version: str
    instrument: str
    data_source: str
    structure_price: str
    htf_anchor: str
    session: SessionRules
    bias: BiasRules
    fvg_4h: FVG4HRules
    trigger: TriggerRules
    risk: RiskRules
    news_filter: NewsFilterRules
    holding: HoldingRules
    execution: ExecutionRules


# ---- Parameters (config/parameters.yaml) ------------------------------


class GridParamFloat(_Strict):
    """A declared default plus its Grid of allowed alternatives (RA-15/16/17)."""

    default: float
    grid: tuple[float, ...] | None = None


class DisplacementModelChoice(_Strict):
    """Which Displacement model (D1..D5) is active vs. available for experiments."""

    default: str
    experiment_levels: tuple[str, ...]


class D1Params(_Strict):
    """D1 BodyRatio parameters (RA-17)."""

    body_vs_avg_n: int
    ratio_min: GridParamFloat


class DisplacementParams(_Strict):
    """Displacement model selection and D1 parameters."""

    model: DisplacementModelChoice
    d1: D1Params


class CostDefault(_Strict):
    """A single declared cost-model default (RA-10..RA-13)."""

    default: float


class ExecutionDelayParam(_Strict):
    """Execution Delay default and robustness-run values (RA-14, D-050)."""

    default: int
    robustness: tuple[int, ...]


class CostsParams(_Strict):
    """Cost model parameters (RA-10..RA-14)."""

    slippage_stop_usd: CostDefault
    news_slip_mult: CostDefault
    slippage_market_usd: CostDefault
    commission_per_unit: CostDefault
    execution_delay_ms: ExecutionDelayParam


class ScoringWeights(_Strict):
    """Log-Only Scoring component weights (RA-20)."""

    fvg_level: float
    ts: float
    sweep_quality: float
    bias_recency: float


class Parameters(_Strict):
    """Mirrors config/parameters.yaml -- declared parameters and Grids."""

    sl_buffer_usd: GridParamFloat
    min_stop_k_spread: GridParamFloat
    displacement: DisplacementParams
    costs: CostsParams
    warmup_days: int
    tick_on_demand_band_usd: float
    scoring_weights: ScoringWeights
    initial_equity_usd: float


# ---- RunConfig (config/run_default.yaml) -------------------------------


class Guards(_Strict):
    """Statistical-validity guard thresholds (RA-02..RA-04)."""

    p_vs_baseline_max: float
    pf_min: float
    min_trades: int
    worst_quarter_r_min: float


class Period(_Strict):
    """Backtest period boundaries."""

    start: date
    end: date


class Holdout(_Strict):
    """Hold-Out window declaration and unlock flag (RA-06)."""

    last_months: int
    unlocked: bool


class WalkForward(_Strict):
    """Walk-Forward split sizing (RA-05)."""

    train_months: int
    test_months: int


class Arms(_Strict):
    """The declared Grid of entry models x SL anchors for this run."""

    entry_models: tuple[Literal["M1", "M2", "M4"], ...]
    sl_anchors: tuple[Literal["R_body", "S_body", "S_wick"], ...]


class Baseline(_Strict):
    """Random Baseline simulation parameters (RA-07)."""

    n_sims: int
    seed: int


class RunConfig(_Strict):
    """Mirrors config/run_default.yaml (or a run-specific override)."""

    experiment: str
    objective: str
    guards: Guards
    period: Period
    holdout: Holdout
    walk_forward: WalkForward
    arms: Arms
    baseline: Baseline
    seed: int


# ---- Loaders ------------------------------------------------------------


def load_rules_v1(path: Path = CONFIG_DIR / "rules_v1.yaml") -> RulesV1:
    """Verify the frozen hash, then parse. Any drift or schema violation raises."""
    verify_frozen_rules(rules_path=path)
    return RulesV1.model_validate(yaml.safe_load(path.read_text()))


def load_parameters(path: Path = CONFIG_DIR / "parameters.yaml") -> Parameters:
    """Load and validate config/parameters.yaml."""
    return Parameters.model_validate(yaml.safe_load(path.read_text()))


def load_run_config(path: Path = CONFIG_DIR / "run_default.yaml") -> RunConfig:
    """Load and validate a RunConfig YAML (default: config/run_default.yaml)."""
    return RunConfig.model_validate(yaml.safe_load(path.read_text()))


def config_hash(
    rules: RulesV1, parameters: Parameters, run_config: RunConfig,
    data_version: str, code_version: str,
) -> str:
    """SHA256(canonical_json(merged) + data_version + code_version) -- CONFIG_SCHEMA.md."""
    merged = {
        "rules": rules.model_dump(mode="json"),
        "parameters": parameters.model_dump(mode="json"),
        "run_config": run_config.model_dump(mode="json"),
    }
    canonical = json.dumps(merged, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((canonical + data_version + code_version).encode()).hexdigest()
