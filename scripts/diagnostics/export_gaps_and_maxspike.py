"""Diagnostic export: full flagged_gaps + max-move spike detail.

Reads tick data and writes full_gaps_export.json to the repository root.
Does not modify source tick data, frozen configuration, or tracked source
files. Reuses Validator exactly as-is, same pattern as
scripts/diagnostics/analyze_spikes.py.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.tick_store import TickParquetStore, months_between  # noqa: E402
from src.data.validator import Validator  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def _as_plain_dict(obj) -> dict:
    """Best-effort: dataclass -> asdict; otherwise fall back to __dict__."""
    try:
        return dataclasses.asdict(obj)
    except TypeError:
        return dict(vars(obj))


def main() -> int:
    symbol = "XAUUSD"
    start = datetime(2022, 11, 1, tzinfo=UTC)
    end = datetime(2023, 6, 1, tzinfo=UTC)  # exclusive -> covers through 2023-05-31

    store = TickParquetStore(REPO_ROOT / "data" / "ticks")
    months = months_between(start, end - timedelta(seconds=1))
    frames = [store.read_month(symbol, y, m) for y, m in months]
    ticks = pl.concat(frames).sort("ts").filter((pl.col("ts") >= start) & (pl.col("ts") < end))
    print(f"Loaded {ticks.height:,} ticks for {symbol} {start.date()}..{(end - timedelta(days=1)).date()}")

    report = Validator().validate(ticks, symbol)

    # 1) Full gap list -- no truncation, no logic touched.
    gaps_out = [_as_plain_dict(g) for g in report.flagged_gaps]
    out_path = REPO_ROOT / "full_gaps_export.json"
    out_path.write_text(json.dumps(gaps_out, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {len(gaps_out)} gaps to {out_path}")

    # 2) Max-move spike + surrounding ticks, bid/ask separately (not just mid).
    max_spike = max(report.spikes, key=lambda s: s.move)
    print(f"\nMax spike: ts={max_spike.ts}  mid={max_spike.mid}  move={max_spike.move}")

    match = ticks.with_row_index().filter(pl.col("ts") == max_spike.ts)
    if match.height == 0:
        print("WARNING: no exact ts match (dtype/precision mismatch?) -- nearest ticks instead:")
        idx = (ticks["ts"] - max_spike.ts).abs().arg_min()
    else:
        idx = match["index"][0]

    window = ticks.slice(max(0, idx - 3), 7)
    print("\nSurrounding ticks (bid/ask separately, not just mid):")
    print(window.select(["ts", "bid", "ask"]))

    return 0


if __name__ == "__main__":
    sys.exit(main())
