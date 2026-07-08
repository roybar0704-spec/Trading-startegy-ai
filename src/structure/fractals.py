"""Fractal (Swing) detection: 3-bar pattern, confirmed at the 3rd bar's close.

docs/SPEC_V1_FROZEN.md §2: "Swing: Fractal 3 נרות; מאושר רק בסגירת הנר השלישי."
The swing point is the *middle* bar of a 3-bar window; it becomes a
confirmed Swing only once the 3rd bar closes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.core.rolling import ThreeBarWindowDetector
from src.core.types import Bar, Swing


@dataclass
class FractalDetector(ThreeBarWindowDetector):
    """Stateful, one instance per TF. Feed bars in order via ``on_bar_close``."""

    def on_bar_close(self, bar: Bar) -> list[Swing]:
        """Feed one closed bar; returns newly confirmed Swings (0, 1, or 2)."""
        window = self._push(bar)
        if window is None:
            return []

        left, mid, right = window
        confirmed: list[Swing] = []
        if mid.h > left.h and mid.h > right.h:
            confirmed.append(self._make_swing("H", mid, right))
        if mid.l < left.l and mid.l < right.l:
            confirmed.append(self._make_swing("L", mid, right))
        return confirmed

    def _make_swing(self, kind: Literal["H", "L"], mid_bar: Bar, confirm_bar: Bar) -> Swing:
        self._seq += 1
        price = mid_bar.h if kind == "H" else mid_bar.l
        return Swing(
            id=f"SW-{self.tf.value}-{kind}-{self._seq}",
            tf=self.tf,
            kind=kind,
            price=price,
            created_at=mid_bar.close_ts,
            confirmed_at=confirm_bar.close_ts,
            taken_at=None,
        )
