"""AT-3.8 no_ifvg: full R->S sequence with no bearish 1M FVG ever forming -> `no_ifvg`
recorded, distinct from generic `expired` (SPEC S7: "logged" as a research-relevant
outcome in its own right, not just "ran out of time").
"""

from datetime import timedelta

from src.entry.setup_stream import SetupStream
from tests.fixtures.setup_stream import IN_WINDOW, m1, m5, seed_store

TOP, BOTTOM = 100.0, 95.0


def test_no_bearish_1m_gap_ever_forms_yields_no_ifvg_at_window_close():
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()
    stream.on_bar_close(m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    stream.step(store.as_of(IN_WINDOW + timedelta(minutes=1)))
    r_ts = IN_WINDOW + timedelta(minutes=5)
    stream.on_bar_close(m5(r_ts, 99.0, 99.8, 97.0, 99.5), store)
    stream.step(store.as_of(r_ts + timedelta(minutes=1)))
    s_ts = IN_WINDOW + timedelta(minutes=10)
    stream.on_bar_close(m5(s_ts, 98.0, 98.5, 96.0, 97.5), store)  # S
    stream.step(store.as_of(s_ts + timedelta(minutes=1)))

    # Only ever-rising 1M bars after S -- never forms a bearish c1.low > c3.high pattern.
    base = IN_WINDOW + timedelta(minutes=20)
    for i in range(5):
        ts = base + timedelta(minutes=i)
        stream.on_bar_close(
            m1(ts, 97.0 + i * 0.1, 97.2 + i * 0.1, 96.9 + i * 0.1, 97.1 + i * 0.1), store
        )
    stream.step(store.as_of(base + timedelta(minutes=5)))

    close_ts = IN_WINDOW.replace(hour=15, minute=30, second=0, microsecond=0)  # window end (winter)
    events = stream.step(store.as_of(close_ts))
    assert any(e.kind == "no_ifvg" for e in events)
    assert not any(e.kind == "expired" for e in events)
