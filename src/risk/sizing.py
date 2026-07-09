"""Position sizing (SPEC §10; RA-22 realized-balance basis; RA-26 no rounding)."""

from __future__ import annotations


def size_units(equity: float, sizing_pct: float, stop_distance_usd: float) -> float:
    """Units = (equity * sizing_pct) / stop_distance -- exact float, no rounding (D-044/RA-26)."""
    if stop_distance_usd <= 0:
        raise ValueError("stop_distance_usd must be positive")
    return (equity * sizing_pct) / stop_distance_usd
