from datetime import datetime, timedelta

from src.core.types import TF, Bar


def make_bars(
    tf: TF, start: datetime, interval: timedelta, ohlc: list[tuple[float, float, float, float]]
) -> list[Bar]:
    """Build sequential Bars from (o, h, l, c) tuples, each spaced ``interval`` apart."""
    bars = []
    ts = start
    for o, h, low, c in ohlc:
        bars.append(
            Bar(tf=tf, open_ts=ts, close_ts=ts + interval, o=o, h=h, l=low, c=c, tick_volume=1)
        )
        ts += interval
    return bars
