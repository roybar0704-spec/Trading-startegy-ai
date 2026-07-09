"""AT-2.2 SL sides: SL long checked vs Bid; short vs Ask (wide-spread fixture proves it)."""

from datetime import UTC, datetime

from src.core.types import Tick
from src.execution.fill_simulator import FillSimulator
from tests.fixtures.execution import make_cost_model, make_order


def test_at_2_2_sl_long_checked_vs_bid():
    sim = FillSimulator(make_cost_model(), in_news_checker=lambda ts: False)
    order = make_order(otype="market", side="buy", price=None, sl=100.0, tp=110.0)
    sim.place(order, "P1")
    sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, tzinfo=UTC), bid=104.0, ask=104.2))
    assert order.status == "filled"

    # Wide spread: Bid below SL(100), Ask still above SL -- only the Bid-side check can fire.
    fills = sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, 1, tzinfo=UTC), bid=99.5, ask=100.5))
    assert len(fills) == 1
    assert fills[0].kind == "sl_exit"


def test_at_2_2_sl_short_checked_vs_ask():
    sim = FillSimulator(make_cost_model(), in_news_checker=lambda ts: False)
    order = make_order(otype="market", side="sell", price=None, sl=100.0, tp=90.0)
    sim.place(order, "P1")
    sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, tzinfo=UTC), bid=95.8, ask=96.0))
    assert order.status == "filled"

    # Wide spread: Ask above SL(100), Bid still below SL -- only the Ask-side check can fire.
    fills = sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, 1, tzinfo=UTC), bid=99.5, ask=100.5))
    assert len(fills) == 1
    assert fills[0].kind == "sl_exit"
