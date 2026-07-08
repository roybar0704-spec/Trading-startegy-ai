"""HTF Bias State Machine (docs/SPEC_V1_FROZEN.md §3), source_tf = 4H (config/rules_v1.yaml).

Bullish <- confirmed BOS up | Bearish <- confirmed BOS down | Neutral = opening
state only (never re-entered). Only actual state *transitions* are recorded —
a same-direction continuation BOS does not re-emit a redundant BiasEvent
(AT-1.3: "היסטוריית מצבים תואמת טבלת המעברים", history matches the
*transition* table).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from src.store.state_store import BiasEvent, BiasState


@dataclass
class BiasStateMachine:
    """Single-instance state machine for the Bias source TF (4H in v1)."""

    state: BiasState = field(default="neutral")

    def on_bos(
        self, direction: Literal["up", "down"], ts: datetime, swing_id: str
    ) -> BiasEvent | None:
        """Feed a confirmed BOS; returns a BiasEvent only if the state actually changed."""
        new_state: BiasState = "bullish" if direction == "up" else "bearish"
        if new_state == self.state:
            return None
        self.state = new_state
        return BiasEvent(
            ts=ts, state=new_state, trigger_bos={"swing_id": swing_id, "direction": direction}
        )
