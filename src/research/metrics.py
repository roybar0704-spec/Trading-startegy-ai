"""Strategy-agnostic Metrics Engine (Research System, Phase 1).

Reads persisted results for one isolated portfolio (db/schema.sql's
``portfolios`` table -- one entry_model x sl_anchor combination that owns
its own P&L, per PortfolioArm's own "one of the 9 isolated portfolios"
docstring, src/backtest/portfolio_arm.py) and computes generic performance
measurements from the Journal's own tables.

Never executes a backtest. Never writes. Never imports Strategy A, its
SetupStream, EntryModel, structure/FVG engines, or any SMC-specific
concept (FVG/BOS/React/Sweep/iFVG/M1/M2/M4/R_body/S_body/S_wick). The only
knowledge this module has is db/schema.sql's generic trading-result shape
-- if tomorrow the database holds a fundamentally different strategy's
trades, this module works unchanged.

Design note -- portfolio_id, not run_id, is the primary key: ``trades``,
``orders``, ``setup_arm_outcomes`` and ``equity_curve`` are all keyed by
``portfolio_id``, and one ``run_id`` legitimately owns several isolated
portfolios (Strategy A: 9). Computing metrics per run_id would blend
unrelated P&L streams together. ``run_id`` is resolved from
``portfolios`` and carried on the result for traceability. Only the
opportunity funnel's ``engaged``/``armed`` counts intentionally read by
``run_id`` alone -- those are db/schema.sql's own model-agnostic ``setups``
rows (D-052: identical across every portfolio of the same run), so
querying them by run_id does not mix any portfolio's P&L; every P&L-
bearing query below is scoped strictly by ``portfolio_id``.

P&L convention -- verified against src/backtest/orchestrator.py's
_close_trade (the sole place a trade's P&L is computed), not invented:
    price_pnl = units * ((exit_px - entry_px) if side == "buy"
                          else (entry_px - exit_px))          # line 542-544
    commission = cost_model.commission(units)                 # line 545
    net_pnl = price_pnl - commission                           # line 546
    arm.portfolio.apply_realized_pnl(net_pnl)                  # line 547 -- the
                                                                 # trusted, applied P&L
    result_r = (price_pnl / units) / risk_per_unit              # line 550 -- derived
                                                                 # from price_pnl, i.e.
                                                                 # GROSS (pre-commission)
This module reproduces price_pnl's formula (verified identical to
orchestrator.py:542-544) rather than importing the protected Orchestrator.
cost_spread/cost_slippage/cost_commission are each an ADDITIONAL cost
subtracted from price_pnl (not already embedded in entry_px/exit_px --
entry_px/exit_px are the order's actual fill/exit prices, and
Orchestrator's own net_pnl already subtracts commission separately from
price_pnl, confirming costs are deducted, not baked into the price
fields). Every per-trade dollar figure here therefore extends
Orchestrator's net_pnl to also subtract cost_spread/cost_slippage (real
schema columns; currently always 0.0 per KI-012 -- see _COST_DATA_NOTE),
so the one net-P&L definition used throughout this module is a strict
superset of Orchestrator's own, numerically identical to it today, with
no double-counting: each of the three cost fields is subtracted exactly
once.

Enum values used in queries below were verified against db/schema.sql's
own CHECK constraints (side IN ('buy','sell'); orders.status IN
('pending','filled','cancelled'); setups.outcome IN ('armed','expired',
'invalidated','no_ifvg'); setup_arm_outcomes.outcome IN ('pending',
'closed','expired','invalidated','blocked_news','blocked_quota',
'invalid_geometry')) -- any row that exists in these tables is guaranteed
by DuckDB to already satisfy its CHECK constraint, so these are not
assumptions but enforced invariants.

Measurements only -- this module never classifies a result as
profitable/promising/a candidate. That judgment belongs to later
Research System layers (Analysis/Validation/Comparison/Report), not here.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from src.journal.duckdb_writer import DuckDBJournal

_COST_DATA_NOTE = (
    "total_cost/net_pnl currently reflect commission only: cost_spread and "
    "cost_slippage are real schema columns but are always written as 0.0 by "
    "the Backtest Engine today (not yet separable from fill price -- KI-012, "
    "deferred to a future Statistics Engine). Do not read net_pnl as fully "
    "cost-adjusted until KI-012 is resolved."
)
_MAE_MFE_UNAVAILABLE_NOTE = (
    "mae_r/mfe_r are not yet populated by the Backtest Engine for any trade "
    "in this portfolio (always NULL at write time -- KI-013, deferred to a "
    "future Statistics Engine)."
)
_EXPOSURE_UNAVAILABLE_NOTE = (
    "equity_curve has no rows for this portfolio -- the table exists in "
    "db/schema.sql but Orchestrator never writes to it today. Exposure "
    "cannot be computed from real data until a writer exists."
)
_PROFIT_FACTOR_BASIS_NOTE = (
    "profit_factor is computed from each trade's net monetary P&L "
    "(price_pnl - cost_spread - cost_slippage - cost_commission, matching "
    "Orchestrator._close_trade's own net_pnl convention), NOT from result_r. "
    "Its win/loss split can therefore differ from win_count/loss_count/"
    "max_consecutive_wins/losses below, which are classified by result_r "
    "sign (a small R-positive trade can still have net_pnl <= 0 once "
    "commission is subtracted). This distinction is intentional: result_r "
    "is the schema's own named trade-result field and is preserved as the "
    "classification basis for win_rate/streaks/expectancy, while Profit "
    "Factor is by definition a monetary P&L ratio and uses the Backtest "
    "Engine's trusted net_pnl convention instead."
)


@dataclass(frozen=True)
class FunnelCounts:
    """Opportunity/execution funnel -- deliberately separate from trade
    performance metrics. A rejected order, a cancelled order, or an
    unfilled/expired/invalidated setup is never a losing trade and must
    never contaminate P&L-based metrics.

    ``engaged``/``armed`` are model-agnostic (db/schema.sql's ``setups``
    table, D-052: identical across every portfolio of the same run).
    ``orders_placed``/``orders_filled``/``orders_cancelled`` and
    ``arm_outcomes`` are portfolio-specific.
    """

    engaged: int
    armed: int
    orders_placed: int
    orders_filled: int
    orders_cancelled: int
    arm_outcomes: dict[str, int]  # setup_arm_outcomes.outcome -> count, schema-driven
    closed_trades: int


@dataclass(frozen=True)
class MetricsResult:
    """One portfolio's measured performance. Strategy-agnostic by
    construction -- every field is derivable from db/schema.sql's generic
    trading-result tables alone. Contains measurements only, never an
    interpretation or a recommendation.
    """

    portfolio_id: str
    run_id: str

    closed_trade_count: int
    open_trade_count: int
    trades_available: bool  # False iff closed_trade_count == 0

    win_count: int | None  # result_r > 0 (see _PROFIT_FACTOR_BASIS_NOTE for the exception)
    loss_count: int | None
    scratch_count: int | None  # result_r == 0
    win_rate: float | None  # win_count / closed_trade_count (scratches count in denominator only)

    gross_pnl: float | None
    total_cost_spread: float | None
    total_cost_slippage: float | None
    total_cost_commission: float | None
    total_cost: float | None
    net_pnl: float | None
    cost_data_note: str

    expectancy_r: float | None  # == average_r (same computation; both exposed for naming clarity)
    average_r: float | None
    median_r: float | None

    profit_factor: float | None  # net monetary P&L basis -- see profit_factor_note
    profit_factor_note: str | None

    average_duration_min: float | None

    average_mae_r: float | None
    median_mae_r: float | None
    average_mfe_r: float | None
    median_mfe_r: float | None
    mae_mfe_note: str | None

    max_consecutive_wins: int | None
    max_consecutive_losses: int | None

    exposure_avg_open_risk_r: float | None
    exposure_note: str

    funnel: FunnelCounts


class MetricsEngine:
    """Reads via the existing Journal read path (``DuckDBJournal.query``,
    "never used by write paths" per its own docstring). Introduces no new
    database access layer and no write path.
    """

    def __init__(self, journal: DuckDBJournal) -> None:
        self._journal = journal

    def compute(self, portfolio_id: str) -> MetricsResult:
        run_id = self._resolve_run_id(portfolio_id)
        rows = self._fetch_closed_trades(portfolio_id)
        open_trade_count = self._scalar(
            "SELECT COUNT(*) FROM trades WHERE portfolio_id = ? AND exit_ts IS NULL",
            [portfolio_id],
        )
        funnel = self._fetch_funnel(run_id, portfolio_id)

        if not rows:
            return MetricsResult(
                portfolio_id=portfolio_id,
                run_id=run_id,
                closed_trade_count=0,
                open_trade_count=open_trade_count,
                trades_available=False,
                win_count=None,
                loss_count=None,
                scratch_count=None,
                win_rate=None,
                gross_pnl=None,
                total_cost_spread=None,
                total_cost_slippage=None,
                total_cost_commission=None,
                total_cost=None,
                net_pnl=None,
                cost_data_note=_COST_DATA_NOTE,
                expectancy_r=None,
                average_r=None,
                median_r=None,
                profit_factor=None,
                profit_factor_note="no closed trades -- profit factor undefined",
                average_duration_min=None,
                average_mae_r=None,
                median_mae_r=None,
                average_mfe_r=None,
                median_mfe_r=None,
                mae_mfe_note="no closed trades",
                max_consecutive_wins=None,
                max_consecutive_losses=None,
                exposure_avg_open_risk_r=None,
                exposure_note=self._exposure_note(portfolio_id),
                funnel=funnel,
            )

        return self._compute_from_rows(portfolio_id, run_id, rows, open_trade_count, funnel)

    # -- internals -----------------------------------------------------

    def _compute_from_rows(
        self,
        portfolio_id: str,
        run_id: str,
        rows: list[tuple],
        open_trade_count: int,
        funnel: FunnelCounts,
    ) -> MetricsResult:
        closed_trade_count = len(rows)

        result_r_values: list[float] = []
        durations: list[float] = []
        mae_values: list[float] = []
        mfe_values: list[float] = []
        gross_pnl_total = 0.0
        cost_spread_total = 0.0
        cost_slippage_total = 0.0
        cost_commission_total = 0.0
        win_count = loss_count = scratch_count = 0
        classifications: list[int] = []  # +1 win, -1 loss, 0 scratch, in entry_ts order
        pf_gross_win_dollars = 0.0
        pf_gross_loss_dollars = 0.0

        for (
            _entry_ts,
            _exit_ts,
            entry_px,
            exit_px,
            result_r,
            mae_r,
            mfe_r,
            duration_min,
            cost_spread,
            cost_slippage,
            cost_commission,
            units,
            side,
        ) in rows:
            result_r_values.append(result_r)
            if duration_min is not None:
                durations.append(duration_min)
            if mae_r is not None:
                mae_values.append(mae_r)
            if mfe_r is not None:
                mfe_values.append(mfe_r)

            # price_pnl -- verified identical to orchestrator.py:542-544 (module docstring).
            trade_price_pnl = units * (
                (exit_px - entry_px) if side == "buy" else (entry_px - exit_px)
            )
            gross_pnl_total += trade_price_pnl
            cost_spread_total += cost_spread
            cost_slippage_total += cost_slippage
            cost_commission_total += cost_commission

            trade_net_pnl = trade_price_pnl - cost_spread - cost_slippage - cost_commission
            if trade_net_pnl > 0:
                pf_gross_win_dollars += trade_net_pnl
            elif trade_net_pnl < 0:
                pf_gross_loss_dollars += trade_net_pnl

            if result_r > 0:
                win_count += 1
                classifications.append(1)
            elif result_r < 0:
                loss_count += 1
                classifications.append(-1)
            else:
                scratch_count += 1
                classifications.append(0)

        total_cost = cost_spread_total + cost_slippage_total + cost_commission_total
        net_pnl = gross_pnl_total - total_cost

        average_r = statistics.mean(result_r_values)
        median_r = statistics.median(result_r_values)

        if pf_gross_loss_dollars == 0:
            profit_factor = None
            profit_factor_note = (
                "undefined: zero gross losing net P&L (no net-losing trades) -- "
                f"gross winning net P&L = {pf_gross_win_dollars:.4f}. "
                + _PROFIT_FACTOR_BASIS_NOTE
            )
        else:
            profit_factor = pf_gross_win_dollars / abs(pf_gross_loss_dollars)
            profit_factor_note = _PROFIT_FACTOR_BASIS_NOTE

        average_duration = statistics.mean(durations) if durations else None

        if mae_values:
            average_mae = statistics.mean(mae_values)
            median_mae = statistics.median(mae_values)
        else:
            average_mae = median_mae = None
        if mfe_values:
            average_mfe = statistics.mean(mfe_values)
            median_mfe = statistics.median(mfe_values)
        else:
            average_mfe = median_mfe = None
        mae_mfe_note = None if (mae_values and mfe_values) else _MAE_MFE_UNAVAILABLE_NOTE

        max_win_streak, max_loss_streak = _max_streaks(classifications)

        exposure_rows = self._journal.query(
            "SELECT open_risk_r FROM equity_curve WHERE portfolio_id = ?",
            [portfolio_id],
        )
        if exposure_rows:
            exposure_avg = statistics.mean(r[0] for r in exposure_rows)
            exposure_note = f"average of {len(exposure_rows)} equity_curve snapshot(s)"
        else:
            exposure_avg = None
            exposure_note = _EXPOSURE_UNAVAILABLE_NOTE

        return MetricsResult(
            portfolio_id=portfolio_id,
            run_id=run_id,
            closed_trade_count=closed_trade_count,
            open_trade_count=open_trade_count,
            trades_available=True,
            win_count=win_count,
            loss_count=loss_count,
            scratch_count=scratch_count,
            win_rate=win_count / closed_trade_count,
            gross_pnl=gross_pnl_total,
            total_cost_spread=cost_spread_total,
            total_cost_slippage=cost_slippage_total,
            total_cost_commission=cost_commission_total,
            total_cost=total_cost,
            net_pnl=net_pnl,
            cost_data_note=_COST_DATA_NOTE,
            expectancy_r=average_r,
            average_r=average_r,
            median_r=median_r,
            profit_factor=profit_factor,
            profit_factor_note=profit_factor_note,
            average_duration_min=average_duration,
            average_mae_r=average_mae,
            median_mae_r=median_mae,
            average_mfe_r=average_mfe,
            median_mfe_r=median_mfe,
            mae_mfe_note=mae_mfe_note,
            max_consecutive_wins=max_win_streak,
            max_consecutive_losses=max_loss_streak,
            exposure_avg_open_risk_r=exposure_avg,
            exposure_note=exposure_note,
            funnel=funnel,
        )

    def _resolve_run_id(self, portfolio_id: str) -> str:
        rows = self._journal.query(
            "SELECT run_id FROM portfolios WHERE portfolio_id = ?", [portfolio_id]
        )
        if not rows:
            raise ValueError(f"unknown portfolio_id {portfolio_id!r} -- no row in portfolios")
        return rows[0][0]

    def _fetch_closed_trades(self, portfolio_id: str) -> list[tuple]:
        return self._journal.query(
            """
            SELECT t.entry_ts, t.exit_ts, t.entry_px, t.exit_px, t.result_r,
                   t.mae_r, t.mfe_r, t.duration_min,
                   t.cost_spread, t.cost_slippage, t.cost_commission,
                   o.units, o.side
            FROM trades t
            JOIN orders o ON t.order_id = o.order_id
            WHERE t.portfolio_id = ? AND t.exit_ts IS NOT NULL
            ORDER BY t.entry_ts
            """,
            [portfolio_id],
        )

    def _fetch_funnel(self, run_id: str, portfolio_id: str) -> FunnelCounts:
        engaged = self._scalar("SELECT COUNT(*) FROM setups WHERE run_id = ?", [run_id])
        armed = self._scalar(
            "SELECT COUNT(*) FROM setups WHERE run_id = ? AND outcome = 'armed'", [run_id]
        )
        orders_placed = self._scalar(
            "SELECT COUNT(*) FROM orders WHERE portfolio_id = ?", [portfolio_id]
        )
        orders_filled = self._scalar(
            "SELECT COUNT(*) FROM orders WHERE portfolio_id = ? AND status = 'filled'",
            [portfolio_id],
        )
        orders_cancelled = self._scalar(
            "SELECT COUNT(*) FROM orders WHERE portfolio_id = ? AND status = 'cancelled'",
            [portfolio_id],
        )
        arm_outcome_rows = self._journal.query(
            "SELECT outcome, COUNT(*) FROM setup_arm_outcomes WHERE portfolio_id = ? "
            "GROUP BY outcome",
            [portfolio_id],
        )
        arm_outcomes = {outcome: count for outcome, count in arm_outcome_rows}
        closed_trades = self._scalar(
            "SELECT COUNT(*) FROM trades WHERE portfolio_id = ? AND exit_ts IS NOT NULL",
            [portfolio_id],
        )
        return FunnelCounts(
            engaged=engaged,
            armed=armed,
            orders_placed=orders_placed,
            orders_filled=orders_filled,
            orders_cancelled=orders_cancelled,
            arm_outcomes=arm_outcomes,
            closed_trades=closed_trades,
        )

    def _scalar(self, sql: str, params: list) -> int:
        rows = self._journal.query(sql, params)
        return int(rows[0][0]) if rows else 0

    def _exposure_note(self, portfolio_id: str) -> str:
        rows = self._journal.query(
            "SELECT COUNT(*) FROM equity_curve WHERE portfolio_id = ?", [portfolio_id]
        )
        if rows and rows[0][0] > 0:
            return f"average of {rows[0][0]} equity_curve snapshot(s)"
        return _EXPOSURE_UNAVAILABLE_NOTE


def _max_streaks(classifications: list[int]) -> tuple[int, int]:
    """Longest consecutive-win and consecutive-loss run, in the given
    (chronological, entry_ts) order. A scratch (0) breaks both streaks --
    it is neither a win nor a loss, so it cannot extend either run.
    """
    max_win = max_loss = 0
    current_win = current_loss = 0
    for c in classifications:
        if c > 0:
            current_win += 1
            current_loss = 0
        elif c < 0:
            current_loss += 1
            current_win = 0
        else:
            current_win = 0
            current_loss = 0
        max_win = max(max_win, current_win)
        max_loss = max(max_loss, current_loss)
    return max_win, max_loss
