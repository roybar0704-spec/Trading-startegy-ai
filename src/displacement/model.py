"""DisplacementModel Protocol (docs/INTERFACES.md). Only D1 is implemented in v1.

docs/SPEC_V1_FROZEN.md §4: "Displacement: מודל D1 (BodyRatio) כברירת מחדל
v1; D1–D5 = רמות ניסוי (Experiment-level), לא פרמטר Walk-Forward." D2-D5 are
intentionally not implemented — only the Protocol they'll conform to.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.core.types import Bar


class DisplacementModel(Protocol):
    """A pluggable displacement test. ``id`` is the model name (e.g. "D1")."""

    id: str

    def evaluate(self, bars: Sequence[Bar], params: dict) -> bool:
        """True if the last bar in ``bars`` exhibits displacement."""
        ...
