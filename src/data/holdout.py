"""Physical hold-out isolation (docs/SPEC_V1_FROZEN.md §13, RA-06).

This module handles Track B: *physically moving* the hold-out range (last 6
months by default) out of the main tick store into a separate root, and
``HoldoutGuard`` as the gate back in once that separation has happened.

Track A (fail-closed enforcement on the main store, D-085) lives in
``src.data.tick_store`` -- ``HoldoutRange``/``HoldoutAccessDenied`` are
defined there (``TickParquetStore`` cannot depend on this module without a
cycle, since this module already depends on ``TickParquetStore``) and
re-exported here for backward compatibility.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from src.data.tick_store import (
    HoldoutAccessDenied,
    HoldoutRange,
    TickParquetStore,
    months_between,
)

__all__ = [
    "HoldoutAccessDenied",
    "HoldoutRange",
    "HoldoutGuard",
    "XAUUSD_HOLDOUT_RANGE",
    "compute_holdout_range",
    "separate_holdout",
]


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


# The hold-out window implied by config/run_default.yaml (period 2023-01-01..2025-12-31,
# holdout.last_months=6 -> 2025-07-01..2025-12-31). Scripts operating on the real XAUUSD
# dataset use this single, shared definition rather than each recomputing it ad hoc
# (D-085) -- config/run_default.yaml itself is not read here to keep this module
# config-agnostic; the two must be kept in sync by hand if run_default.yaml's period or
# holdout.last_months ever change (both are FROZEN-adjacent, RA-governed values).
XAUUSD_HOLDOUT_RANGE = compute_holdout_range(
    datetime(2023, 1, 1, tzinfo=UTC), datetime(2025, 12, 31, tzinfo=UTC), last_months=6
)


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
        # D-085: the store here reads from holdout_root itself, which IS the
        # separated hold-out data -- HoldoutGuard.load() below is the gate, so
        # the inner TickParquetStore's own (redundant) hold-out check is
        # explicitly disabled rather than asked to reason about a range that
        # doesn't apply to this root.
        self.store = TickParquetStore.unprotected(
            holdout_root, reason="HoldoutGuard is itself the gate; holdout_root is the "
            "already-separated hold-out data, not the main data/ticks/ store"
        )
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
