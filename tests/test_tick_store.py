"""Unit coverage for T0.3: monthly Parquet tick store immutability."""

from datetime import UTC, datetime

import polars as pl
import pytest

from src.data.tick_store import TickParquetStore, TickStoreConflictError, months_between


def _df(ts_list):
    return pl.DataFrame(
        {"ts": ts_list, "bid": [2000.0] * len(ts_list), "ask": [2000.3] * len(ts_list)},
        schema={"ts": pl.Datetime("us", "UTC"), "bid": pl.Float64, "ask": pl.Float64},
    )


def test_write_month_roundtrip(tmp_path):
    store = TickParquetStore.unprotected(tmp_path, reason="unit test, synthetic data")
    ts = [datetime(2024, 3, 1, 0, 0, tzinfo=UTC), datetime(2024, 3, 1, 0, 1, tzinfo=UTC)]
    result = store.write_month("XAUUSD", 2024, 3, _df(ts))

    assert result.row_count == 2
    read_back = store.read_month("XAUUSD", 2024, 3)
    assert read_back.height == 2


def test_write_month_same_content_is_a_noop(tmp_path):
    store = TickParquetStore.unprotected(tmp_path, reason="unit test, synthetic data")
    ts = [datetime(2024, 3, 1, 0, 0, tzinfo=UTC)]
    r1 = store.write_month("XAUUSD", 2024, 3, _df(ts))
    r2 = store.write_month("XAUUSD", 2024, 3, _df(ts))
    assert r1.data_version == r2.data_version


def test_write_month_conflicting_content_raises(tmp_path):
    store = TickParquetStore.unprotected(tmp_path, reason="unit test, synthetic data")
    store.write_month("XAUUSD", 2024, 3, _df([datetime(2024, 3, 1, tzinfo=UTC)]))
    with pytest.raises(TickStoreConflictError):
        store.write_month("XAUUSD", 2024, 3, _df([datetime(2024, 3, 2, tzinfo=UTC)]))


def test_months_between():
    start = datetime(2024, 11, 15, tzinfo=UTC)
    end = datetime(2025, 2, 3, tzinfo=UTC)
    assert months_between(start, end) == [(2024, 11), (2024, 12), (2025, 1), (2025, 2)]
