"""T3.2 test scaffolding: seed a StateStore with a confirmed 4H FVG + matching Bias
directly (bypassing StructureEngine/FVGEngine simulation -- SetupStream only ever
queries the resulting state, never how it got there), plus a SessionEngine.
"""

from datetime import UTC, datetime, timedelta

from src.core.types import FVG, TF, Bar, Side
from src.session.calendar_engine import CalendarEngine
from src.session.session_engine import SessionEngine
from src.store.state_store import BiasEvent, StateStore

SESSION = SessionEngine.from_config(window=("08:30", "10:30"), tz="America/New_York")
NO_BLACKOUT = CalendarEngine.from_config(
    [], currencies=("USD",), impacts=("red",), blackout_before_min=30, blackout_after_min=30,
)
SEED_TS = datetime(2024, 1, 10, 12, 0, tzinfo=UTC)  # well before any window used in tests
IN_WINDOW = datetime(2024, 1, 10, 14, 0, tzinfo=UTC)  # 09:00 ET, winter (EST, UTC-5)


def seed_store(
    direction: Side, top: float, bottom: float, fvg_id: str = "FVG-H4-1",
    calendar: CalendarEngine = NO_BLACKOUT,
) -> StateStore:
    """A store with one confirmed, unmitigated 4H FVG and matching Bias, both from SEED_TS."""
    store = StateStore(session_engine=SESSION, calendar_engine=calendar)
    store.put(
        FVG(
            id=fvg_id,
            tf=TF.H4,
            direction="bull" if direction == "long" else "bear",
            top=top,
            bottom=bottom,
            level=1,
            created_at=SEED_TS,
            confirmed_at=SEED_TS,
            mitigation_pct=0.0,
            invalidated_at=None,
            bos_link=None,
            displacement=False,
        )
    )
    store.put(
        BiasEvent(
            ts=SEED_TS,
            state="bullish" if direction == "long" else "bearish",
            trigger_bos=None,
        )
    )
    return store


def m1(ts: datetime, o: float, h: float, low: float, c: float) -> Bar:
    """A 1M Bar closing 1 minute after ``ts``."""
    return Bar(
        tf=TF.M1, open_ts=ts, close_ts=ts + timedelta(minutes=1),
        o=o, h=h, l=low, c=c, tick_volume=1,
    )


def m5(ts: datetime, o: float, h: float, low: float, c: float) -> Bar:
    """A 5M Bar closing 5 minutes after ``ts``."""
    return Bar(
        tf=TF.M5, open_ts=ts, close_ts=ts + timedelta(minutes=5),
        o=o, h=h, l=low, c=c, tick_volume=1,
    )
