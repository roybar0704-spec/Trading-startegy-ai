"""AT-2.8 Execution Delay (SPEC §12, D-050): 0ms default is a no-op; >0ms
defers the fill (entry or exit) until the delay has elapsed from the tick
that first satisfied the trigger condition, using the resolving tick's
market data for price/slippage inputs -- SL/TP/limit price stay anchored
(D-018), only timing and time-dependent costs shift.
"""

from datetime import UTC, datetime, timedelta

from src.core.types import Tick
from src.execution.fill_simulator import FillSimulator
from tests.fixtures.execution import make_cost_model, make_order

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def test_zero_delay_limit_entry_fills_immediately():
    sim = FillSimulator(make_cost_model(), in_news_checker=lambda ts: False, execution_delay_ms=0)
    order = make_order(otype="limit", side="buy", price=100.0)
    sim.place(order, "P1")
    fills = sim.on_tick(Tick(ts=T0, bid=99.8, ask=99.9))
    assert len(fills) == 1
    assert fills[0].price == 100.0
    assert fills[0].ts == T0


def test_delayed_limit_entry_waits_for_delay_then_fills_at_limit_price():
    sim = FillSimulator(
        make_cost_model(), in_news_checker=lambda ts: False, execution_delay_ms=250
    )
    order = make_order(otype="limit", side="buy", price=100.0)
    sim.place(order, "P1")

    trigger_ts = T0
    fills = sim.on_tick(Tick(ts=trigger_ts, bid=99.8, ask=99.9))
    assert fills == []  # condition met, but delay not yet elapsed
    assert order.status == "pending"

    too_early = trigger_ts + timedelta(milliseconds=100)
    fills = sim.on_tick(Tick(ts=too_early, bid=99.7, ask=99.8))
    assert fills == []

    resolves = trigger_ts + timedelta(milliseconds=250)
    fills = sim.on_tick(Tick(ts=resolves, bid=99.6, ask=99.7))
    assert len(fills) == 1
    assert fills[0].price == 100.0  # anchored to limit price, not the resolving tick
    assert fills[0].ts == resolves


def test_delayed_sl_exit_uses_resolving_ticks_news_status_for_slippage():
    sim = FillSimulator(
        make_cost_model(), in_news_checker=lambda ts: ts >= T0 + timedelta(milliseconds=200),
        execution_delay_ms=250,
    )
    order = make_order(otype="market", side="buy", price=None, sl=98.0, tp=106.0)
    sim.place(order, "P1")
    sim.on_tick(Tick(ts=T0, bid=100.0, ask=100.2))  # market entry, delayed too

    entry_resolve = T0 + timedelta(milliseconds=250)
    fills = sim.on_tick(Tick(ts=entry_resolve, bid=100.0, ask=100.2))
    assert len(fills) == 1 and fills[0].kind == "market_entry"

    trigger_ts = entry_resolve + timedelta(seconds=1)
    fills = sim.on_tick(Tick(ts=trigger_ts, bid=97.9, ask=98.1))  # SL condition met
    assert fills == []

    resolve_ts = trigger_ts + timedelta(milliseconds=250)  # inside the news window
    fills = sim.on_tick(Tick(ts=resolve_ts, bid=97.5, ask=97.7))
    assert len(fills) == 1
    assert fills[0].kind == "sl_exit"
    # slippage_stop_usd=0.10 * news_slip_mult=3.0 = 0.30 (news at resolve time)
    assert abs(fills[0].price - (98.0 - 0.30)) < 1e-9
