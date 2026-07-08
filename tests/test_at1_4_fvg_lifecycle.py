"""AT-1.4 FVG lifecycle: created only on 3 closed bars; mitigation_pct updates on price;
100% -> invalidated.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.types import TF
from src.fvg.detector import FVGDetector
from src.fvg.mitigation import MitigationTracker
from src.store.state_store import StateStore
from tests.fixtures.bars import make_bars

START = datetime(2024, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(hours=4)


def test_at_1_4_fvg_lifecycle():
    bars = make_bars(
        TF.H4,
        START,
        INTERVAL,
        [
            (95, 100, 90, 98),  # c1: high=100
            (98, 130, 97, 125),  # c2: displacement candle
            (125, 128, 110, 120),  # c3: low=110  -> bullish FVG [100, 110]
        ],
    )
    detector = FVGDetector(TF.H4)
    store = StateStore()

    for bar in bars[:2]:
        assert detector.on_bar_close(bar) is None  # not a pattern until the 3rd bar closes

    fvg = detector.on_bar_close(bars[2])
    assert fvg is not None
    assert fvg.direction == "bull"
    assert fvg.bottom == pytest.approx(100)
    assert fvg.top == pytest.approx(110)
    assert fvg.mitigation_pct == 0.0
    assert fvg.invalidated_at is None
    store.put(fvg)

    tracker = MitigationTracker()
    t0 = bars[2].close_ts

    tracker.on_price(t0 + timedelta(minutes=1), 115.0, store)  # above the zone -> no mitigation
    assert store.all_fvgs()[0].mitigation_pct == 0.0

    tracker.on_price(t0 + timedelta(minutes=2), 108.0, store)  # 20% into [100,110]
    assert store.all_fvgs()[0].mitigation_pct == pytest.approx(20.0)

    tracker.on_price(t0 + timedelta(minutes=3), 106.0, store)  # deeper: 40%
    assert store.all_fvgs()[0].mitigation_pct == pytest.approx(40.0)

    tracker.on_price(t0 + timedelta(minutes=4), 112.0, store)  # retreats -- monotonic, stays 40%
    assert store.all_fvgs()[0].mitigation_pct == pytest.approx(40.0)
    assert store.all_fvgs()[0].invalidated_at is None

    full_mitigation_ts = t0 + timedelta(minutes=5)
    tracker.on_price(full_mitigation_ts, 95.0, store)  # through the bottom -> 100%
    final = store.all_fvgs()[0]
    assert final.mitigation_pct == 100.0
    assert final.invalidated_at == full_mitigation_ts
