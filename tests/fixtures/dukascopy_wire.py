import lzma
import struct
from datetime import datetime, timedelta

_RECORD = struct.Struct(">IIIff")


def encode_hour(
    hour_start: datetime, ticks: list[tuple[datetime, float, float]], point_value: float
) -> bytes:
    """Encode (ts, bid, ask) tuples into a real Dukascopy-format compressed bi5 payload."""
    body = b""
    for ts, bid, ask in ticks:
        time_ms = int((ts - hour_start).total_seconds() * 1000)
        body += _RECORD.pack(time_ms, round(ask / point_value), round(bid / point_value), 1.0, 1.0)
    return lzma.compress(body, format=lzma.FORMAT_ALONE)


def synthetic_hour_ticks(
    hour_start: datetime,
    count: int,
    base_bid: float = 2000.0,
    spread: float = 0.30,
    step_ms: int = 1000,
) -> list[tuple[datetime, float, float]]:
    """Generate a monotonic, valid (bid <= ask) synthetic tick sequence for one hour."""
    out = []
    for i in range(count):
        ts = hour_start + timedelta(milliseconds=step_ms * i)
        wobble = 0.01 * ((i % 21) - 10)
        bid = base_bid + wobble
        ask = bid + spread
        out.append((ts, round(bid, 3), round(ask, 3)))
    return out


class FakeTransport:
    """A DukascopyDownloader transport backed by an in-memory url->bytes map, with a call log."""

    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if url not in self.responses:
            raise KeyError(f"no fake response registered for {url}")
        return self.responses[url]
