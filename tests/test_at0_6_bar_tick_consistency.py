"""AT-0.6 Bar<->Tick consistency: 1M bar OHLC = min/max/first/last Mid of its own ticks."""

import random
from datetime import UTC, datetime, timedelta

import polars as pl

from src.data.bar_builder import BarBuilder
from src.data.types import TF


def test_at_0_6_bar_tick_consistency():
    rng = random.Random(42)
    start = datetime(2024, 6, 3, 8, 0, tzinfo=UTC)
    timestamps, bids, asks = [], [], []
    ts = start
    while ts < start + timedelta(hours=1):
        bid = 2000.0 + rng.uniform(-2.0, 2.0)
        timestamps.append(ts)
        bids.append(bid)
        asks.append(bid + 0.3)
        ts += timedelta(seconds=rng.randint(1, 20))
    df = pl.DataFrame(
        {"ts": timestamps, "bid": bids, "ask": asks},
        schema={"ts": pl.Datetime("us", "UTC"), "bid": pl.Float64, "ask": pl.Float64},
    ).with_columns(((pl.col("bid") + pl.col("ask")) / 2.0).alias("mid"))

    bars = BarBuilder().build(df.drop("mid"), TF.M1)
    assert len(bars) > 0

    for bar in bars:
        in_bar = df.filter((pl.col("ts") >= bar.open_ts) & (pl.col("ts") < bar.close_ts))
        assert in_bar.height == bar.tick_volume
        assert bar.o == in_bar["mid"][0]
        assert bar.c == in_bar["mid"][-1]
        assert bar.h == in_bar["mid"].max()
        assert bar.l == in_bar["mid"].min()
