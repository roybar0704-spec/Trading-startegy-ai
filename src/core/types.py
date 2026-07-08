"""Core domain types shared by every layer (docs/INTERFACES.md "טיפוסי ליבה").

This module has zero dependencies on the rest of ``src`` — every layer
(data, store, structure, fvg, displacement, entry, risk, execution, ...) may
import from here without violating the layering contract, since nothing
here imports back. Only the types actually consumed so far are implemented;
``Setup``/``OrderIntent``/``ArmId`` are added here the same way once a
module needs them (D-038).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal


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


@dataclass(frozen=True)
class Swing:
    """A confirmed market-structure Swing (fractal high/low)."""

    id: str
    tf: TF
    kind: Literal["H", "L"]
    price: float
    created_at: datetime
    confirmed_at: datetime
    taken_at: datetime | None


@dataclass(frozen=True)
class FVG:
    """A Fair Value Gap: 3-bar imbalance, valid until 100% Mid mitigation."""

    id: str
    tf: TF
    direction: Literal["bull", "bear"]
    top: float
    bottom: float
    level: int  # 1..3
    created_at: datetime
    confirmed_at: datetime
    mitigation_pct: float
    invalidated_at: datetime | None
    bos_link: str | None
    displacement: bool
