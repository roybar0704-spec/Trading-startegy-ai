"""Monthly Parquet tick store with a content-hash ``data_version``.

Each calendar month of ticks for a symbol is written once to a canonical
Parquet path. Writes are immutable: re-writing the same month is a no-op if
the new content is byte-identical, and a hard error if it differs (that
would mean the upstream source or decode logic changed silently, which must
never happen for an already-published month).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl


class TickStoreConflictError(RuntimeError):
    """Raised when re-writing a month would silently change already-published data."""


@dataclass(frozen=True)
class MonthlyTickFile:
    """A written monthly tick Parquet file and its content hash."""

    path: Path
    data_version: str
    row_count: int


class TickParquetStore:
    """Writes/reads monthly tick Parquet files under ``root``."""

    def __init__(self, root: Path) -> None:
        """Create a store rooted at ``root`` (e.g. ``data/ticks``)."""
        self.root = Path(root)

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
        """Read one month of ticks back from Parquet."""
        return pl.read_parquet(self.month_path(symbol, year, month))

    def data_version(self, symbol: str, months: list[tuple[int, int]]) -> str:
        """Combine per-month content hashes into one version string for a range."""
        hashes = []
        for year, month in sorted(months):
            hash_path = self.month_path(symbol, year, month).with_suffix(".parquet.sha256")
            hashes.append(hash_path.read_text().strip())
        return hashlib.sha256((symbol + "".join(hashes)).encode()).hexdigest()


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
