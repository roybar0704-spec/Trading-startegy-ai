"""Dukascopy tick downloader: bi5+LZMA fetch, decode, immutable caching.

Source format (per hour, per symbol): a ``.bi5`` file that is a raw LZMA
stream of fixed 20-byte big-endian records::

    time_ms  : uint32   milliseconds since the start of the file's hour
    ask_raw  : uint32   ask price, scaled by ``point_value``
    bid_raw  : uint32   bid price, scaled by ``point_value``
    ask_vol  : float32  ask volume (Dukascopy's own liquidity proxy)
    bid_vol  : float32  bid volume

Cached files are immutable: once a hour-file is written to disk with its
SHA-256 sidecar, it is never re-fetched or overwritten. A mismatch between
a cached file's bytes and its recorded hash is treated as a tampered-cache
error, never silently repaired.

``point_value`` for XAUUSD (0.001, i.e. raw integer / 1000 = USD price) is
a data-format assumption carried over from the public Dukascopy tooling
ecosystem; it has not been verified against a real download in this
environment (see docs/KNOWN_ISSUES.md) and must be confirmed the first time
real network access is available.
"""

from __future__ import annotations

import hashlib
import lzma
import struct
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

XAUUSD_POINT_VALUE = 0.001

_RECORD_STRUCT = struct.Struct(">IIIff")
_RECORD_SIZE = _RECORD_STRUCT.size

Transport = Callable[[str], bytes]


class DukascopyFetchError(RuntimeError):
    """Raised when an hour-file cannot be fetched after retries."""


class CacheTamperedError(RuntimeError):
    """Raised when a cached hour-file's bytes no longer match its recorded hash."""


def hour_url(symbol: str, hour_start: datetime) -> str:
    """Build the Dukascopy bi5 URL for one UTC hour (month directory is 0-indexed)."""
    return (
        f"https://datafeed.dukascopy.com/datafeed/{symbol}/"
        f"{hour_start.year:04d}/{hour_start.month - 1:02d}/{hour_start.day:02d}/"
        f"{hour_start.hour:02d}h_ticks.bi5"
    )


def _default_transport(url: str) -> bytes:
    """Fetch raw bytes over HTTPS. Swapped out for a fake in tests."""
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - fixed https host
        return resp.read()


def _decompress(raw: bytes) -> bytes:
    """Decompress a bi5 payload, trying auto-detect then the legacy LZMA_ALONE format."""
    if not raw:
        return b""
    try:
        return lzma.decompress(raw)
    except lzma.LZMAError:
        return lzma.decompress(raw, format=lzma.FORMAT_ALONE)


def decode_hour(hour_start: datetime, decompressed: bytes, point_value: float) -> list[dict]:
    """Decode one hour's worth of raw 20-byte tick records into tick dicts.

    Raises:
        ValueError: if the payload length is not a multiple of the record size.
    """
    if len(decompressed) % _RECORD_SIZE != 0:
        raise ValueError(
            f"corrupt bi5 payload for hour {hour_start.isoformat()}: "
            f"{len(decompressed)} bytes is not a multiple of {_RECORD_SIZE}"
        )
    ticks = []
    for offset in range(0, len(decompressed), _RECORD_SIZE):
        time_ms, ask_raw, bid_raw, _ask_vol, _bid_vol = _RECORD_STRUCT.unpack_from(
            decompressed, offset
        )
        ts = hour_start + timedelta(milliseconds=time_ms)
        ticks.append(
            {
                "ts": ts,
                "bid": bid_raw * point_value,
                "ask": ask_raw * point_value,
            }
        )
    return ticks


class DukascopyDownloader:
    """DataProvider for Dukascopy Bid/Ask ticks, with immutable local caching."""

    def __init__(
        self,
        cache_dir: Path,
        transport: Transport = _default_transport,
        point_value: float = XAUUSD_POINT_VALUE,
        max_retries: int = 4,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Create a downloader backed by ``cache_dir`` for the raw hour-files."""
        self.cache_dir = Path(cache_dir)
        self.transport = transport
        self.point_value = point_value
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep

    def _cache_path(self, symbol: str, hour_start: datetime) -> Path:
        return (
            self.cache_dir
            / symbol
            / f"{hour_start.year:04d}"
            / f"{hour_start.month:02d}"
            / f"{hour_start.day:02d}"
            / f"{hour_start.hour:02d}h_ticks.bi5"
        )

    def _fetch_with_retry(self, url: str) -> bytes:
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return self.transport(url)
            except Exception as exc:  # noqa: BLE001 - retried, re-raised below if exhausted
                last_err = exc
                if attempt < self.max_retries - 1:
                    self._sleep(self.backoff_seconds * (2**attempt))
        raise DukascopyFetchError(
            f"failed to fetch {url} after {self.max_retries} attempts"
        ) from last_err

    def _get_hour_raw(self, symbol: str, hour_start: datetime) -> bytes:
        """Return the raw (still-compressed) bytes for one hour, using the immutable cache."""
        path = self._cache_path(symbol, hour_start)
        hash_path = path.with_suffix(path.suffix + ".sha256")
        if path.exists() and hash_path.exists():
            content = path.read_bytes()
            recorded = hash_path.read_text().strip()
            actual = hashlib.sha256(content).hexdigest()
            if actual != recorded:
                raise CacheTamperedError(f"{path} no longer matches recorded hash {recorded}")
            return content

        content = self._fetch_with_retry(hour_url(symbol, hour_start))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        hash_path.write_text(hashlib.sha256(content).hexdigest())
        return content

    def get_ticks(self, symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        """Return all ticks in ``[start, end)`` as a Polars DataFrame sorted by ts."""
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start/end must be timezone-aware (UTC)")
        rows: list[dict] = []
        hour = start.replace(minute=0, second=0, microsecond=0)
        while hour < end:
            raw = self._get_hour_raw(symbol, hour)
            decompressed = _decompress(raw)
            for tick in decode_hour(hour, decompressed, self.point_value):
                if start <= tick["ts"] < end:
                    rows.append(tick)
            hour += timedelta(hours=1)
        schema = {"ts": pl.Datetime("us", "UTC"), "bid": pl.Float64, "ask": pl.Float64}
        df = pl.DataFrame(rows, schema=schema)
        return df.sort("ts")

    def data_version(self, symbol: str, start: datetime, end: datetime) -> str:
        """Stable hash identifying exactly which cached source bytes back this range."""
        parts = []
        hour = start.replace(minute=0, second=0, microsecond=0)
        while hour < end:
            hash_path = self._cache_path(symbol, hour).with_suffix(".bi5.sha256")
            if hash_path.exists():
                parts.append(hash_path.read_text().strip())
            hour += timedelta(hours=1)
        digest_input = symbol + start.isoformat() + end.isoformat() + "".join(sorted(parts))
        return hashlib.sha256(digest_input.encode()).hexdigest()


def utc_now() -> datetime:
    """Return the current time in UTC (helper to keep call sites tz-explicit)."""
    return datetime.now(UTC)
