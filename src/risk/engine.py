"""Risk Engine (docs/SPEC_V1_FROZEN.md §9/§10, T2.3): geometry, min-stop, sizing, quota.

One instance per arm/portfolio (INTERFACES.md comment on RiskEngine).
Checks run in this order (D-047 / user-approved): geometry first (a
fundamentally malformed setup shape), then quota (resource availability)
-- this only affects which rejection reason gets recorded on the rare
simultaneous failure, never the trading outcome itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from zoneinfo import ZoneInfo

from src.core.types import Order, OrderIntent, Rejection
from src.risk.portfolio import Portfolio
from src.risk.sizing import size_units
from src.store.state_store import MarketContext

NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class RiskEngineParams:
    """Injected, never hardcoded (same discipline as D-043/KI-004).

    ``sizing_pct`` is the FROZEN rules_v1.yaml risk.sizing_pct;
    ``min_stop_k_spread`` is RA-16 (config/parameters.yaml).
    """

    sizing_pct: float
    min_stop_k_spread: float


@dataclass
class RiskEngine:
    """Approves or rejects OrderIntents for exactly one Portfolio (arm)."""

    portfolio: Portfolio
    params: RiskEngineParams
    _order_seq: count = field(default_factory=lambda: count(1), init=False)

    def approve(self, intent: OrderIntent, ctx: MarketContext) -> Order | Rejection:
        """Geometry -> quota -> sizing, in that order (D-047)."""
        if intent.price is None:
            raise ValueError(
                f"OrderIntent.price must always be populated (Reference Entry Price, "
                f"D-045); got None for setup_id={intent.setup_id!r} -- this is an "
                f"EntryModel contract violation, not a legitimate rejection."
            )

        stop_distance = (
            intent.price - intent.sl if intent.side == "long" else intent.sl - intent.price
        )
        hour_et = ctx.now.astimezone(NY).hour
        min_stop_distance = self.params.min_stop_k_spread * ctx.median_spread(hour_et)
        if stop_distance < min_stop_distance:
            return Rejection(setup_id=intent.setup_id, reason="invalid_geometry")

        ny_date = ctx.now.astimezone(NY).date()
        if self.portfolio.quota_remaining(ny_date) <= 0:
            return Rejection(setup_id=intent.setup_id, reason="blocked_quota")

        units = size_units(self.portfolio.realized_equity, self.params.sizing_pct, stop_distance)

        return Order(
            order_id=f"ORD-{self.portfolio.portfolio_id}-{next(self._order_seq)}",
            setup_id=intent.setup_id,
            portfolio_id=self.portfolio.portfolio_id,
            otype=intent.otype,
            side="buy" if intent.side == "long" else "sell",
            price=intent.price if intent.otype == "limit" else None,
            sl=intent.sl,
            tp=intent.tp,
            units=units,
            placed_at=ctx.now,
            valid_until=intent.valid_until,
        )
