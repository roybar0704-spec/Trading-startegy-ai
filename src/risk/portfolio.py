"""Per-arm Portfolio: realized equity + daily fill quota (SPEC §10, T2.4 isolation).

One ``Portfolio`` instance per arm (db/schema.sql ``portfolios`` row). A
``RiskEngine`` holds exactly one ``Portfolio`` and never sees another
arm's state -- isolation is by composition, not a shared/keyed structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.core.types import ArmId, PortfolioId

DAILY_FILL_QUOTA = 2  # SPEC §10: "2 מילויים ליום NY, לכל תיק בנפרד"


@dataclass
class Portfolio:
    """Isolated capital + quota tracking for one arm."""

    portfolio_id: PortfolioId
    arm: ArmId
    initial_equity: float
    realized_equity: float = field(init=False)
    _fills_by_day: dict[date, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        """Realized equity starts at the initial funding amount."""
        self.realized_equity = self.initial_equity

    def fills_today(self, ny_date: date) -> int:
        """Number of *filled* orders recorded so far for ``ny_date`` (RA-22/D-014)."""
        return self._fills_by_day.get(ny_date, 0)

    def quota_remaining(self, ny_date: date) -> int:
        """Remaining daily fill quota (AT-2.7); unfilled orders never consume it."""
        return DAILY_FILL_QUOTA - self.fills_today(ny_date)

    def record_fill(self, ny_date: date) -> None:
        """Count one more fill against ``ny_date``'s quota."""
        self._fills_by_day[ny_date] = self.fills_today(ny_date) + 1

    def apply_realized_pnl(self, pnl_usd: float) -> None:
        """Update realized equity when a trade closes (RA-22: realized balance, no open PnL)."""
        self.realized_equity += pnl_usd
