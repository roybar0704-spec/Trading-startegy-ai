"""Per-TF FVG Engine: composes detection + Displacement/BOS ranking + live mitigation.

``step_bar_close`` does the real work and returns the newly formed FVG (with
its level/displacement/bos_link already resolved), if any. ``on_bar_close``/
``on_price`` are the docs/INTERFACES.md ``FVGEngine`` Protocol methods
(``-> None``) for future Orchestrator wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.core.types import FVG, TF, Bar
from src.displacement.model import DisplacementModel
from src.fvg.detector import FVGDetector
from src.fvg.mitigation import MitigationTracker
from src.fvg.ranking import with_rank
from src.store.state_store import StateStore

_HISTORY_CAP = 64


@dataclass
class FVGEngine:
    """One instance per TF."""

    tf: TF
    displacement_model: DisplacementModel
    displacement_params: dict
    _detector: FVGDetector = field(init=False)
    _bar_history: list[Bar] = field(default_factory=list, init=False)
    _mitigation: MitigationTracker = field(default_factory=MitigationTracker, init=False)

    def __post_init__(self) -> None:
        """Build the sub-detector for this TF."""
        self._detector = FVGDetector(self.tf)

    def step_bar_close(self, bar: Bar, store: StateStore) -> FVG | None:
        """Process one closed bar; returns the newly ranked FVG, if one formed."""
        self._bar_history.append(bar)
        if len(self._bar_history) > _HISTORY_CAP:
            self._bar_history.pop(0)

        raw = self._detector.on_bar_close(bar)
        if raw is None:
            return None

        # The 3-bar window is (c1, c2, c3); c3 is the bar just appended, c2 is the displacement
        # candle one bar before it.
        c2_index = len(self._bar_history) - 2
        c2 = self._bar_history[c2_index]
        window = self._bar_history[: c2_index + 1]
        displacement = self.displacement_model.evaluate(window, self.displacement_params)
        bos_link = store.bos_at(self.tf, c2.close_ts)

        fvg = with_rank(raw, displacement=displacement, bos_link=bos_link)
        store.put(fvg)
        return fvg

    def on_bar_close(self, bar: Bar, store: StateStore) -> None:
        """docs/INTERFACES.md FVGEngine Protocol method."""
        self.step_bar_close(bar, store)

    def on_price(self, ts: datetime, mid: float, store: StateStore) -> None:
        """docs/INTERFACES.md FVGEngine Protocol method: live mitigation."""
        self._mitigation.on_price(ts, mid, store)
