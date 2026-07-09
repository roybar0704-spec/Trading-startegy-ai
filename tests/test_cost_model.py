"""Unit coverage for T2.1 CostModel — including the news multiplier, untested until now
(found during the Phase 2 Critical Review: no test exercised in_news=True)."""

from datetime import UTC, datetime

import pytest

from src.execution.cost_model import CostModelParams, StaticCostModel

TS = datetime(2024, 1, 1, tzinfo=UTC)


def _model() -> StaticCostModel:
    return StaticCostModel(
        CostModelParams(
            slippage_stop_usd=0.10,
            news_slip_mult=3.0,
            slippage_market_usd=0.05,
            commission_per_unit=0.02,
        )
    )


def test_stop_slippage_outside_news():
    assert _model().stop_slippage(TS, in_news=False) == pytest.approx(0.10)


def test_stop_slippage_inside_news_applies_multiplier():
    assert _model().stop_slippage(TS, in_news=True) == pytest.approx(0.30)


def test_market_slippage():
    assert _model().market_slippage(TS) == pytest.approx(0.05)


def test_commission_scales_with_units():
    assert _model().commission(10.0) == pytest.approx(0.20)
