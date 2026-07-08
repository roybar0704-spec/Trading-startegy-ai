"""AT-1.3 Bias transitions: mixed BOS sequence -> state history matches the transition table;
opening state is Neutral.
"""

from datetime import UTC, datetime, timedelta

from src.core.types import TF
from src.store.state_store import StateStore
from src.structure.engine import StructureEngine
from tests.fixtures.bars import make_bars

START = datetime(2024, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(hours=4)

# A mixed sequence: swing high -> BOS up (bullish), swing low -> BOS down (bearish, with an
# extra incidental low swing + a second down-BOS along the way that must NOT double-count as a
# transition), swing high -> BOS up again (bullish).
BARS = make_bars(
    TF.H4,
    START,
    INTERVAL,
    [
        (100, 105, 99, 102),  # 0
        (102, 110, 101, 108),  # 1 candidate H=110
        (108, 106, 100, 103),  # 2 confirms H=110
        (103, 115, 102, 112),  # 3 BOS up (close 112 > 110) -> bullish
        (112, 114, 108, 110),  # 4
        (110, 112, 90, 95),  # 5 BOS down against an incidental L (close 95 < 100) -> bearish
        (95, 100, 92, 98),  # 6 confirms L=90
        (98, 99, 80, 85),  # 7 continuation BOS down (close 85 < 90) -> still bearish, no re-emit
        (85, 95, 83, 90),  # 8
        (90, 105, 88, 100),  # 9 candidate H=105
        (100, 98, 90, 95),  # 10 confirms H=105
        (95, 112, 93, 108),  # 11 BOS up (close 108 > 105) -> bullish
    ],
)


def test_at_1_3_bias_transitions():
    store = StateStore()
    engine = StructureEngine(TF.H4, is_bias_source=True)

    assert store.as_of(START).bias() == "neutral"

    bos_kinds = []
    for bar in BARS:
        for event in engine.step(bar, store):
            bos_kinds.append(event.kind)

    assert bos_kinds == ["BOS", "BOS", "BOS", "BOS"]

    states = [e.state for e in store._bias_events]  # noqa: SLF001
    assert states == ["bullish", "bearish", "bullish"], (
        "history must match TRANSITIONS only: the 2nd down-BOS is a continuation, not a new one"
    )

    assert store.as_of(BARS[2].close_ts).bias() == "neutral"
    assert store.as_of(BARS[3].close_ts).bias() == "bullish"
    assert store.as_of(BARS[5].close_ts).bias() == "bearish"
    assert store.as_of(BARS[7].close_ts).bias() == "bearish"
    assert store.as_of(BARS[11].close_ts).bias() == "bullish"
