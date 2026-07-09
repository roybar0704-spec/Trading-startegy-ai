"""AT-3.6 H1: R before 08:30, or Inversion after 10:30 -> no entry (expired), even if the
rest is otherwise valid.
"""

from datetime import UTC, datetime, timedelta

from src.entry.setup_stream import SetupStream
from tests.fixtures.setup_stream import m1, m5, seed_store

TOP, BOTTOM = 100.0, 95.0
BEFORE_WINDOW = datetime(2024, 1, 10, 12, 0, tzinfo=UTC)  # 07:00 ET, before 08:30
NEAR_CLOSE = datetime(2024, 1, 10, 15, 25, tzinfo=UTC)  # 10:25 ET, 5min before close


def test_engagement_and_r_before_window_still_progresses_but_expires_without_entry():
    # Engagement is allowed before the window (SPEC S6 H1); R/S/entry are not.
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()
    stream.on_bar_close(m1(BEFORE_WINDOW, 100.5, 100.6, 99.5, 100.2), store)
    events = stream.step(store.as_of(BEFORE_WINDOW + timedelta(minutes=1)))
    assert any(e.kind == "engaged" for e in events)
    # in_window() is False this early -- the very next step() must expire it immediately,
    # since it never reaches ARMED and isn't specifically AWAITING_IFVG either.
    assert any(e.kind == "expired" for e in events) or not stream._active


def test_inversion_after_window_close_never_arms():
    store = seed_store("long", TOP, BOTTOM)
    stream = SetupStream()
    engage_ts = NEAR_CLOSE
    stream.on_bar_close(m1(engage_ts, 100.5, 100.6, 99.5, 100.2), store)
    stream.step(store.as_of(engage_ts + timedelta(minutes=1)))

    r_ts = engage_ts + timedelta(minutes=1)
    stream.on_bar_close(m5(r_ts, 99.0, 99.8, 97.0, 99.5), store)
    stream.step(store.as_of(r_ts + timedelta(minutes=1)))

    s_ts = r_ts + timedelta(minutes=1)
    stream.on_bar_close(m5(s_ts, 98.0, 98.5, 96.0, 97.5), store)  # S closes just before 10:30
    stream.step(store.as_of(s_ts + timedelta(minutes=1)))

    # Window closes at 10:30 ET (15:30 UTC). Any iFVG inversion attempted after that must
    # not arm -- the guard in step() expires/no_ifvg's the setup once in_window() is False.
    close_ts = datetime(2024, 1, 10, 15, 30, tzinfo=UTC)
    events = stream.step(store.as_of(close_ts))
    assert any(e.kind in ("expired", "no_ifvg") for e in events)

    # A "late" inversion bar after this point must find no active candidate to arm.
    late_ts = close_ts + timedelta(minutes=1)
    stream.on_bar_close(m1(late_ts, 96.8, 97.3, 96.7, 97.2), store)
    late_events = stream.step(store.as_of(late_ts + timedelta(minutes=1)))
    assert not any(e.kind == "armed" for e in late_events)
