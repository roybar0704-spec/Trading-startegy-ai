"""M4 Entry Model.

Touch at gap.top + a 1M rejection candle closing in the trade's direction -> Market
at the next bar's open (SPEC S8).

"Rejection candle" is under-specified beyond "closes in the direction" (trigger_spec
S2.4) -- no zone/wick condition is stated for it (unlike R's three explicit conditions),
so this is a direct transcription of the only stated criterion, not a guessed
interpretation of a genuine fork. "Market at the next bar's open" needs no special
FillSimulator handling: the intent is placed the moment the rejection candle closes, and
FillSimulator's normal Market-order semantics (fills on the very next tick seen) already
land at effectively the next bar's open.

Known scope limitation (KI-011): if two+ watched Setups reject on the exact same 1M bar,
only the first (dict iteration order) fires this call -- the Protocol allows returning at
most one OrderIntent per ``on_bar_close_1m`` call. Extremely rare (needs two Setups from
different 4H zones simultaneously ARMED and rejecting on the identical minute) and not
worth a multi-return signature change for.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from src.core.types import ArmId, Bar, OrderIntent, Setup, SetupEvent
from src.entry.sl_geometry import gap_reference_price
from src.store.state_store import MarketContext


@dataclass
class M4EntryModel:
    """Watches ARMED Setups for a rejection candle, then fires Market at the next open."""

    get_setup: Callable[[str], Setup]
    id: str = "M4"
    _watching: dict[str, Setup] = field(default_factory=dict, init=False)

    def on_event(self, ev: SetupEvent, ctx: MarketContext) -> OrderIntent | None:
        """Start watching on Armed; stop watching on any terminal/post-arm-cancel event."""
        if ev.kind == "armed" and not ev.post_arm:
            self._watching[ev.setup_id] = self.get_setup(ev.setup_id)
        else:
            self._watching.pop(ev.setup_id, None)
        return None

    def on_bar_close_1m(self, bar: Bar, ctx: MarketContext) -> OrderIntent | None:
        """Check every watched Setup against this bar; fire on the first qualifying rejection."""
        for setup_id, setup in list(self._watching.items()):
            rejects = bar.c > bar.o if setup.direction == "long" else bar.c < bar.o
            if rejects:
                del self._watching[setup_id]
                return OrderIntent(
                    setup_id=setup_id,
                    arm=ArmId(entry="M4", sl_anchor="R_body"),
                    side=setup.direction,
                    otype="market",
                    price=gap_reference_price(setup),
                    sl=0.0,
                    tp=0.0,
                    valid_until=bar.close_ts,
                )
        return None
