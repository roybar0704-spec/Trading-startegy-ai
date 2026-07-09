"""T3.2 M1/M2/M4 EntryModels: entry price/side/otype per SPEC S8, driven off Armed events."""

from datetime import UTC, datetime, timedelta

from src.core.types import IFVG, TF, Bar, Setup, SetupEvent
from src.entry.m1 import M1EntryModel
from src.entry.m2 import M2EntryModel
from src.entry.m4 import M4EntryModel
from src.session.session_engine import SessionEngine

TS = datetime(2024, 1, 10, 14, 0, tzinfo=UTC)  # 09:00 ET
SESSION = SessionEngine.from_config(window=("08:30", "10:30"), tz="America/New_York")


def _setup(direction="long") -> Setup:
    return Setup(
        id="S1", direction=direction, fvg_id="FVG-1", state="ARMED",
        engagement_ts=TS, ifvg=IFVG(top=100.5, bottom=100.0, formed_at=TS, inversion_ts=TS),
    )


def _armed_event(setup_id="S1", inversion_close=100.3) -> SetupEvent:
    return SetupEvent(
        kind="armed", setup_id=setup_id, ts=TS,
        ifvg=IFVG(top=100.5, bottom=100.0, formed_at=TS, inversion_ts=TS),
        inversion_close=inversion_close,
    )


def test_m1_places_limit_at_gap_top_valid_until_window_end():
    setup = _setup("long")
    model = M1EntryModel(session=SESSION, get_setup=lambda sid: setup)
    intent = model.on_event(_armed_event(), ctx=None)
    assert intent is not None
    assert intent.otype == "limit"
    assert intent.side == "long"
    assert intent.price == 100.5  # gap.top
    assert intent.valid_until == datetime(2024, 1, 10, 15, 30, tzinfo=UTC)  # 10:30 ET


def test_m1_short_uses_gap_bottom():
    setup = _setup("short")
    model = M1EntryModel(session=SESSION, get_setup=lambda sid: setup)
    intent = model.on_event(_armed_event(), ctx=None)
    assert intent.price == 100.0  # gap.bottom
    assert intent.side == "short"


def test_m1_ignores_non_armed_and_post_arm_events():
    setup = _setup("long")
    model = M1EntryModel(session=SESSION, get_setup=lambda sid: setup)
    assert model.on_event(SetupEvent(kind="expired", setup_id="S1", ts=TS), ctx=None) is None
    post_arm_ev = SetupEvent(kind="invalidated", setup_id="S1", ts=TS, post_arm=True)
    assert model.on_event(post_arm_ev, ctx=None) is None


def test_m2_uses_inversion_close_as_reference_price():
    setup = _setup("long")
    model = M2EntryModel(get_setup=lambda sid: setup)
    intent = model.on_event(_armed_event(inversion_close=100.3), ctx=None)
    assert intent.otype == "market"
    assert intent.price == 100.3  # Inversion candle's close, NOT gap.top (D-045)


def test_m4_watches_and_fires_on_first_rejection_candle():
    setup = _setup("long")
    model = M4EntryModel(get_setup=lambda sid: setup)
    assert model.on_event(_armed_event(), ctx=None) is None  # starts watching, no immediate intent

    non_rejecting = Bar(
        tf=TF.M1, open_ts=TS, close_ts=TS + timedelta(minutes=1),
        o=100.4, h=100.5, l=100.3, c=100.35, tick_volume=1,  # bearish close -- not a rejection
    )
    assert model.on_bar_close_1m(non_rejecting, ctx=None) is None

    rejecting = Bar(
        tf=TF.M1, open_ts=TS, close_ts=TS + timedelta(minutes=2),
        o=100.3, h=100.6, l=100.2, c=100.55, tick_volume=1,  # bullish close -- rejects down
    )
    intent = model.on_bar_close_1m(rejecting, ctx=None)
    assert intent is not None
    assert intent.otype == "market"
    assert intent.price == 100.5  # gap.top reference


def test_m4_stops_watching_once_setup_terminates():
    setup = _setup("long")
    model = M4EntryModel(get_setup=lambda sid: setup)
    model.on_event(_armed_event(), ctx=None)
    model.on_event(SetupEvent(kind="invalidated", setup_id="S1", ts=TS, post_arm=True), ctx=None)

    rejecting = Bar(
        tf=TF.M1, open_ts=TS, close_ts=TS + timedelta(minutes=1),
        o=100.3, h=100.6, l=100.2, c=100.55, tick_volume=1,
    )
    assert model.on_bar_close_1m(rejecting, ctx=None) is None
