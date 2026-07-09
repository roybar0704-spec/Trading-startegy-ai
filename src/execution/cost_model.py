"""Cost Model (docs/SPEC_V1_FROZEN.md §12).

Spread is real market data (handled by FillSimulator directly via
Bid/Ask); this covers Slippage and Commission only. Values come from
config/parameters.yaml ``costs`` (RA-10..RA-14) -- injected via
``CostModelParams``, never hardcoded, so a config change is always
visible to callers and never silently masked (same principle as
D-043/KI-004 for Displacement).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CostModelParams:
    """config/parameters.yaml ``costs`` section, verbatim (RA-10..RA-14)."""

    slippage_stop_usd: float
    news_slip_mult: float
    slippage_market_usd: float
    commission_per_unit: float


class StaticCostModel:
    """Fixed-value Cost Model.

    ``ts`` is accepted (per the Protocol) for future time-varying models
    but unused here -- v1's costs are constant.
    """

    def __init__(self, params: CostModelParams) -> None:
        """Build a cost model from ``params`` (load these from config/parameters.yaml)."""
        self.params = params

    def stop_slippage(self, ts: datetime, in_news: bool) -> float:
        """Slippage applied to Stop exits, ×news_slip_mult inside a news window."""
        mult = self.params.news_slip_mult if in_news else 1.0
        return self.params.slippage_stop_usd * mult

    def market_slippage(self, ts: datetime) -> float:
        """Slippage applied to Market entries."""
        return self.params.slippage_market_usd

    def commission(self, units: float) -> float:
        """Commission for a fill of ``units`` size."""
        return self.params.commission_per_unit * units
