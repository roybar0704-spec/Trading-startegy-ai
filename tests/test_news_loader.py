"""B-7 Commit 3 -- unit tests for src/data/news_loader.py (KI-010 Phase 1)."""

from datetime import UTC, datetime

import pytest

from src.core.types import NewsEvent
from src.data.news_loader import NewsLoaderError, load_bls_csv

HEADER = "date,time_et,release,source\n"


def _write(tmp_path, content: str, name: str = "events.csv"):
    path = tmp_path / name
    path.write_text(content)
    return path


def test_parses_a_well_formed_row(tmp_path):
    path = _write(
        tmp_path,
        HEADER + "2023-01-12,08:30,Consumer Price Index,BLS:2023_sched.htm\n",
    )
    events = load_bls_csv(path)
    assert events == [
        NewsEvent(
            ts_utc=datetime(2023, 1, 12, 13, 30, tzinfo=UTC),
            currency="USD",
            impact="red",
            title="CPI",
            source="BLS:2023_sched.htm",
        )
    ]


def test_et_to_utc_during_est_winter(tmp_path):
    # 2023-01-12 is standard time (EST, UTC-5): 08:30 ET -> 13:30 UTC.
    path = _write(tmp_path, HEADER + "2023-01-12,08:30,Consumer Price Index,BLS:2023_sched.htm\n")
    [event] = load_bls_csv(path)
    assert event.ts_utc == datetime(2023, 1, 12, 13, 30, tzinfo=UTC)


def test_et_to_utc_during_edt_summer(tmp_path):
    # 2023-07-12 is daylight time (EDT, UTC-4): 08:30 ET -> 12:30 UTC.
    path = _write(tmp_path, HEADER + "2023-07-12,08:30,Consumer Price Index,BLS:2023_sched.htm\n")
    [event] = load_bls_csv(path)
    assert event.ts_utc == datetime(2023, 7, 12, 12, 30, tzinfo=UTC)


def test_dst_transition_shifts_the_utc_offset(tmp_path):
    # US spring-forward 2023 was 2023-03-12. A same-clock-time 08:30 ET event just
    # before it (still EST, UTC-5) and just after it (now EDT, UTC-4) must resolve to
    # different UTC offsets, not a fixed -5/-4 assumption.
    path = _write(
        tmp_path,
        HEADER
        + "2023-03-10,08:30,Employment Situation,BLS:2023_sched.htm\n"
        + "2023-03-14,08:30,Consumer Price Index,BLS:2023_sched.htm\n",
    )
    before, after = load_bls_csv(path)
    assert before.ts_utc == datetime(2023, 3, 10, 13, 30, tzinfo=UTC)  # EST: -5
    assert after.ts_utc == datetime(2023, 3, 14, 12, 30, tzinfo=UTC)  # EDT: -4


@pytest.mark.parametrize("missing_column", ["date", "time_et", "release", "source"])
def test_missing_or_empty_required_field_fails_loud(tmp_path, missing_column):
    row = {
        "date": "2023-01-12",
        "time_et": "08:30",
        "release": "Consumer Price Index",
        "source": "BLS:2023_sched.htm",
    }
    row[missing_column] = ""
    line = ",".join(row[c] for c in ("date", "time_et", "release", "source"))
    path = _write(tmp_path, HEADER + line + "\n")
    with pytest.raises(NewsLoaderError, match=missing_column):
        load_bls_csv(path)


@pytest.mark.parametrize(
    "date_str,time_str",
    [
        ("2023-13-01", "08:30"),  # invalid month
        ("2023-01-12", "25:99"),  # invalid time
        ("not-a-date", "08:30"),
        ("2023-01-12", "not-a-time"),
    ],
)
def test_malformed_date_or_time_fails_loud(tmp_path, date_str, time_str):
    path = _write(
        tmp_path, HEADER + f"{date_str},{time_str},Consumer Price Index,BLS:2023_sched.htm\n"
    )
    with pytest.raises(NewsLoaderError):
        load_bls_csv(path)


def test_unknown_release_not_in_whitelist_fails_loud(tmp_path):
    path = _write(
        tmp_path,
        HEADER + "2023-01-12,08:30,Producer Price Index,BLS:2023_sched.htm\n",
    )
    with pytest.raises(NewsLoaderError, match="whitelist"):
        load_bls_csv(path)


def test_empty_csv_fails_loud(tmp_path):
    path = _write(tmp_path, "")
    with pytest.raises(NewsLoaderError):
        load_bls_csv(path)


def test_header_only_csv_fails_loud(tmp_path):
    path = _write(tmp_path, HEADER)
    with pytest.raises(NewsLoaderError, match="zero data rows"):
        load_bls_csv(path)


def test_missing_required_column_in_header_fails_loud(tmp_path):
    path = _write(
        tmp_path,
        "date,time_et,release\n2023-01-12,08:30,Consumer Price Index\n",  # no "source" column
    )
    with pytest.raises(NewsLoaderError, match="source"):
        load_bls_csv(path)


def test_output_is_deterministic_and_sorted_regardless_of_input_order(tmp_path):
    # Rows intentionally out of chronological order in the file.
    path = _write(
        tmp_path,
        HEADER
        + "2023-02-14,08:30,Consumer Price Index,BLS:2023_sched.htm\n"
        + "2023-01-06,08:30,Employment Situation,BLS:2023_sched.htm\n"
        + "2023-01-12,08:30,Consumer Price Index,BLS:2023_sched.htm\n",
    )
    first_run = load_bls_csv(path)
    second_run = load_bls_csv(path)
    assert first_run == second_run
    assert [e.ts_utc for e in first_run] == sorted(e.ts_utc for e in first_run)


def test_real_bls_calendar_csv_loads_cleanly():
    """The actual committed Phase 1 dataset (B-7 Commit 2) loads without error."""
    events = load_bls_csv("data/news/bls_calendar.csv")
    assert len(events) == 66
    assert sum(1 for e in events if e.title == "CPI") == 33
    assert sum(1 for e in events if e.title == "Employment Situation") == 33
    assert all(e.currency == "USD" and e.impact == "red" for e in events)
    assert [e.ts_utc for e in events] == sorted(e.ts_utc for e in events)
