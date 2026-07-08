"""AT-0.3 Gap detection: artificial 7-minute weekday hole -> flagged; weekend gap -> not flagged."""

from datetime import UTC, datetime, timedelta

import polars as pl

from src.data.validator import Validator


def _ticks_df(timestamps: list[datetime]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": timestamps,
            "bid": [2000.0] * len(timestamps),
            "ask": [2000.3] * len(timestamps),
        },
        schema={"ts": pl.Datetime("us", "UTC"), "bid": pl.Float64, "ask": pl.Float64},
    )


def test_at_0_3_weekday_gap_is_flagged():
    # Wednesday 2024-03-06, one-minute ticks with an artificial 7-minute hole at 10:05.
    base = datetime(2024, 3, 6, 10, 0, tzinfo=UTC)
    timestamps = [base + timedelta(minutes=i) for i in range(5)]
    timestamps += [base + timedelta(minutes=5 + 7 + i) for i in range(5)]  # 7-minute hole
    df = _ticks_df(timestamps)

    report = Validator(gap_threshold=timedelta(minutes=5)).validate(df, "XAUUSD")

    assert len(report.flagged_gaps) == 1
    assert report.flagged_gaps[0].duration >= timedelta(minutes=7)
    assert report.weekend_gaps == []


def test_at_0_3_weekend_gap_is_not_flagged():
    # Friday 2024-03-08 21:00 UTC close through Sunday 2024-03-10 21:00 UTC open.
    friday_close = datetime(2024, 3, 8, 20, 55, tzinfo=UTC)
    sunday_open = datetime(2024, 3, 10, 21, 5, tzinfo=UTC)
    timestamps = [friday_close - timedelta(minutes=i) for i in range(5, 0, -1)]
    timestamps += [sunday_open + timedelta(minutes=i) for i in range(5)]
    df = _ticks_df(timestamps)

    report = Validator(gap_threshold=timedelta(minutes=5)).validate(df, "XAUUSD")

    assert report.flagged_gaps == []
    assert len(report.weekend_gaps) == 1
