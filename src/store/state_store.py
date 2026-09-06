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

import bisect
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import datetime
from typing import Literal

from src.core.types import FVG, TF, Swing
from src.data.spread_report import SpreadSource
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


class _OutOfOrderIndexWrite(RuntimeError):
    """Raised when a D-093 supplementary FVG index update would go backwards
    in time -- either the global per-tf confirm index, or a single id's own
    invalidation-interval list.

    D-093 (perf): the ``_fvg_confirm_events``/``_fvg_invalidation_intervals``
    structures (see ``StateStore.__init__``) are supplementary to -- never a
    replacement for -- ``_fvg_versions`` (still the sole source of truth,
    unchanged). They exist purely to avoid an O(all-ids-ever-created) scan on
    every ``active_fvgs()``/``fvgs_as_of()`` call, by exploiting the one
    invariant every real caller already satisfies: ``put()``/``invalidate()``
    are only ever invoked from the bar-close-driven fvg/structure engines,
    which process strictly chronologically -- so each structure is naturally
    sorted/consistent at append time, with no separate sort step required. If
    that invariant is ever violated, the structures would silently return
    wrong results -- so this raises loudly instead of silently sorting,
    coercing, or repairing, exactly like this project's existing fail-loud
    discipline elsewhere (e.g. NewsLoaderError).
    """


class StateStore:
    """Write side for structure/fvg engines; read side is only via ``as_of``."""

    def __init__(
        self,
        spread_report: SpreadSource | None = None,
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
        # D-093 (perf, DECISIONS_LOG): supplementary indexes ONLY -- narrow
        # which fvg_ids active_fvgs()/fvgs_as_of() must resolve, instead of
        # scanning every id ever created. _fvg_versions remains the sole
        # source of truth; both structures below are rebuildable from it and
        # never consulted for anything but candidate-id narrowing.
        #
        # _fvg_confirm_events: per-tf, a (confirmed_at, fvg_id) list, one
        # entry per id (its FIRST ever put()), appended in that first-seen
        # order -- an id's existence-by-ts never changes across later
        # invalidate/reconfirm epochs, so one entry per id is sufficient and
        # exact. See _append_fvg_index_entry for why this ordering keeps
        # active_fvgs()'s iteration order identical to the pre-D-093
        # dict-scan implementation.
        #
        # _fvg_invalidation_intervals: per fvg_id (not per tf -- an id's tf
        # never changes), a list of [start, end_or_None] epochs during which
        # that id was invalidated. Supports the full, general StateStore
        # contract -- confirm -> invalidate -> reconfirm -> invalidate -> ...
        # -- not just one-directional invalidation. Rebuilt in put()/
        # invalidate() by _open_invalidation_interval/_close_invalidation_interval.
        self._fvg_confirm_events: dict[TF, list[tuple[datetime, str]]] = {}
        self._fvg_invalidation_intervals: dict[str, list[list[datetime | None]]] = {}
        self._spread_report = spread_report
        self._session_engine = session_engine
        self._calendar_engine = calendar_engine

    def put(self, obj: Swing | FVG | BiasEvent) -> None:
        """Append a new version of a Swing/FVG, or record a BiasEvent."""
        if isinstance(obj, Swing):
            self._swing_versions.setdefault(obj.id, []).append(obj)
        elif isinstance(obj, FVG):
            existing = self._fvg_versions.setdefault(obj.id, [])
            is_new_id = not existing
            was_invalidated_before = bool(existing) and existing[-1].invalidated_at is not None
            existing.append(obj)
            if is_new_id:
                self._append_fvg_index_entry(
                    self._fvg_confirm_events, obj.tf, obj.confirmed_at, obj.id
                )
            if obj.invalidated_at is not None and not was_invalidated_before:
                self._open_invalidation_interval(obj.id, obj.invalidated_at)
            elif obj.invalidated_at is None and was_invalidated_before:
                self._close_invalidation_interval(obj.id, obj.confirmed_at)
        elif isinstance(obj, BiasEvent):
            if self._bias_events and obj.ts < self._bias_events[-1].ts:
                raise _OutOfOrderIndexWrite(
                    f"StateStore: BiasEvent received out-of-order timestamp {obj.ts!r} < "
                    f"last-recorded {self._bias_events[-1].ts!r}. put() must be called in "
                    "non-decreasing timestamp order for BiasEvents; not silently sorted."
                )
            self._bias_events.append(obj)
        else:
            raise TypeError(f"StateStore.put: unsupported object type {type(obj)!r}")

    def invalidate(self, obj_id: str, ts: datetime) -> None:
        """Append a version marking a Swing (taken_at) or FVG (invalidated_at) as of ``ts``."""
        if obj_id in self._fvg_versions:
            latest = self._fvg_versions[obj_id][-1]
            was_invalidated_before = latest.invalidated_at is not None
            new_version = dc_replace(latest, invalidated_at=ts)
            self._fvg_versions[obj_id].append(new_version)
            if not was_invalidated_before:
                self._open_invalidation_interval(obj_id, ts)
        elif obj_id in self._swing_versions:
            latest = self._swing_versions[obj_id][-1]
            self._swing_versions[obj_id].append(dc_replace(latest, taken_at=ts))
        else:
            raise KeyError(f"no stored object with id {obj_id!r}")

    def _append_fvg_index_entry(
        self, index: dict[TF, list[tuple[datetime, str]]], tf: TF, ts: datetime, fvg_id: str,
    ) -> None:
        """Append ``(ts, fvg_id)`` to ``index[tf]``, fail-loud if that would go backwards.

        D-093: ``put()``/``invalidate()`` are only ever called from the
        bar-close-driven fvg/structure engines, which write strictly
        chronologically -- confirmed by direct code-path review, not
        assumed. Reads via ``as_of``/Prefix-Consistency (AT-1.6, D-041) CAN
        be retroactive; only WRITE order needs to be chronological for the
        bisect-based lookups in ``fvgs_as_of``/``active_fvgs`` to stay
        correct. If that invariant is ever violated, silently accepting the
        out-of-order entry would make those bisect lookups silently wrong --
        so this raises instead of sorting/coercing.
        """
        bucket = index.setdefault(tf, [])
        if bucket and ts < bucket[-1][0]:
            raise _OutOfOrderIndexWrite(
                f"StateStore: FVG confirm index for {tf!r} received out-of-order timestamp "
                f"{ts!r} < last-indexed {bucket[-1][0]!r} (fvg_id={fvg_id!r}). "
                "put()/invalidate() must be called in non-decreasing timestamp order; "
                "this is not silently sorted or coerced."
            )
        bucket.append((ts, fvg_id))

    def _open_invalidation_interval(self, fvg_id: str, ts: datetime) -> None:
        """Record that ``fvg_id`` became invalidated at ``ts`` -- D-093.

        Called only on a not-invalidated -> invalidated transition (the
        caller already checked ``was_invalidated_before`` is False). Opens a
        new ``[ts, None]`` epoch. Fail-loud, not silently coerced, if this
        would go backwards relative to this SAME id's own last-recorded
        interval boundary -- this id's own writes are assumed chronological
        (the same pre-existing assumption ``_fvg_versions[id].append()`` +
        ``[-1]`` access already relies on, not a new one).
        """
        intervals = self._fvg_invalidation_intervals.setdefault(fvg_id, [])
        if intervals and intervals[-1][1] is None:
            raise _OutOfOrderIndexWrite(
                f"StateStore: fvg_id={fvg_id!r} already has an open invalidation "
                f"interval starting {intervals[-1][0]!r} -- cannot open a second one "
                f"at {ts!r} without first closing it (reconfirming). This indicates "
                "invalidate()/put() was called twice in a row without an intervening "
                "reconfirmation, which should be structurally impossible given the "
                "was_invalidated_before guard at every call site."
            )
        last_end = intervals[-1][1] if intervals else None
        if last_end is not None and ts < last_end:
            raise _OutOfOrderIndexWrite(
                f"StateStore: fvg_id={fvg_id!r} invalidated at {ts!r}, which is before "
                f"its own previous reconfirmation at {last_end!r} -- out-of-order write, "
                "not silently sorted or coerced."
            )
        intervals.append([ts, None])

    def _close_invalidation_interval(self, fvg_id: str, ts: datetime) -> None:
        """Record that ``fvg_id`` became active again (reconfirmed) at ``ts`` -- D-093.

        Called only on an invalidated -> not-invalidated transition (the
        caller already checked ``was_invalidated_before`` is True). Closes
        the most recent open ``[start, None]`` epoch by setting its end to
        ``ts``. Fail-loud if there is no open interval to close (an
        inconsistent/impossible state given the call-site guards) or if
        ``ts`` would precede that interval's own start (a nonsensical
        reactivation before its own invalidation).
        """
        intervals = self._fvg_invalidation_intervals.get(fvg_id)
        if not intervals or intervals[-1][1] is not None:
            raise _OutOfOrderIndexWrite(
                f"StateStore: fvg_id={fvg_id!r} transitioned to not-invalidated at "
                f"{ts!r}, but has no open invalidation interval to close. This "
                "indicates an inconsistent internal state, not a value to silently "
                "repair."
            )
        start = intervals[-1][0]
        if ts < start:
            raise _OutOfOrderIndexWrite(
                f"StateStore: fvg_id={fvg_id!r} reconfirmed at {ts!r}, which is before "
                f"its own invalidation at {start!r} -- a reactivation cannot precede "
                "the invalidation it reactivates from; not silently coerced."
            )
        intervals[-1][1] = ts

    def _fvg_invalidated_at(self, fvg_id: str, ts: datetime) -> bool:
        """Whether ``fvg_id`` was inside an invalidated epoch as of ``ts`` -- D-093.

        Scans only this id's OWN (typically 0 or 1, rarely more) invalidation
        intervals -- not the whole registry -- so this stays cheap regardless
        of how many other FVGs exist. Correct for retroactive ``ts`` values
        exactly like ``_fvg_visible_version`` is, since it depends only on
        what has been WRITTEN (chronological, by construction) not on the
        order queries happen to arrive in.
        """
        for start, end in self._fvg_invalidation_intervals.get(fvg_id, ()):
            if start <= ts and (end is None or ts < end):
                return True
        return False

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
        """The version of each FVG that was actually knowable as of ``ts``.

        D-093 (perf): when ``tf`` is given, uses ``_fvg_confirm_events[tf]``
        (bisect on the naturally-sorted-by-write-order confirm index) to
        avoid scanning FVG ids that were never even confirmed by ``ts`` --
        equivalent to, but far cheaper than, the full ``_fvg_versions.values()``
        scan below for a growing registry. Falls back to the original full
        scan when ``tf`` is omitted (no caller does this today, but the
        signature allows it, and there's no per-tf index to bisect in that
        case).
        """
        if tf is None:
            result = []
            for versions in self._fvg_versions.values():
                visible = [v for v in versions if _fvg_effective_ts(v) <= ts]
                if visible:
                    result.append(visible[-1])
            return result

        confirm_index = self._fvg_confirm_events.get(tf, [])
        boundary = bisect.bisect_right(confirm_index, ts, key=lambda entry: entry[0])
        result = []
        for _, fvg_id in confirm_index[:boundary]:
            version = self._fvg_visible_version(fvg_id, ts)
            if version is not None:
                result.append(version)
        return result

    def _fvg_visible_version(self, fvg_id: str, ts: datetime) -> FVG | None:
        """The single version of ``fvg_id`` that was knowable as of ``ts``, or ``None``.

        Same effective-timestamp resolution as the original ``fvgs_as_of``
        inline scan -- extracted as its own method purely so both
        ``fvgs_as_of`` and ``MarketContext.active_fvgs`` (via
        ``_active_fvgs_indexed``) share one, unchanged, per-id resolution
        path. Does not touch KI-003 (intermediate mitigation_pct timing) at
        all -- identical logic to before D-093.
        """
        visible = [v for v in self._fvg_versions[fvg_id] if _fvg_effective_ts(v) <= ts]
        return visible[-1] if visible else None

    def _active_fvgs_indexed(self, ts: datetime, tf: TF, direction: str) -> list[FVG]:
        """D-093 fast path for ``MarketContext.active_fvgs`` -- see its own docstring.

        Narrows candidates via the confirm index (ids confirmed by ``ts``),
        then excludes any id currently inside one of its OWN invalidation
        epochs as of ``ts`` (``_fvg_invalidated_at`` -- correct across
        multiple confirm/invalidate/reconfirm cycles for the same id, unlike
        the rejected v1 design's permanent-exclusion set) before resolving
        the per-id visible version -- avoiding the more expensive per-id
        version-list scan for ids that are excluded. The final per-version
        re-check below duplicates ``MarketContext.active_fvgs``'s own filter
        exactly -- kept as a defensive, exact-parity safety net, not because
        the index narrowing could otherwise be wrong.

        Iterates ``confirm_index`` in its own append order -- the same
        order ``fvg_id`` was first ``put()`` in -- so the result order is
        identical to the pre-D-093 ``_fvg_versions.values()`` dict-iteration
        order (Python dicts preserve insertion order) restricted to the
        same qualifying ids, including a reactivated id, which keeps its
        ORIGINAL creation-order position -- this is the one invariant
        explicitly required before this change was approved (SetupStream
        engages the *first* qualifying FVG it sees).
        """
        confirm_index = self._fvg_confirm_events.get(tf, [])
        boundary = bisect.bisect_right(confirm_index, ts, key=lambda entry: entry[0])

        result = []
        for _, fvg_id in confirm_index[:boundary]:
            if self._fvg_invalidated_at(fvg_id, ts):
                continue
            version = self._fvg_visible_version(fvg_id, ts)
            if version is None:
                continue
            if version.direction != direction:
                continue
            if not (version.confirmed_at <= ts and (version.invalidated_at is None or version.invalidated_at > ts)):
                continue
            result.append(version)
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

    def _bias_state_as_of(self, ts: datetime) -> BiasState:
        """O(log n) equivalent of the current linear scan over _bias_events."""
        idx = bisect.bisect_right(self._bias_events, ts, key=lambda e: e.ts) - 1
        return self._bias_events[idx].state if idx >= 0 else "neutral"

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
        return self._store._bias_state_as_of(self.now)

    def active_fvgs(self, tf: TF, direction: str) -> list[FVG]:
        """Confirmed, not-yet-100%-mitigated FVGs on ``tf``/``direction`` as of ``now``.

        D-093 (perf): delegates to ``StateStore._active_fvgs_indexed``, which
        computes the exact same result (same set, same filtering, same
        iteration order) as the original list-comprehension over
        ``fvgs_as_of`` used to -- see that method's own docstring and
        ``tests/test_state_store_fvg_indexing.py`` for the equivalence
        proof. ``_fvg_versions`` (the source of truth) is unchanged.
        """
        return self._store._active_fvgs_indexed(self.now, tf, direction)

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
