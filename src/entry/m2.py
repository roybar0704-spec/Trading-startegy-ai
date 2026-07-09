"""M2 Entry Model: Market at the Inversion candle's close (SPEC S8, D-045).

Reference Entry Price = the 1M Inversion bar's close (``SetupEvent.inversion_close``),
not gap.top/bottom -- this is the one entry model where the two differ.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.core.types import ArmId, Bar, OrderIntent, Setup, SetupEvent
from src.store.state_store import MarketContext


@dataclass
class M2EntryModel:
    """Immediate Market entry at the Inversion candle's own close price."""

    get_setup: Callable[[str], Setup]
    id: str = "M2"

    def on_event(self, ev: SetupEvent, ctx: MarketContext) -> OrderIntent | None:
        """Fire a Market order the instant the Setup arms."""
        if ev.kind != "armed" or ev.post_arm:
            return None
        setup = self.get_setup(ev.setup_id)
        if ev.inversion_close is None:
            raise ValueError(f"'armed' event for {ev.setup_id!r} missing inversion_close")
        return OrderIntent(
            setup_id=ev.setup_id,
            arm=ArmId(entry="M2", sl_anchor="R_body"),
            side=setup.direction,
            otype="market",
            price=ev.inversion_close,
            sl=0.0,
            tp=0.0,
            valid_until=ev.ts,
        )

    def on_bar_close_1m(self, bar: Bar, ctx: MarketContext) -> OrderIntent | None:
        """M2 has no bar-driven logic -- its only trigger is the Armed event."""
        return None
