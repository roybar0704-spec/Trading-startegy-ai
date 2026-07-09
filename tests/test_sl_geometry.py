"""T3.2 sl_geometry: SPEC S9 SL formulas per anchor/direction + S10's 3R TP."""

from datetime import UTC, datetime

from src.core.types import IFVG, TF, ArmId, Bar, OrderIntent, Setup
from src.entry.sl_geometry import apply_sl_anchor, compute_sl, gap_reference_price

TS = datetime(2024, 1, 1, tzinfo=UTC)


def _bar(o, h, low, c) -> Bar:
    return Bar(tf=TF.M5, open_ts=TS, close_ts=TS, o=o, h=h, l=low, c=c, tick_volume=1)


def _setup(direction, r_bar, s_bar) -> Setup:
    return Setup(
        id="S1", direction=direction, fvg_id="FVG-1", state="AWAITING_IFVG",
        engagement_ts=TS, r_bar=r_bar, s_bar=s_bar,
        ifvg=IFVG(top=100.5, bottom=100.0, formed_at=TS, inversion_ts=TS),
    )


def test_compute_sl_long_all_anchors():
    r = _bar(99.0, 99.8, 97.0, 99.5)  # min(o,c)=99.0
    s = _bar(98.0, 98.5, 96.0, 97.5)  # min(o,c)=97.5, low=96.0
    setup = _setup("long", r, s)
    assert compute_sl(setup, "R_body", buffer_usd=0.3) == 99.0 - 0.3
    assert compute_sl(setup, "S_body", buffer_usd=0.3) == 97.5 - 0.3
    assert compute_sl(setup, "S_wick", buffer_usd=0.3) == 96.0 - 0.3


def test_compute_sl_short_all_anchors_mirror():
    r = _bar(99.5, 99.8, 99.0, 99.0)  # max(o,c)=99.5
    s = _bar(97.5, 98.5, 97.0, 98.0)  # max(o,c)=98.0, high=98.5
    setup = _setup("short", r, s)
    assert compute_sl(setup, "R_body", buffer_usd=0.3) == 99.5 + 0.3
    assert compute_sl(setup, "S_body", buffer_usd=0.3) == 98.0 + 0.3
    assert compute_sl(setup, "S_wick", buffer_usd=0.3) == 98.5 + 0.3


def test_apply_sl_anchor_computes_3r_tp_long():
    r = _bar(99.0, 99.8, 97.0, 99.5)
    s = _bar(98.0, 98.5, 96.0, 97.5)
    setup = _setup("long", r, s)
    intent = OrderIntent(
        setup_id="S1", arm=ArmId(entry="M1", sl_anchor="R_body"), side="long",
        otype="limit", price=100.5, sl=0.0, tp=0.0, valid_until=TS,
    )
    out = apply_sl_anchor(intent, "R_body", setup, buffer_usd=0.3)
    assert out.sl == 99.0 - 0.3
    stop_distance = 100.5 - out.sl
    assert abs(out.tp - (100.5 + 3.0 * stop_distance)) < 1e-9
    assert out.arm.sl_anchor == "R_body"
    assert out.price == 100.5  # Reference Entry Price untouched (D-045)


def test_gap_reference_price_mirrors_by_direction():
    r = _bar(99.0, 99.8, 97.0, 99.5)
    s = _bar(98.0, 98.5, 96.0, 97.5)
    long_setup = _setup("long", r, s)
    short_setup = _setup("short", r, s)
    assert gap_reference_price(long_setup) == 100.5  # top
    assert gap_reference_price(short_setup) == 100.0  # bottom
