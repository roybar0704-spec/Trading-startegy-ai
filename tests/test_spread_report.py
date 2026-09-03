"""Unit coverage for T0.6: hourly spread report."""

import random
import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from src.core.types import Tick
from src.data.spread_report import ExpandingSpreadReport, build_spread_report

_ET = ZoneInfo("America/New_York")


def test_spread_report_basic():
    # 09:00 UTC == 04:00 ET in January (EST); pick a fixed spread to check the math.
    ts = [datetime(2024, 1, 10, 9, i, tzinfo=UTC) for i in range(5)]
    df = pl.DataFrame(
        {"ts": ts, "bid": [2000.0] * 5, "ask": [2000.20] * 5},
        schema={"ts": pl.Datetime("us", "UTC"), "bid": pl.Float64, "ask": pl.Float64},
    )

    report = build_spread_report(df, "XAUUSD")

    stats = report.by_hour[4]  # 09:00 UTC -> 04:00 ET
    assert stats.tick_count == 5
    assert stats.median_spread == pytest.approx(0.20)
    assert report.median_spread(4) == pytest.approx(0.20)


# ===== ExpandingSpreadReport: two-heap streaming median (D-093 perf follow-up) =====
#
# These are differential/regression tests for the *internal* algorithm swap only
# (per-hour list + statistics.median() -> per-hour two-heap). The behavioral
# contract itself (point-in-time correctness, KeyError-on-empty, warm_start
# semantics) is already covered by tests/test_at3_12_spread_pit.py, deliberately
# left unmodified -- it must keep passing unchanged as the regression gate.

_BASE = datetime(2024, 1, 10, 14, 0, tzinfo=UTC)  # 09:00 ET, winter (EST)


def _tick(ts: datetime, spread: float) -> Tick:
    return Tick(ts=ts, bid=2000.0, ask=2000.0 + spread)


def test_expanding_median_empty_hour_raises_keyerror():
    report = ExpandingSpreadReport(symbol="XAUUSD")
    with pytest.raises(KeyError):
        report.median_spread(9)


def test_expanding_median_one_observation():
    report = ExpandingSpreadReport(symbol="XAUUSD")
    tick = _tick(_BASE, 0.10)
    report.update(tick)
    assert report.median_spread(9) == (tick.ask - tick.bid)


def test_expanding_median_two_observations_exact_even_average():
    report = ExpandingSpreadReport(symbol="XAUUSD")
    t1 = _tick(_BASE, 0.10)
    t2 = _tick(_BASE + timedelta(minutes=1), 9.99)
    report.update(t1)
    report.update(t2)
    s1, s2 = t1.ask - t1.bid, t2.ask - t2.bid
    assert report.median_spread(9) == statistics.median([s1, s2])
    assert report.median_spread(9) == (s1 + s2) / 2


def test_expanding_median_odd_count_matches_reference():
    report = ExpandingSpreadReport(symbol="XAUUSD")
    spreads = [3.0, 1.0, 4.0, 1.0, 5.0]  # 5 values, includes a duplicate
    for i, s in enumerate(spreads):
        report.update(_tick(_BASE + timedelta(seconds=i), s))
    assert report.median_spread(9) == statistics.median(spreads)


def test_expanding_median_duplicates():
    report = ExpandingSpreadReport(symbol="XAUUSD")
    spreads = [2.0, 2.0, 2.0, 2.0]
    for i, s in enumerate(spreads):
        report.update(_tick(_BASE + timedelta(seconds=i), s))
    assert report.median_spread(9) == statistics.median(spreads) == 2.0


def test_expanding_median_monotonically_increasing():
    report = ExpandingSpreadReport(symbol="XAUUSD")
    spreads = [float(i) for i in range(1, 101)]
    for i, s in enumerate(spreads):
        report.update(_tick(_BASE + timedelta(seconds=i), s))
    assert report.median_spread(9) == statistics.median(spreads)


def test_expanding_median_monotonically_decreasing():
    report = ExpandingSpreadReport(symbol="XAUUSD")
    spreads = [float(i) for i in range(100, 0, -1)]
    for i, s in enumerate(spreads):
        report.update(_tick(_BASE + timedelta(seconds=i), s))
    assert report.median_spread(9) == statistics.median(spreads)


def test_expanding_median_already_sorted_sequence_with_plateaus():
    # Ascending but with repeated (plateau) values, distinct from the strictly
    # monotonic case above -- exercises duplicate handling within a sorted feed.
    spreads = [1.0, 1.0, 2.0, 2.0, 2.0, 3.0, 4.0, 4.0, 5.0]
    report = ExpandingSpreadReport(symbol="XAUUSD")
    for i, s in enumerate(spreads):
        report.update(_tick(_BASE + timedelta(seconds=i), s))
    assert report.median_spread(9) == statistics.median(spreads)


def test_expanding_median_reverse_sorted_sequence_with_plateaus():
    spreads = [5.0, 4.0, 4.0, 3.0, 2.0, 2.0, 2.0, 1.0, 1.0]
    report = ExpandingSpreadReport(symbol="XAUUSD")
    for i, s in enumerate(spreads):
        report.update(_tick(_BASE + timedelta(seconds=i), s))
    assert report.median_spread(9) == statistics.median(spreads)


def test_expanding_median_large_n_exercises_rebalancing():
    # 10,001 values (odd) in a fixed pseudo-random but reproducible order --
    # large enough to force many push/rebalance cycles in the two-heap structure.
    # Millisecond increments keep all 10,001 ticks within the same ET hour (9).
    # Reference is built from the same (ask - bid) values update() actually stores
    # -- not the raw random draws, since (2000.0 + s) - 2000.0 != s in general for
    # arbitrary floats (only exact for values like small integers, which is why
    # the smaller fixed-value tests above didn't need this distinction).
    rng = random.Random(1234)
    report = ExpandingSpreadReport(symbol="XAUUSD")
    computed_spreads = []
    for i in range(10_001):
        tick = _tick(_BASE + timedelta(milliseconds=i), rng.uniform(-5, 25))
        report.update(tick)
        computed_spreads.append(tick.ask - tick.bid)
    assert report.median_spread(9) == statistics.median(computed_spreads)


def test_expanding_median_randomized_differential_against_statistics_median():
    """Feed 20,000 ticks spanning several ET-hour boundaries; after *every* update,
    compare the heap-based result against statistics.median() on the exact same
    per-hour accumulated values (mirroring the real per-hour bucketing) -- not
    just at the end, matching ExpandingSpreadReport's own point-in-time contract.
    """
    rng = random.Random(42)
    report = ExpandingSpreadReport(symbol="XAUUSD")
    reference_by_hour: dict[int, list[float]] = defaultdict(list)
    for i in range(20_000):
        ts = _BASE + timedelta(seconds=i)
        tick = _tick(ts, rng.uniform(-5, 25))
        computed_spread = tick.ask - tick.bid
        hour_et = ts.astimezone(_ET).hour
        report.update(tick)
        reference_by_hour[hour_et].append(computed_spread)
        assert report.median_spread(hour_et) == statistics.median(reference_by_hour[hour_et])
    assert len(reference_by_hour) > 1  # confirms the feed actually crossed hour boundaries


def test_warm_start_equivalence_with_sequential_updates():
    """warm_start(ticks) must produce exactly the same logical state as constructing
    an empty tracker and calling update() for each tick in the same order."""
    rng = random.Random(7)
    ticks = [
        _tick(_BASE + timedelta(seconds=i), rng.uniform(-5, 25)) for i in range(500)
    ]

    warm_started = ExpandingSpreadReport.warm_start(symbol="XAUUSD", ticks=ticks)

    sequential = ExpandingSpreadReport(symbol="XAUUSD")
    for tick in ticks:
        sequential.update(tick)

    hour_et = ticks[-1].ts.astimezone(_ET).hour
    assert warm_started.median_spread(hour_et) == sequential.median_spread(hour_et)
