"""Production browser-like HTTP transport (KI-001 root-cause fix).

Presents a browser-like fingerprint (realistic headers + HTTP/2 via ALPN)
instead of Python's bare urllib default used by ``_default_transport`` in
``dukascopy_downloader.py``. Root cause proven in
``scripts/diagnostics/test_h1_fingerprint.py``: the exact same URL that
failed 12/12 times (all HTTP 429) via ``_default_transport`` succeeded
immediately with this fingerprint, from the same machine/IP.

Satisfies the exact same ``Transport = Callable[[str], bytes]`` contract as
``_default_transport`` (``src/data/dukascopy_downloader.py``) -- a drop-in
replacement via constructor injection only. ``dukascopy_downloader.py``
itself is never modified (Option B, approved KI-001 Work Order).

Holds one persistent ``httpx.Client`` for the object's lifetime, so a long
backfill run reuses HTTP/2 connections instead of paying a fresh TLS
handshake on every single hourly request. Callers own the lifecycle:
construct once, call many times, ``close()`` once when done (or use as a
context manager).
"""

from __future__ import annotations

import httpx

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


class BrowserLikeTransport:
    """A ``Transport`` (``Callable[[str], bytes]``) with a browser-like fingerprint.

    Construct once per run, call many times, ``close()`` once at the end.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        *,
        _mock_transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Open one persistent HTTP/2 client for the object's lifetime.

        ``_mock_transport`` swaps out only the network/socket layer (for
        tests, via ``httpx.MockTransport``) while still exercising the real
        header/HTTP-2 configuration below -- production callers never pass it.
        """
        self._client = httpx.Client(
            http2=True,
            headers=_BROWSER_HEADERS,
            timeout=timeout,
            transport=_mock_transport,
        )

    def __call__(self, url: str) -> bytes:
        """Fetch raw bytes over HTTPS. Raises on a non-2xx response.

        Same contract as ``_default_transport``: a string URL in, raw
        response bytes out. ``httpx`` transparently decompresses any
        gzip/br transport-level compression, so the bytes returned here are
        the same "raw bi5 payload" the caller already expects.
        """
        response = self._client.get(url)
        response.raise_for_status()
        return response.content

    def close(self) -> None:
        """Close the underlying persistent HTTP client."""
        self._client.close()

    def __enter__(self) -> BrowserLikeTransport:
        """Return self, for use as a context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the underlying client on context-manager exit."""
        self.close()
