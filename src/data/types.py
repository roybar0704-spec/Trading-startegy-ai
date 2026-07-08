"""Core price-series types shared by the data layer.

Mirrors docs/INTERFACES.md exactly; only the subset needed through Phase 0
(``TF``, ``Tick``, ``Bar``) is implemented here. Later phases add the
remaining core types (``Swing``, ``FVG``, ``Setup``, ...) when a module
actually needs them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TF(Enum):
    """Timeframe identifiers used throughout the platform."""

    M1 = "1M"
    M5 = "5M"
    H4 = "4H"


@dataclass(frozen=True)
class Tick:
    """A single Bid/Ask quote. ``ts`` is always UTC."""

    ts: datetime
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        """Mid price — the price used for all structure (Swings/BOS/FVG/...)."""
        return (self.bid + self.ask) / 2.0


@dataclass(frozen=True)
class Bar:
    """An OHLC bar built on Mid price, plus tick-count volume."""

    tf: TF
    open_ts: datetime
    close_ts: datetime
    o: float
    h: float
    l: float  # noqa: E741 - matches docs/INTERFACES.md field name
    c: float
    tick_volume: int
