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

``execution_delay_ms`` (SPEC §12, D-050; user-approved, entry+exit
scope): 0ms default -- byte-identical to pre-delay behaviour (Regression
Gate). When >0 (robustness runs, 250/500ms), a fill trigger (entry
condition met, or SL/TP touched) is recorded but not executed; execution
happens on the first later tick at or after ``trigger_ts + delay``, using
that later tick's market data (so a delayed exit that lands inside a
news window pays the news slippage multiplier, per the trigger-time cost
model). Limit-entry and SL/TP prices stay anchored to ``order.price`` /
``order.sl`` / ``order.tp`` regardless of delay (D-018 invariant) -- delay
shifts *when* a fill happens and *which tick's cost inputs* apply, never
which price level it anchors to. Scoped to the tick path only: the 1M
SL-First/Gap-Through fallback (``on_bar_1m``) is a no-tick-data regime by
definition, and a sub-second delay has no observable effect at 1-minute
granularity.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

from src.core.types import Bar, Fill, Order, PortfolioId, Tick
from src.execution.cost_model import StaticCostModel

ExitKind = Literal["sl", "tp"]


class FillSimulator:
    """Tracks pending orders and open (filled, unexited) positions; emits Fills."""

    def __init__(
        self,
        cost_model: StaticCostModel,
        in_news_checker: Callable[[datetime], bool],
        execution_delay_ms: int = 0,
    ) -> None:
        """``in_news_checker(ts)`` must be supplied explicitly -- see module docstring."""
        self.cost_model = cost_model
        self.in_news_checker = in_news_checker
        self.execution_delay_ms = execution_delay_ms
        self._orders: dict[str, Order] = {}
        self._open: set[str] = set()
        self._pending_entries: dict[str, datetime] = {}
        self._pending_exits: dict[str, tuple[datetime, ExitKind]] = {}

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
        fills = self._resolve_pending(tick)
        for order in list(self._orders.values()):
            if order.status == "pending" and order.order_id not in self._pending_entries:
                if self._entry_condition_met(order, tick):
                    fill = self._arm_or_fill_entry(order, tick)
                    if fill is not None:
                        fills.append(fill)
            elif order.order_id in self._open and order.order_id not in self._pending_exits:
                kind = self._exit_condition_met(order, tick)
                if kind is not None:
                    fill = self._arm_or_fill_exit(order, kind, tick)
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

    def _resolve_pending(self, tick: Tick) -> list[Fill]:
        """Execute any armed entry/exit whose execution_delay_ms has elapsed."""
        fills: list[Fill] = []
        for order_id, eligible_at in list(self._pending_entries.items()):
            order = self._orders[order_id]
            if order.status != "pending":  # cancelled while armed
                del self._pending_entries[order_id]
                continue
            if tick.ts >= eligible_at:
                price, kind = self._entry_fill_price(order, tick)
                fills.append(self._fill_entry(order, price, tick.ts, kind))
                del self._pending_entries[order_id]
        for order_id, (eligible_at, exit_kind) in list(self._pending_exits.items()):
            if tick.ts >= eligible_at:
                order = self._orders[order_id]
                price = self._exit_fill_price(order, exit_kind, tick.ts)
                out_kind: Literal["sl_exit", "tp_exit"] = (
                    "sl_exit" if exit_kind == "sl" else "tp_exit"
                )
                fills.append(self._fill_exit(order, price, tick.ts, out_kind))
                del self._pending_exits[order_id]
        return fills

    def _arm_or_fill_entry(self, order: Order, tick: Tick) -> Fill | None:
        if self.execution_delay_ms == 0:
            price, kind = self._entry_fill_price(order, tick)
            return self._fill_entry(order, price, tick.ts, kind)
        self._pending_entries[order.order_id] = tick.ts + timedelta(
            milliseconds=self.execution_delay_ms
        )
        return None

    def _arm_or_fill_exit(self, order: Order, kind: ExitKind, tick: Tick) -> Fill | None:
        if self.execution_delay_ms == 0:
            price = self._exit_fill_price(order, kind, tick.ts)
            out_kind: Literal["sl_exit", "tp_exit"] = "sl_exit" if kind == "sl" else "tp_exit"
            return self._fill_exit(order, price, tick.ts, out_kind)
        eligible_at = tick.ts + timedelta(milliseconds=self.execution_delay_ms)
        self._pending_exits[order.order_id] = (eligible_at, kind)
        return None

    def _entry_condition_met(self, order: Order, tick: Tick) -> bool:
        if order.otype != "limit":
            return True  # market: always triggers on the first tick seen
        if order.side == "buy":
            return tick.ask <= order.price
        return tick.bid >= order.price

    def _entry_fill_price(
        self, order: Order, tick: Tick
    ) -> tuple[float, Literal["limit_entry", "market_entry"]]:
        if order.otype == "limit":
            return order.price, "limit_entry"
        slip = self.cost_model.market_slippage(tick.ts)
        price = tick.ask + slip if order.side == "buy" else tick.bid - slip
        return price, "market_entry"

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

    def _exit_condition_met(self, order: Order, tick: Tick) -> ExitKind | None:
        if order.side == "buy":  # long: exit = sell, checked vs Bid
            if tick.bid <= order.sl:
                return "sl"
            if tick.bid >= order.tp:
                return "tp"
        else:  # short: exit = buy, checked vs Ask
            if tick.ask >= order.sl:
                return "sl"
            if tick.ask <= order.tp:
                return "tp"
        return None

    def _exit_fill_price(self, order: Order, kind: ExitKind, ts: datetime) -> float:
        if kind == "tp":
            return order.tp
        slip = self._stop_slip(ts)
        return order.sl - slip if order.side == "buy" else order.sl + slip

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
