"""One of the 9 isolated portfolios (SPEC S9's Grid: {M1,M2,M4} x {R_body,S_body,S_wick})."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.types import ArmId
from src.execution.fill_simulator import FillSimulator
from src.risk.engine import RiskEngine
from src.risk.portfolio import Portfolio


@dataclass
class PortfolioArm:
    """Bundles one arm's identity with its own Portfolio/RiskEngine/FillSimulator."""

    arm_id: ArmId
    portfolio: Portfolio
    risk: RiskEngine
    fill_sim: FillSimulator
