"""Physical hold-out isolation (docs/SPEC_V1_FROZEN.md §13, RA-06).

The hold-out range (last 6 months by default) is *moved*, not copied, out of
the main tick store into a physically separate root. A normal loader
therefore cannot see it by accident; ``HoldoutGuard`` is the only way back
in, and every unlocked access is logged append-only — the Phase 5
Experiment Tracker will later consume this same log.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from src.data.tick_store import TickParquetStore, months_between


class HoldoutAccessDenied(RuntimeError):
    """Raised when a range overlapping the hold-out is loaded without holdout_unlock=True."""


@dataclass(frozen=True)
class HoldoutRange:
    """The [start, end) hold-out window, physically isolated."""

    start: datetime
    end: datetime

    def overlaps(self, start: datetime, end: datetime) -> bool:
        """True if [start, end) intersects this hold-out range."""
        return start < self.end and end > self.start


def compute_holdout_range(
    data_start: datetime, data_end: datetime, last_months: int = 6
) -> HoldoutRange:
    """The hold-out is the last ``last_months`` calendar months of [data_start, data_end]."""
    months = months_between(data_start, data_end)
    if len(months) < last_months:
        raise ValueError(
            f"data range only has {len(months)} months, cannot carve out a "
            f"{last_months}-month hold-out"
        )
    holdout_months = months[-last_months:]
    hy, hm = holdout_months[0]
    holdout_start = datetime(hy, hm, 1, tzinfo=UTC)
    return HoldoutRange(start=holdout_start, end=data_end)


def separate_holdout(
    store: TickParquetStore, holdout_root: Path, symbol: str, holdout_range: HoldoutRange
) -> list[Path]:
    """Move every monthly Parquet file overlapping ``holdout_range`` into ``holdout_root``.

    Returns the list of destination paths. Idempotent: months already moved
    (source missing, destination present) are skipped rather than erroring.
    """
    moved: list[Path] = []
    for year, month in months_between(holdout_range.start, holdout_range.end):
        src = store.month_path(symbol, year, month)
        src_hash = src.with_suffix(".parquet.sha256")
        if not src.exists():
            continue
        dst = holdout_root / symbol / f"{year:04d}" / f"{month:02d}.parquet"
        dst_hash = dst.with_suffix(".parquet.sha256")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.replace(dst)
        if src_hash.exists():
            src_hash.replace(dst_hash)
        moved.append(dst)
    return moved


class HoldoutGuard:
    """Gate in front of the physically separated hold-out store."""

    def __init__(self, holdout_root: Path, usage_log_path: Path) -> None:
        """Create a guard reading from ``holdout_root`` and logging to ``usage_log_path``."""
        self.store = TickParquetStore(holdout_root)
        self.usage_log_path = usage_log_path

    def load(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        holdout_range: HoldoutRange,
        holdout_unlock: bool = False,
        reason: str = "",
    ) -> pl.DataFrame:
        """Load ticks overlapping the hold-out; refuses unless ``holdout_unlock=True``.

        Raises:
            HoldoutAccessDenied: if [start, end) overlaps the hold-out and
                ``holdout_unlock`` is False.
        """
        if not holdout_range.overlaps(start, end):
            raise ValueError("[start, end) does not overlap the hold-out range at all")
        if not holdout_unlock:
            raise HoldoutAccessDenied(
                f"refusing to load hold-out range {holdout_range.start}..{holdout_range.end} "
                "without holdout_unlock=True"
            )
        self._log_usage(symbol, start, end, reason)
        frames = [
            self.store.read_month(symbol, year, month) for year, month in months_between(start, end)
        ]
        return pl.concat(frames).sort("ts").filter((pl.col("ts") >= start) & (pl.col("ts") < end))

    def _log_usage(self, symbol: str, start: datetime, end: datetime, reason: str) -> None:
        self.usage_log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "accessed_at": datetime.now(UTC).isoformat(),
            "symbol": symbol,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "reason": reason,
        }
        with self.usage_log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
