"""FVG ranking (SPEC §4): L1/L2/L3 classification + selection priority.

These are two independent concerns from the same two signals:
- **Level** (L1/L2/L3, stored on the FVG): L1 plain, L2 +Displacement,
  L3 +Displacement **and** BOS — requires both.
- **Priority** among several active FVGs when choosing one ("עדיפות בין
  כמה: BOS → Displacement → רגיל → הקרוב למחיר"): BOS alone outranks
  Displacement alone outranks plain, tie-broken by proximity to price —
  these are independent tiers, not the same as the L1-L3 level.
"""

from __future__ import annotations

from dataclasses import replace

from src.core.types import FVG


def level_for(displacement: bool, bos_link: str | None) -> int:
    """L3 requires both Displacement and BOS; L2 requires Displacement alone; else L1."""
    if displacement and bos_link:
        return 3
    if displacement:
        return 2
    return 1


def with_rank(fvg: FVG, displacement: bool, bos_link: str | None) -> FVG:
    """Return ``fvg`` updated with its displacement/bos_link/level fields set."""
    return replace(
        fvg, displacement=displacement, bos_link=bos_link, level=level_for(displacement, bos_link)
    )


def sort_by_priority(fvgs: list[FVG], current_price: float) -> list[FVG]:
    """BOS -> Displacement -> plain -> proximity to current price (closest first)."""

    def key(f: FVG) -> tuple[bool, bool, float]:
        midpoint = (f.top + f.bottom) / 2.0
        return (f.bos_link is None, not f.displacement, abs(midpoint - current_price))

    return sorted(fvgs, key=key)
