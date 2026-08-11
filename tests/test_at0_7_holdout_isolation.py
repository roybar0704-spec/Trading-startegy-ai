"""AT-0.7 Holdout isolation: loading a holdout-overlapping range without the unlock flag
raises; with the flag, it's recorded (Tracker stand-in: an append-only usage log)."""

import json
from datetime import UTC, datetime

import polars as pl
import pytest

from src.data.holdout import (
    HoldoutAccessDenied,
    HoldoutGuard,
    compute_holdout_range,
    separate_holdout,
)
from src.data.tick_store import TickParquetStore


def _month_ticks(year: int, month: int) -> pl.DataFrame:
    ts = datetime(year, month, 15, 12, 0, tzinfo=UTC)
    return pl.DataFrame(
        {"ts": [ts], "bid": [2000.0], "ask": [2000.3]},
        schema={"ts": pl.Datetime("us", "UTC"), "bid": pl.Float64, "ask": pl.Float64},
    )


def _test_holdout_range():
    return compute_holdout_range(
        datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 12, 31, tzinfo=UTC), last_months=6
    )


@pytest.fixture
def populated_store(tmp_path):
    # D-085: this store carries the same holdout_range the test separates below --
    # Track A (read_month()'s own check) now blocks the moved months structurally,
    # not just because the underlying file is physically gone (Track B).
    store = TickParquetStore(tmp_path / "ticks", holdout_range=_test_holdout_range())
    for month in range(1, 13):
        store.write_month("XAUUSD", 2024, month, _month_ticks(2024, month))
    return store


def test_at_0_7_holdout_isolation(tmp_path, populated_store):
    holdout_range = _test_holdout_range()
    assert holdout_range.start == datetime(2024, 7, 1, tzinfo=UTC)

    holdout_root = tmp_path / "holdout"
    moved = separate_holdout(populated_store, holdout_root, "XAUUSD", holdout_range)
    assert len(moved) == 6

    # Track A: the main store's own read_month() now refuses the hold-out month directly
    # (HoldoutAccessDenied), independent of the physical move performed above.
    with pytest.raises(HoldoutAccessDenied):
        populated_store.read_month("XAUUSD", 2024, 8)

    usage_log = tmp_path / "holdout_usage.jsonl"
    guard = HoldoutGuard(holdout_root, usage_log)

    with pytest.raises(HoldoutAccessDenied):
        guard.load(
            "XAUUSD",
            datetime(2024, 8, 1, tzinfo=UTC),
            datetime(2024, 9, 1, tzinfo=UTC),
            holdout_range,
            holdout_unlock=False,
        )
    assert not usage_log.exists()

    df = guard.load(
        "XAUUSD",
        datetime(2024, 8, 1, tzinfo=UTC),
        datetime(2024, 9, 1, tzinfo=UTC),
        holdout_range,
        holdout_unlock=True,
        reason="AT-0.7 test",
    )
    assert df.height == 1
    assert usage_log.exists()
    entry = json.loads(usage_log.read_text().splitlines()[0])
    assert entry["reason"] == "AT-0.7 test"
