"""Diagnostic-only transport for the H1 (client-fingerprint) hypothesis test.

NOT used by any production code path. Implements the exact same Transport
contract as src/data/dukascopy_downloader.py's _default_transport
(``Callable[[str], bytes]``), so it can be injected into the existing,
unmodified ``DukascopyDownloader`` without touching that module at all --
see the approved H1 fingerprint-test Work Order (KI-001).

Sends a browser-like fingerprint (realistic headers + HTTP/2 via ALPN)
instead of Python's bare urllib default (``Python-urllib/X.Y`` User-Agent,
``Accept-Encoding: identity``, HTTP/1.1-only ALPN -- see the technical
report this Work Order is based on, which traced these exact facts to
Python's stdlib source).

Requires ``httpx`` + ``h2``, installed *ephemerally* for this one diagnostic
run only (e.g. ``uv run --with httpx --with h2 ...``) -- deliberately NOT
added to pyproject.toml; adopting a new production dependency is a separate
decision, out of scope for this diagnostic.
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


def browser_like_transport(url: str) -> bytes:
    """Fetch raw bytes over HTTPS with a browser-like fingerprint (headers + HTTP/2).

    Same Transport contract as ``_default_transport``: a string URL in, raw
    response bytes out. ``httpx`` transparently decompresses any gzip/br
    transport-level compression, so the bytes returned here are the same
    "raw bi5 payload" the caller already expects -- identical in meaning to
    what ``_default_transport`` returns, just fetched with a different
    client fingerprint. Raises on a non-2xx status (mirroring
    ``urllib.error.HTTPError``'s behavior), so ``DukascopyDownloader``'s
    existing retry logic keeps working unmodified.
    """
    with httpx.Client(http2=True, headers=_BROWSER_HEADERS, timeout=30.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content
