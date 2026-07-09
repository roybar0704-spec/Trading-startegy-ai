"""AT-2.5 Sizing: equity 10,000, stop 2.00$ -> 25 units (0.5% = 50$); realized balance only."""

from datetime import UTC, datetime

from src.core.types import ArmId, OrderIntent
from src.risk.engine import RiskEngine, RiskEngineParams
from src.risk.portfolio import Portfolio
from src.risk.sizing import size_units
from src.store.state_store import StateStore
from tests.fixtures.spread import make_spread_report

ARM = ArmId(entry="M2", sl_anchor="S_body")


def test_at_2_5_size_units_formula():
    assert size_units(equity=10_000, sizing_pct=0.005, stop_distance_usd=2.00) == 25.0


def test_at_2_5_risk_engine_sizes_from_realized_equity():
    now = datetime(2024, 1, 1, 14, 0, tzinfo=UTC)  # 09:00 ET (winter)
    store = StateStore(spread_report=make_spread_report({9: 0.10}))
    ctx = store.as_of(now)
    portfolio = Portfolio(portfolio_id="P1", arm=ARM, initial_equity=10_000)
    engine = RiskEngine(portfolio, RiskEngineParams(sizing_pct=0.005, min_stop_k_spread=3.0))

    intent = OrderIntent(
        setup_id="S1", arm=ARM, side="long", otype="market",
        price=2000.00, sl=1998.00, tp=2006.00, valid_until=now,
    )
    order = engine.approve(intent, ctx)

    assert order.units == 25.0
