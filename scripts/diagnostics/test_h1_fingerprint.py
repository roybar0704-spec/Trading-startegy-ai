#!/usr/bin/env python3
"""H1 fingerprint diagnostic (KI-001) -- NOT part of production code.

Fetches exactly ONE hour of real XAUUSD data -- the exact hour that failed
100% (12/12 attempts, all HTTP 429) via the plain urllib-based
``DukascopyDownloader`` in the November 2022 home-machine test -- using a
browser-like transport instead. Isolates the client-fingerprint variable
only: the cache directory is a throwaway temp dir (never the real
``data/raw``/``data/ticks`` used by the actual backfill), there is no
checkpoint, and none of the retry/pacing machinery is touched -- this
script does not modify or exercise any of that at all.

Per the approved Work Order, this MUST be run from the same machine/network
that produced the original 100% failure (NOT from Claude Code -- running it
there would reintroduce the shared-egress-IP confound documented earlier in
the KI-001 investigation and invalidate the comparison).

Usage (ephemeral httpx+h2 install, NOT added to pyproject.toml):
    uv run --with httpx --with h2 python scripts/diagnostics/test_h1_fingerprint.py
"""

from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from browser_like_transport import browser_like_transport  # noqa: E402

from src.data.dukascopy_downloader import (  # noqa: E402
    DukascopyDownloader,
    DukascopyFetchError,
    hour_url,
)

SYMBOL = "XAUUSD"
# The exact hour that failed 12/12 in the November 2022 home-machine test.
TARGET_HOUR = datetime(2022, 11, 1, 0, tzinfo=UTC)


def main() -> int:
    url = hour_url(SYMBOL, TARGET_HOUR)
    print(f"H1 fingerprint diagnostic -- fetching exactly one hour: {TARGET_HOUR.isoformat()}")
    print(f"URL: {url}")
    print("Transport: browser_like_transport (httpx, HTTP/2, browser headers)")
    print("Cache dir: throwaway temp directory (isolated from real data/raw, data/ticks)\n")

    with tempfile.TemporaryDirectory(prefix="h1_fingerprint_diag_") as tmp_dir:
        downloader = DukascopyDownloader(
            cache_dir=Path(tmp_dir),
            transport=browser_like_transport,
        )
        try:
            df = downloader.get_ticks(SYMBOL, TARGET_HOUR, TARGET_HOUR.replace(hour=1))
        except DukascopyFetchError as exc:
            print(f"RESULT: FAILED -- {exc}")
            print("\n=== H1 VERDICT: browser-like fingerprint did NOT resolve the block ===")
            return 1

        print(f"RESULT: SUCCESS -- {df.height:,} ticks decoded")

        # Structural sanity, reusing the exact same checks used throughout this
        # investigation (AT-0.1-style) -- no new validation logic invented here.
        bid_le_ask = bool((df["bid"] <= df["ask"]).all()) if df.height else True
        ts_list = df["ts"].to_list()
        monotonic = ts_list == sorted(ts_list)
        unique = len(set(ts_list)) == len(ts_list)
        price_band_ok = (
            bool(((df["bid"] >= 500) & (df["bid"] <= 20000)).all())
            and bool(((df["ask"] >= 500) & (df["ask"] <= 20000)).all())
        ) if df.height else True

        print(f"  bid<=ask (all rows): {bid_le_ask}")
        print(f"  timestamps monotonic: {monotonic}")
        print(f"  timestamps unique: {unique}")
        print(f"  price sanity band (500-20000): {price_band_ok}")
        if df.height:
            print(f"  bid range: {df['bid'].min()} .. {df['bid'].max()}")
            print(f"  ask range: {df['ask'].min()} .. {df['ask'].max()}")

        all_ok = bid_le_ask and monotonic and unique and price_band_ok
        status = "VALID" if all_ok else "INVALID -- see above"
        print(
            "\n=== H1 VERDICT: browser-like fingerprint SUCCEEDED on the "
            f"previously-100%-failing URL; payload structurally {status} ==="
        )
        return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
