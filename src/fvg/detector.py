"""4H FVG detection: 3-closed-candle pattern, no minimum size (SPEC §4).

Bullish FVG: ``c1.high < c3.low``, area ``[c1.high, c3.low]``.
Bearish FVG: ``c1.low > c3.high``, area ``[c3.high, c1.low]`` (mirrors the
1M iFVG candidate definition in trigger_spec_state_machine_v1_1.md §2.1).
Both ``created_at`` and ``confirmed_at`` are the 3rd candle's close: the
gap isn't knowable (and isn't a "pattern" at all) until all 3 bars closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.core.rolling import ThreeBarWindowDetector
from src.core.types import FVG, Bar


@dataclass
class FVGDetector(ThreeBarWindowDetector):
    """Stateful, one instance per TF. Feed bars in order via ``on_bar_close``."""

    def on_bar_close(self, bar: Bar) -> FVG | None:
        """Feed one closed bar; returns a newly detected raw (level=1) FVG, if any."""
        window = self._push(bar)
        if window is None:
            return None

        c1, _c2, c3 = window
        if c1.h < c3.l:
            return self._make(c1, c3, "bull", bottom=c1.h, top=c3.l)
        if c1.l > c3.h:
            return self._make(c1, c3, "bear", bottom=c3.h, top=c1.l)
        return None

    def _make(
        self, c1: Bar, c3: Bar, direction: Literal["bull", "bear"], bottom: float, top: float
    ) -> FVG:
        self._seq += 1
        return FVG(
            id=f"FVG-{self.tf.value}-{direction}-{self._seq}",
            tf=self.tf,
            direction=direction,
            top=top,
            bottom=bottom,
            level=1,
            created_at=c3.close_ts,
            confirmed_at=c3.close_ts,
            mitigation_pct=0.0,
            invalidated_at=None,
            bos_link=None,
            displacement=False,
        )
