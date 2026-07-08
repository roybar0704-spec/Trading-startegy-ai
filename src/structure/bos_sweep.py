"""BOS vs Sweep, measured against the last confirmed Swing of each kind.

docs/SPEC_V1_FROZEN.md §2: "BOS: סגירת נר מלאה מעבר ל-Swing מאושר. Wick בלבד
= Liquidity Sweep (Wick מעבר + סגירה חזרה). BOS נמדד מול ה-Fractal המאושר
האחרון." The reference Swing for each direction is the most recently
*confirmed* one of that kind. A **BOS** truly breaks it: the reference is
cleared until a new Swing of that kind confirms. A **Sweep** does not break
structure (only the wick traded through; price closed back) — the same
reference stays live and can still Sweep or eventually BOS on a later bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from src.core.types import TF, Bar, Swing


@dataclass(frozen=True)
class BOSSweepEvent:
    """A BOS or Sweep detected against a specific (previously confirmed) Swing."""

    kind: Literal["BOS", "SWEEP"]
    direction: Literal["up", "down"]
    swing: Swing
    ts: datetime


@dataclass
class BOSSweepDetector:
    """Stateful, one instance per TF. Tracks the current reference high/low Swing."""

    tf: TF
    _last_high: Swing | None = field(default=None, init=False)
    _last_low: Swing | None = field(default=None, init=False)

    def register_swing(self, swing: Swing) -> None:
        """Update the reference Swing for its kind (called after a new Swing confirms)."""
        if swing.kind == "H":
            self._last_high = swing
        else:
            self._last_low = swing

    def on_bar_close(self, bar: Bar) -> list[BOSSweepEvent]:
        """Evaluate one closed bar against the current reference high/low."""
        events: list[BOSSweepEvent] = []
        if self._last_high is not None and bar.h > self._last_high.price:
            kind: Literal["BOS", "SWEEP"] = "BOS" if bar.c > self._last_high.price else "SWEEP"
            events.append(
                BOSSweepEvent(kind=kind, direction="up", swing=self._last_high, ts=bar.close_ts)
            )
            if kind == "BOS":
                self._last_high = None
        if self._last_low is not None and bar.l < self._last_low.price:
            kind = "BOS" if bar.c < self._last_low.price else "SWEEP"
            events.append(
                BOSSweepEvent(kind=kind, direction="down", swing=self._last_low, ts=bar.close_ts)
            )
            if kind == "BOS":
                self._last_low = None
        return events
