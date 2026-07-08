"""AT-0.1 Download integrity: known day -> tick count > 0, bid<=ask, monotonic ts.

Real network access to datafeed.dukascopy.com is blocked in this environment
(see docs/KNOWN_ISSUES.md), so the transport is a fake serving synthetic,
wire-format-accurate bi5 payloads for a "known day" instead of a live fetch.
"""

from datetime import UTC, datetime, timedelta

from src.data.dukascopy_downloader import XAUUSD_POINT_VALUE, DukascopyDownloader, hour_url
from tests.fixtures.dukascopy_wire import FakeTransport, encode_hour, synthetic_hour_ticks


def _known_day_transport(day: datetime, symbol: str = "XAUUSD") -> FakeTransport:
    responses = {}
    for h in range(24):
        hour_start = day + timedelta(hours=h)
        ticks = synthetic_hour_ticks(hour_start, count=120)
        responses[hour_url(symbol, hour_start)] = encode_hour(hour_start, ticks, XAUUSD_POINT_VALUE)
    return FakeTransport(responses)


def test_at_0_1_download_integrity(tmp_path):
    day = datetime(2024, 3, 5, tzinfo=UTC)  # a known, ordinary Tuesday
    transport = _known_day_transport(day)
    downloader = DukascopyDownloader(cache_dir=tmp_path / "cache", transport=transport)

    df = downloader.get_ticks("XAUUSD", day, day + timedelta(days=1))

    assert df.height > 0
    assert (df["bid"] <= df["ask"]).all()
    ts = df["ts"].to_list()
    assert ts == sorted(ts)
    assert len(set(ts)) == len(ts), "timestamps must be strictly monotonic (no duplicates)"
