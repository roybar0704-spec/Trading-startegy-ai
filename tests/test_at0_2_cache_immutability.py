"""AT-0.2 Cache immutability: repeated download doesn't touch cached files; data_version stable."""

from datetime import UTC, datetime, timedelta

from src.data.dukascopy_downloader import XAUUSD_POINT_VALUE, DukascopyDownloader, hour_url
from tests.fixtures.dukascopy_wire import FakeTransport, encode_hour, synthetic_hour_ticks


def test_at_0_2_cache_immutability(tmp_path):
    hour_start = datetime(2024, 3, 5, 10, tzinfo=UTC)
    symbol = "XAUUSD"
    ticks = synthetic_hour_ticks(hour_start, count=100)
    payload = encode_hour(hour_start, ticks, XAUUSD_POINT_VALUE)
    transport = FakeTransport({hour_url(symbol, hour_start): payload})
    downloader = DukascopyDownloader(cache_dir=tmp_path / "cache", transport=transport)

    df1 = downloader.get_ticks(symbol, hour_start, hour_start + timedelta(hours=1))
    version1 = downloader.data_version(symbol, hour_start, hour_start + timedelta(hours=1))
    cache_path = downloader._cache_path(symbol, hour_start)
    mtime1 = cache_path.stat().st_mtime_ns
    bytes1 = cache_path.read_bytes()
    assert transport.calls == [hour_url(symbol, hour_start)]

    # Second "download" of the exact same range must not re-fetch or rewrite the cache file.
    df2 = downloader.get_ticks(symbol, hour_start, hour_start + timedelta(hours=1))
    version2 = downloader.data_version(symbol, hour_start, hour_start + timedelta(hours=1))

    assert transport.calls == [hour_url(symbol, hour_start)], "must not re-fetch a cached hour"
    assert cache_path.stat().st_mtime_ns == mtime1, "cached file must not be rewritten"
    assert cache_path.read_bytes() == bytes1
    assert version1 == version2
    assert df1.equals(df2)
