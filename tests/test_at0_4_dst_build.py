"""AT-0.4 DST build: spring-forward + fall-back weeks -> 08:30 ET bar exists and is contiguous,
zero duplicate/missing bars around the transition.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from src.data.bar_builder import BarBuilder
from src.data.types import TF

NY = ZoneInfo("America/New_York")


def _continuous_ticks(start: datetime, end: datetime, step_seconds: int = 30) -> pl.DataFrame:
    n = int((end - start).total_seconds() // step_seconds)
    timestamps = [start + timedelta(seconds=step_seconds * i) for i in range(n)]
    return pl.DataFrame(
        {
            "ts": timestamps,
            "bid": [2000.0] * n,
            "ask": [2000.3] * n,
        },
        schema={"ts": pl.Datetime("us", "UTC"), "bid": pl.Float64, "ask": pl.Float64},
    )


SPRING_FORWARD_WEEK = (datetime(2024, 3, 7, tzinfo=UTC), datetime(2024, 3, 12, tzinfo=UTC))
FALL_BACK_WEEK = (datetime(2024, 10, 31, tzinfo=UTC), datetime(2024, 11, 5, tzinfo=UTC))


@pytest.mark.parametrize("range_start,range_end", [SPRING_FORWARD_WEEK, FALL_BACK_WEEK])
def test_at_0_4_dst_build(range_start, range_end):
    ticks = _continuous_ticks(range_start, range_end)
    bars = BarBuilder().build(ticks, TF.M5)

    open_ts_list = [b.open_ts for b in bars]
    no_dup_msg = "no duplicate 5M bars around the DST transition"
    assert len(open_ts_list) == len(set(open_ts_list)), no_dup_msg
    for prev, nxt in zip(open_ts_list, open_ts_list[1:], strict=False):
        assert nxt - prev == timedelta(minutes=5), "no missing 5M bars around the DST transition"

    day = range_start.astimezone(NY).date()
    last_day = range_end.astimezone(NY).date()
    while day < last_day:
        expected_open = datetime(day.year, day.month, day.day, 8, 30, tzinfo=NY).astimezone(UTC)
        if range_start <= expected_open < range_end - timedelta(minutes=5):
            matches = [b for b in bars if b.open_ts == expected_open]
            assert len(matches) == 1, f"expected one 08:30 ET bar on {day}, found {len(matches)}"
        day += timedelta(days=1)
