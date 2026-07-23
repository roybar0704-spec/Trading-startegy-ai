"""AT-3.16 (Stage A / B-2 Commit 2, closes remaining part of KI-015): quota
interaction when more than 2 Setups reach ARMED on the same portfolio/day.

D-047/D-052 already define per-arm quota enforcement (RiskEngine.approve(),
checked at ARM time; Portfolio.record_fill() only decrements on an actual
entry fill, never on order placement/approval -- src/risk/portfolio.py).
AT-3.11 (tests/test_orchestrator.py) already proves quota isolation between
two different *portfolios* competing for the same single Setup. What has
never been exercised: a sequence of >2 distinct Setups (3 separate FVG
zones) all reaching ARMED on the *same* portfolio/day, where the third
arrives only after the first two have already consumed the day's 2-fill
quota through real fills -- not artificially seeded via record_fill().

Per WORK_ORDER_B2.md rule 2: this test is written first, with no prior
assumption about the outcome. If it fails, that is evidence to report and
await Roy's approval on a minimal fix -- not something to patch quietly.
"""

from datetime import timedelta
from pathlib import Path

from src.core.types import Tick
from src.journal.duckdb_writer import DuckDBJournal
from tests.fixtures.orchestrator import IN_WINDOW, make_arm, make_orchestrator, seed_fvg_and_bias
from tests.fixtures.setup_stream import m1, m5

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

# 3 well-separated, non-overlapping FVG price zones, engaged sequentially in time,
# price *descending* across zones (100 -> 50 -> 0 offset) to mimic one continuous
# downtrending price path. This isn't just cosmetic: src/fvg/mitigation.py's bull-FVG
# formula treats any price at or below a zone's bottom as 100% mitigated (correct
# physical semantics for a single monotonic price path -- "price already fell
# through and past this zone"). An *ascending* price order was tried first and
# failed for exactly this reason: zone 1's very first (low-price) bar retroactively
# 100%-mitigated zones 2 and 3 before they ever got a chance to engage (confirmed via
# direct inspection: mitigation_pct jumped to 100.0 for both on the first bar). With
# descending order, a not-yet-reached lower zone always has current price >= its top
# (penetration = 0, safe) until its own time slot arrives. Once a Setup reaches ARMED
# it becomes immune to further mitigation checks regardless (_check_guards returns
# immediately for state == "ARMED", setup_stream.py:331), so zone 1 also stays safe
# once armed, even as price later drops through its zone during zones 2/3.
ZONE_OFFSETS = (100.0, 50.0, 0.0)
ZONE_START_OFFSETS_MIN = (0, 30, 60)  # minutes from IN_WINDOW; each zone's own
# sequence spans ~23 minutes (see _zone_bars), so 30-minute spacing never overlaps.


def _zone_bars(t0, price_offset):
    """Same relative shape as test_orchestrator.py::_happy_path_bars (Engagement ->
    R -> S -> 3-candle iFVG -> Inversion), shifted in price (distinct FVG zone) and
    in time (distinct, non-overlapping window slot on the shared bar stream).
    """
    o = price_offset
    r_ts = t0 + timedelta(minutes=5)
    s_ts = t0 + timedelta(minutes=10)
    base = t0 + timedelta(minutes=20)
    bars_1m = [
        m1(t0, 100.5 + o, 100.6 + o, 99.5 + o, 100.2 + o),  # engagement
        m1(base, 97.5 + o, 97.6 + o, 97.0 + o, 97.3 + o),  # c1
        m1(base + timedelta(minutes=1), 97.2 + o, 97.3 + o, 96.8 + o, 97.0 + o),  # c2
        m1(base + timedelta(minutes=2), 96.4 + o, 96.5 + o, 96.2 + o, 96.3 + o),  # c3
        m1(base + timedelta(minutes=3), 96.8 + o, 97.3 + o, 96.7 + o, 97.2 + o),  # inversion
    ]
    bars_5m = [
        m5(r_ts, 99.0 + o, 99.8 + o, 97.0 + o, 99.5 + o),  # R, low = 97+o
        m5(s_ts, 98.0 + o, 98.5 + o, 96.0 + o, 97.5 + o),  # S, low = 96+o
    ]
    inversion_ts = bars_1m[-1].close_ts
    return bars_1m, bars_5m, inversion_ts


def _scenario(journal=None):
    """One portfolio (M2/S_wick); 3 separate Setups (distinct FVG zones) all reach
    ARMED on this same portfolio, same NY trading day. Only the first two zones get
    a fill tick -- quota decrements on fill (not approval), so by the time zone 3
    arms, the day's 2-fill quota is exhausted only if zones 1 and 2 actually filled.
    """
    arm = make_arm("M2", "S_wick")
    all_bars_1m, all_bars_5m, ticks = [], [], []
    for zone_idx, (price_offset, start_min) in enumerate(zip(ZONE_OFFSETS, ZONE_START_OFFSETS_MIN)):
        t0 = IN_WINDOW + timedelta(minutes=start_min)
        bars_1m, bars_5m, inversion_ts = _zone_bars(t0, price_offset)
        all_bars_1m.extend(bars_1m)
        all_bars_5m.extend(bars_5m)
        if zone_idx < 2:  # only zones 1 and 2 get a fill tick
            ticks.append(
                Tick(
                    ts=inversion_ts + timedelta(seconds=1),
                    bid=100.0 + price_offset, ask=100.05 + price_offset,
                )
            )

    orch = make_orchestrator(bars_1m=all_bars_1m, bars_5m=all_bars_5m, ticks=ticks, arms=[arm])
    orch.journal = journal
    for zone_idx, price_offset in enumerate(ZONE_OFFSETS):
        seed_fvg_and_bias(
            orch, "long", 100.0 + price_offset, 95.0 + price_offset,
            fvg_id=f"FVG-H4-{zone_idx + 1}",
        )
    return orch, arm


def test_third_setup_armed_on_same_portfolio_same_day_is_quota_blocked(tmp_path):
    db_path = tmp_path / "test.duckdb"
    journal = DuckDBJournal(db_path, SCHEMA_PATH)
    orch, arm = _scenario(journal=journal)

    result = orch.run()  # closes `journal`

    assert result.armed == 3  # all three distinct Setups reached ARMED
    assert result.orders_placed == 2  # zones 1 and 2 approved
    assert result.orders_rejected == 1  # zone 3 rejected -- quota exhausted by real fills

    ny_date = IN_WINDOW.date()
    assert arm.portfolio.fills_today(ny_date) == 2
    assert arm.portfolio.quota_remaining(ny_date) == 0

    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    rows = reader.query(
        "SELECT setup_id, portfolio_id, outcome FROM setup_arm_outcomes WHERE outcome = ?",
        ["blocked_quota"],
    )
    reader.close()
    # Exactly one blocked_quota row (zone 3) -- zones 1/2 filled but never closed
    # (no exit tick given), so they get no setup_arm_outcomes row at all (KI-019,
    # single-terminal-write only, D-060) -- not a gap this test needs to cover.
    assert len(rows) == 1
    [(blocked_setup_id, blocked_portfolio_id, outcome)] = rows
    assert outcome == "blocked_quota"
    assert blocked_portfolio_id == arm.portfolio.portfolio_id
