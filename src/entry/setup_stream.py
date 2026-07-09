"""Setup Stream — the model-agnostic Entry State Machine.

SPEC_V1_FROZEN.md S6-S7/S14 + docs/trigger_spec_state_machine_v1_1.md S1-S3.
One instance for the whole run; identical behavior for all 9 portfolios
(D-052) -- nothing here reads/writes anything portfolio-specific.

Two-method split (user-approved, Option B): ``on_bar_close`` mirrors
StructureEngine/FVGEngine's existing pattern -- it mutates internal
per-candidate state (R/S bar tracking, iFVG candidate pool, Engagement
detection) and buffers any resulting ``SetupEvent``s. ``MarketContext``'s
signature is untouched. ``step(ctx)`` (Stage 2, called once per timestamp
per ARCHITECTURE.md's two-stage loop) evaluates the ctx-dependent
Setup-level guards (Bias-flip, Mitigation-100%, window-close) that cannot
be evaluated from a bar-close event alone, then drains and returns
whatever events accumulated since the last call -- this is what makes
processing order-independent within one timestamp (H2/Race-09:00): every
bar-close effect for a given instant lands in the buffer before any
guard runs or any event is reported.

``armed`` is model-agnostic and terminal for ``Setup.outcome`` (D-052):
once reached, this Setup's own story is over. A later Re-Inversion or
S.low-break of the chosen iFVG still gets reported (so the Orchestrator
can cancel any not-yet-filled per-arm pending orders), but as a
``post_arm=True`` event that leaves ``Setup.outcome == "armed"`` alone --
only ``setup_arm_outcomes`` (per-arm) rows change from that point on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from itertools import count
from typing import Literal

from src.core.rolling import BarWindow
from src.core.types import FVG, IFVG, TF, Bar, Setup, SetupEvent, Side
from src.store.state_store import MarketContext, StateStore

_ACTIVE_STATES = ("ZONE_ENGAGED", "REACTION_SEEN", "SWEEP_CONFIRMED", "AWAITING_IFVG")


@dataclass
class _IFVGCandidate:
    """A raw 1M gap pattern that might later become the chosen (armed) iFVG."""

    top: float
    bottom: float
    formed_at: datetime
    inverted_at: datetime | None = None


@dataclass
class _Candidate:
    """Mutable tracking state for one in-flight Setup."""

    setup: Setup
    fvg: FVG  # the 4H FVG this Setup engaged -- top/bottom are immutable once created
    window: BarWindow = field(default_factory=lambda: BarWindow(3))
    ifvg_pool: list[_IFVGCandidate] = field(default_factory=list)
    dead: bool = False  # reached a Setup-level terminal outcome this pass; drop after draining


def _pool(bar: Bar, direction: Side) -> float:
    """R's liquidity level ("Pool"): the wick extreme the S candle must take out."""
    return bar.l if direction == "long" else bar.h


def _qualifies_as_r(bar: Bar, fvg: FVG, direction: Side) -> bool:
    if direction == "long":
        in_zone = bar.l <= fvg.top
        body_with_zone = bar.c > bar.o
        has_wick = bar.l < min(bar.o, bar.c)
    else:
        in_zone = bar.h >= fvg.bottom
        body_with_zone = bar.c < bar.o
        has_wick = bar.h > max(bar.o, bar.c)
    return in_zone and body_with_zone and has_wick


def _qualifies_as_s(bar: Bar, r_bar: Bar, direction: Side) -> bool:
    pool = _pool(r_bar, direction)
    if direction == "long":
        return bar.l < pool and bar.c > pool
    return bar.h > pool and bar.c < pool


def _closed_through_r(bar: Bar, r_bar: Bar, direction: Side) -> bool:
    pool = _pool(r_bar, direction)
    return bar.c < pool if direction == "long" else bar.c > pool


def _ifvg_candidate_range(c1: Bar, c3: Bar, direction: Side) -> tuple[float, float] | None:
    """(bottom, top) if [c1, c3] forms a valid iFVG candidate for ``direction``, else None.

    Long: candidate must be a *bearish* 1M gap (``c1.low > c3.high``) -- the thing that
    later inverts upward. Short is the exact mirror (bullish gap, inverts downward).
    """
    if direction == "long":
        if c1.l > c3.h:
            return c3.h, c1.l
    elif c1.h < c3.l:
        return c1.h, c3.l
    return None


def _closes_beyond(bar: Bar, top: float, bottom: float, direction: Side) -> bool:
    """Full-body close through the candidate's edge (Wick-through = nothing, S2.2)."""
    return bar.c > top if direction == "long" else bar.c < bottom


class SetupStream:
    """One model-agnostic State Machine instance for the whole run."""

    def __init__(self) -> None:
        """Create an empty stream; no Setups tracked yet."""
        self._active: dict[str, _Candidate] = {}
        self._finished: dict[str, Setup] = {}
        self._engaged_fvg_ids: set[str] = set()
        self._ever_engaged_fvg_ids: set[str] = set()
        self._pending: list[SetupEvent] = []
        self._seq = count(1)

    def on_bar_close(self, bar: Bar, store: StateStore) -> None:
        """Feed one closed bar (1M or 5M); mutates internal state, buffers any events."""
        if bar.tf == TF.M5:
            self._on_5m_close(bar, store)
        elif bar.tf == TF.M1:
            self._on_1m_close(bar, store)

    def step(self, ctx: MarketContext) -> list[SetupEvent]:
        """Evaluate ctx-dependent guards, then drain and return this tick's events."""
        self._finished.clear()  # last tick's callers have had their chance at get_setup()
        for candidate in list(self._active.values()):
            if candidate.dead:
                continue
            self._check_guards(candidate, ctx)
        drained, self._pending = self._pending, []
        for setup_id in [sid for sid, c in self._active.items() if c.dead]:
            self._finished[setup_id] = self._active.pop(setup_id).setup
        return drained

    def get_setup(self, setup_id: str) -> Setup:
        """The full Setup record (r_bar/s_bar/ifvg included).

        Valid for active Setups, and for ones that just went terminal during the most
        recent ``step()`` call.
        """
        if setup_id in self._active:
            return self._active[setup_id].setup
        return self._finished[setup_id]

    def active_setups(self) -> list[Setup]:
        """Every Setup still being tracked (any non-terminal or ARMED state), unordered."""
        return [c.setup for c in self._active.values()]

    # ---- Stage 1: bar-close bookkeeping -----------------------------------

    def _on_1m_close(self, bar: Bar, store: StateStore) -> None:
        ctx_now = store.as_of(bar.close_ts)
        bias = ctx_now.bias()
        if bias != "neutral" and not ctx_now.in_blackout():
            # Engagement is allowed before the window opens (SPEC S6 H1) -- unlike
            # R/S/Inversion below, no in_window() gate here. Blackout does block new
            # Setups outright (SPEC S11: "no new Setups"), unlike window which only
            # restricts R/S/Inversion.
            direction: Side = "long" if bias == "bullish" else "short"
            fvg_direction = "bull" if direction == "long" else "bear"
            for fvg in ctx_now.active_fvgs(TF.H4, fvg_direction):
                if fvg.id in self._engaged_fvg_ids:
                    continue
                touched = bar.l <= fvg.top if direction == "long" else bar.h >= fvg.bottom
                if touched:
                    self._engage(fvg, direction, bar.close_ts)

        in_window = ctx_now.in_window()
        for candidate in self._active.values():
            if candidate.dead:
                continue
            if self._s_low_broken(candidate, bar):
                self._report_s_low_break(candidate, bar.close_ts)
                continue
            if candidate.setup.state in _ACTIVE_STATES:
                self._track_ifvg_candidates(candidate, bar, in_window)
            elif candidate.setup.state == "ARMED":
                self._check_post_arm_reinversion(candidate, bar)

    def _s_low_broken(self, candidate: _Candidate, bar: Bar) -> bool:
        """Mid < S.low (S2.5): the Sweep's premise broke -- only meaningful once S exists."""
        s_bar = candidate.setup.s_bar
        if s_bar is None:
            return False
        pool = _pool(s_bar, candidate.setup.direction)
        return bar.l < pool if candidate.setup.direction == "long" else bar.h > pool

    def _report_s_low_break(self, candidate: _Candidate, ts: datetime) -> None:
        setup = candidate.setup
        post_arm = setup.state == "ARMED"
        if not post_arm:
            setup.outcome = "invalidated"
            setup.outcome_reason = "s_low_break"
        self._pending.append(
            SetupEvent(
                kind="invalidated", setup_id=setup.id, ts=ts,
                reason="s_low_break", post_arm=post_arm,
            )
        )
        candidate.dead = True
        self._engaged_fvg_ids.discard(setup.fvg_id)

    def _engage(self, fvg: FVG, direction: Side, ts: datetime) -> None:
        setup_id = f"SETUP-{next(self._seq)}"
        setup = Setup(
            id=setup_id,
            direction=direction,
            fvg_id=fvg.id,
            state="ZONE_ENGAGED",
            engagement_ts=ts,
            same_zone_reentry=fvg.id in self._ever_engaged_fvg_ids,
        )
        self._active[setup_id] = _Candidate(setup=setup, fvg=fvg)
        self._engaged_fvg_ids.add(fvg.id)
        self._ever_engaged_fvg_ids.add(fvg.id)
        self._pending.append(SetupEvent(kind="engaged", setup_id=setup_id, ts=ts))

    def _track_ifvg_candidates(self, candidate: _Candidate, bar: Bar, in_window: bool) -> None:
        window = candidate.window.push(bar)
        if len(window) == 3:
            c1, _c2, c3 = window
            rng = _ifvg_candidate_range(c1, c3, candidate.setup.direction)
            if rng is not None:
                bottom, top = rng
                candidate.ifvg_pool.append(
                    _IFVGCandidate(top=top, bottom=bottom, formed_at=c3.close_ts)
                )

        just_inverted = []
        for cand in candidate.ifvg_pool:
            if cand.inverted_at is None and _closes_beyond(
                bar, cand.top, cand.bottom, candidate.setup.direction
            ):
                cand.inverted_at = bar.close_ts
                just_inverted.append(cand)

        # Inversion (the entry itself) must land inside the window (SPEC S6 H1) --
        # candidates keep forming/inverting-tracking regardless, only arming is gated.
        if candidate.setup.state == "AWAITING_IFVG" and just_inverted and in_window:
            chosen = (
                max(just_inverted, key=lambda c: c.top)
                if candidate.setup.direction == "long"
                else min(just_inverted, key=lambda c: c.bottom)
            )
            candidate.setup.state = "ARMED"
            candidate.setup.ifvg = IFVG(
                top=chosen.top, bottom=chosen.bottom,
                formed_at=chosen.formed_at, inversion_ts=bar.close_ts,
            )
            candidate.setup.outcome = "armed"
            self._pending.append(
                SetupEvent(
                    kind="armed", setup_id=candidate.setup.id, ts=bar.close_ts,
                    ifvg=candidate.setup.ifvg, inversion_close=bar.c,
                )
            )

    def _check_post_arm_reinversion(self, candidate: _Candidate, bar: Bar) -> None:
        """Re-Inversion of the *chosen* iFVG (S2.5).

        Setup.outcome stays 'armed' (D-052) -- this only signals the Orchestrator to
        cancel any not-yet-filled per-arm orders.
        """
        chosen = candidate.setup.ifvg
        if chosen is None:
            return
        re_inverted = (
            bar.c < chosen.bottom if candidate.setup.direction == "long" else bar.c > chosen.top
        )
        if re_inverted:
            self._pending.append(
                SetupEvent(
                    kind="invalidated", setup_id=candidate.setup.id, ts=bar.close_ts,
                    reason="re_inversion", post_arm=True,
                )
            )
            candidate.dead = True
            self._engaged_fvg_ids.discard(candidate.setup.fvg_id)

    def _on_5m_close(self, bar: Bar, store: StateStore) -> None:
        in_window = store.as_of(bar.close_ts).in_window()
        for candidate in self._active.values():
            setup = candidate.setup
            if candidate.dead or setup.state not in ("ZONE_ENGAGED", "REACTION_SEEN"):
                continue
            self._track_r_and_s(candidate, bar, in_window)

    def _track_r_and_s(self, candidate: _Candidate, bar: Bar, in_window: bool) -> None:
        """R's close and S's close must both land inside the window (SPEC S6 H1).

        The Close-Through reset back to ZONE_ENGAGED is a rejection, not a new
        formation, so it isn't gated the same way.
        """
        setup = candidate.setup

        if in_window and setup.state == "REACTION_SEEN" and setup.r_bar is not None:
            if _qualifies_as_s(bar, setup.r_bar, setup.direction):
                setup.s_bar = bar
                setup.state = "SWEEP_CONFIRMED"
                self._pending.append(
                    SetupEvent(kind="sweep_confirmed", setup_id=setup.id, ts=bar.close_ts)
                )
                setup.state = "AWAITING_IFVG"
                return

        if in_window and _qualifies_as_r(bar, candidate.fvg, setup.direction):
            setup.r_bar = bar
            if setup.state != "REACTION_SEEN":
                setup.state = "REACTION_SEEN"
                self._pending.append(
                    SetupEvent(kind="reaction_seen", setup_id=setup.id, ts=bar.close_ts)
                )
            return

        if setup.state == "REACTION_SEEN" and setup.r_bar is not None:
            if _closed_through_r(bar, setup.r_bar, setup.direction):
                setup.state = "ZONE_ENGAGED"
                setup.r_bar = None

    # ---- Stage 2: ctx-dependent guards -------------------------------------

    def _check_guards(self, candidate: _Candidate, ctx: MarketContext) -> None:
        setup = candidate.setup
        if setup.state == "ARMED":
            # Model-agnostic story already over (D-052) -- outcome stays 'armed' regardless.
            # Retire from active tracking once the window closes: every per-arm order tied to
            # this Setup is necessarily resolved (filled or cancelled, SPEC S10) by then, so
            # post-arm Re-Inversion tracking no longer has anything left to protect.
            if not ctx.in_window():
                candidate.dead = True
                self._engaged_fvg_ids.discard(setup.fvg_id)
            return

        fvg_direction = "bull" if setup.direction == "long" else "bear"
        active_ids = {f.id for f in ctx.active_fvgs(TF.H4, fvg_direction)}
        mitigated = setup.fvg_id not in active_ids

        bias = ctx.bias()
        bias_ok = (bias == "bullish") if setup.direction == "long" else (bias == "bearish")

        if mitigated or not bias_ok:
            reason = "mitigation_100" if mitigated else "bias_flip"
            self._finish(candidate, "invalidated", reason, ctx.now)
            return

        if not ctx.in_window():
            reason_kind = "no_ifvg" if setup.state == "AWAITING_IFVG" else "expired"
            self._finish(candidate, reason_kind, None, ctx.now)

    def _finish(
        self, candidate: _Candidate, outcome: Literal["invalidated", "expired", "no_ifvg"],
        reason: str | None, ts: datetime,
    ) -> None:
        setup = candidate.setup
        setup.outcome = outcome
        setup.outcome_reason = reason
        self._pending.append(
            SetupEvent(kind=outcome, setup_id=setup.id, ts=ts, reason=reason)
        )
        candidate.dead = True
        self._engaged_fvg_ids.discard(setup.fvg_id)
