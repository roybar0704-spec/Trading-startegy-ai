"""Unit coverage for T0.6: hourly spread report."""

from datetime import UTC, datetime

import polars as pl
import pytest

from src.data.spread_report import build_spread_report


def test_spread_report_basic():
    # 09:00 UTC == 04:00 ET in January (EST); pick a fixed spread to check the math.
    ts = [datetime(2024, 1, 10, 9, i, tzinfo=UTC) for i in range(5)]
    df = pl.DataFrame(
        {"ts": ts, "bid": [2000.0] * 5, "ask": [2000.20] * 5},
        schema={"ts": pl.Datetime("us", "UTC"), "bid": pl.Float64, "ask": pl.Float64},
    )

    report = build_spread_report(df, "XAUUSD")

    stats = report.by_hour[4]  # 09:00 UTC -> 04:00 ET
    assert stats.tick_count == 5
    assert stats.median_spread == pytest.approx(0.20)
    assert report.median_spread(4) == pytest.approx(0.20)
