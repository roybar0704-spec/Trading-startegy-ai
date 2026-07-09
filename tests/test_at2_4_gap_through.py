"""AT-2.4 Gap-Through: a gap beyond SL fills at the first available price + Slippage,
never at the SL price itself.
"""

from datetime import UTC, datetime

from src.core.types import TF, Bar, Tick
from src.execution.fill_simulator import FillSimulator
from tests.fixtures.execution import make_cost_model, make_order


def test_at_2_4_gap_through_never_fills_at_sl_price():
    sim = FillSimulator(make_cost_model(), in_news_checker=lambda ts: False)
    order = make_order(otype="market", side="buy", price=None, sl=98.0, tp=110.0)
    sim.place(order, "P1")
    sim.on_tick(Tick(ts=datetime(2024, 1, 1, 1, tzinfo=UTC), bid=100.0, ask=100.2))
    assert order.status == "filled"

    # Bar opens already below SL: price gapped through overnight, never traded at 98.
    bar = Bar(
        tf=TF.M1,
        open_ts=datetime(2024, 1, 1, 6, tzinfo=UTC),
        close_ts=datetime(2024, 1, 1, 6, 1, tzinfo=UTC),
        o=95.0,
        h=95.5,
        l=94.0,
        c=94.5,
        tick_volume=1,
    )
    fills = sim.on_bar_1m(bar)
    assert len(fills) == 1
    assert fills[0].kind == "gap_through_sl_exit"
    assert fills[0].price != order.sl
    assert fills[0].price == 95.0 - 0.10  # bar's open (first available), minus stop slippage
