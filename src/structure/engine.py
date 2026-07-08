"""Per-TF Structure Engine: composes Fractals + BOS/Sweep + (for the Bias source TF) Bias-SM.

``step`` does the real work and returns the BOS/Sweep events detected on this
bar close (used internally by the FVG Engine to link a new FVG to a
same-bar BOS). ``on_bar_close`` is the docs/INTERFACES.md
``StructureEngine`` Protocol method (``-> None``) for future Orchestrator
wiring (Phase 3) — engines communicate through the store, not return values.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.types import TF, Bar
from src.store.state_store import StateStore
from src.structure.bias import BiasStateMachine
from src.structure.bos_sweep import BOSSweepDetector, BOSSweepEvent
from src.structure.fractals import FractalDetector


@dataclass
class StructureEngine:
    """One instance per TF; pass ``is_bias_source=True`` for the 4H instance."""

    tf: TF
    is_bias_source: bool = False
    _fractals: FractalDetector = field(init=False)
    _bos_sweep: BOSSweepDetector = field(init=False)
    _bias_sm: BiasStateMachine = field(init=False)

    def __post_init__(self) -> None:
        """Build the sub-engines for this TF."""
        self._fractals = FractalDetector(self.tf)
        self._bos_sweep = BOSSweepDetector(self.tf)
        self._bias_sm = BiasStateMachine()

    def step(self, bar: Bar, store: StateStore) -> list[BOSSweepEvent]:
        """Process one closed bar; returns the BOS/Sweep events detected."""
        events = self._bos_sweep.on_bar_close(bar)
        for event in events:
            if event.kind == "BOS":
                store.invalidate(event.swing.id, event.ts)
                store.record_bos(self.tf, event.ts, event.swing.id)
                if self.is_bias_source:
                    bias_event = self._bias_sm.on_bos(event.direction, event.ts, event.swing.id)
                    if bias_event is not None:
                        store.put(bias_event)

        for swing in self._fractals.on_bar_close(bar):
            store.put(swing)
            self._bos_sweep.register_swing(swing)

        return events

    def on_bar_close(self, bar: Bar, store: StateStore) -> None:
        """docs/INTERFACES.md StructureEngine Protocol method."""
        self.step(bar, store)
