"""Point-in-Time State Store + MarketContext (docs/INTERFACES.md "Store").

Write side (structure/fvg engines only): ``StateStore.put``/``invalidate``,
plus the small read-side helpers engines need on their own prior writes
(``all_swings``/``all_fvgs``/``bos_at``). Read side for decision logic:
``StateStore.as_of(ts)`` returns a ``MarketContext`` that only ever sees
``confirmed_at <= now`` (docs/ARCHITECTURE.md principle #1, No-Lookahead by
Construction).

Every update to a Swing/FVG is appended as a new *version*, not an
in-place overwrite: a naive "latest write wins" store is only point-in-time
correct if ``as_of`` is queried in forward lockstep with processing and
never again for an earlier ``ts`` afterwards. Prefix-Consistency checking
(AT-1.6) does exactly that — it re-queries a fully-processed store at every
earlier bar boundary — so real version history is required, not optional.
Each version's "effective timestamp" (when it became knowable) is derived
from its own fields: a Swing's is ``taken_at`` if set, else ``confirmed_at``;
an FVG's is ``invalidated_at`` if set, else ``confirmed_at``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import datetime
from typing import Literal

from src.core.types import FVG, TF, Swing
from src.data.spread_report import SpreadReport
from src.session.calendar_engine import CalendarEngine
from src.session.session_engine import SessionEngine

BiasState = Literal["bullish", "bearish", "neutral"]


@dataclass(frozen=True)
class BiasEvent:
    """A recorded Bias *transition* (docs/SPEC_V1_FROZEN.md §3) — not every BOS, only changes."""

    ts: datetime
    state: BiasState
    trigger_bos: dict | None


def _swing_effective_ts(swing: Swing) -> datetime:
    return swing.taken_at if swing.taken_at is not None else swing.confirmed_at


def _fvg_effective_ts(fvg: FVG) -> datetime:
    return fvg.invalidated_at if fvg.invalidated_at is not None else fvg.confirmed_at


class StateStore:
    """Write side for structure/fvg engines; read side is only via ``as_of``."""

    def __init__(
        self,
        spread_report: SpreadReport | None = None,
        session_engine: SessionEngine | None = None,
        calendar_engine: CalendarEngine | None = None,
    ) -> None:
        """Create an empty store.

        Optional engines back ``median_spread``/``in_window``/``in_blackout`` (D-039);
        each raises ``NotImplementedError`` until wired, same pattern for all three.
        """
        self._swing_versions: dict[str, list[Swing]] = {}
        self._fvg_versions: dict[str, list[FVG]] = {}
        self._bias_events: list[BiasEvent] = []
        self._bos_by_tf: dict[TF, dict[datetime, str]] = defaultdict(dict)
        self._spread_report = spread_report
        self._session_engine = session_engine
        self._calendar_engine = calendar_engine

    def put(self, obj: Swing | FVG | BiasEvent) -> None:
        """Append a new version of a Swing/FVG, or record a BiasEvent."""
        if isinstance(obj, Swing):
            self._swing_versions.setdefault(obj.id, []).append(obj)
        elif isinstance(obj, FVG):
            self._fvg_versions.setdefault(obj.id, []).append(obj)
        elif isinstance(obj, BiasEvent):
            self._bias_events.append(obj)
        else:
            raise TypeError(f"StateStore.put: unsupported object type {type(obj)!r}")

    def invalidate(self, obj_id: str, ts: datetime) -> None:
        """Append a version marking a Swing (taken_at) or FVG (invalidated_at) as of ``ts``."""
        if obj_id in self._fvg_versions:
            latest = self._fvg_versions[obj_id][-1]
            self._fvg_versions[obj_id].append(dc_replace(latest, invalidated_at=ts))
        elif obj_id in self._swing_versions:
            latest = self._swing_versions[obj_id][-1]
            self._swing_versions[obj_id].append(dc_replace(latest, taken_at=ts))
        else:
            raise KeyError(f"no stored object with id {obj_id!r}")

    def as_of(self, ts: datetime) -> MarketContext:
        """Read-only, point-in-time view: nothing with confirmed_at > ts is visible."""
        return MarketContext(store=self, now=ts)

    def all_swings(self, tf: TF | None = None) -> list[Swing]:
        """Latest known version of every swing (engine-side read, NOT point-in-time filtered)."""
        latest = [versions[-1] for versions in self._swing_versions.values()]
        return [s for s in latest if tf is None or s.tf is tf]

    def all_fvgs(self, tf: TF | None = None) -> list[FVG]:
        """Latest known version of every FVG (engine-side read, NOT point-in-time filtered)."""
        latest = [versions[-1] for versions in self._fvg_versions.values()]
        return [f for f in latest if tf is None or f.tf is tf]

    def swings_as_of(self, ts: datetime, tf: TF | None = None) -> list[Swing]:
        """The version of each swing that was actually knowable as of ``ts``."""
        result = []
        for versions in self._swing_versions.values():
            visible = [v for v in versions if _swing_effective_ts(v) <= ts]
            if visible and (tf is None or visible[-1].tf is tf):
                result.append(visible[-1])
        return result

    def fvgs_as_of(self, ts: datetime, tf: TF | None = None) -> list[FVG]:
        """The version of each FVG that was actually knowable as of ``ts``."""
        result = []
        for versions in self._fvg_versions.values():
            visible = [v for v in versions if _fvg_effective_ts(v) <= ts]
            if visible and (tf is None or visible[-1].tf is tf):
                result.append(visible[-1])
        return result

    def record_bos(self, tf: TF, ts: datetime, swing_id: str) -> None:
        """Record that a (confirmed, close-through) BOS happened on ``tf`` at ``ts``."""
        self._bos_by_tf[tf][ts] = swing_id

    def bos_at(self, tf: TF, ts: datetime) -> str | None:
        """The swing_id of a BOS recorded on ``tf`` at exactly ``ts``, if any."""
        return self._bos_by_tf[tf].get(ts)

    def bias_history(self) -> list[BiasEvent]:
        """Full, chronological history of Bias *transitions* recorded so far."""
        return list(self._bias_events)

    def median_spread(self, hour_et: int) -> float:
        """Median spread (USD) for an ET hour, from the SpreadReport wired into this store."""
        if self._spread_report is None:
            raise NotImplementedError(
                "No SpreadReport wired into this StateStore (D-039); construct it with "
                "StateStore(spread_report=...) to use median_spread()/min_stop geometry checks."
            )
        return self._spread_report.median_spread(hour_et)

    def in_window(self, ts: datetime) -> bool:
        """Whether ``ts`` is inside the NY session window (SessionEngine wired in, T3.1)."""
        if self._session_engine is None:
            raise NotImplementedError(
                "No SessionEngine wired into this StateStore (D-039); construct it with "
                "StateStore(session_engine=...) to use in_window()."
            )
        return self._session_engine.in_window(ts)

    def in_blackout(self, ts: datetime) -> bool:
        """Whether ``ts`` is inside a news Blackout, from the CalendarEngine wired in (T3.1)."""
        if self._calendar_engine is None:
            raise NotImplementedError(
                "No CalendarEngine wired into this StateStore (D-039); construct it with "
                "StateStore(calendar_engine=...) to use in_blackout()."
            )
        return self._calendar_engine.in_blackout(ts)


class MarketContext:
    """Read-only, point-in-time view of a StateStore. Valid only for the tick it was built for."""

    def __init__(self, store: StateStore, now: datetime) -> None:
        """Bind to ``store`` as of ``now``. Do not cache across ticks — build fresh each time."""
        self.now = now
        self._store = store

    def bias(self) -> BiasState:
        """The Bias state as of ``now`` (docs/SPEC_V1_FROZEN.md §3)."""
        visible = [e for e in self._store.bias_history() if e.ts <= self.now]
        return visible[-1].state if visible else "neutral"

    def active_fvgs(self, tf: TF, direction: str) -> list[FVG]:
        """Confirmed, not-yet-100%-mitigated FVGs on ``tf``/``direction`` as of ``now``."""
        return [
            f
            for f in self._store.fvgs_as_of(self.now, tf)
            if f.direction == direction
            and f.confirmed_at <= self.now
            and (f.invalidated_at is None or f.invalidated_at > self.now)
        ]

    def confirmed_swings(self, tf: TF, since: datetime) -> list[Swing]:
        """Swings on ``tf`` confirmed in [since, now], oldest first."""
        return sorted(
            (
                s
                for s in self._store.swings_as_of(self.now, tf)
                if since <= s.confirmed_at <= self.now
            ),
            key=lambda s: s.confirmed_at,
        )

    def in_window(self) -> bool:
        """Whether ``now`` is inside the NY session window (T3.1)."""
        return self._store.in_window(self.now)

    def in_blackout(self) -> bool:
        """Whether ``now`` is inside a news blackout (T3.1)."""
        return self._store.in_blackout(self.now)

    def median_spread(self, hour_et: int) -> float:
        """Median spread (USD) for an ET hour, from the SpreadReport wired into the store."""
        return self._store.median_spread(hour_et)
