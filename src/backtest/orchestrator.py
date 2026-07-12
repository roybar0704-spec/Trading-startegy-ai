"""Backtest Orchestrator: the two-stage event loop (SPEC S14, ARCHITECTURE.md pseudo-loop).

Stage 1 (every timestamp, in order 1M -> 5M -> 4H, then Ticks -- H2/Race-09:00): every
bar-close/tick event updates State (Structure/FVG/SetupStream/FillSimulator). Stage 2
(once per timestamp, on the now-fully-updated state): SetupStream.step(ctx) always runs
(its own guards need to see every window/blackout transition, even outside the window --
see D-053/D-054); new order creation from its events is gated on
``in_window and not in_blackout`` separately, since "no new Setups/orders in Blackout"
(SPEC S11) is about *creating* things, not about the state machine's own bookkeeping.

Order/Fill wiring per event:
  1. Each of the 3 EntryModel instances (M1/M2/M4) gets one ``on_event`` call (not one
     per arm -- callers sharing an entry model would otherwise trigger it 3x for no
     reason, and M4's internal watch-state must not be touched 3x either).
  2. For each of the 9 arms whose ``arm_id.entry`` produced an intent: apply_sl_anchor
     turns the shared, sl-agnostic intent into this arm's real one, then
     RiskEngine.approve() -> Order | Rejection, exactly as Phase 2 already does.
  3. An approved Order is placed with that arm's own FillSimulator and tracked in
     ``_pending_by_setup`` so a later Setup-level cancellation (window close, Blackout,
     Re-Inversion, S.low-break -- all reported as SetupEvents) can find and cancel it.

M4's ``on_bar_close_1m`` fires separately, once per 1M bar, and is likewise fanned out
to the (up to 3) arms sharing the M4 model.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from src.backtest.context_snapshot import bar_to_json, ifvg_to_json, make_snapshot_row
from src.backtest.portfolio_arm import PortfolioArm
from src.core.types import TF, Bar, Order, Rejection, SetupEvent, Tick
from src.data.spread_report import ExpandingSpreadReport
from src.displacement.model import DisplacementModel
from src.entry.setup_stream import SetupStream
from src.entry.sl_geometry import apply_sl_anchor
from src.execution.cost_model import StaticCostModel
from src.fvg.engine import FVGEngine
from src.journal.duckdb_writer import DuckDBJournal
from src.session.calendar_engine import CalendarEngine
from src.session.session_engine import SessionEngine
from src.store.state_store import StateStore
from src.structure.engine import StructureEngine

_ENTRY_ORDER = {"bar1m": 0, "bar5m": 1, "bar4h": 2, "tick": 3}  # H2: 1M->5M->4H, then Ticks


@dataclass
class RunResult:
    """Summary counters for one run -- full detail lives in the Journal."""

    engaged: int = 0
    reaction_seen: int = 0
    sweep_confirmed: int = 0
    armed: int = 0
    expired: int = 0
    invalidated: int = 0
    no_ifvg: int = 0
    orders_placed: int = 0
    orders_rejected: int = 0
    fills: int = 0
    orders_cancelled: int = 0


@dataclass
class Orchestrator:
    """One run: owns the shared engines and drives all 9 arms off one Setup Stream."""

    bars_1m: list[Bar]
    bars_5m: list[Bar]
    bars_4h: list[Bar]
    ticks: list[Tick]
    session: SessionEngine
    calendar: CalendarEngine
    arms: list[PortfolioArm]
    entry_models: dict[str, object]  # {"M1": M1EntryModel, "M2": ..., "M4": ...}
    displacement_model: DisplacementModel
    displacement_params: dict
    cost_model: StaticCostModel
    sl_buffer_usd: float
    symbol: str = "XAUUSD"
    # Ticks strictly before this run's own timeline (e.g. the 90-day Warm-Up window,
    # SPEC S2/RA-18) used only to warm-start median_spread so day-1 hours aren't empty.
    # Never fed to FillSimulator/SetupStream -- see ExpandingSpreadReport.warm_start (D-049).
    spread_warmup_ticks: list[Tick] = field(default_factory=list)
    journal: DuckDBJournal | None = None
    run_id: str = "run"
    # Run identity (Stage A / B-1, D-068, closes KI-018): plain injected values --
    # this Orchestrator never computes them (D-037 data/config-agnostic); real
    # resolution (config_hash(), git detection) lives in run_builder only. Defaults
    # preserve the pre-B-1 KI-018 placeholder behavior for any caller that builds
    # an Orchestrator directly, bypassing build_orchestrator (e.g. tests/fixtures).
    config_hash: str = "unknown"
    code_version: str = "unknown"
    data_version: str = "unknown"
    split_type: str = "unknown"
    seed: int | None = None

    store: StateStore = field(init=False)
    structure_4h: StructureEngine = field(init=False)
    fvg_4h: FVGEngine = field(init=False)
    setup_stream: SetupStream = field(init=False)
    spread_tracker: ExpandingSpreadReport = field(init=False)
    _pending_by_setup: dict[str, list[tuple[PortfolioArm, str]]] = field(init=False)
    # Engagement snapshots are captured before `setups` can legally exist (outcome
    # is NOT NULL -- unknown at Engagement) -- held here until the Setup's terminal
    # model-agnostic event writes the setups row they FK to. See _finalize_setup_journal.
    _pending_engagement_snapshots: dict[str, dict] = field(init=False)

    def __post_init__(self) -> None:
        """Wire the shared engines. One StateStore/SetupStream for the whole run."""
        self.spread_tracker = ExpandingSpreadReport.warm_start(
            symbol=self.symbol, ticks=self.spread_warmup_ticks
        )
        self.store = StateStore(
            spread_report=self.spread_tracker, session_engine=self.session,
            calendar_engine=self.calendar,
        )
        self.structure_4h = StructureEngine(TF.H4, is_bias_source=True)
        self.fvg_4h = FVGEngine(
            TF.H4, displacement_model=self.displacement_model,
            displacement_params=self.displacement_params,
        )
        self.setup_stream = SetupStream()
        self._pending_by_setup = defaultdict(list)
        self._pending_engagement_snapshots = {}
        # Every EntryModel's get_setup must resolve through *this* run's SetupStream --
        # there is no legitimate reason for a caller to wire a different one, and
        # leaving this to every caller was pure duplicated glue (KI-016 cleanup).
        for model in self.entry_models.values():
            model.get_setup = self.setup_stream.get_setup

    def _write_run_identity_rows(self) -> None:
        """Write experiments/runs/portfolios once, before anything that FKs to them.

        KI-018 (closed, D-068): config_hash/code_version/data_version/split_type/seed
        are not computed here -- this Orchestrator stays data/config-agnostic
        (D-037); real resolution happens in run_builder (build_orchestrator), which
        passes the resolved values in as plain fields (self.config_hash etc.,
        defaulting to the pre-B-1 "unknown"/None placeholders for any caller that
        builds an Orchestrator directly). Without this method, *nothing* referencing
        portfolios/runs/experiments could ever be journaled -- found while testing
        T3.6 against real FK constraints for the first time (D-059):
        setups/portfolios/runs/experiments had never actually been written.
        """
        if self.journal is None:
            return
        experiment_id = f"{self.run_id}-exp"
        all_ts = [b.close_ts for b in (*self.bars_1m, *self.bars_5m, *self.bars_4h)]
        period_start = min(all_ts).date() if all_ts else date.today()
        period_end = max(all_ts).date() if all_ts else date.today()
        created_at = min(all_ts) if all_ts else datetime.now(UTC)

        self.journal.record(
            "experiments",
            {
                "experiment_id": experiment_id, "name": self.run_id,
                "hypothesis": "n/a -- Orchestrator run, not a declared Experiment (KI-018)",
                "objective_fn": "n/a",
                "declared_grid": json.dumps(
                    {
                        "entry_models": sorted({a.arm_id.entry for a in self.arms}),
                        "sl_anchors": sorted({a.arm_id.sl_anchor for a in self.arms}),
                    }
                ),
                "holdout_range": json.dumps(None), "created_at": created_at,
            },
        )
        self.journal.record(
            "runs",
            {
                "run_id": self.run_id, "experiment_id": experiment_id,
                "config_hash": self.config_hash, "code_version": self.code_version,
                "data_version": self.data_version, "period_start": period_start,
                "period_end": period_end, "split_type": self.split_type, "seed": self.seed,
                "created_at": created_at,
            },
        )
        for arm in self.arms:
            self.journal.record(
                "portfolios",
                {
                    "portfolio_id": arm.portfolio.portfolio_id, "run_id": self.run_id,
                    "entry_model": arm.arm_id.entry, "sl_anchor": arm.arm_id.sl_anchor,
                    "initial_equity": arm.portfolio.initial_equity,
                },
            )

    def run(self) -> RunResult:
        """Process the full merged timeline; return summary counters."""
        self._write_run_identity_rows()
        result = RunResult()
        was_in_window = False
        was_in_blackout = False

        for ts, group in self._merged_timeline():
            for _, _, kind, obj in group:
                if kind == "bar4h":
                    self._apply_4h(obj)
                elif kind == "bar5m":
                    self._apply_5m(obj)
                elif kind == "bar1m":
                    self._apply_1m(obj)
                elif kind == "tick":
                    self._apply_tick(obj, result)

            in_window = self.store.in_window(ts)
            in_blackout = self.store.in_blackout(ts)

            if was_in_window and not in_window:
                self._cancel_all_pending(ts, "expired", result)
            if not was_in_blackout and in_blackout:
                self._cancel_all_pending(ts, "blocked_news", result)

            ctx = self.store.as_of(ts)
            for event in self.setup_stream.step(ctx):
                self._count_event(result, event)
                if event.kind == "engaged":
                    self._buffer_engagement_snapshot(ts, ctx, event.setup_id)
                elif event.kind == "armed" and not event.post_arm:
                    self._finalize_setup_journal(event.setup_id, ts)
                    self._record_snapshot("armed", ts, ctx, event.setup_id)
                    if in_window and not in_blackout:
                        self._open_orders_for_event(event, ctx, result)
                elif event.kind in ("invalidated", "expired", "no_ifvg"):
                    if not event.post_arm:
                        self._finalize_setup_journal(event.setup_id, ts)
                    self._cancel_for_setup(ts, event.setup_id, event.kind, result)

            was_in_window, was_in_blackout = in_window, in_blackout

        if self.journal is not None:
            self.journal.close()
        return result

    # ---- Stage 1: bar-close / tick application -----------------------------

    def _apply_4h(self, bar: Bar) -> None:
        self.structure_4h.step(bar, self.store)
        self.fvg_4h.step_bar_close(bar, self.store)
        self._record_bias_if_journaled(bar.close_ts)

    def _apply_5m(self, bar: Bar) -> None:
        self.setup_stream.on_bar_close(bar, self.store)

    def _apply_1m(self, bar: Bar) -> None:
        self.fvg_4h.on_price(bar.close_ts, bar.l, self.store)
        self.fvg_4h.on_price(bar.close_ts, bar.h, self.store)
        self.setup_stream.on_bar_close(bar, self.store)
        m4 = self.entry_models.get("M4")
        if m4 is not None:
            ctx = self.store.as_of(bar.close_ts)
            # "No new orders" in Blackout (SPEC S11) applies here too. Skip the call
            # entirely rather than discard its result: on_bar_close_1m has the side
            # effect of consuming the watched Setup the moment it finds a rejection
            # candle, so calling it during a blocked period and throwing the intent
            # away would burn M4's one chance instead of leaving it watching for a
            # later, valid rejection candle once the window/Blackout clears.
            if ctx.in_window() and not ctx.in_blackout():
                intent = m4.on_bar_close_1m(bar, ctx)
                if intent is not None:
                    self._route_intent("M4", intent, ctx, result=None)

    def _apply_tick(self, tick: Tick, result: RunResult) -> None:
        # Grow the point-in-time spread tracker first (D-049): this tick's own spread
        # must already be included by the time Stage 2 queries median_spread() for the
        # same timestamp, and this ordering has no bearing on fill simulation below.
        self.spread_tracker.update(tick)
        for arm in self.arms:
            for fill in arm.fill_sim.on_tick(tick):
                self._on_fill(arm, fill, result)

    def _record_bias_if_journaled(self, ts: datetime) -> None:
        if self.journal is None:
            return
        history = self.store.bias_history()
        if history and history[-1].ts == ts:
            ev = history[-1]
            self.journal.record(
                "bias_history",
                {"run_id": self.run_id, "ts": ts, "state": ev.state, "trigger_bos": None},
            )

    def _record_snapshot(
        self, kind: str, ts: datetime, ctx, setup_id: str, order: Order | None = None,
    ) -> None:
        """Record one context_snapshots row.

        engagement/armed (order=None, model-agnostic) or entry/exit (order
        required, per-arm) -- see src/backtest/context_snapshot.py (D-058).
        """
        if self.journal is None:
            return
        setup = self.setup_stream.get_setup(setup_id)
        self.journal.record(
            "context_snapshots", make_snapshot_row(kind, ts, ctx, setup, order)
        )

    def _buffer_engagement_snapshot(self, ts: datetime, ctx, setup_id: str) -> None:
        """Build the engagement snapshot now, but hold it for later.

        Its content is correctly point-in-time already -- it's only the *write* that
        waits: ``context_snapshots.setup_id`` FKs to ``setups``, and
        ``setups.outcome`` is NOT NULL, so that row cannot exist yet at Engagement.
        Flushed by ``_finalize_setup_journal`` once the Setup reaches its first
        model-agnostic terminal event.
        """
        if self.journal is None:
            return
        setup = self.setup_stream.get_setup(setup_id)
        self._pending_engagement_snapshots[setup_id] = make_snapshot_row(
            "engagement", ts, ctx, setup
        )

    def _finalize_setup_journal(self, setup_id: str, ts: datetime) -> None:
        """Write this Setup's one ``setups`` row and flush its buffered snapshot.

        Only possible now that the Setup's model-agnostic outcome is finally known.
        Every other Journal write that FKs to ``setups`` (orders, setup_arm_outcomes,
        context_snapshots) happens at or after this same event, so this must run
        first among them -- callers order it that way (see ``run()``).
        """
        if self.journal is None:
            return
        setup = self.setup_stream.get_setup(setup_id)
        self.journal.record(
            "setups",
            {
                "setup_id": setup.id, "run_id": self.run_id, "direction": setup.direction,
                "fvg_id": setup.fvg_id, "engagement_ts": setup.engagement_ts,
                "r_bar": json.dumps(bar_to_json(setup.r_bar)),
                "s_bar": json.dumps(bar_to_json(setup.s_bar)),
                "ifvg": json.dumps(ifvg_to_json(setup.ifvg)), "ts_flag": setup.ts_flag,
                "same_zone_reentry": setup.same_zone_reentry, "score": setup.score,
                "outcome": setup.outcome, "outcome_reason": setup.outcome_reason,
                "state_log": "[]",
            },
        )
        pending = self._pending_engagement_snapshots.pop(setup_id, None)
        if pending is not None:
            self.journal.record("context_snapshots", pending)

    # ---- Stage 2: setup-event -> order flow --------------------------------

    def _count_event(self, result: RunResult, event: SetupEvent) -> None:
        if event.post_arm:
            return  # counted once already at the original (pre-arm) event
        current = getattr(result, event.kind)
        setattr(result, event.kind, current + 1)

    def _open_orders_for_event(self, event: SetupEvent, ctx, result: RunResult) -> None:
        for model_id, model in self.entry_models.items():
            intent = model.on_event(event, ctx)
            if intent is not None:
                self._route_intent(model_id, intent, ctx, result)

    def _route_intent(self, model_id: str, intent, ctx, result: RunResult | None) -> None:
        setup = self.setup_stream.get_setup(intent.setup_id)
        for arm in self.arms:
            if arm.arm_id.entry != model_id:
                continue
            final_intent = apply_sl_anchor(intent, arm.arm_id.sl_anchor, setup, self.sl_buffer_usd)
            outcome = arm.risk.approve(final_intent, ctx)
            self._handle_approval(arm, outcome, ctx.now, result)

    def _handle_approval(self, arm: PortfolioArm, outcome: Order | Rejection, ts, result) -> None:
        if isinstance(outcome, Rejection):
            if result is not None:
                result.orders_rejected += 1
            self._record_arm_outcome(outcome.setup_id, arm, outcome.reason, order_id=None)
            return
        arm.fill_sim.place(outcome, arm.portfolio.portfolio_id)
        self._pending_by_setup[outcome.setup_id].append((arm, outcome.order_id))
        if result is not None:
            result.orders_placed += 1
        # No Journal write here, for *either* orders or setup_arm_outcomes (D-060):
        # both are append-only, single-row-per-key tables (order_id / (setup_id,
        # portfolio_id)) -- an interim "pending" row would need a later UPDATE to
        # reach its real outcome, which the append-only design forbids. Each is
        # written exactly once, at whichever event makes this order/arm reach its
        # actual terminal state: filled+closed (_close_trade), or cancelled
        # (_cancel_for_setup) -- see KI-019 for the one edge case this leaves open.

    def _record_arm_outcome(
        self, setup_id: str, arm: PortfolioArm, outcome: str, order_id: str | None,
    ) -> None:
        if self.journal is None:
            return
        self.journal.record(
            "setup_arm_outcomes",
            {
                "setup_id": setup_id, "portfolio_id": arm.portfolio.portfolio_id,
                "outcome": outcome, "outcome_reason": None, "order_id": order_id,
                "state_log": "[]",
            },
        )

    def _on_fill(self, arm: PortfolioArm, fill, result: RunResult) -> None:
        result.fills += 1
        if fill.kind in ("limit_entry", "market_entry"):
            ny_date = self.session.ny_date(fill.ts)
            arm.portfolio.record_fill(ny_date)
            self._write_filled_order(arm, fill)
        else:
            self._close_trade(arm, fill)

    def _write_filled_order(self, arm: PortfolioArm, fill) -> None:
        if self.journal is None:
            return
        order = arm.fill_sim.get_order(fill.order_id)
        self.journal.record(
            "orders",
            {
                "order_id": order.order_id, "setup_id": order.setup_id,
                "portfolio_id": order.portfolio_id, "otype": order.otype,
                "side": order.side, "price": order.price, "sl": order.sl, "tp": order.tp,
                "units": order.units, "placed_at": order.placed_at,
                "valid_until": order.valid_until, "status": order.status,
                "filled_at": order.filled_at, "fill_price": order.fill_price,
                "cancel_reason": None,
            },
        )
        self._record_snapshot("entry", fill.ts, self.store.as_of(fill.ts), order.setup_id, order)

    def _close_trade(self, arm: PortfolioArm, fill) -> None:
        """Exit fill: compute R-multiple/P&L, journal the trade, update realized equity.

        KI-006 -- this is the wiring the Research Readiness Review checklist requires.
        """
        order = arm.fill_sim.get_order(fill.order_id)
        entry_px, exit_px, sl_px, tp_px = order.fill_price, fill.price, order.sl, order.tp
        long = order.side == "buy"
        price_pnl = order.units * (
            (exit_px - entry_px) if long else (entry_px - exit_px)
        )
        commission = self.cost_model.commission(order.units)
        net_pnl = price_pnl - commission
        arm.portfolio.apply_realized_pnl(net_pnl)

        risk_per_unit = (entry_px - sl_px) if long else (sl_px - entry_px)
        result_r = (price_pnl / order.units) / risk_per_unit if risk_per_unit > 0 else 0.0

        if self.journal is not None:
            exit_kind = {"sl_exit": "sl", "tp_exit": "tp", "gap_through_sl_exit": "gap_through_sl"}
            self.journal.record(
                "trades",
                {
                    "trade_id": f"TRADE-{order.order_id}", "order_id": order.order_id,
                    "portfolio_id": arm.portfolio.portfolio_id, "entry_ts": order.filled_at,
                    "exit_ts": fill.ts, "entry_px": entry_px, "exit_px": exit_px,
                    "sl_px": sl_px, "tp_px": tp_px, "exit_kind": exit_kind[fill.kind],
                    "result_r": result_r, "mae_r": None, "mfe_r": None,  # KI-013 (T4.2)
                    "duration_min": int((fill.ts - order.filled_at).total_seconds() / 60),
                    # cost_spread/cost_slippage: not yet separable from fill price at this
                    # layer -- KI-012, deferred to Phase 4's Statistics Engine (T4.2), which
                    # already owns full cost attribution/MAE/MFE. tag_*: same deferral.
                    "cost_spread": 0.0, "cost_slippage": 0.0, "cost_commission": commission,
                    "tag_overnight": False, "tag_weekend": False, "tag_news_cross": False,
                    "tag_concurrent": False, "tag_bias_flip": False,
                    "hour_bucket_et": self.session.local(order.filled_at).hour,
                },
            )
            self._record_snapshot(
                "exit", fill.ts, self.store.as_of(fill.ts), order.setup_id, order
            )
            # orders row for this order_id already exists (written at fill time,
            # _write_filled_order) -- FK-safe to record the arm's terminal outcome now.
            self._record_arm_outcome(order.setup_id, arm, "closed", order_id=order.order_id)

    def _cancel_all_pending(self, ts: datetime, reason: str, result: RunResult) -> None:
        for setup_id in list(self._pending_by_setup.keys()):
            self._cancel_for_setup(ts, setup_id, reason, result)

    def _cancel_for_setup(
        self, ts: datetime, setup_id: str, reason: str, result: RunResult,
    ) -> None:
        pending = self._pending_by_setup.pop(setup_id, [])
        for arm, order_id in pending:
            # `_pending_by_setup` is never trimmed as individual orders fill (only
            # popped whole, here) -- an entry recorded at placement may have already
            # filled by the time a *later* cancellation event fires for this setup.
            # A filled order resolves its own outcome via _close_trade ("closed"),
            # never via cancellation -- skip it, or this would both mis-record its
            # outcome as `reason` and collide with _close_trade's PK write later.
            if arm.fill_sim.get_order(order_id).status != "pending":
                continue
            arm.fill_sim.cancel(order_id, reason)
            result.orders_cancelled += 1
            # Write the cancelled orders row *before* the arm outcome that FKs to it.
            self._write_cancelled_order(arm, order_id)
            self._record_arm_outcome(setup_id, arm, reason, order_id=order_id)

    def _write_cancelled_order(self, arm: PortfolioArm, order_id: str) -> None:
        if self.journal is None:
            return
        order = arm.fill_sim.get_order(order_id)
        if order.status != "cancelled":
            return  # already filled by the time the cancel arrived -- no-op in FillSimulator
        self.journal.record(
            "orders",
            {
                "order_id": order.order_id, "setup_id": order.setup_id,
                "portfolio_id": order.portfolio_id, "otype": order.otype,
                "side": order.side, "price": order.price, "sl": order.sl, "tp": order.tp,
                "units": order.units, "placed_at": order.placed_at,
                "valid_until": order.valid_until, "status": order.status,
                "filled_at": None, "fill_price": None, "cancel_reason": order.cancel_reason,
            },
        )

    # ---- merged timeline ----------------------------------------------------

    def _merged_timeline(self):
        events: list[tuple[datetime, int, str, object]] = []
        for b in self.bars_1m:
            events.append((b.close_ts, _ENTRY_ORDER["bar1m"], "bar1m", b))
        for b in self.bars_5m:
            events.append((b.close_ts, _ENTRY_ORDER["bar5m"], "bar5m", b))
        for b in self.bars_4h:
            events.append((b.close_ts, _ENTRY_ORDER["bar4h"], "bar4h", b))
        for t in self.ticks:
            events.append((t.ts, _ENTRY_ORDER["tick"], "tick", t))
        events.sort(key=lambda e: (e[0], e[1]))

        i = 0
        while i < len(events):
            ts = events[i][0]
            group = []
            while i < len(events) and events[i][0] == ts:
                group.append(events[i])
                i += 1
            yield ts, group
