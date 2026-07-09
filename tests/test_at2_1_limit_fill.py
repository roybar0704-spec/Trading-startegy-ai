"""AT-2.1 Limit fill: buying Limit at P -> fills only when Ask <= P, at price P."""

from datetime import UTC, datetime

from src.core.types import Tick
from src.execution.fill_simulator import FillSimulator
from tests.fixtures.execution import make_cost_model, make_order


def test_at_2_1_limit_fill_only_when_ask_leq_price_at_price():
    sim = FillSimulator(make_cost_model(), in_news_checker=lambda ts: False)
    order = make_order()
    sim.place(order, "P1")

    no_fill = sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, tzinfo=UTC), bid=100.3, ask=100.5))
    assert no_fill == []
    assert order.status == "pending"

    fills = sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, 1, tzinfo=UTC), bid=99.7, ask=99.9))
    assert len(fills) == 1
    assert fills[0].price == 100.0  # exactly P, never better (no positive slippage, D-018)
    assert fills[0].kind == "limit_entry"
    assert order.status == "filled"
    assert order.fill_price == 100.0
