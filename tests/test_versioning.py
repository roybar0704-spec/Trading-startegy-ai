"""B-1 Commit 2: data_version_for_files / data_version_for_ticks (src/data/versioning.py)."""

from datetime import UTC, datetime

from src.core.types import Tick
from src.data.versioning import data_version_for_files, data_version_for_ticks


def _tick(hour: int, bid: float, ask: float) -> Tick:
    return Tick(ts=datetime(2024, 1, 1, hour, tzinfo=UTC), bid=bid, ask=ask)


# ---- data_version_for_files -------------------------------------------------


def test_files_content_change_sensitivity(tmp_path):
    a = tmp_path / "a.parquet"
    a.write_bytes(b"content-1")
    v1 = data_version_for_files([a])

    a.write_bytes(b"content-2")
    v2 = data_version_for_files([a])

    assert v1 != v2


def test_files_input_order_invariance(tmp_path):
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    a.write_bytes(b"content-a")
    b.write_bytes(b"content-b")

    assert data_version_for_files([a, b]) == data_version_for_files([b, a])


def test_files_stability_across_calls(tmp_path):
    a = tmp_path / "a.parquet"
    a.write_bytes(b"content-1")

    assert data_version_for_files([a]) == data_version_for_files([a])


# ---- data_version_for_ticks --------------------------------------------------


def test_ticks_content_change_sensitivity():
    ticks1 = [_tick(0, 2000.0, 2000.1), _tick(1, 2001.0, 2001.1)]
    ticks2 = [_tick(0, 2000.0, 2000.1), _tick(1, 2002.0, 2002.1)]

    assert data_version_for_ticks(ticks1) != data_version_for_ticks(ticks2)


def test_ticks_stability_across_calls():
    ticks = [_tick(0, 2000.0, 2000.1), _tick(1, 2001.0, 2001.1)]

    assert data_version_for_ticks(ticks) == data_version_for_ticks(ticks)


def test_ticks_order_sensitivity():
    ticks_asc = [_tick(0, 2000.0, 2000.1), _tick(1, 2001.0, 2001.1)]
    ticks_desc = list(reversed(ticks_asc))

    assert data_version_for_ticks(ticks_asc) != data_version_for_ticks(ticks_desc)
