"""AT-2.6 Geometry: entry-SL < min_stop -> invalid_geometry, no order."""

from datetime import UTC, datetime

from src.core.types import ArmId, Order, OrderIntent, Rejection
from src.risk.engine import RiskEngine, RiskEngineParams
from src.risk.portfolio import Portfolio
from src.store.state_store import StateStore
from tests.fixtures.spread import make_spread_report

ARM = ArmId(entry="M2", sl_anchor="S_body")


def test_at_2_6_geometry_rejected_below_min_stop():
    now = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)  # 04:00 ET (winter)
    store = StateStore(spread_report=make_spread_report({4: 0.20}))
    ctx = store.as_of(now)
    portfolio = Portfolio(portfolio_id="P1", arm=ARM, initial_equity=10_000)
    engine = RiskEngine(portfolio, RiskEngineParams(sizing_pct=0.005, min_stop_k_spread=3.0))

    # stop_distance = 0.10; min_stop = 3.0 * 0.20 = 0.60 -> must be rejected
    intent = OrderIntent(
        setup_id="S1", arm=ARM, side="long", otype="market",
        price=2000.00, sl=1999.90, tp=2000.30, valid_until=now,
    )
    result = engine.approve(intent, ctx)

    assert isinstance(result, Rejection)
    assert result.reason == "invalid_geometry"


def test_at_2_6_geometry_approved_at_or_above_min_stop():
    now = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    store = StateStore(spread_report=make_spread_report({4: 0.20}))
    ctx = store.as_of(now)
    portfolio = Portfolio(portfolio_id="P1", arm=ARM, initial_equity=10_000)
    engine = RiskEngine(portfolio, RiskEngineParams(sizing_pct=0.005, min_stop_k_spread=3.0))

    # stop_distance = 0.70, comfortably above min_stop (0.60) -- must be approved.
    # (Not testing the exact boundary: 2000.00 - 1999.40 != 0.6 in IEEE 754, which
    # would make this a floating-point precision test, not a geometry-rule test.)
    intent = OrderIntent(
        setup_id="S1", arm=ARM, side="long", otype="market",
        price=2000.00, sl=1999.30, tp=2002.10, valid_until=now,
    )
    result = engine.approve(intent, ctx)

    assert isinstance(result, Order)
