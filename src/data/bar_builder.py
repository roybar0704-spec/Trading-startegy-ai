"""Builds 1M/5M/4H Mid-price bars from a tick stream.

1M/5M bars are plain UTC-calendar-aligned buckets. 4H bars are anchored to
NY-Close (docs/SPEC_V1_FROZEN.md §1): boundaries at 17:00/21:00/01:00/05:00/
09:00/13:00 America/New_York, computed per-day in wall-clock ET and then
converted to UTC — so the UTC boundary offsets shift by exactly one hour
across a DST transition, while the ET wall-clock boundaries stay fixed.
None of the anchor hours (01/05/09/13/17/21) coincide with the US DST
transition hour (02:00 local), so every anchor instant is unambiguous.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

from src.core.types import TF, Bar

NY = ZoneInfo("America/New_York")
H4_ANCHOR_HOURS_ET = (1, 5, 9, 13, 17, 21)

_INTERVAL_BY_TF = {
    TF.M1: timedelta(minutes=1),
    TF.M5: timedelta(minutes=5),
}
_POLARS_EVERY_BY_TF = {
    TF.M1: "1m",
    TF.M5: "5m",
}


def h4_boundaries_utc(start: datetime, end: datetime) -> list[datetime]:
    """List UTC instants of every NY-Close 4H anchor covering [start, end]."""
    first_day = (start - timedelta(days=1)).astimezone(NY).date()
    last_day = (end + timedelta(days=1)).astimezone(NY).date()
    boundaries: set[datetime] = set()
    day = first_day
    while day <= last_day:
        for hour in H4_ANCHOR_HOURS_ET:
            local_dt = datetime(day.year, day.month, day.day, hour, 0, tzinfo=NY)
            boundaries.add(local_dt.astimezone(UTC))
        day += timedelta(days=1)
    return sorted(boundaries)


class BarBuilder:
    """Builds Bar lists (Mid OHLC + tick-count volume) from a sorted tick DataFrame."""

    def build(self, ticks: pl.DataFrame, tf: TF) -> list[Bar]:
        """Build bars for one timeframe. ``ticks`` must have columns ts/bid/ask."""
        if ticks.height == 0:
            return []
        mid_expr = ((pl.col("bid") + pl.col("ask")) / 2.0).alias("mid")
        with_mid = ticks.sort("ts").with_columns(mid_expr)
        if tf in _INTERVAL_BY_TF:
            return self._build_fixed_interval(with_mid, tf)
        if tf is TF.H4:
            return self._build_h4_ny_close(with_mid)
        raise ValueError(f"unsupported timeframe: {tf}")

    def _build_fixed_interval(self, with_mid: pl.DataFrame, tf: TF) -> list[Bar]:
        interval = _INTERVAL_BY_TF[tf]
        grouped = with_mid.group_by_dynamic(
            "ts", every=_POLARS_EVERY_BY_TF[tf], closed="left", label="left"
        ).agg(
            [
                pl.col("mid").first().alias("o"),
                pl.col("mid").max().alias("h"),
                pl.col("mid").min().alias("l"),
                pl.col("mid").last().alias("c"),
                pl.len().alias("tick_volume"),
            ]
        )
        return [
            Bar(
                tf=tf,
                open_ts=row["ts"],
                close_ts=row["ts"] + interval,
                o=row["o"],
                h=row["h"],
                l=row["l"],
                c=row["c"],
                tick_volume=row["tick_volume"],
            )
            for row in grouped.sort("ts").iter_rows(named=True)
        ]

    def _build_h4_ny_close(self, with_mid: pl.DataFrame) -> list[Bar]:
        ts_min, ts_max = with_mid["ts"].min(), with_mid["ts"].max()
        boundaries = h4_boundaries_utc(ts_min, ts_max)
        naive_boundaries = [b.replace(tzinfo=None) for b in boundaries]
        boundary_arr = np.array(naive_boundaries, dtype="datetime64[us]")
        tick_arr = with_mid["ts"].to_numpy().astype("datetime64[us]")
        bucket_idx = np.searchsorted(boundary_arr, tick_arr, side="right") - 1

        bucketed = with_mid.with_columns(pl.Series("bucket", bucket_idx))
        grouped = bucketed.group_by("bucket").agg(
            [
                pl.col("mid").first().alias("o"),
                pl.col("mid").max().alias("h"),
                pl.col("mid").min().alias("l"),
                pl.col("mid").last().alias("c"),
                pl.len().alias("tick_volume"),
            ]
        )

        bars = []
        for row in grouped.sort("bucket").iter_rows(named=True):
            idx = row["bucket"]
            if idx < 0 or idx >= len(boundaries) - 1:
                continue  # outside the computed boundary coverage window
            bars.append(
                Bar(
                    tf=TF.H4,
                    open_ts=boundaries[idx],
                    close_ts=boundaries[idx + 1],
                    o=row["o"],
                    h=row["h"],
                    l=row["l"],
                    c=row["c"],
                    tick_volume=row["tick_volume"],
                )
            )
        return bars
