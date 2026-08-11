"""D-085: TickParquetStore fail-closed hold-out enforcement (Track A).

T1-T6 per WORK ORDER -- Holdout Enforcement (Fail-Closed), Acceptance Criteria.
T7 (non-hold-out months in the 13 real callers keep working) is covered by
running those scripts themselves, not by a unit test here -- they are manual
diagnostic tools, not part of the pytest suite.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from src.data.tick_store import HoldoutAccessDenied, HoldoutRange, TickParquetStore

REPO_ROOT = Path(__file__).resolve().parents[1]


def _df(ts_list):
    return pl.DataFrame(
        {"ts": ts_list, "bid": [2000.0] * len(ts_list), "ask": [2000.3] * len(ts_list)},
        schema={"ts": pl.Datetime("us", "UTC"), "bid": pl.Float64, "ask": pl.Float64},
    )


@pytest.fixture
def holdout_range():
    # 2024-07-01 .. 2024-12-31 (6 months), same shape as XAUUSD_HOLDOUT_RANGE.
    return HoldoutRange(
        start=datetime(2024, 7, 1, tzinfo=UTC), end=datetime(2024, 12, 31, tzinfo=UTC)
    )


@pytest.fixture
def guarded_store(tmp_path, holdout_range):
    store = TickParquetStore(tmp_path / "ticks", holdout_range=holdout_range)
    for year, month in [(2024, 6), (2024, 8)]:
        store.write_month("XAUUSD", year, month, _df([datetime(year, month, 15, tzinfo=UTC)]))
    return store


# T1 -- Holdout access -> DENIED
def test_t1_holdout_access_denied_without_unlock(guarded_store):
    with pytest.raises(HoldoutAccessDenied):
        guarded_store.read_month("XAUUSD", 2024, 8)


# T2 -- Non-Holdout access -> ALLOWED
def test_t2_non_holdout_access_allowed(guarded_store):
    df = guarded_store.read_month("XAUUSD", 2024, 6)
    assert df.height == 1


# T3 -- Explicit unlock -> ALLOWED
def test_t3_explicit_unlock_allowed(tmp_path, holdout_range):
    store = TickParquetStore(
        tmp_path / "ticks",
        holdout_range=holdout_range,
        holdout_unlock=True,
        unlock_reason="T3 test",
        usage_log_path=tmp_path / "holdout_access_log.jsonl",
    )
    store.write_month("XAUUSD", 2024, 8, _df([datetime(2024, 8, 15, tzinfo=UTC)]))
    df = store.read_month("XAUUSD", 2024, 8)
    assert df.height == 1


# T4 -- Explicit unlock -> recorded to audit log
def test_t4_explicit_unlock_logs_to_audit_log(tmp_path, holdout_range):
    log_path = tmp_path / "holdout_access_log.jsonl"
    store = TickParquetStore(
        tmp_path / "ticks",
        holdout_range=holdout_range,
        holdout_unlock=True,
        unlock_reason="T4 test",
        usage_log_path=log_path,
    )
    store.write_month("XAUUSD", 2024, 8, _df([datetime(2024, 8, 15, tzinfo=UTC)]))
    assert not log_path.exists()  # write_month is not hold-out-gated -- nothing logged yet

    store.read_month("XAUUSD", 2024, 8)
    assert log_path.exists()
    entry = json.loads(log_path.read_text().splitlines()[0])
    assert entry["symbol"] == "XAUUSD"
    assert entry["year"] == 2024
    assert entry["month"] == 8
    assert entry["reason"] == "T4 test"

    # A non-hold-out read must NOT be logged (only actual hold-out accesses are).
    store.write_month("XAUUSD", 2024, 6, _df([datetime(2024, 6, 15, tzinfo=UTC)]))
    store.read_month("XAUUSD", 2024, 6)
    assert len(log_path.read_text().splitlines()) == 1


def test_unlock_without_reason_fails_at_construction(tmp_path, holdout_range):
    with pytest.raises(ValueError, match="unlock_reason"):
        TickParquetStore(
            tmp_path / "ticks", holdout_range=holdout_range,
            holdout_unlock=True, unlock_reason="",
            usage_log_path=tmp_path / "log.jsonl",
        )


def test_unlock_without_usage_log_path_fails_at_construction(tmp_path, holdout_range):
    with pytest.raises(ValueError, match="usage_log_path"):
        TickParquetStore(
            tmp_path / "ticks", holdout_range=holdout_range,
            holdout_unlock=True, unlock_reason="valid reason",
            usage_log_path=None,
        )


def test_unprotected_requires_non_empty_reason(tmp_path):
    with pytest.raises(ValueError, match="reason"):
        TickParquetStore.unprotected(tmp_path, reason="")


def test_unprotected_store_bypasses_holdout_check(tmp_path):
    store = TickParquetStore.unprotected(tmp_path, reason="unit test")
    store.write_month("XAUUSD", 2024, 8, _df([datetime(2024, 8, 15, tzinfo=UTC)]))
    df = store.read_month("XAUUSD", 2024, 8)  # would be a hold-out month for a real range
    assert df.height == 1


# T6 -- No bypass through the normal path: every real TickParquetStore(...) construction
# in src/ + scripts/ (never tests/) supplies holdout_range= explicitly or is unprotected().
def _balanced_call_args(text: str, open_paren_index: int) -> str:
    """Return the text between a '(' at ``open_paren_index`` and its matching ')'."""
    depth = 1
    i = open_paren_index + 1
    while i < len(text) and depth > 0:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
        i += 1
    return text[open_paren_index + 1 : i - 1]


def test_t6_no_bypass_all_real_callers_declare_holdout_intent():
    offenders = []
    for py_file in list(REPO_ROOT.joinpath("src").rglob("*.py")) + list(
        REPO_ROOT.joinpath("scripts").rglob("*.py")
    ):
        text = py_file.read_text(encoding="utf-8")
        for m in re.finditer(r"TickParquetStore\(", text):
            call_start = m.start()
            args = _balanced_call_args(text, m.end() - 1)
            if "holdout_range" not in args:
                line_no = text.count("\n", 0, call_start) + 1
                offenders.append(f"{py_file.relative_to(REPO_ROOT)}:{line_no}")
    assert not offenders, (
        "TickParquetStore constructed without holdout_range= and without "
        f"unprotected() -- bypasses D-085 fail-closed enforcement: {offenders}"
    )
