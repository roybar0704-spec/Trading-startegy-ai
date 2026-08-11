"""Monthly Parquet tick store, fail-closed on the hold-out window (D-085).

Each calendar month of ticks for a symbol is written once to a canonical
Parquet path with a content-hash ``data_version``. Writes are immutable:
re-writing the same month is a no-op if the new content is byte-identical,
and a hard error if it differs (that would mean the upstream source or
decode logic changed silently, which must never happen for an
already-published month). See docs/SPEC_V1_FROZEN.md §13, RA-06 for the
hold-out itself.

``TickParquetStore`` is the single point every real-data caller reads
through -- ``holdout_range`` is therefore a mandatory constructor argument,
not an optional one with a "safe" default: there is no way to build a store
that is silently unaware of the hold-out. A caller that genuinely needs no
protection (synthetic/scratch data only, never ``data/ticks/``) must go
through ``unprotected()``, a differently-named, self-documenting opt-out
that requires a ``reason`` -- not a parameter that is easy to omit by
accident.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl


class TickStoreConflictError(RuntimeError):
    """Raised when re-writing a month would silently change already-published data."""


class HoldoutAccessDenied(RuntimeError):
    """Raised when a month overlapping the hold-out is read without holdout_unlock=True."""


@dataclass(frozen=True)
class HoldoutRange:
    """The [start, end) hold-out window.

    A degenerate range (``start >= end``, see ``none()``) never overlaps
    anything -- it is the building block behind ``TickParquetStore.unprotected()``.
    """

    start: datetime
    end: datetime

    def overlaps(self, start: datetime, end: datetime) -> bool:
        """True if [start, end) intersects this hold-out range."""
        if self.start >= self.end:
            return False
        return start < self.end and end > self.start

    @classmethod
    def none(cls) -> HoldoutRange:
        """A degenerate range that never overlaps anything."""
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        return cls(start=epoch, end=epoch)


@dataclass(frozen=True)
class MonthlyTickFile:
    """A written monthly tick Parquet file and its content hash."""

    path: Path
    data_version: str
    row_count: int


class TickParquetStore:
    """Writes/reads monthly tick Parquet files under ``root``.

    ``holdout_range`` is mandatory (D-085) -- every caller must explicitly
    state what the hold-out window is, even if that means calling
    ``unprotected()`` to declare "none, on purpose". ``read_month()`` refuses
    (``HoldoutAccessDenied``) any month overlapping ``holdout_range`` unless
    the store was built with ``holdout_unlock=True``, which itself requires a
    non-empty ``unlock_reason`` and ``usage_log_path`` -- every unlocked
    access is logged append-only.
    """

    def __init__(
        self,
        root: Path,
        *,
        holdout_range: HoldoutRange,
        holdout_unlock: bool = False,
        unlock_reason: str = "",
        usage_log_path: Path | None = None,
    ) -> None:
        """Create a store rooted at ``root`` (e.g. ``data/ticks``).

        Raises:
            ValueError: if ``holdout_unlock=True`` but ``unlock_reason`` or
                ``usage_log_path`` is missing -- unlocking must always be
                explicit and auditable, never silent.
        """
        if holdout_unlock and not unlock_reason.strip():
            raise ValueError("holdout_unlock=True requires a non-empty unlock_reason")
        if holdout_unlock and usage_log_path is None:
            raise ValueError("holdout_unlock=True requires an explicit usage_log_path")
        self.root = Path(root)
        self.holdout_range = holdout_range
        self.holdout_unlock = holdout_unlock
        self.unlock_reason = unlock_reason
        self.usage_log_path = usage_log_path

    @classmethod
    def unprotected(cls, root: Path, *, reason: str) -> TickParquetStore:
        """Build a store with hold-out enforcement fully disabled.

        For synthetic/scratch data only (benchmarks, unit tests) -- never for
        a store pointed at real production data (``data/ticks/``). ``reason``
        is mandatory so every opt-out is self-documenting and auditable via
        ``git grep -n "TickParquetStore.unprotected"``.

        Raises:
            ValueError: if ``reason`` is empty.
        """
        if not reason.strip():
            raise ValueError("unprotected() requires a non-empty reason")
        return cls(root, holdout_range=HoldoutRange.none())

    def month_path(self, symbol: str, year: int, month: int) -> Path:
        """Canonical Parquet path for one (symbol, year, month)."""
        return self.root / symbol / f"{year:04d}" / f"{month:02d}.parquet"

    def write_month(
        self, symbol: str, year: int, month: int, ticks: pl.DataFrame
    ) -> MonthlyTickFile:
        """Write one month of ticks (columns: ts, bid, ask), sorted by ts.

        Raises:
            TickStoreConflictError: if a file already exists for this month
                with different content than what would be written now.
        """
        ordered = ticks.sort("ts")
        path = self.month_path(symbol, year, month)
        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = path.with_suffix(".parquet.tmp")
        ordered.write_parquet(tmp_path, compression="zstd")
        new_bytes = tmp_path.read_bytes()
        new_hash = hashlib.sha256(new_bytes).hexdigest()

        hash_path = path.with_suffix(".parquet.sha256")
        if path.exists() and hash_path.exists():
            recorded = hash_path.read_text().strip()
            if recorded != new_hash:
                tmp_path.unlink()
                raise TickStoreConflictError(
                    f"{path} already exists with a different content hash "
                    f"(recorded={recorded}, new={new_hash}); monthly tick files are immutable"
                )
            tmp_path.unlink()
        else:
            tmp_path.replace(path)
            hash_path.write_text(new_hash)

        return MonthlyTickFile(path=path, data_version=new_hash, row_count=ordered.height)

    def read_month(self, symbol: str, year: int, month: int) -> pl.DataFrame:
        """Read one month of ticks back from Parquet.

        Raises:
            HoldoutAccessDenied: if this month overlaps ``holdout_range`` and
                the store was not built with ``holdout_unlock=True``.
        """
        self._check_holdout(symbol, year, month)
        return pl.read_parquet(self.month_path(symbol, year, month))

    def _check_holdout(self, symbol: str, year: int, month: int) -> None:
        month_start = datetime(year, month, 1, tzinfo=UTC)
        month_end = _next_month_start(month_start)
        if not self.holdout_range.overlaps(month_start, month_end):
            return
        if not self.holdout_unlock:
            raise HoldoutAccessDenied(
                f"refusing to read {symbol} {year:04d}-{month:02d}: overlaps hold-out range "
                f"{self.holdout_range.start.date()}..{self.holdout_range.end.date()} "
                "without holdout_unlock=True"
            )
        self._log_holdout_usage(symbol, year, month)

    def _log_holdout_usage(self, symbol: str, year: int, month: int) -> None:
        assert self.usage_log_path is not None  # enforced in __init__ when holdout_unlock=True
        self.usage_log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "accessed_at": datetime.now(UTC).isoformat(),
            "symbol": symbol,
            "year": year,
            "month": month,
            "reason": self.unlock_reason,
        }
        with self.usage_log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def data_version(self, symbol: str, months: list[tuple[int, int]]) -> str:
        """Combine per-month content hashes into one version string for a range."""
        hashes = []
        for year, month in sorted(months):
            hash_path = self.month_path(symbol, year, month).with_suffix(".parquet.sha256")
            hashes.append(hash_path.read_text().strip())
        return hashlib.sha256((symbol + "".join(hashes)).encode()).hexdigest()


def _next_month_start(month_start: datetime) -> datetime:
    if month_start.month == 12:
        return month_start.replace(year=month_start.year + 1, month=1)
    return month_start.replace(month=month_start.month + 1)


def months_between(start: datetime, end: datetime) -> list[tuple[int, int]]:
    """List (year, month) tuples covering [start, end], inclusive of both endpoints' months."""
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months
