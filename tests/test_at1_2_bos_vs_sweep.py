"""AT-1.2 BOS vs Sweep: full close beyond -> BOS; wick beyond + close back -> Sweep, not BOS."""

from datetime import UTC, datetime, timedelta

from src.core.types import TF
from src.structure.bos_sweep import BOSSweepDetector
from src.structure.fractals import FractalDetector
from tests.fixtures.bars import make_bars

START = datetime(2024, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(hours=4)
SWING_HIGH_SETUP = [
    (100, 105, 99, 102),  # bar0
    (102, 110, 101, 108),  # bar1 - candidate swing high (h=110)
    (108, 106, 100, 103),  # bar2 - confirms it
]


def _run(extra_bar: tuple[float, float, float, float]):
    bars = make_bars(TF.H4, START, INTERVAL, [*SWING_HIGH_SETUP, extra_bar])
    fractals = FractalDetector(TF.H4)
    bos_sweep = BOSSweepDetector(TF.H4)
    all_events = []
    for bar in bars:
        all_events.extend(bos_sweep.on_bar_close(bar))
        for swing in fractals.on_bar_close(bar):
            bos_sweep.register_swing(swing)
    return all_events


def test_at_1_2_full_close_beyond_is_bos():
    events = _run((103, 115, 102, 112))  # high=115>110, close=112>110
    assert len(events) == 1
    assert events[0].kind == "BOS"
    assert events[0].direction == "up"


def test_at_1_2_wick_beyond_close_back_is_sweep_not_bos():
    events = _run((103, 115, 102, 107))  # high=115>110, close=107<110
    assert len(events) == 1
    assert events[0].kind == "SWEEP"
    assert events[0].direction == "up"
