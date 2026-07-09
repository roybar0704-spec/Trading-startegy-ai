"""RiskEngine.approve() module-boundary contract checks (found untested during
the Phase 2 Critical Review): OrderIntent.price=None (D-045) and an invalid
OrderIntent.side both indicate a bug in whatever produced the intent, not a
legitimate trading rejection -- so they raise, not Reject.
"""

from datetime import UTC, datetime

import pytest

from src.core.types import ArmId, OrderIntent
from src.risk.engine import RiskEngine, RiskEngineParams
from src.risk.portfolio import Portfolio
from src.store.state_store import StateStore
from tests.fixtures.spread import make_spread_report

ARM = ArmId(entry="M2", sl_anchor="S_body")


def _engine() -> RiskEngine:
    portfolio = Portfolio(portfolio_id="P1", arm=ARM, initial_equity=10_000)
    return RiskEngine(portfolio, RiskEngineParams(sizing_pct=0.005, min_stop_k_spread=3.0))


def _ctx(now: datetime):
    store = StateStore(spread_report=make_spread_report({4: 0.20}))
    return store.as_of(now)


def test_price_none_raises_not_rejects():
    now = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    intent = OrderIntent(
        setup_id="S1", arm=ARM, side="long", otype="market",
        price=None, sl=1999.30, tp=2002.10, valid_until=now,
    )
    with pytest.raises(ValueError, match="Reference Entry Price"):
        _engine().approve(intent, _ctx(now))


def test_invalid_side_raises_not_rejects():
    now = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    intent = OrderIntent(
        setup_id="S1", arm=ARM, side="sideways", otype="market",
        price=2000.00, sl=1999.30, tp=2002.10, valid_until=now,
    )
    with pytest.raises(ValueError, match="side must be"):
        _engine().approve(intent, _ctx(now))
