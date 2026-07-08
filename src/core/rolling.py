"""A small fixed-capacity rolling window of Bars, shared by 3-bar pattern detectors."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.types import TF, Bar


class BarWindow:
    """Keeps the last ``capacity`` bars, oldest dropped first."""

    def __init__(self, capacity: int) -> None:
        """Create an empty window holding at most ``capacity`` bars."""
        self.capacity = capacity
        self._bars: list[Bar] = []

    def push(self, bar: Bar) -> list[Bar]:
        """Append ``bar``, drop the oldest beyond capacity, and return the current window."""
        self._bars.append(bar)
        if len(self._bars) > self.capacity:
            self._bars.pop(0)
        return self._bars

    def __len__(self) -> int:
        """Number of bars currently held (up to ``capacity``)."""
        return len(self._bars)


@dataclass
class ThreeBarWindowDetector:
    """Shared scaffolding for detectors that key off a rolling 3-closed-bar window."""

    tf: TF
    _window: BarWindow = field(default_factory=lambda: BarWindow(3), init=False)
    _seq: int = field(default=0, init=False)

    def _push(self, bar: Bar) -> list[Bar] | None:
        """Push ``bar``; return the full 3-bar window once it fills, else None."""
        window = self._window.push(bar)
        return window if len(window) == 3 else None
