"""Live FVG Mitigation on Mid, at 1M/Tick resolution (SPEC §4).

A bullish FVG is a demand zone below price at creation; price mitigates it
by falling back down into ``[bottom, top]`` from above. A bearish FVG is a
supply zone above price at creation; price mitigates it by rising up into
``[bottom, top]`` from below. ``mitigation_pct`` is monotonic (a retrace
that partially fills and then leaves never decreases the recorded
percentage) and is capped at 100%, at which point the FVG is invalidated.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from src.core.types import FVG
from src.store.state_store import StateStore


def mitigation_pct(fvg: FVG, mid: float) -> float:
    """The mitigation percentage ``mid`` implies for ``fvg``, floored at its current value."""
    span = fvg.top - fvg.bottom
    if span <= 0:
        return 100.0
    if fvg.direction == "bull":
        if mid >= fvg.top:
            penetration = 0.0
        else:
            penetration = fvg.top - max(mid, fvg.bottom)
    else:
        if mid <= fvg.bottom:
            penetration = 0.0
        else:
            penetration = min(mid, fvg.top) - fvg.bottom
    pct = penetration / span * 100.0
    return min(100.0, max(fvg.mitigation_pct, pct))


class MitigationTracker:
    """Updates mitigation_pct (and invalidated_at at 100%) for every active FVG on a price tick."""

    def on_price(self, ts: datetime, mid: float, store: StateStore) -> None:
        """Feed one Mid price observation at ``ts``."""
        for fvg in store.all_fvgs():
            if fvg.invalidated_at is not None or fvg.confirmed_at > ts:
                continue
            pct = mitigation_pct(fvg, mid)
            if pct <= fvg.mitigation_pct:
                continue
            store.put(replace(fvg, mitigation_pct=pct, invalidated_at=ts if pct >= 100.0 else None))
