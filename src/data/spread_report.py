"""Per-ET-hour spread report: calibration input for RA-10 (slippage) and min_stop.

Spread is measured directly from real Bid/Ask ticks (docs/RESEARCH_ASSUMPTIONS_V1.md
notes this is a fact, not an assumption). This report is what a later calibration
step reads to propose updated RA-10/min_stop values — Phase 0 only produces the
measurement.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

_QUANTILES = (0.25, 0.50, 0.75, 0.95)


@dataclass(frozen=True)
class HourSpreadStats:
    """Spread distribution summary for one ET hour-of-day (0-23)."""

    hour_et: int
    tick_count: int
    mean_spread: float
    p25_spread: float
    median_spread: float
    p75_spread: float
    p95_spread: float


@dataclass(frozen=True)
class SpreadReport:
    """Full 24-hour (or fewer, if hours are missing from the sample) spread report."""

    symbol: str
    by_hour: dict[int, HourSpreadStats]

    def median_spread(self, hour_et: int) -> float:
        """Median spread for one ET hour; raises KeyError if that hour has no ticks."""
        return self.by_hour[hour_et].median_spread

    def to_markdown(self) -> str:
        """Render as a markdown table, sorted by hour."""
        lines = [
            "| hour_et | ticks | mean | p25 | median | p75 | p95 |",
            "|---|---|---|---|---|---|---|",
        ]
        for hour in sorted(self.by_hour):
            s = self.by_hour[hour]
            lines.append(
                f"| {hour:02d} | {s.tick_count} | {s.mean_spread:.4f} | {s.p25_spread:.4f} | "
                f"{s.median_spread:.4f} | {s.p75_spread:.4f} | {s.p95_spread:.4f} |"
            )
        return "\n".join(lines)


def build_spread_report(ticks: pl.DataFrame, symbol: str) -> SpreadReport:
    """Build an hourly (ET) spread report from a tick DataFrame (columns ts/bid/ask)."""
    enriched = ticks.with_columns(
        [
            (pl.col("ask") - pl.col("bid")).alias("spread"),
            pl.col("ts").dt.convert_time_zone("America/New_York").dt.hour().alias("hour_et"),
        ]
    )
    grouped = enriched.group_by("hour_et").agg(
        [
            pl.len().alias("tick_count"),
            pl.col("spread").mean().alias("mean_spread"),
            pl.col("spread").quantile(0.25).alias("p25_spread"),
            pl.col("spread").quantile(0.50).alias("median_spread"),
            pl.col("spread").quantile(0.75).alias("p75_spread"),
            pl.col("spread").quantile(0.95).alias("p95_spread"),
        ]
    )
    by_hour = {
        int(row["hour_et"]): HourSpreadStats(
            hour_et=int(row["hour_et"]),
            tick_count=row["tick_count"],
            mean_spread=row["mean_spread"],
            p25_spread=row["p25_spread"],
            median_spread=row["median_spread"],
            p75_spread=row["p75_spread"],
            p95_spread=row["p95_spread"],
        )
        for row in grouped.iter_rows(named=True)
    }
    return SpreadReport(symbol=symbol, by_hour=by_hour)
