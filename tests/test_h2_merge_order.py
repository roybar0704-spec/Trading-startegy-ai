"""Critical Review finding (Phase 3 close-out, D-063): `_ENTRY_ORDER`'s priorities
were backwards -- {"bar4h": 0, "bar5m": 1, "bar1m": 2} sorts 4H *before* 1M/5M for
a shared timestamp, the exact opposite of the declared and SPEC-mandated H2 rule
("Stage 1, in order 1M -> 5M -> 4H, then Ticks" -- module docstring, CLAUDE.md).
Invisible until now because every existing Orchestrator test leaves bars_4h empty,
so a same-timestamp 4H/1M/5M collision (which happens at every 4H close --
17/21/01/05/09/13 ET, 6x/day, every day) was never exercised.

This tests `_merged_timeline()` directly rather than through a full scenario: it's
the exact sort/group mechanism that was wrong, and constructing a genuine
StructureEngine-driven Bias flip through real 4H bars to observe this indirectly
would test far more machinery than the bug itself without adding precision.
"""

from datetime import timedelta

from src.core.types import TF, Bar
from tests.fixtures.orchestrator import IN_WINDOW, make_orchestrator
from tests.fixtures.setup_stream import m1, m5


def _m4h(close_ts, o, h, low, c) -> Bar:
    return Bar(
        tf=TF.H4, open_ts=close_ts - timedelta(hours=4), close_ts=close_ts,
        o=o, h=h, l=low, c=c, tick_volume=1,
    )


def test_same_timestamp_bars_process_1m_then_5m_then_4h():
    # H2/Race-09:00: a 1M, 5M, and 4H bar all closing at the exact same instant --
    # the collision this ordering exists to resolve, and which happens at every
    # 4H close (17/21/01/05/09/13 ET), 6x/day, every day.
    shared_ts = IN_WINDOW
    bar1m = m1(shared_ts - timedelta(minutes=1), 100.0, 100.1, 99.9, 100.0)
    bar5m = m5(shared_ts - timedelta(minutes=5), 100.0, 100.1, 99.9, 100.0)
    bar4h = _m4h(shared_ts, 100.0, 100.1, 99.9, 100.0)

    orch = make_orchestrator(bars_1m=[bar1m], bars_5m=[bar5m], bars_4h=[bar4h])
    [(ts, group)] = list(orch._merged_timeline())  # noqa: SLF001 -- exact mechanism under test

    assert ts == shared_ts
    assert [kind for (_, _, kind, _) in group] == ["bar1m", "bar5m", "bar4h"]
