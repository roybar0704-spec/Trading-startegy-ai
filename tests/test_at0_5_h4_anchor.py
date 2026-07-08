"""AT-0.5 4H anchor: bar boundaries are exactly 17/21/01/05/09/13 ET, in winter and summer."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.data.bar_builder import H4_ANCHOR_HOURS_ET, h4_boundaries_utc

NY = ZoneInfo("America/New_York")
YEAR_START = datetime(2024, 1, 1, tzinfo=UTC)
YEAR_END = datetime(2024, 12, 31, tzinfo=UTC)


def test_at_0_5_boundaries_are_exact_anchor_hours_year_round():
    boundaries = h4_boundaries_utc(YEAR_START, YEAR_END)

    for b in boundaries:
        local = b.astimezone(NY)
        assert local.hour in H4_ANCHOR_HOURS_ET
        assert local.minute == 0
        assert local.second == 0

    assert len(boundaries) == len(set(boundaries)), "no duplicate boundary instants"


def test_at_0_5_winter_and_summer_utc_offsets_differ_by_one_hour():
    boundaries = h4_boundaries_utc(YEAR_START, YEAR_END)

    def at_1700(month: int) -> datetime:
        return next(
            b for b in boundaries if b.astimezone(NY).month == month and b.astimezone(NY).hour == 17
        )

    assert at_1700(1).hour == 22  # January: EST = UTC-5
    assert at_1700(7).hour == 21  # July: EDT = UTC-4
