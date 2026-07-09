"""T3.1: SessionEngine window/day-roll, DST-correct (winter vs summer offsets)."""

from datetime import UTC, date, datetime

from src.session.session_engine import SessionEngine

ENGINE = SessionEngine.from_config(window=("08:30", "10:30"), tz="America/New_York")


def test_in_window_winter_est():
    assert ENGINE.in_window(datetime(2024, 1, 10, 13, 30, tzinfo=UTC))  # 08:30 ET
    assert ENGINE.in_window(datetime(2024, 1, 10, 15, 29, tzinfo=UTC))  # 10:29 ET
    assert not ENGINE.in_window(datetime(2024, 1, 10, 15, 30, tzinfo=UTC))  # 10:30 ET, half-open
    assert not ENGINE.in_window(datetime(2024, 1, 10, 13, 29, tzinfo=UTC))  # 08:29 ET


def test_in_window_summer_edt():
    assert ENGINE.in_window(datetime(2024, 7, 10, 12, 30, tzinfo=UTC))  # 08:30 ET
    assert not ENGINE.in_window(datetime(2024, 7, 10, 14, 30, tzinfo=UTC))  # 10:30 ET


def test_ny_date_is_local_calendar_date():
    # 23:00 ET on Jan 10 is already Jan 11 03:00 UTC -- ny_date must read the NY date, not UTC's.
    ts = datetime(2024, 1, 11, 3, 0, tzinfo=UTC)
    assert ENGINE.ny_date(ts) == date(2024, 1, 10)


def test_window_bounds_utc_dst_correct():
    winter_start, winter_end = ENGINE.window_bounds_utc(date(2024, 1, 10))
    assert (winter_start.hour, winter_start.minute) == (13, 30)
    assert (winter_end.hour, winter_end.minute) == (15, 30)

    summer_start, summer_end = ENGINE.window_bounds_utc(date(2024, 7, 10))
    assert (summer_start.hour, summer_start.minute) == (12, 30)
    assert (summer_end.hour, summer_end.minute) == (14, 30)
