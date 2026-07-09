from datetime import UTC, datetime

from src.core.types import Order
from src.execution.cost_model import CostModelParams, StaticCostModel


def make_cost_model() -> StaticCostModel:
    return StaticCostModel(
        CostModelParams(
            slippage_stop_usd=0.10,
            news_slip_mult=3.0,
            slippage_market_usd=0.05,
            commission_per_unit=0.0,
        )
    )


def make_order(**overrides) -> Order:
    base = {
        "order_id": "O1",
        "setup_id": "S1",
        "portfolio_id": "P1",
        "otype": "limit",
        "side": "buy",
        "price": 100.0,
        "sl": 98.0,
        "tp": 106.0,
        "units": 10.0,
        "placed_at": datetime(2024, 1, 1, tzinfo=UTC),
        "valid_until": datetime(2024, 1, 1, 12, tzinfo=UTC),
    }
    base.update(overrides)
    return Order(**base)
