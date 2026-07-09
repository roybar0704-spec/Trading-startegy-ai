"""Core domain types shared by every layer (docs/INTERFACES.md "טיפוסי ליבה").

This module has zero dependencies on the rest of ``src`` — every layer
(data, store, structure, fvg, displacement, entry, risk, execution, ...) may
import from here without violating the layering contract, since nothing
here imports back. Only the types actually consumed so far are implemented;
``Setup`` is added here the same way once a module needs it (D-038).

``Order``/``Fill``/``Rejection``/``PortfolioId`` (D-046) are not part of
INTERFACES.md's "core types" list -- they're referenced only as Protocol
return types, with no fields ever specified. They live here (not in
src.risk or src.execution) for the same reason Swing/FVG do: RiskEngine
*constructs* an Order and execution *consumes* one, so both need the type
without either depending on the other's module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal


class TF(Enum):
    """Timeframe identifiers used throughout the platform."""

    M1 = "1M"
    M5 = "5M"
    H4 = "4H"


@dataclass(frozen=True)
class Tick:
    """A single Bid/Ask quote. ``ts`` is always UTC."""

    ts: datetime
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        """Mid price — the price used for all structure (Swings/BOS/FVG/...)."""
        return (self.bid + self.ask) / 2.0


@dataclass(frozen=True)
class Bar:
    """An OHLC bar built on Mid price, plus tick-count volume."""

    tf: TF
    open_ts: datetime
    close_ts: datetime
    o: float
    h: float
    l: float  # noqa: E741 - matches docs/INTERFACES.md field name
    c: float
    tick_volume: int


@dataclass(frozen=True)
class Swing:
    """A confirmed market-structure Swing (fractal high/low)."""

    id: str
    tf: TF
    kind: Literal["H", "L"]
    price: float
    created_at: datetime
    confirmed_at: datetime
    taken_at: datetime | None


@dataclass(frozen=True)
class FVG:
    """A Fair Value Gap: 3-bar imbalance, valid until 100% Mid mitigation."""

    id: str
    tf: TF
    direction: Literal["bull", "bear"]
    top: float
    bottom: float
    level: int  # 1..3
    created_at: datetime
    confirmed_at: datetime
    mitigation_pct: float
    invalidated_at: datetime | None
    bos_link: str | None
    displacement: bool


PortfolioId = str
Side = Literal["long", "short"]


@dataclass(frozen=True)
class ArmId:
    """One of the 9 arms: an entry model paired with an SL anchor."""

    entry: Literal["M1", "M2", "M4"]
    sl_anchor: Literal["R_body", "S_body", "S_wick"]


@dataclass(frozen=True)
class OrderIntent:
    """An EntryModel's request to enter, before Risk approval (docs/SPEC_V1_FROZEN.md §8)."""

    setup_id: str
    arm: ArmId
    side: Side
    otype: Literal["limit", "market"]
    price: float | None  # Reference Entry Price (D-045) -- always populated in practice
    sl: float
    tp: float
    valid_until: datetime


@dataclass
class Order:
    """An approved order (db/schema.sql ``orders`` table, transcribed verbatim -- D-046)."""

    order_id: str
    setup_id: str
    portfolio_id: PortfolioId
    otype: Literal["limit", "market"]
    side: Literal["buy", "sell"]
    price: float | None  # limit price; None for market orders
    sl: float
    tp: float
    units: float
    placed_at: datetime
    valid_until: datetime
    status: Literal["pending", "filled", "cancelled"] = "pending"
    filled_at: datetime | None = None
    fill_price: float | None = None
    cancel_reason: str | None = None


@dataclass(frozen=True)
class Fill:
    """A single execution event against an Order (entry or exit)."""

    order_id: str
    ts: datetime
    price: float
    kind: Literal["limit_entry", "market_entry", "sl_exit", "tp_exit", "gap_through_sl_exit"]


@dataclass(frozen=True)
class Rejection:
    """RiskEngine's refusal to approve an OrderIntent, with a reason."""

    setup_id: str
    reason: str


@dataclass(frozen=True)
class NewsEvent:
    """A single calendar entry (db/schema.sql ``news_events``, RA-23)."""

    ts_utc: datetime
    currency: str
    impact: str
    title: str
    source: str


@dataclass
class SetupArmOutcome:
    """Per-(setup, portfolio) result (D-052) -- never stored on ``Setup`` itself."""

    setup_id: str
    portfolio_id: PortfolioId
    outcome: Literal[
        "pending", "closed", "expired", "invalidated", "blocked_news", "blocked_quota",
        "invalid_geometry",
    ]
    outcome_reason: str | None = None
    order_id: str | None = None


SetupState = Literal[
    "ZONE_ENGAGED", "REACTION_SEEN", "SWEEP_CONFIRMED", "AWAITING_IFVG", "ARMED",
]


@dataclass
class IFVG:
    """A chosen (armed) iFVG: 1M gap that inverted (docs/trigger_spec S2)."""

    top: float
    bottom: float
    formed_at: datetime
    inversion_ts: datetime


@dataclass
class Setup:
    """A model-agnostic Setup (D-052): one FVG x R x S x iFVG sequence, shared by all 9 arms."""

    id: str
    direction: Side
    fvg_id: str
    state: SetupState
    engagement_ts: datetime
    r_bar: Bar | None = None
    s_bar: Bar | None = None
    ifvg: IFVG | None = None
    ts_flag: bool = False
    same_zone_reentry: bool = False
    score: float | None = None
    outcome: Literal["armed", "expired", "invalidated", "no_ifvg"] | None = None
    outcome_reason: str | None = None


@dataclass(frozen=True)
class SetupEvent:
    """One Setup Stream transition (docs/INTERFACES.md SetupStream)."""

    kind: Literal[
        "engaged", "reaction_seen", "sweep_confirmed", "armed",
        "invalidated", "expired", "no_ifvg",
    ]
    setup_id: str
    ts: datetime
    reason: str | None = None
    ifvg: IFVG | None = None
    post_arm: bool = False  # True: setups.outcome already 'armed' -- cancel pending orders only
