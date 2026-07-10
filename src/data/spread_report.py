"""Per-ET-hour spread report: calibration input for RA-10 (slippage) and min_stop.

Spread is measured directly from real Bid/Ask ticks (docs/RESEARCH_ASSUMPTIONS_V1.md
notes this is a fact, not an assumption). This report is what a later calibration
step reads to propose updated RA-10/min_stop values — Phase 0 only produces the
measurement.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

import polars as pl

if TYPE_CHECKING:
    from src.core.types import Tick

_ET = ZoneInfo("America/New_York")


@runtime_checkable
class SpreadSource(Protocol):
    """Anything that can back ``MarketContext.median_spread`` (D-039/D-049).

    ``SpreadReport`` (below, T0.6) and ``ExpandingSpreadReport`` both satisfy this
    structurally — callers (``StateStore``, ``Orchestrator``) depend only on this,
    never on a concrete class.
    """

    def median_spread(self, hour_et: int) -> float:
        """Median spread (USD) for one ET hour; raises KeyError if unavailable."""


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


@dataclass
class ExpandingSpreadReport:
    """Point-in-time-correct median-spread tracker for live backtest decisions.

    D-049, closes KI-007. ``SpreadReport``/``build_spread_report`` above is a Phase 0
    *one-time, full-period*
    calibration report (T0.6) — it is what a researcher reads once to propose RA-10, and
    must never be queried for a live ``min_stop_distance`` decision inside a backtest,
    since its median already contains data from *after* any given decision timestamp.

    ``ExpandingSpreadReport`` is the opposite: it starts empty (or warm-started from
    strictly-prior ticks — see ``warm_start``) and only ever grows via ``update()``.
    ``median_spread(hour_et)`` at any point reflects exactly the ticks fed to it up to
    that point, in feed order — nothing later, ever. The Orchestrator feeds it every Tick
    at the moment that Tick is processed (Stage 1), before any Stage 2 decision for that
    same timestamp can query it, so the accumulated median is always "as of now".

    No Rolling (fixed trailing window) variant is implemented: the Expanding variant was
    chosen for v1 specifically because it needs no additional declared RA/parameter.
    """

    symbol: str
    _spreads_by_hour: dict[int, list[float]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def warm_start(cls, symbol: str, ticks: list[Tick]) -> ExpandingSpreadReport:
        """Pre-seed from a chronologically-prior tick stream.

        E.g. the 90-day Warm-Up window (SPEC S2/RA-18) — legitimate, not lookahead,
        since every one of these ticks is strictly earlier than any timestamp this
        tracker will later be queried for. This is how a real run avoids an
        empty/degenerate bucket on day 1.
        """
        report = cls(symbol=symbol)
        for tick in ticks:
            report.update(tick)
        return report

    def update(self, tick: Tick) -> None:
        """Record one more observed spread. Call this, and only this, to grow the tracker."""
        hour_et = tick.ts.astimezone(_ET).hour
        self._spreads_by_hour[hour_et].append(tick.ask - tick.bid)

    def median_spread(self, hour_et: int) -> float:
        """Median spread (USD) for ET hour, from ticks observed so far.

        Raises ``KeyError`` if this hour has no observations yet — an anomaly to
        surface (CLAUDE.md: no silent fallback on data gaps), not a bug to hide behind
        a default value that would itself be an unrecorded research assumption.
        """
        spreads = self._spreads_by_hour.get(hour_et)
        if not spreads:
            raise KeyError(
                f"ExpandingSpreadReport: no spread observations yet for ET hour {hour_et} "
                "(D-049 forbids falling back to a full-period or future-inclusive value)."
            )
        return statistics.median(spreads)
