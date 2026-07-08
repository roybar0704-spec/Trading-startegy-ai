"""Tick-stream validator: gaps, weekend closures, DST-week sanity, spike flags.

Anomalies are flagged, never silently dropped or fixed (CLAUDE.md: "אין
try/except pass על נתונים"). The FX/Gold market's weekly closure is
approximated as Friday 21:00 UTC through Sunday 21:00 UTC; gaps that fall
inside that window are expected and excluded from the flagged-gap list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import polars as pl

DEFAULT_GAP_THRESHOLD = timedelta(minutes=5)
DEFAULT_SPIKE_Z_THRESHOLD = 8.0
WEEKEND_CLOSE_WEEKDAY = 4  # Friday
WEEKEND_CLOSE_HOUR_UTC = 21
WEEKEND_OPEN_WEEKDAY = 6  # Sunday
WEEKEND_OPEN_HOUR_UTC = 21


def is_weekend_close_utc(ts: datetime) -> bool:
    """Approximate whether ``ts`` falls inside the weekly FX/Gold market closure."""
    wd, hour = ts.weekday(), ts.hour
    if wd == 5:  # Saturday
        return True
    if wd == WEEKEND_CLOSE_WEEKDAY and hour >= WEEKEND_CLOSE_HOUR_UTC:
        return True
    if wd == WEEKEND_OPEN_WEEKDAY and hour < WEEKEND_OPEN_HOUR_UTC:
        return True
    return False


def _weekend_window_around(ts: datetime) -> tuple[datetime, datetime]:
    """The Friday-21:00-UTC..Sunday-21:00-UTC closure window of ``ts``'s (Mon-Sun) week."""
    monday_midnight = ts - timedelta(
        days=ts.weekday(),
        hours=ts.hour,
        minutes=ts.minute,
        seconds=ts.second,
        microseconds=ts.microsecond,
    )
    friday_close = monday_midnight + timedelta(days=4, hours=WEEKEND_CLOSE_HOUR_UTC)
    sunday_open = monday_midnight + timedelta(days=6, hours=WEEKEND_OPEN_HOUR_UTC)
    return friday_close, sunday_open


def gap_overlaps_weekend(start: datetime, end: datetime) -> bool:
    """Whether the [start, end] gap interval overlaps the weekly market closure at all."""
    friday_close, sunday_open = _weekend_window_around(start)
    return start < sunday_open and end > friday_close


@dataclass(frozen=True)
class Gap:
    """A time gap between consecutive ticks exceeding the flag threshold."""

    start: datetime
    end: datetime
    duration: timedelta


@dataclass(frozen=True)
class Spike:
    """A single tick whose Mid move from the previous tick is a statistical outlier."""

    ts: datetime
    mid: float
    move: float


@dataclass
class ValidationReport:
    """Result of validating one tick range. Anomalies are flagged, not removed."""

    symbol: str
    tick_count: int
    flagged_gaps: list[Gap] = field(default_factory=list)
    weekend_gaps: list[Gap] = field(default_factory=list)
    spikes: list[Spike] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True if no non-weekend gaps or spikes were flagged."""
        return not self.flagged_gaps and not self.spikes


class Validator:
    """Flags gaps and spikes in a sorted tick DataFrame; never mutates or drops rows."""

    def __init__(
        self,
        gap_threshold: timedelta = DEFAULT_GAP_THRESHOLD,
        spike_z_threshold: float = DEFAULT_SPIKE_Z_THRESHOLD,
        spike_baseline_window: int = 500,
    ) -> None:
        """Configure flag thresholds. Defaults are Research Assumptions, not law."""
        self.gap_threshold = gap_threshold
        self.spike_z_threshold = spike_z_threshold
        self.spike_baseline_window = spike_baseline_window

    def validate(self, ticks: pl.DataFrame, symbol: str) -> ValidationReport:
        """Validate a sorted-by-ts tick DataFrame with columns ts/bid/ask."""
        if ticks.height == 0:
            return ValidationReport(symbol=symbol, tick_count=0)

        enriched = ticks.with_columns(
            [
                ((pl.col("bid") + pl.col("ask")) / 2.0).alias("mid"),
            ]
        ).with_columns(
            [
                pl.col("ts").diff().alias("dt"),
                pl.col("ts").shift(1).alias("prev_ts"),
            ]
        )
        dmid_expr = (pl.col("mid") - pl.col("mid").shift(1)).abs().alias("dmid")
        enriched = enriched.with_columns(dmid_expr)
        baseline_std_expr = pl.col("dmid").rolling_std(
            window_size=self.spike_baseline_window, min_samples=30
        ).alias("baseline_std")
        enriched = enriched.with_columns(baseline_std_expr)

        gap_rows = enriched.filter(pl.col("dt") >= self.gap_threshold).select(
            ["prev_ts", "ts", "dt"]
        )
        flagged_gaps: list[Gap] = []
        weekend_gaps: list[Gap] = []
        for row in gap_rows.iter_rows(named=True):
            gap = Gap(start=row["prev_ts"], end=row["ts"], duration=row["dt"])
            if gap_overlaps_weekend(row["prev_ts"], row["ts"]):
                weekend_gaps.append(gap)
            else:
                flagged_gaps.append(gap)

        spike_rows = enriched.filter(
            pl.col("baseline_std").is_not_null()
            & (pl.col("baseline_std") > 0)
            & (pl.col("dmid") > self.spike_z_threshold * pl.col("baseline_std"))
        ).select(["ts", "mid", "dmid"])
        spikes = [
            Spike(ts=row["ts"], mid=row["mid"], move=row["dmid"])
            for row in spike_rows.iter_rows(named=True)
        ]

        return ValidationReport(
            symbol=symbol,
            tick_count=ticks.height,
            flagged_gaps=flagged_gaps,
            weekend_gaps=weekend_gaps,
            spikes=spikes,
        )
