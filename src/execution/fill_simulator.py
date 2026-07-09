"""Fill Simulator (docs/SPEC_V1_FROZEN.md §12, docs/INTERFACES.md FillSimulator).

Limit fills at exactly the limit price, never with positive slippage
(D-018, config/rules_v1.yaml execution.limit_fill). Market entries get
market_slippage applied against the trader. SL/TP exits check price
against the side matching a real close-out trade: a long exits by
selling (checked vs Bid, AT-2.2), a short exits by buying (checked vs
Ask) -- the same general Bid/Ask rule that AT-2.2 states for SL applies
to TP too (SPEC §12's Bid/Ask rule is not SL-specific). SL-First fallback
resolves an ambiguous 1M bar that touches both SL and TP without tick
data (AT-2.3). Gap-Through fills at the first available price (this
bar's open) plus stop slippage, never at the SL price itself (AT-2.4).
TP exits are always capped at exactly ``tp`` -- conservative by
construction (D-018): a favorable gap past TP is never credited.

``in_news_checker`` has **no default** (D-043/KI-004 precedent: no silent
defaults for something that changes a real cost). Calendar/Blackout
detection doesn't exist until Phase 3 T3.1 -- callers must pass an
explicit stub (e.g. ``lambda ts: False``) so the limitation is visible at
every call site, not hidden inside this class.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from src.core.types import Bar, Fill, Order, PortfolioId, Tick
from src.execution.cost_model import StaticCostModel


class FillSimulator:
    """Tracks pending orders and open (filled, unexited) positions; emits Fills."""

    def __init__(
        self, cost_model: StaticCostModel, in_news_checker: Callable[[datetime], bool]
    ) -> None:
        """``in_news_checker(ts)`` must be supplied explicitly -- see module docstring."""
        self.cost_model = cost_model
        self.in_news_checker = in_news_checker
        self._orders: dict[str, Order] = {}
        self._open: set[str] = set()

    def place(self, order: Order, portfolio: PortfolioId) -> None:
        """Register a new pending order."""
        self._orders[order.order_id] = order

    def cancel(self, order_id: str, reason: str) -> None:
        """Cancel a still-pending order; no-op if already filled/cancelled."""
        order = self._orders[order_id]
        if order.status != "pending":
            return
        order.status = "cancelled"
        order.cancel_reason = reason

    def on_tick(self, tick: Tick) -> list[Fill]:
        """Check every pending entry and every open exit against one real tick."""
        fills: list[Fill] = []
        for order in list(self._orders.values()):
            if order.status == "pending":
                fill = self._try_entry_tick(order, tick)
            elif order.order_id in self._open:
                fill = self._try_exit_tick(order, tick)
            else:
                fill = None
            if fill is not None:
                fills.append(fill)
        return fills

    def on_bar_1m(self, bar: Bar) -> list[Fill]:
        """SL-First fallback: resolve open positions from a 1M bar with no tick data."""
        fills: list[Fill] = []
        for order_id in list(self._open):
            fill = self._try_exit_bar(self._orders[order_id], bar)
            if fill is not None:
                fills.append(fill)
        return fills

    def _try_entry_tick(self, order: Order, tick: Tick) -> Fill | None:
        if order.otype == "limit":
            if order.side == "buy" and tick.ask <= order.price:
                return self._fill_entry(order, order.price, tick.ts, "limit_entry")
            if order.side == "sell" and tick.bid >= order.price:
                return self._fill_entry(order, order.price, tick.ts, "limit_entry")
            return None
        slip = self.cost_model.market_slippage(tick.ts)
        price = tick.ask + slip if order.side == "buy" else tick.bid - slip
        return self._fill_entry(order, price, tick.ts, "market_entry")

    def _fill_entry(
        self, order: Order, price: float, ts: datetime, kind: Literal["limit_entry", "market_entry"]
    ) -> Fill:
        order.status = "filled"
        order.filled_at = ts
        order.fill_price = price
        self._open.add(order.order_id)
        return Fill(order_id=order.order_id, ts=ts, price=price, kind=kind)

    def _stop_slip(self, ts: datetime) -> float:
        return self.cost_model.stop_slippage(ts, in_news=self.in_news_checker(ts))

    def _try_exit_tick(self, order: Order, tick: Tick) -> Fill | None:
        if order.side == "buy":  # long: exit = sell, checked vs Bid
            if tick.bid <= order.sl:
                sl_price = order.sl - self._stop_slip(tick.ts)
                return self._fill_exit(order, sl_price, tick.ts, "sl_exit")
            if tick.bid >= order.tp:
                return self._fill_exit(order, order.tp, tick.ts, "tp_exit")
        else:  # short: exit = buy, checked vs Ask
            if tick.ask >= order.sl:
                sl_price = order.sl + self._stop_slip(tick.ts)
                return self._fill_exit(order, sl_price, tick.ts, "sl_exit")
            if tick.ask <= order.tp:
                return self._fill_exit(order, order.tp, tick.ts, "tp_exit")
        return None

    def _try_exit_bar(self, order: Order, bar: Bar) -> Fill | None:
        if order.side == "buy":
            gapped = bar.o <= order.sl
            sl_touched = bar.l <= order.sl
            tp_touched = bar.h >= order.tp
        else:
            gapped = bar.o >= order.sl
            sl_touched = bar.h >= order.sl
            tp_touched = bar.l <= order.tp

        if gapped:
            slip = self._stop_slip(bar.close_ts)
            price = bar.o - slip if order.side == "buy" else bar.o + slip
            return self._fill_exit(order, price, bar.close_ts, "gap_through_sl_exit")
        if sl_touched:  # includes the SL-First fallback when both SL and TP are touched
            slip = self._stop_slip(bar.close_ts)
            price = order.sl - slip if order.side == "buy" else order.sl + slip
            return self._fill_exit(order, price, bar.close_ts, "sl_exit")
        if tp_touched:
            return self._fill_exit(order, order.tp, bar.close_ts, "tp_exit")
        return None

    def _fill_exit(
        self,
        order: Order,
        price: float,
        ts: datetime,
        kind: Literal["sl_exit", "tp_exit", "gap_through_sl_exit"],
    ) -> Fill:
        self._open.discard(order.order_id)
        return Fill(order_id=order.order_id, ts=ts, price=price, kind=kind)
