"""AT-2.7 Quota: the third fill on the same NY day is blocked; an unfilled order
never counts against the quota.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.core.types import ArmId, Order, OrderIntent, Rejection
from src.risk.engine import RiskEngine, RiskEngineParams
from src.risk.portfolio import Portfolio
from src.store.state_store import StateStore
from tests.fixtures.spread import make_spread_report

ARM = ArmId(entry="M2", sl_anchor="S_body")
NY = ZoneInfo("America/New_York")


def test_at_2_7_third_fill_blocked_unfilled_order_not_counted():
    now = datetime(2024, 1, 1, 14, 0, tzinfo=UTC)  # 09:00 ET
    store = StateStore(spread_report=make_spread_report({9: 0.10}))
    ctx = store.as_of(now)
    portfolio = Portfolio(portfolio_id="P1", arm=ARM, initial_equity=10_000)
    engine = RiskEngine(portfolio, RiskEngineParams(sizing_pct=0.005, min_stop_k_spread=3.0))
    ny_date = now.astimezone(NY).date()

    def intent(setup_id: str) -> OrderIntent:
        return OrderIntent(
            setup_id=setup_id, arm=ARM, side="long", otype="market",
            price=2000.00, sl=1999.00, tp=2003.00, valid_until=now,
        )

    order1 = engine.approve(intent("S1"), ctx)
    assert isinstance(order1, Order)
    portfolio.record_fill(ny_date)  # order1 fills

    order2 = engine.approve(intent("S2"), ctx)
    assert isinstance(order2, Order)
    # order2 is placed but never fills (e.g. cancelled) -- must NOT count against quota.

    order3 = engine.approve(intent("S3"), ctx)
    assert isinstance(order3, Order)
    portfolio.record_fill(ny_date)  # order3 fills -- this is the 2nd fill, still within quota

    rejected = engine.approve(intent("S4"), ctx)
    assert isinstance(rejected, Rejection)
    assert rejected.reason == "blocked_quota"
