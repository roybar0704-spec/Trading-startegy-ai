"""D1 (BodyRatio) displacement model — the v1 default (RA-17).

body(candidate) >= ratio_min * mean(body(prior N bars)), N and ratio_min
from config/parameters.yaml (``displacement.d1``). Both are **required**
in ``params`` (KI-004, D-043): a caller that forgets to wire them from
config must fail loudly, not silently fall back to a copy of the RA-17
defaults baked into this module — that could mask a Grid/RA change in
config/parameters.yaml that no test would ever catch.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.core.types import Bar

# The current config/parameters.yaml (RA-17) declared default -- for callers (tests,
# demos) that intentionally want it rather than a Grid-selected value. A real
# Orchestrator run (Phase 3+) must load this from config, never import this constant.
D1_DEFAULT_PARAMS = {"body_vs_avg_n": 10, "ratio_min": 1.5}


class D1BodyRatio:
    """Body-size-vs-trailing-average displacement test."""

    id = "D1"

    def evaluate(self, bars: Sequence[Bar], params: dict) -> bool:
        """``bars`` must end with the candidate bar and hold at least n+1 bars total.

        Raises:
            KeyError: if ``params`` is missing "body_vs_avg_n" or "ratio_min" -- these
                must come from config/parameters.yaml, never a silent default.
        """
        try:
            n = params["body_vs_avg_n"]
            ratio_min = params["ratio_min"]
        except KeyError as exc:
            raise KeyError(
                "D1BodyRatio.evaluate requires 'body_vs_avg_n' and 'ratio_min' in params "
                f"(config/parameters.yaml displacement.d1); missing {exc}"
            ) from exc
        if len(bars) < n + 1:
            return False
        window = bars[-(n + 1) :]
        prior, candidate = window[:-1], window[-1]
        avg_body = sum(abs(b.c - b.o) for b in prior) / len(prior)
        if avg_body <= 0:
            return False
        return abs(candidate.c - candidate.o) >= ratio_min * avg_body
