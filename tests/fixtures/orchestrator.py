"""T3.3 Orchestrator test scaffolding."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.backtest.orchestrator import Orchestrator
from src.backtest.portfolio_arm import PortfolioArm
from src.core.types import FVG, TF, ArmId, RunIdentity, Tick
from src.data.versioning import data_version_for_ticks
from src.displacement.d1_body import D1_DEFAULT_PARAMS, D1BodyRatio
from src.entry.m1 import M1EntryModel
from src.entry.m2 import M2EntryModel
from src.entry.m4 import M4EntryModel
from src.execution.cost_model import CostModelParams, StaticCostModel
from src.execution.fill_simulator import FillSimulator
from src.risk.engine import RiskEngine, RiskEngineParams
from src.risk.portfolio import Portfolio
from src.session.calendar_engine import CalendarEngine
from src.session.session_engine import SessionEngine
from src.store.state_store import BiasEvent

# Fixed override (Stage A / B-1, WORK_ORDER_B1.md S4 Commit 3) -- tests never
# depend on git state for code_version.
TEST_CODE_VERSION = "b1-test-fixed-sha"


def make_identity(ticks=(), split_type: str = "fixture") -> RunIdentity:
    """RunIdentity for tests: data_version derived from the fixture's own ticks
    (D-037: even a synthetic/fixture run gets a real data_version); code_version
    fixed so tests never depend on git state.
    """
    return RunIdentity(
        data_version=data_version_for_ticks(list(ticks)),
        split_type=split_type,
        code_version=TEST_CODE_VERSION,
    )

SESSION = SessionEngine.from_config(window=("08:30", "10:30"), tz="America/New_York")
NO_BLACKOUT = CalendarEngine.from_config(
    [], currencies=("USD",), impacts=("red",), blackout_before_min=30, blackout_after_min=30,
)
SEED_TS = datetime(2024, 1, 10, 12, 0, tzinfo=UTC)
IN_WINDOW = datetime(2024, 1, 10, 14, 0, tzinfo=UTC)  # 09:00 ET, winter
_ET = ZoneInfo("America/New_York")


def warmup_ticks(spread_by_hour: dict[int, float]) -> list[Tick]:
    """One synthetic pre-run Tick per ET hour (2024-01-01, strictly before SEED_TS) at a
    fixed spread -- warm-starts ExpandingSpreadReport (D-049) so median_spread() has data
    before any Tick appears on the test's own timeline. Legitimately prior data, not a
    lookahead shortcut -- see ExpandingSpreadReport.warm_start.
    """
    ticks = []
    for hour, spread in spread_by_hour.items():
        ts_ny = datetime(2024, 1, 1, hour, 0, tzinfo=_ET)
        ticks.append(Tick(ts=ts_ny.astimezone(UTC), bid=2000.0, ask=2000.0 + spread))
    return ticks


def cost_model() -> StaticCostModel:
    return StaticCostModel(
        CostModelParams(
            slippage_stop_usd=0.10, news_slip_mult=3.0,
            slippage_market_usd=0.05, commission_per_unit=0.0,
        )
    )


def make_arm(
    entry: str, sl_anchor: str, initial_equity: float = 10_000,
    min_stop_k_spread: float = 0.01,
) -> PortfolioArm:
    """min_stop_k_spread defaults tiny -- test SL distances are small, real geometry
    isn't the point of these tests (already covered by test_at2_6_geometry.py)."""
    arm_id = ArmId(entry=entry, sl_anchor=sl_anchor)
    portfolio_id = f"P-{entry}-{sl_anchor}"
    portfolio = Portfolio(portfolio_id=portfolio_id, arm=arm_id, initial_equity=initial_equity)
    risk = RiskEngine(
        portfolio, RiskEngineParams(sizing_pct=0.005, min_stop_k_spread=min_stop_k_spread)
    )
    fill_sim = FillSimulator(cost_model(), in_news_checker=lambda ts: False)
    return PortfolioArm(arm_id=arm_id, portfolio=portfolio, risk=risk, fill_sim=fill_sim)


def make_orchestrator(
    bars_1m=(), bars_5m=(), bars_4h=(), ticks=(),
    arms=None, entry_models=None, calendar=NO_BLACKOUT,
) -> Orchestrator:
    if arms is None:
        arms = [make_arm("M2", "R_body")]
    if entry_models is None:
        entry_models = {
            "M1": M1EntryModel(session=SESSION, get_setup=None),
            "M2": M2EntryModel(get_setup=None),
            "M4": M4EntryModel(get_setup=None),
        }
    orch = Orchestrator(
        bars_1m=list(bars_1m), bars_5m=list(bars_5m), bars_4h=list(bars_4h), ticks=list(ticks),
        session=SESSION, calendar=calendar, arms=arms, entry_models=entry_models,
        displacement_model=D1BodyRatio(), displacement_params=D1_DEFAULT_PARAMS,
        cost_model=cost_model(), sl_buffer_usd=0.05,
        spread_warmup_ticks=warmup_ticks({h: 0.01 for h in range(24)}), journal=None,
    )
    return orch


def seed_fvg_and_bias(
    orch: Orchestrator, direction: str, top: float, bottom: float, fvg_id: str = "FVG-H4-1",
) -> None:
    """Bypass StructureEngine/FVGEngine simulation -- Orchestrator only ever queries the
    resulting state, so this is equivalent and much cheaper to set up (matches
    tests/fixtures/setup_stream.py's seed_store pattern)."""
    orch.store.put(
        FVG(
            id=fvg_id, tf=TF.H4, direction="bull" if direction == "long" else "bear",
            top=top, bottom=bottom, level=1, created_at=SEED_TS, confirmed_at=SEED_TS,
            mitigation_pct=0.0, invalidated_at=None, bos_link=None, displacement=False,
        )
    )
    orch.store.put(
        BiasEvent(
            ts=SEED_TS, state="bullish" if direction == "long" else "bearish", trigger_bos=None,
        )
    )
