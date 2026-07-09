"""SL-anchor geometry (SPEC S9).

Turns a model-agnostic entry OrderIntent into the final, arm-specific one. Lives in
``src.entry`` (not ``src.core.types``) because it encodes strategy formulas, not a bare
data shape -- ``src.core`` stays dependency-free/pure-data.

Every EntryModel produces one shared ``OrderIntent`` per Setup with a placeholder
sl/tp (never read downstream); the Orchestrator calls ``apply_sl_anchor`` once per one
of the 9 arms to produce the real, sl_anchor-specific intent before handing it to that
arm's ``RiskEngine.approve()`` -- mirrors ``intent.with_sl(arm.sl_anchor)`` from
ARCHITECTURE.md's pseudo-loop (illustrative there, not a binding signature).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from src.core.types import ArmId, OrderIntent, Setup

TP_RR = 3.0  # SPEC S10: TP fixed at 3R

SLAnchor = Literal["R_body", "S_body", "S_wick"]


def gap_reference_price(setup: Setup) -> float:
    """gap.top for long, gap.bottom for short.

    Used by M1 (Limit price) and M4 (Market reference price) -- M2 uses
    inversion_close instead.
    """
    if setup.ifvg is None:
        raise ValueError(f"setup {setup.id!r} has no ifvg yet")
    return setup.ifvg.top if setup.direction == "long" else setup.ifvg.bottom


def compute_sl(setup: Setup, sl_anchor: SLAnchor, buffer_usd: float) -> float:
    """SL price for one of the three declared anchors (SPEC S9). Requires r_bar/s_bar set."""
    if setup.r_bar is None or setup.s_bar is None:
        raise ValueError(f"compute_sl requires r_bar/s_bar to be set (setup={setup.id!r})")
    r, s = setup.r_bar, setup.s_bar
    if setup.direction == "long":
        if sl_anchor == "R_body":
            return min(r.o, r.c) - buffer_usd
        if sl_anchor == "S_body":
            return min(s.o, s.c) - buffer_usd
        return s.l - buffer_usd  # S_wick
    if sl_anchor == "R_body":
        return max(r.o, r.c) + buffer_usd
    if sl_anchor == "S_body":
        return max(s.o, s.c) + buffer_usd
    return s.h + buffer_usd  # S_wick


def apply_sl_anchor(
    intent: OrderIntent, sl_anchor: SLAnchor, setup: Setup, buffer_usd: float,
) -> OrderIntent:
    """Return a new OrderIntent with this arm's SL and 3R TP.

    D-045: entry.price is unchanged -- it's the Reference Entry Price regardless of
    which SL anchor is applied.
    """
    sl = compute_sl(setup, sl_anchor, buffer_usd)
    stop_distance = intent.price - sl if setup.direction == "long" else sl - intent.price
    tp = (
        intent.price + TP_RR * stop_distance
        if setup.direction == "long"
        else intent.price - TP_RR * stop_distance
    )
    return replace(intent, arm=ArmId(entry=intent.arm.entry, sl_anchor=sl_anchor), sl=sl, tp=tp)
