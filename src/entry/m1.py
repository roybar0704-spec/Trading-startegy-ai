"""M1 Entry Model: Limit at gap.top (SPEC S8), valid until end of the NY session window.

sl/tp are placeholders (D-052/Orchestrator applies the real per-arm values via
``sl_geometry.apply_sl_anchor`` before RiskEngine ever sees the intent) -- see that
module's docstring for why EntryModel can't compute them itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.core.types import ArmId, Bar, OrderIntent, Setup, SetupEvent
from src.entry.sl_geometry import gap_reference_price
from src.session.session_engine import SessionEngine
from src.store.state_store import MarketContext


@dataclass
class M1EntryModel:
    """Limit order at the iFVG's gap edge, live until the session window closes."""

    session: SessionEngine
    get_setup: Callable[[str], Setup]
    id: str = "M1"

    def on_event(self, ev: SetupEvent, ctx: MarketContext) -> OrderIntent | None:
        """Place a Limit at gap.top/bottom the moment the Setup arms."""
        if ev.kind != "armed" or ev.post_arm:
            return None
        setup = self.get_setup(ev.setup_id)
        _, window_end = self.session.window_bounds_utc(self.session.ny_date(ev.ts))
        return OrderIntent(
            setup_id=ev.setup_id,
            arm=ArmId(entry="M1", sl_anchor="R_body"),
            side=setup.direction,
            otype="limit",
            price=gap_reference_price(setup),
            sl=0.0,
            tp=0.0,
            valid_until=window_end,
        )

    def on_bar_close_1m(self, bar: Bar, ctx: MarketContext) -> OrderIntent | None:
        """M1 has no bar-driven logic -- its only trigger is the Armed event."""
        return None
