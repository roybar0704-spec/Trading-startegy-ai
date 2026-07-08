"""AT-1.6 Prefix-Consistency (mandatory in CI forever, docs/ARCHITECTURE.md "בדיקות-על"):
a full two-week fixture run vs. runs truncated at every bar boundary must agree exactly, up
to the truncation point.
"""

import random
from datetime import UTC, datetime, timedelta

from src.core.types import TF
from src.store.state_store import StateStore
from tests.fixtures.bars import make_bars
from tests.fixtures.pipeline import run_pipeline

START = datetime(2024, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(hours=4)
BARS_PER_DAY = 6
TWO_WEEKS = 14 * BARS_PER_DAY


def _generate_two_week_fixture(seed: int = 7):
    rng = random.Random(seed)
    price = 2000.0
    ohlc = []
    for _ in range(TWO_WEEKS):
        o = price
        c = o + rng.uniform(-3.0, 3.0)
        h = max(o, c) + rng.uniform(0.0, 1.5)
        low = min(o, c) - rng.uniform(0.0, 1.5)
        ohlc.append((o, h, low, c))
        price = c
    return make_bars(TF.H4, START, INTERVAL, ohlc)


def _snapshot(store: StateStore, ts: datetime) -> dict:
    ctx = store.as_of(ts)
    return {
        "bias": ctx.bias(),
        "swings": sorted(
            (s.id, s.kind, s.price, s.confirmed_at.isoformat(), str(s.taken_at))
            for s in ctx.confirmed_swings(TF.H4, since=START)
        ),
        "fvgs_bull": sorted(
            (f.id, f.top, f.bottom, f.level, f.mitigation_pct)
            for f in ctx.active_fvgs(TF.H4, "bull")
        ),
        "fvgs_bear": sorted(
            (f.id, f.top, f.bottom, f.level, f.mitigation_pct)
            for f in ctx.active_fvgs(TF.H4, "bear")
        ),
    }


def test_at_1_6_prefix_consistency():
    bars = _generate_two_week_fixture()
    full_store = run_pipeline(bars)

    # Truncate at every bar boundary once enough bars exist for the first fractal (3).
    for k in range(3, len(bars) + 1):
        truncated_store = run_pipeline(bars[:k])
        ts = bars[k - 1].close_ts

        full_snapshot = _snapshot(full_store, ts)
        truncated_snapshot = _snapshot(truncated_store, ts)

        assert full_snapshot == truncated_snapshot, (
            f"prefix inconsistency at bar {k} (ts={ts.isoformat()}): "
            f"full={full_snapshot} truncated={truncated_snapshot}"
        )
