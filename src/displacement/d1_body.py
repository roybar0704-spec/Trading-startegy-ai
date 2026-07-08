"""D1 (BodyRatio) displacement model — the v1 default (RA-17).

body(candidate) >= ratio_min * mean(body(prior N bars)), N and ratio_min
from config/parameters.yaml (``displacement.d1``).
"""

from __future__ import annotations

from collections.abc import Sequence

from src.core.types import Bar

DEFAULT_BODY_VS_AVG_N = 10
DEFAULT_RATIO_MIN = 1.5


class D1BodyRatio:
    """Body-size-vs-trailing-average displacement test."""

    id = "D1"

    def evaluate(self, bars: Sequence[Bar], params: dict) -> bool:
        """``bars`` must end with the candidate bar and hold at least n+1 bars total."""
        n = params.get("body_vs_avg_n", DEFAULT_BODY_VS_AVG_N)
        ratio_min = params.get("ratio_min", DEFAULT_RATIO_MIN)
        if len(bars) < n + 1:
            return False
        window = bars[-(n + 1) :]
        prior, candidate = window[:-1], window[-1]
        avg_body = sum(abs(b.c - b.o) for b in prior) / len(prior)
        if avg_body <= 0:
            return False
        return abs(candidate.c - candidate.o) >= ratio_min * avg_body
