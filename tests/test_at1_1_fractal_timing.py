"""AT-1.1 Fractal timing: Swing confirmed_at = 3rd bar's close; as_of before that doesn't see it."""

from datetime import UTC, datetime, timedelta

from src.core.types import TF
from src.store.state_store import StateStore
from src.structure.fractals import FractalDetector
from tests.fixtures.bars import make_bars


def test_at_1_1_fractal_timing():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    interval = timedelta(hours=4)
    bars = make_bars(
        TF.H4,
        start,
        interval,
        [
            (100, 105, 99, 102),  # bar0
            (102, 110, 101, 108),  # bar1 - candidate swing high (h=110)
            (108, 106, 100, 103),  # bar2 - confirms it
        ],
    )
    store = StateStore()
    detector = FractalDetector(TF.H4)
    confirmed = []
    for bar in bars:
        new_swings = detector.on_bar_close(bar)
        for swing in new_swings:
            store.put(swing)
        confirmed.extend(new_swings)

    assert len(confirmed) == 1
    swing = confirmed[0]
    assert swing.kind == "H"
    assert swing.price == 110
    assert swing.confirmed_at == bars[2].close_ts

    before = store.as_of(bars[1].close_ts)
    assert swing not in before.confirmed_swings(TF.H4, since=start)

    after = store.as_of(bars[2].close_ts)
    assert swing in after.confirmed_swings(TF.H4, since=start)
