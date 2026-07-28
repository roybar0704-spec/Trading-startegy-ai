"""Unit coverage for src/data/browser_transport.py (KI-001 root-cause fix).

No real network access anywhere in this file -- httpx.MockTransport swaps
out only the socket layer, so the real header/HTTP-2 configuration path in
BrowserLikeTransport is still genuinely exercised.
"""

import inspect
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from src.data.browser_transport import BrowserLikeTransport
from src.data.dukascopy_downloader import (
    XAUUSD_POINT_VALUE,
    DukascopyDownloader,
    _default_transport,
    hour_url,
)
from tests.fixtures.dukascopy_wire import encode_hour, synthetic_hour_ticks


def _make_transport(handler) -> BrowserLikeTransport:
    return BrowserLikeTransport(_mock_transport=httpx.MockTransport(handler))


def test_sends_browser_like_headers_not_python_urllib_default():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, content=b"raw-bytes")

    transport = _make_transport(handler)
    try:
        body = transport("https://datafeed.dukascopy.com/datafeed/XAUUSD/2024/00/01/00h_ticks.bi5")
        assert body == b"raw-bytes"
    finally:
        transport.close()

    ua = captured["headers"]["user-agent"]
    assert "python-urllib" not in ua.lower()
    assert "chrome" in ua.lower()
    assert captured["headers"]["accept-encoding"] != "identity"


def test_raises_on_non_2xx_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b'{"error": "Too Many Requests"}')

    transport = _make_transport(handler)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            transport("https://datafeed.dukascopy.com/x.bi5")
    finally:
        transport.close()


def test_returns_raw_bytes_type():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\x00\x01\x02binary")

    transport = _make_transport(handler)
    try:
        result = transport("https://x/y.bi5")
    finally:
        transport.close()
    assert isinstance(result, bytes)


def test_reuses_one_persistent_client_across_calls():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, content=b"ok")

    transport = _make_transport(handler)
    client_id_before = id(transport._client)
    try:
        transport("https://x/a.bi5")
        transport("https://x/b.bi5")
    finally:
        transport.close()
    assert call_count == 2
    assert id(transport._client) == client_id_before  # same client object, no re-open per call


def test_close_does_not_raise():
    transport = BrowserLikeTransport(
        _mock_transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x"))
    )
    transport.close()


def test_context_manager_closes_on_exit():
    handler = lambda r: httpx.Response(200, content=b"x")  # noqa: E731
    with BrowserLikeTransport(_mock_transport=httpx.MockTransport(handler)) as transport:
        transport("https://x/a.bi5")


# --- Backward-compatibility / Transport-contract Acceptance Criterion ---


def test_transport_contract_signature_compatible_with_default_transport():
    """Both _default_transport and BrowserLikeTransport.__call__ satisfy the
    exact same Transport = Callable[[str], bytes] signature shape -- one
    required positional argument -- so DukascopyDownloader (which only ever
    calls transport(url)) works identically with either."""
    default_params = list(inspect.signature(_default_transport).parameters.values())
    browser_params = [
        p
        for p in inspect.signature(BrowserLikeTransport.__call__).parameters.values()
        if p.name != "self"
    ]

    assert len(default_params) == 1
    assert len(browser_params) == 1
    assert default_params[0].kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    assert browser_params[0].kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )


def test_dukascopy_downloader_accepts_browser_like_transport_unchanged(tmp_path):
    """DukascopyDownloader takes any Transport-compatible callable through the
    exact same constructor parameter, with zero changes to
    dukascopy_downloader.py -- proves the existing injection point already
    supports this without modification."""
    hour_start = datetime(2024, 3, 5, 10, tzinfo=UTC)
    ticks = synthetic_hour_ticks(hour_start, count=10)
    payload = encode_hour(hour_start, ticks, XAUUSD_POINT_VALUE)
    url = hour_url("XAUUSD", hour_start)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == url
        return httpx.Response(200, content=payload)

    browser_transport = _make_transport(handler)
    try:
        downloader = DukascopyDownloader(cache_dir=tmp_path, transport=browser_transport)
        df = downloader.get_ticks("XAUUSD", hour_start, hour_start + timedelta(hours=1))
        assert df.height == 10
    finally:
        browser_transport.close()
