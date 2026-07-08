#!/usr/bin/env python3
"""Phase 0 demo (docs/PHASE_PLAN.md working-software table).

Loads one month of XAUUSD ticks, runs the Validator, builds 1M/5M/4H bars
(4H anchored to NY-Close), and prints the hourly spread report.

Real Dukascopy network access (datafeed.dukascopy.com) is blocked in this
environment (docs/KNOWN_ISSUES.md). This script tries the real downloader
first; if that fails, it falls back to a clearly-labeled synthetic month so
the rest of the pipeline (validate/build/report) can still be demonstrated
end-to-end. Every synthetic-data line is prefixed "[SYNTHETIC]".

Usage:
    python scripts/demo_phase0.py --month 2024-03
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import polars as pl

from src.config.frozen_guard import verify_frozen_rules
from src.core.types import TF
from src.data.bar_builder import BarBuilder
from src.data.dukascopy_downloader import DukascopyDownloader, DukascopyFetchError
from src.data.spread_report import build_spread_report
from src.data.validator import Validator

REPO_ROOT = Path(__file__).resolve().parents[1]


def _synthetic_month(symbol: str, year: int, month: int) -> pl.DataFrame:
    """A weekday-only, DST-aware, deterministic synthetic month of Bid/Ask ticks."""
    print(f"[SYNTHETIC] generating a stand-in month of {symbol} ticks for {year}-{month:02d} "
          "(real Dukascopy fetch unavailable in this environment)")
    rng = random.Random(20240000 + year * 100 + month)
    start = datetime(year, month, 1, tzinfo=UTC)
    end = (start + timedelta(days=32)).replace(day=1)

    rows = []
    price = 2000.0
    ts = start
    step = timedelta(seconds=5)
    while ts < end:
        weekday = ts.weekday()
        is_weekend = (
            weekday == 5 or (weekday == 4 and ts.hour >= 21) or (weekday == 6 and ts.hour < 21)
        )
        if not is_weekend:
            price += rng.uniform(-0.05, 0.05)
            spread = 0.20 + (0.30 if ts.hour in (13, 14) else 0.0)  # wider spread during NY AM
            rows.append((ts, round(price, 3), round(price + spread, 3)))
        ts += step
    return pl.DataFrame(
        {"ts": [r[0] for r in rows], "bid": [r[1] for r in rows], "ask": [r[2] for r in rows]},
        schema={"ts": pl.Datetime("us", "UTC"), "bid": pl.Float64, "ask": pl.Float64},
    )


def load_month(symbol: str, year: int, month: int) -> pl.DataFrame:
    """Real Dukascopy fetch, falling back to a synthetic month on failure."""
    start = datetime(year, month, 1, tzinfo=UTC)
    end = (start + timedelta(days=32)).replace(day=1)
    # Fail fast on the probe (this demo's own retry policy, not the downloader's default);
    # a real unattended run should use DukascopyDownloader's default retry/backoff.
    probe = DukascopyDownloader(
        cache_dir=REPO_ROOT / "data" / "raw", max_retries=1, backoff_seconds=0.1
    )
    try:
        df = probe.get_ticks(symbol, start, min(end, start + timedelta(hours=1)))
        if df.height == 0:
            raise DukascopyFetchError("empty response")
        print(f"real Dukascopy data available; downloading full month {year}-{month:02d}...")
        downloader = DukascopyDownloader(cache_dir=REPO_ROOT / "data" / "raw")
        return downloader.get_ticks(symbol, start, end)
    except Exception as exc:  # noqa: BLE001 - any network failure -> documented fallback
        print(f"[SYNTHETIC] real Dukascopy fetch failed ({exc.__class__.__name__}: {exc}); "
              "falling back to synthetic data for this demo.")
        return _synthetic_month(symbol, year, month)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--symbol", default="XAUUSD")
    args = parser.parse_args()
    year, month = (int(x) for x in args.month.split("-"))

    print("== frozen config integrity ==")
    print("rules_v1.yaml hash:", verify_frozen_rules())

    print(f"\n== loading {args.symbol} {args.month} ==")
    ticks = load_month(args.symbol, year, month)
    print(f"tick count: {ticks.height:,}")

    print("\n== validation report ==")
    report = Validator().validate(ticks, args.symbol)
    print(f"flagged (non-weekend) gaps: {len(report.flagged_gaps)}")
    print(f"weekend gaps (expected, not flagged): {len(report.weekend_gaps)}")
    print(f"spikes flagged: {len(report.spikes)}")

    print("\n== spread report by ET hour ==")
    spread = build_spread_report(ticks, args.symbol)
    print(spread.to_markdown())

    print("\n== bars ==")
    builder = BarBuilder()
    bars_1m = builder.build(ticks, TF.M1)
    bars_5m = builder.build(ticks, TF.M5)
    bars_4h = builder.build(ticks, TF.H4)
    print(f"1M bars: {len(bars_1m)}")
    print(f"5M bars: {len(bars_5m)}")
    print(f"4H bars (NY-Close anchored): {len(bars_4h)}")
    print("first 4 4H bars (open_ts / close_ts are UTC; anchors are 17/21/01/05/09/13 ET):")
    for bar in bars_4h[:4]:
        print(
            f"  {bar.open_ts.isoformat()} -> {bar.close_ts.isoformat()}  "
            f"O={bar.o:.3f} H={bar.h:.3f} L={bar.l:.3f} C={bar.c:.3f} vol={bar.tick_volume}"
        )

    print("\nPhase 0 demo complete.")


if __name__ == "__main__":
    main()
