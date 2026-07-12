"""Build a fully-wired Orchestrator directly from the frozen config files (KI-016).

Before this module existed, every caller (tests, demo, bench scripts) hand-translated
config/rules_v1.yaml + config/parameters.yaml + config/run_default.yaml into
Orchestrator constructor arguments -- each translation was independent, undeclared,
and could silently drift from the frozen values. ``build_orchestrator`` is the single
place that translation happens: given the three loaded config models plus the data a
run needs (bars/ticks/news -- D-037, still injected, never read from disk here), it
returns an ``Orchestrator`` wired exactly per the declared config, for every one of the
9 arms in ``run_config.arms``.

Only the D1 displacement model exists in code so far (D2-D5 are declared in
parameters.yaml as future ``experiment_levels`` but have no implementation yet,
per PHASE_PLAN.md) -- selecting one of those raises clearly rather than silently
falling back to D1.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.backtest.orchestrator import Orchestrator
from src.backtest.portfolio_arm import PortfolioArm
from src.config.models import Parameters, RulesV1, RunConfig, config_hash
from src.core.types import ArmId, Bar, NewsEvent, RunIdentity, Tick
from src.displacement.d1_body import D1BodyRatio
from src.displacement.model import DisplacementModel
from src.entry.m1 import M1EntryModel
from src.entry.m2 import M2EntryModel
from src.entry.m4 import M4EntryModel
from src.execution.cost_model import CostModelParams, StaticCostModel
from src.execution.fill_simulator import FillSimulator
from src.journal.duckdb_writer import DuckDBJournal
from src.risk.engine import RiskEngine, RiskEngineParams
from src.risk.portfolio import Portfolio
from src.session.calendar_engine import CalendarEngine
from src.session.session_engine import SessionEngine

_DISPLACEMENT_MODELS: dict[str, type[DisplacementModel]] = {"D1": D1BodyRatio}

REPO_ROOT = Path(__file__).resolve().parents[2]
# Temporary run registry (Stage A / B-1, D-067) -- until T5.5's Experiment Tracker
# replaces it. data/ is entirely gitignored; only .gitkeep is force-tracked (C3).
_DEFAULT_REGISTRY_PATH = REPO_ROOT / "data" / "registry" / "runs.jsonl"


def detect_code_version() -> str:
    """Identify the running code from git: ``<sha>`` or ``<sha>+dirty``.

    Fails loudly (``RuntimeError``) rather than falling back silently -- a
    reproducibility identity that can't be trusted is worse than none (SPEC S13).
    """
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        raise RuntimeError(f"detect_code_version: git command failed: {exc}") from exc
    return f"{sha}+dirty" if status.strip() else sha


def _displacement_model_and_params(parameters: Parameters) -> tuple[DisplacementModel, dict]:
    choice = parameters.displacement.model.default
    if choice not in _DISPLACEMENT_MODELS:
        raise NotImplementedError(
            f"Displacement model {choice!r} is declared in parameters.yaml's "
            f"experiment_levels but has no implementation yet (only D1 exists)."
        )
    params = {
        "body_vs_avg_n": parameters.displacement.d1.body_vs_avg_n,
        "ratio_min": parameters.displacement.d1.ratio_min.default,
    }
    return _DISPLACEMENT_MODELS[choice](), params


def _build_cost_model(parameters: Parameters) -> StaticCostModel:
    return StaticCostModel(
        CostModelParams(
            slippage_stop_usd=parameters.costs.slippage_stop_usd.default,
            news_slip_mult=parameters.costs.news_slip_mult.default,
            slippage_market_usd=parameters.costs.slippage_market_usd.default,
            commission_per_unit=parameters.costs.commission_per_unit.default,
        )
    )


def _build_arms(
    rules: RulesV1, parameters: Parameters, run_config: RunConfig, calendar: CalendarEngine,
) -> list[PortfolioArm]:
    arms = []
    for entry in run_config.arms.entry_models:
        for sl_anchor in run_config.arms.sl_anchors:
            arm_id = ArmId(entry=entry, sl_anchor=sl_anchor)
            portfolio = Portfolio(
                portfolio_id=f"P-{entry}-{sl_anchor}", arm=arm_id,
                initial_equity=parameters.initial_equity_usd,
            )
            risk = RiskEngine(
                portfolio,
                RiskEngineParams(
                    sizing_pct=rules.risk.sizing_pct,
                    min_stop_k_spread=parameters.min_stop_k_spread.default,
                ),
            )
            # Calendar now exists (T3.1) -- no more silent no-news stub (FillSimulator's
            # own docstring flagged this as the intended follow-up once it did).
            fill_sim = FillSimulator(
                _build_cost_model(parameters), in_news_checker=calendar.in_blackout,
                execution_delay_ms=parameters.costs.execution_delay_ms.default,
            )
            arms.append(
                PortfolioArm(arm_id=arm_id, portfolio=portfolio, risk=risk, fill_sim=fill_sim)
            )
    return arms


def _build_entry_models(run_config: RunConfig, session: SessionEngine) -> dict:
    declared = set(run_config.arms.entry_models)
    models = {}
    if "M1" in declared:
        models["M1"] = M1EntryModel(session=session, get_setup=None)
    if "M2" in declared:
        models["M2"] = M2EntryModel(get_setup=None)
    if "M4" in declared:
        models["M4"] = M4EntryModel(get_setup=None)
    return models


def build_orchestrator(
    rules: RulesV1,
    parameters: Parameters,
    run_config: RunConfig,
    *,
    identity: RunIdentity,
    bars_1m: list[Bar],
    bars_5m: list[Bar],
    bars_4h: list[Bar],
    ticks: list[Tick],
    news: list[NewsEvent] = (),
    spread_warmup_ticks: list[Tick] = (),
    journal: DuckDBJournal | None = None,
    run_id: str = "run",
    registry_path: Path | None = None,
) -> Orchestrator:
    """Translate the three loaded config models into a fully-wired Orchestrator.

    ``bars_*``/``ticks``/``news``/``spread_warmup_ticks`` remain caller-injected data
    (D-037: engines never read a concrete data source) -- only the *shape* of the run
    (session/blackout/arms/costs/displacement/sizing/equity) comes from config here.

    ``identity`` (Stage A / B-1, D-067, closes KI-018): the caller declares
    ``data_version``/``split_type``/``seed``; ``config_hash`` is computed here from
    ``(rules, parameters, run_config, identity.data_version, code_version)`` --
    a caller-supplied ``config_hash`` is a contract violation. ``code_version``
    defaults to git auto-detection (``detect_code_version``); an explicit override
    is for tests only. If ``journal`` is given (already successfully opened by the
    caller), one JSONL record is appended to ``registry_path`` (default
    ``data/registry/runs.jsonl``) -- a temporary run registry until T5.5's
    Experiment Tracker replaces it.
    """
    if identity.config_hash is not None:
        raise ValueError(
            "identity.config_hash is computed internally by build_orchestrator; "
            "callers must not supply it"
        )
    code_version = identity.code_version or detect_code_version()
    resolved_hash = config_hash(
        rules, parameters, run_config,
        data_version=identity.data_version, code_version=code_version,
    )

    session = SessionEngine.from_config(window=rules.session.window, tz=rules.session.tz)
    calendar = CalendarEngine.from_config(
        list(news), currencies=rules.news_filter.currency, impacts=rules.news_filter.impact,
        blackout_before_min=rules.news_filter.blackout_min.before,
        blackout_after_min=rules.news_filter.blackout_min.after,
    )
    displacement_model, displacement_params = _displacement_model_and_params(parameters)

    if journal is not None:
        _append_registry_record(
            registry_path=registry_path or _DEFAULT_REGISTRY_PATH, run_id=run_id,
            config_hash=resolved_hash, code_version=code_version,
            data_version=identity.data_version, split_type=identity.split_type,
            seed=identity.seed,
        )

    return Orchestrator(
        bars_1m=bars_1m, bars_5m=bars_5m, bars_4h=bars_4h, ticks=ticks,
        session=session, calendar=calendar,
        arms=_build_arms(rules, parameters, run_config, calendar),
        entry_models=_build_entry_models(run_config, session),
        displacement_model=displacement_model, displacement_params=displacement_params,
        cost_model=_build_cost_model(parameters),
        sl_buffer_usd=parameters.sl_buffer_usd.default,
        symbol=rules.instrument,
        spread_warmup_ticks=list(spread_warmup_ticks),
        journal=journal, run_id=run_id,
        config_hash=resolved_hash, code_version=code_version,
        data_version=identity.data_version, split_type=identity.split_type,
        seed=identity.seed,
    )


def _append_registry_record(
    *, registry_path: Path, run_id: str, config_hash: str, code_version: str,
    data_version: str, split_type: str, seed: int | None,
) -> None:
    """Append one append-only JSONL record -- mirrors Orchestrator._write_run_identity_rows'
    ``experiment_id`` formula (``f"{run_id}-exp"``); this is a log of *declared* run
    identity, kept independently of whether ``run()`` is later invoked or succeeds.
    """
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "experiment_id": f"{run_id}-exp",
        "config_hash": config_hash,
        "code_version": code_version,
        "data_version": data_version,
        "split_type": split_type,
        "seed": seed,
        "objective_id": "RA-01",
    }
    with registry_path.open("a") as f:
        f.write(json.dumps(record) + "\n")
