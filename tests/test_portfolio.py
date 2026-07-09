"""Unit coverage for T2.4 Portfolio isolation.

``apply_realized_pnl`` is exercised here in isolation; nothing in Phase 2
calls it yet (found during Critical Review -- see docs/KNOWN_ISSUES.md
KI-006: it must be wired to the fill/exit flow in Phase 3, or realized
equity -- and therefore all Phase 4+ sizing -- silently never changes).
"""

from datetime import date

from src.core.types import ArmId
from src.risk.portfolio import DAILY_FILL_QUOTA, Portfolio

ARM = ArmId(entry="M2", sl_anchor="S_body")
DAY = date(2024, 1, 2)


def test_portfolio_starts_at_initial_equity():
    p = Portfolio(portfolio_id="P1", arm=ARM, initial_equity=10_000)
    assert p.realized_equity == 10_000


def test_apply_realized_pnl_updates_equity():
    p = Portfolio(portfolio_id="P1", arm=ARM, initial_equity=10_000)
    p.apply_realized_pnl(150.0)
    assert p.realized_equity == 10_150.0
    p.apply_realized_pnl(-40.0)
    assert p.realized_equity == 10_110.0


def test_quota_isolated_per_day():
    p = Portfolio(portfolio_id="P1", arm=ARM, initial_equity=10_000)
    assert p.quota_remaining(DAY) == DAILY_FILL_QUOTA
    p.record_fill(DAY)
    assert p.quota_remaining(DAY) == DAILY_FILL_QUOTA - 1
    other_day = date(2024, 1, 3)
    assert p.quota_remaining(other_day) == DAILY_FILL_QUOTA  # separate day, unaffected
