"""Streaming-path equivalence tests (Gate 3.7): proves
``Orchestrator.run_streaming()`` + ``TickParquetStore.stream_ticks()`` produce
identical behavior to the existing, unmodified ``Orchestrator.run()`` fed a
materialized ``list[Tick]`` -- additive only, no existing method modified.

Required before any Scope-A (2022-10..2025-06) execution is authorized.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.core.types import TF, Bar, Tick
from src.data.holdout import XAUUSD_HOLDOUT_RANGE
from src.data.tick_store import TickParquetStore
from src.journal.duckdb_writer import DuckDBJournal
from tests.fixtures.orchestrator import IN_WINDOW, make_arm, make_orchestrator, seed_fvg_and_bias
from tests.fixtures.setup_stream import m1, m5
from tests.test_at3_14_determinism import _canonical_export

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def _happy_path_bars_and_ticks():
    """Same proven fixture already used in test_context_snapshots.py /
    test_exit_snapshot_after_window_close.py: one full engagement->armed->
    entry->exit(tp) sequence, M2/S_wick."""
    r_ts = IN_WINDOW + timedelta(minutes=5)
    s_ts = IN_WINDOW + timedelta(minutes=10)
    base = IN_WINDOW + timedelta(minutes=20)
    bars_1m = [
        m1(IN_WINDOW, 100.5, 100.6, 99.5, 100.2),
        m1(base, 97.5, 97.6, 97.0, 97.3),
        m1(base + timedelta(minutes=1), 97.2, 97.3, 96.8, 97.0),
        m1(base + timedelta(minutes=2), 96.4, 96.5, 96.2, 96.3),
        m1(base + timedelta(minutes=3), 96.8, 97.3, 96.7, 97.2),
    ]
    bars_5m = [m5(r_ts, 99.0, 99.8, 97.0, 99.5), m5(s_ts, 98.0, 98.5, 96.0, 97.5)]
    inversion_ts = bars_1m[-1].close_ts
    ticks = [
        Tick(ts=inversion_ts + timedelta(seconds=1), bid=97.15, ask=97.25),  # entry fill
        Tick(ts=inversion_ts + timedelta(minutes=5), bid=101.0, ask=101.1),  # TP exit
    ]
    return bars_1m, bars_5m, ticks


# ---- 1/2/3: old-path vs streaming-path equivalence -------------------------


def test_streaming_path_matches_list_path(tmp_path):
    """Proves: run_streaming() produces the same RunResult counters AND a
    byte-identical Journal (via the existing _canonical_export SHA-256) to
    the existing run() + materialized-list path, on the same known scenario.
    """
    bars_1m, bars_5m, ticks = _happy_path_bars_and_ticks()

    arm_old = make_arm("M2", "S_wick")
    orch_old = make_orchestrator(bars_1m=bars_1m, bars_5m=bars_5m, ticks=ticks, arms=[arm_old])
    old_db = tmp_path / "old.duckdb"
    orch_old.journal = DuckDBJournal(old_db, SCHEMA_PATH)
    seed_fvg_and_bias(orch_old, "long", 100.0, 95.0)
    result_old = orch_old.run()

    arm_new = make_arm("M2", "S_wick")
    orch_new = make_orchestrator(bars_1m=bars_1m, bars_5m=bars_5m, ticks=[], arms=[arm_new])
    new_db = tmp_path / "new.duckdb"
    orch_new.journal = DuckDBJournal(new_db, SCHEMA_PATH)
    seed_fvg_and_bias(orch_new, "long", 100.0, 95.0)
    result_new = orch_new.run_streaming(iter(ticks))

    assert result_old == result_new  # (3) counters
    assert _canonical_export(old_db) == _canonical_export(new_db)  # (1)(2) Journal hash


# ---- 4: H2 exact-timestamp tie-break ---------------------------------------


def test_streaming_merge_preserves_h2_tie_break():
    """A 1M bar, 5M bar, 4H bar, and a tick all sharing the exact same
    timestamp -- proves bars precede the tick, in 1M/5M/4H order."""
    t = IN_WINDOW
    bar_1m = m1(t - timedelta(minutes=1), 100.0, 100.1, 99.9, 100.0)  # close_ts = t
    bar_5m = m5(t - timedelta(minutes=5), 100.0, 100.1, 99.9, 100.0)  # close_ts = t
    bar_4h = Bar(
        tf=TF.H4, open_ts=t - timedelta(hours=4), close_ts=t,
        o=100.0, h=100.1, l=99.9, c=100.0, tick_volume=1,
    )
    tick = Tick(ts=t, bid=100.0, ask=100.1)

    arm = make_arm("M2", "S_wick")
    orch = make_orchestrator(
        bars_1m=[bar_1m], bars_5m=[bar_5m], bars_4h=[bar_4h], ticks=[], arms=[arm]
    )

    ts, group = next(orch._merged_timeline_streaming(iter([tick])))
    assert ts == t
    assert [kind for _, _, kind, _ in group] == ["bar1m", "bar5m", "bar4h", "tick"]


# ---- 5: month-boundary behavior ---------------------------------------------


def test_streaming_merge_handles_month_boundary():
    """Two synthetic 'months' worth of ticks, back to back, each internally
    sorted -- proves no gap/duplicate/misorder exactly at the boundary."""
    boundary = datetime(2024, 2, 1, tzinfo=UTC)
    month_a_ticks = [
        Tick(ts=boundary - timedelta(seconds=s), bid=100.0, ask=100.1) for s in (3, 2, 1)
    ]
    month_b_ticks = [
        Tick(ts=boundary + timedelta(seconds=s), bid=100.0, ask=100.1) for s in (0, 1, 2)
    ]
    combined = iter(month_a_ticks + month_b_ticks)

    arm = make_arm("M2", "S_wick")
    orch = make_orchestrator(bars_1m=[], bars_5m=[], bars_4h=[], ticks=[], arms=[arm])
    emitted_ts = [ts for ts, _ in orch._merged_timeline_streaming(combined)]

    assert emitted_ts == sorted(emitted_ts)
    assert len(emitted_ts) == 6
    assert len(set(emitted_ts)) == 6  # no duplicate timestamp groups


# ---- 6: iterator exhaustion, both directions -------------------------------


def test_streaming_merge_ticks_exhausted_first():
    """Bars remain after the tick source is exhausted -- proves the
    remaining bars still drain correctly, no crash."""
    bar = m1(IN_WINDOW, 100.0, 100.1, 99.9, 100.0)
    arm = make_arm("M2", "S_wick")
    orch = make_orchestrator(bars_1m=[bar], bars_5m=[], bars_4h=[], ticks=[], arms=[arm])

    groups = list(orch._merged_timeline_streaming(iter([])))

    assert len(groups) == 1
    assert groups[0][1][0][2] == "bar1m"


def test_streaming_merge_bars_exhausted_first():
    """Ticks remain after all bars are consumed -- proves the remaining
    ticks still drain correctly, no crash."""
    tick = Tick(ts=IN_WINDOW, bid=100.0, ask=100.1)
    arm = make_arm("M2", "S_wick")
    orch = make_orchestrator(bars_1m=[], bars_5m=[], bars_4h=[], ticks=[], arms=[arm])

    groups = list(orch._merged_timeline_streaming(iter([tick])))

    assert len(groups) == 1
    assert groups[0][1][0][2] == "tick"


# ---- 7/8: row-count + exact timestamp/timezone equivalence (real, ---------
# ---- already-existing Research data; read-only, no Experiment/backtest) ---


def _real_store() -> TickParquetStore:
    return TickParquetStore(REPO_ROOT / "data" / "ticks", holdout_range=XAUUSD_HOLDOUT_RANGE)


def test_stream_ticks_row_count_matches_read_month():
    """Proves: stream_ticks() yields exactly as many ticks as read_month()
    returns for the same month -- no silent drop or duplication. Uses one
    real, already-existing Research month (2024-01, well outside Hold-Out).
    """
    store = _real_store()
    month = [(2024, 1)]

    streamed_count = sum(1 for _ in store.stream_ticks("XAUUSD", month))
    expected_count = store.read_month("XAUUSD", 2024, 1).height

    assert streamed_count == expected_count


def test_stream_ticks_timestamps_match_read_month_exactly():
    """Proves: PyArrow's row-by-row timestamp/value reconstruction
    (stream_ticks) matches Polars' own read path (read_month) exactly, not
    just approximately -- checked around a batch boundary (batch_size=10_000
    here) specifically, since that is where a streaming implementation is
    most likely to introduce an off-by-one.
    """
    store = _real_store()
    month = [(2024, 1)]
    batch_size = 10_000
    sample_indices = {0, 1, batch_size - 1, batch_size, batch_size + 1}
    last_needed = max(sample_indices)

    via_polars = store.read_month("XAUUSD", 2024, 1)
    streamed_sample = {}
    for i, tick in enumerate(store.stream_ticks("XAUUSD", month, batch_size=batch_size)):
        if i in sample_indices:
            streamed_sample[i] = tick
        if i >= last_needed:
            break

    for i in sample_indices:
        row = via_polars.row(i, named=True)
        tick = streamed_sample[i]
        assert tick.ts == row["ts"]
        assert tick.bid == row["bid"]
        assert tick.ask == row["ask"]
        assert tick.ts.tzinfo is not None


# ---- 9: exception / resource cleanup ---------------------------------------


def test_run_streaming_leaves_journal_safely_closeable_after_exception(tmp_path):
    """A tick source that raises partway through -- proves the journal
    connection is left in a state that can still be safely closed afterward
    (no corruption/deadlock), matching run()'s own existing semantics: only
    the success path calls journal.close() internally; on an exception, the
    caller remains responsible for closing it, exactly as today."""
    bars_1m, bars_5m, _ = _happy_path_bars_and_ticks()
    arm = make_arm("M2", "S_wick")
    orch = make_orchestrator(bars_1m=bars_1m, bars_5m=bars_5m, ticks=[], arms=[arm])
    db_path = tmp_path / "crash.duckdb"
    orch.journal = DuckDBJournal(db_path, SCHEMA_PATH)
    seed_fvg_and_bias(orch, "long", 100.0, 95.0)

    def bad_source():
        yield Tick(ts=IN_WINDOW, bid=100.0, ask=100.1)
        raise RuntimeError("simulated mid-stream failure")

    with pytest.raises(RuntimeError, match="simulated mid-stream failure"):
        orch.run_streaming(bad_source())

    orch.journal.close()  # must not raise -- proves no corruption was left behind
