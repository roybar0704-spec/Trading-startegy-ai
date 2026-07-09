"""AT-2.3 SL-First fallback: a 1M bar that touches both SL and TP without tick data -> SL."""

from datetime import UTC, datetime

from src.core.types import TF, Bar, Tick
from src.execution.fill_simulator import FillSimulator
from tests.fixtures.execution import make_cost_model, make_order


def test_at_2_3_bar_touching_both_sl_and_tp_resolves_to_sl():
    sim = FillSimulator(make_cost_model(), in_news_checker=lambda ts: False)
    order = make_order(otype="market", side="buy", price=None, sl=98.0, tp=104.0)
    sim.place(order, "P1")
    sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, tzinfo=UTC), bid=100.0, ask=100.2))
    assert order.status == "filled"

    bar = Bar(
        tf=TF.M1,
        open_ts=datetime(2024, 1, 1, 2, tzinfo=UTC),
        close_ts=datetime(2024, 1, 1, 2, 1, tzinfo=UTC),
        o=100.0,
        h=105.0,  # touches TP (104)
        l=97.0,  # touches SL (98)
        c=101.0,
        tick_volume=1,
    )
    fills = sim.on_bar_1m(bar)
    assert len(fills) == 1
    assert fills[0].kind == "sl_exit"
    assert fills[0].price == 98.0 - 0.10  # SL minus stop slippage, not TP
