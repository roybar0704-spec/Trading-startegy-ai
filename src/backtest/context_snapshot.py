"""Context Snapshots (T3.6, docs/FEATURE_SPEC_V1.md).

Point-in-time capture at engagement/armed/entry/exit for each Setup -- the raw
material later Feature Extractors (T4.4, not yet built) will compute from, never
live market state again.

"Snapshot now, Feature later": every field here is read from ``ctx``/``setup``/
``order`` exactly as they stand at the ``ts`` this snapshot is taken -- the same
No-Lookahead-by-Construction discipline as ``MarketContext.as_of`` itself, since
``ctx`` already only ever sees ``confirmed_at <= now``.

Only fields the engine already produces are captured here -- none of
FEATURE_SPEC_V1.md's "proposed" derived features (CHoCH, sweep_type,
volatility_score, ATR, ...) are computed in this module. Those are unapproved
(D-029), and even once approved belong to T4.4's Feature Extractors reading these
snapshots later, not to snapshot capture itself (FEATURE_SPEC_V1.md's own
principle: "the engine is never reopened for a Feature").

D-058: engagement/armed are model-agnostic (order_id=None, one row per Setup,
shared by all 9 arms -- same principle as D-052's setups/setup_arm_outcomes
split). entry/exit are per-arm (order_id required, one row per Order/trade).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from src.core.types import IFVG, TF, Bar, Order, Setup
from src.store.state_store import MarketContext

SnapshotKind = Literal["engagement", "armed", "entry", "exit"]
_ET = ZoneInfo("America/New_York")


def bar_to_json(bar: Bar | None) -> dict | None:
    """OHLC bar as a JSON-serializable dict, or None."""
    if bar is None:
        return None
    return {
        "open_ts": bar.open_ts.isoformat(), "close_ts": bar.close_ts.isoformat(),
        "o": bar.o, "h": bar.h, "l": bar.l, "c": bar.c, "tick_volume": bar.tick_volume,
    }


def ifvg_to_json(ifvg: IFVG | None) -> dict | None:
    """Armed iFVG as a JSON-serializable dict, or None."""
    if ifvg is None:
        return None
    return {
        "top": ifvg.top, "bottom": ifvg.bottom,
        "formed_at": ifvg.formed_at.isoformat(), "inversion_ts": ifvg.inversion_ts.isoformat(),
    }


def _fvg_dict(setup: Setup, ctx: MarketContext) -> dict | None:
    """The setup's own 4H FVG, as of ``ctx.now``.

    None if it's already fallen out of ``active_fvgs`` by this ts (e.g.
    mitigated/invalidated after entry, at an exit snapshot); that absence is
    itself informative, not an error.
    """
    direction = "bull" if setup.direction == "long" else "bear"
    for fvg in ctx.active_fvgs(TF.H4, direction):
        if fvg.id == setup.fvg_id:
            return {
                "id": fvg.id, "top": fvg.top, "bottom": fvg.bottom, "level": fvg.level,
                "confirmed_at": fvg.confirmed_at.isoformat(),
                "mitigation_pct": fvg.mitigation_pct, "displacement": fvg.displacement,
            }
    return None


def _median_spread_or_none(ctx: MarketContext) -> float | None:
    """Best-effort median_spread lookup.

    Legitimately has no data yet for an hour that hasn't been observed in this run
    (bootstrap edge case, D-049/KI-007) -- this is supplementary descriptive
    context, not a decision input, so an explicit ``None`` is the honest
    representation rather than treating it as a fatal anomaly.
    """
    try:
        return ctx.median_spread(ctx.now.astimezone(_ET).hour)
    except KeyError:
        return None


def build_snapshot(
    kind: SnapshotKind, ts: datetime, ctx: MarketContext, setup: Setup,
    order: Order | None = None,
) -> dict:
    """Build the JSON-serializable payload for one ``context_snapshots`` row.

    ``order`` must be provided for kind in {"entry", "exit"} and omitted for
    {"engagement", "armed"} -- enforced here, not left to the caller to remember.
    """
    if kind in ("entry", "exit") and order is None:
        raise ValueError(f"build_snapshot(kind={kind!r}) requires an order")
    if kind in ("engagement", "armed") and order is not None:
        raise ValueError(f"build_snapshot(kind={kind!r}) must not receive an order")

    payload: dict = {
        "kind": kind,
        "setup_id": setup.id,
        "direction": setup.direction,
        "bias": ctx.bias(),
        "in_window": ctx.in_window(),
        "in_blackout": ctx.in_blackout(),
        "median_spread": _median_spread_or_none(ctx),
        "fvg": _fvg_dict(setup, ctx),
        "r_bar": bar_to_json(setup.r_bar),
        "s_bar": bar_to_json(setup.s_bar),
        "ifvg": ifvg_to_json(setup.ifvg),
        "ts_flag": setup.ts_flag,
        "same_zone_reentry": setup.same_zone_reentry,
        "score": setup.score,
    }
    if order is not None:
        payload["order"] = {
            "order_id": order.order_id, "portfolio_id": order.portfolio_id,
            "otype": order.otype, "side": order.side, "price": order.price,
            "sl": order.sl, "tp": order.tp, "units": order.units,
        }
    return payload


def make_snapshot_row(
    kind: SnapshotKind, ts: datetime, ctx: MarketContext, setup: Setup,
    order: Order | None = None,
) -> dict:
    """Build the full ``context_snapshots`` row, ready to record.

    Includes its own id/FKs, for ``Journal.record("context_snapshots", ...)``.
    """
    if order is not None:
        snapshot_id = f"SNAP-{order.order_id}-{kind}"
    else:
        snapshot_id = f"SNAP-{setup.id}-{kind}"
    return {
        "snapshot_id": snapshot_id,
        "setup_id": setup.id,
        "order_id": order.order_id if order is not None else None,
        "kind": kind,
        "ts": ts,
        "payload": json.dumps(build_snapshot(kind, ts, ctx, setup, order)),
    }
