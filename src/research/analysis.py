"""Strategy-agnostic Analysis Engine (Research System, Phase 2).

Reads persisted closed trades for one isolated portfolio (see
src/research/metrics.py's module docstring for the portfolio_id-as-
primary-key rationale, which applies identically here) and breaks
performance down across generic calendar/side/duration dimensions.

Never executes a backtest. Never writes (Journal.record is never called
-- only DuckDBJournal.query). Never imports Strategy A, SetupStream,
EntryModel, structure/FVG engines, or any SMC-specific concept.

Population semantics -- intentionally identical to MetricsEngine:
    SELECT ... FROM trades t JOIN orders o ON t.order_id = o.order_id
    WHERE t.portfolio_id = ? AND t.exit_ts IS NOT NULL
i.e. the same JOIN, the same portfolio_id scoping, the same open-trade
exclusion as src/research/metrics.py's _fetch_closed_trades. This is a
deliberate duplication, not an independent definition: Phase 2's scope
forbids modifying metrics.py, so there is no shared helper module to
import from yet. Per-trade P&L/classification formulas below
(price_pnl, net_pnl, result_r-based win/loss/scratch, net-$-based
profit factor) are reproduced character-for-character from metrics.py's
own already-verified formulas (which are themselves verified against
src/backtest/orchestrator.py's _close_trade, lines 542-550) -- see
metrics.py's module docstring for the original verification. If the two
modules' definitions ever need to diverge, that divergence must be a
deliberate, documented decision, not drift.

Dimension definitions (each documented because none has an existing
repository convention -- confirmed via repo-wide grep before writing
this module):
  - day_of_week / month / quarter: computed from trades.entry_ts, which
    is stored as UTC (CLAUDE.md: "UTC פנימי בלבד"). This is UTC calendar
    position, NOT NY-session trading-day position -- db/schema.sql's
    `sessions.ny_date` would be the NY-trading-day concept, but
    Orchestrator never writes to `sessions` (confirmed by grep, same
    "schema exists, unpopulated" status as `equity_curve`), so no
    NY-trading-day data exists to use instead. day_of_week/month/quarter
    are pooled across all years in the queried population (e.g. every
    January across every year counts as one "01" bucket) -- a calendar-
    position dimension, mirroring how day_of_week is inherently pooled
    across weeks.
  - hour: uses trades.hour_bucket_et directly (real, already-populated
    ET hour -- src/backtest/orchestrator.py's _close_trade sets it via
    self.session.local(order.filled_at).hour, unlike cost_spread/
    cost_slippage/mae_r/mfe_r, which are placeholder-only per KI-012/
    KI-013). This avoids adding any new timezone-conversion dependency
    to this module.
  - side: trades.orders.side ("buy"/"sell") verbatim -- "buy" == long,
    "sell" == short.
  - duration_bucket: a small generic, timeframe-agnostic set of
    duration_min ranges (see _duration_bucket) -- no existing repository
    convention was found (confirmed via grep), so this is a documented
    MVP default, not a discovered standard.

Minimum-sample policy -- explicit and overridable, not invented as a
statistical claim: `min_sample_size` (default 5) is a conservative
completeness floor only -- below it, a bucket's entire performance
summary is withheld (mirroring MetricsResult's own "unavailable, not a
misleading zero" philosophy), but `trade_count` is always shown. This
default is NOT a claim of statistical validity; a future Validation
Engine is where a real significance test belongs. Override via the
constructor if a different floor is needed.

Multiple-comparison disclosure: AnalysisResult.dimensions_scanned and
.buckets_scanned report exactly how many dimensions/buckets were
computed, so a caller can see the full scan size -- this module makes
no significance claim about any single bucket looking better than
another; that judgment belongs to a later Research System layer.

Measurements only -- this module never classifies a bucket as
profitable/promising/a candidate, and never selects a "best" bucket.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from src.journal.duckdb_writer import DuckDBJournal

_MULTIPLE_COMPARISON_NOTE = (
    "This result scans multiple dimensions/buckets. A bucket that looks "
    "better than another is not evidence of a real effect by itself -- "
    "scanning many buckets makes at least one look good by chance alone. "
    "No significance test is applied here; that belongs to a future "
    "Validation Engine, not this Analysis Engine."
)
_INSUFFICIENT_SAMPLE_NOTE = "trade_count below min_sample_size -- performance fields withheld"
_PROFIT_FACTOR_BASIS_NOTE = (
    "profit_factor is computed from each trade's net monetary P&L "
    "(price_pnl - cost_spread - cost_slippage - cost_commission), NOT from "
    "result_r -- identical convention to src/research/metrics.py's "
    "profit_factor. win/loss/scratch counts remain result_r-based."
)

_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_DIMENSION_ORDER = ["day_of_week", "hour_et", "month", "quarter", "side", "duration_bucket"]
_CANONICAL_BUCKET_ORDER: dict[str, list[str]] = {
    "day_of_week": _WEEKDAY_NAMES,
    "hour_et": [f"{h:02d}" for h in range(24)] + ["unknown"],
    "month": [f"{m:02d}" for m in range(1, 13)],
    "quarter": ["Q1", "Q2", "Q3", "Q4"],
    "side": ["buy", "sell"],
    "duration_bucket": ["under_15m", "15m_to_1h", "1h_to_4h", "4h_to_24h", "over_24h", "unknown"],
}


def _duration_bucket(duration_min: int | None) -> str:
    """Generic, timeframe-agnostic duration buckets -- no existing
    repository convention was found for this (confirmed via grep), so
    this is a documented MVP default, not a discovered standard.
    """
    if duration_min is None:
        return "unknown"
    if duration_min < 15:
        return "under_15m"
    if duration_min < 60:
        return "15m_to_1h"
    if duration_min < 240:
        return "1h_to_4h"
    if duration_min < 1440:
        return "4h_to_24h"
    return "over_24h"


@dataclass(frozen=True)
class _TradeRecord:
    entry_ts: datetime
    result_r: float
    duration_min: int | None
    hour_bucket_et: int | None
    side: str
    price_pnl: float
    net_pnl: float


@dataclass(frozen=True)
class BucketResult:
    """One dimension/bucket combination's measured performance.
    Strategy-agnostic and measurements-only, matching MetricsResult's
    own contract. All fields below ``sufficient_sample`` are None when
    ``sufficient_sample`` is False -- trade_count is always real.
    """

    dimension: str
    bucket_key: str
    trade_count: int
    sufficient_sample: bool
    insufficient_sample_note: str | None

    win_count: int | None
    loss_count: int | None
    scratch_count: int | None
    win_rate: float | None

    net_pnl: float | None
    average_r: float | None
    median_r: float | None

    profit_factor: float | None
    profit_factor_note: str | None


@dataclass(frozen=True)
class AnalysisResult:
    """One portfolio's dimensional breakdown. Measurements only -- never
    an interpretation, recommendation, or "best bucket" selection.
    """

    portfolio_id: str
    run_id: str
    closed_trade_count: int
    trades_available: bool
    min_sample_size: int
    dimensions_scanned: int
    buckets_scanned: int
    multiple_comparison_note: str
    buckets: list[BucketResult]


class AnalysisEngine:
    """Reads via the existing Journal read path (DuckDBJournal.query).
    Never calls .record(). Introduces no new database access layer and
    no write path.
    """

    def __init__(self, journal: DuckDBJournal, *, min_sample_size: int = 5) -> None:
        self._journal = journal
        self._min_sample_size = min_sample_size

    def analyze(self, portfolio_id: str) -> AnalysisResult:
        run_id = self._resolve_run_id(portfolio_id)
        records = [self._to_record(row) for row in self._fetch_closed_trades(portfolio_id)]

        if not records:
            return AnalysisResult(
                portfolio_id=portfolio_id,
                run_id=run_id,
                closed_trade_count=0,
                trades_available=False,
                min_sample_size=self._min_sample_size,
                dimensions_scanned=len(_DIMENSION_ORDER),
                buckets_scanned=0,
                multiple_comparison_note=_MULTIPLE_COMPARISON_NOTE,
                buckets=[],
            )

        dimension_key_fns = {
            "day_of_week": lambda r: _WEEKDAY_NAMES[r.entry_ts.weekday()],
            "hour_et": lambda r: f"{r.hour_bucket_et:02d}" if r.hour_bucket_et is not None else "unknown",
            "month": lambda r: f"{r.entry_ts.month:02d}",
            "quarter": lambda r: f"Q{(r.entry_ts.month - 1) // 3 + 1}",
            "side": lambda r: r.side,
            "duration_bucket": lambda r: _duration_bucket(r.duration_min),
        }

        buckets: list[BucketResult] = []
        for dimension in _DIMENSION_ORDER:
            key_fn = dimension_key_fns[dimension]
            groups: dict[str, list[_TradeRecord]] = defaultdict(list)
            for record in records:
                groups[key_fn(record)].append(record)

            canonical_order = _CANONICAL_BUCKET_ORDER[dimension]
            ordered_keys = sorted(
                groups.keys(),
                key=lambda k: canonical_order.index(k) if k in canonical_order else len(canonical_order),
            )
            for bucket_key in ordered_keys:
                buckets.append(self._aggregate_bucket(dimension, bucket_key, groups[bucket_key]))

        return AnalysisResult(
            portfolio_id=portfolio_id,
            run_id=run_id,
            closed_trade_count=len(records),
            trades_available=True,
            min_sample_size=self._min_sample_size,
            dimensions_scanned=len(_DIMENSION_ORDER),
            buckets_scanned=len(buckets),
            multiple_comparison_note=_MULTIPLE_COMPARISON_NOTE,
            buckets=buckets,
        )

    # -- internals -----------------------------------------------------

    def _aggregate_bucket(
        self, dimension: str, bucket_key: str, records: list[_TradeRecord]
    ) -> BucketResult:
        trade_count = len(records)
        if trade_count < self._min_sample_size:
            return BucketResult(
                dimension=dimension,
                bucket_key=bucket_key,
                trade_count=trade_count,
                sufficient_sample=False,
                insufficient_sample_note=_INSUFFICIENT_SAMPLE_NOTE,
                win_count=None,
                loss_count=None,
                scratch_count=None,
                win_rate=None,
                net_pnl=None,
                average_r=None,
                median_r=None,
                profit_factor=None,
                profit_factor_note=None,
            )

        win_count = loss_count = scratch_count = 0
        result_r_values: list[float] = []
        net_pnl_total = 0.0
        pf_gross_win_dollars = 0.0
        pf_gross_loss_dollars = 0.0

        for record in records:
            result_r_values.append(record.result_r)
            net_pnl_total += record.net_pnl

            if record.net_pnl > 0:
                pf_gross_win_dollars += record.net_pnl
            elif record.net_pnl < 0:
                pf_gross_loss_dollars += record.net_pnl

            if record.result_r > 0:
                win_count += 1
            elif record.result_r < 0:
                loss_count += 1
            else:
                scratch_count += 1

        if pf_gross_loss_dollars == 0:
            profit_factor = None
            profit_factor_note = (
                "undefined: zero gross losing net P&L (no net-losing trades) -- "
                f"gross winning net P&L = {pf_gross_win_dollars:.4f}. " + _PROFIT_FACTOR_BASIS_NOTE
            )
        else:
            profit_factor = pf_gross_win_dollars / abs(pf_gross_loss_dollars)
            profit_factor_note = _PROFIT_FACTOR_BASIS_NOTE

        return BucketResult(
            dimension=dimension,
            bucket_key=bucket_key,
            trade_count=trade_count,
            sufficient_sample=True,
            insufficient_sample_note=None,
            win_count=win_count,
            loss_count=loss_count,
            scratch_count=scratch_count,
            win_rate=win_count / trade_count,
            net_pnl=net_pnl_total,
            average_r=statistics.mean(result_r_values),
            median_r=statistics.median(result_r_values),
            profit_factor=profit_factor,
            profit_factor_note=profit_factor_note,
        )

    def _to_record(self, row: tuple) -> _TradeRecord:
        (
            entry_ts,
            _exit_ts,
            entry_px,
            exit_px,
            result_r,
            duration_min,
            cost_spread,
            cost_slippage,
            cost_commission,
            hour_bucket_et,
            units,
            side,
        ) = row
        # price_pnl/net_pnl -- reproduced identically from metrics.py (see module
        # docstring); metrics.py's own formula is verified against
        # orchestrator.py:542-546.
        price_pnl = units * ((exit_px - entry_px) if side == "buy" else (entry_px - exit_px))
        net_pnl = price_pnl - cost_spread - cost_slippage - cost_commission
        return _TradeRecord(
            entry_ts=entry_ts,
            result_r=result_r,
            duration_min=duration_min,
            hour_bucket_et=hour_bucket_et,
            side=side,
            price_pnl=price_pnl,
            net_pnl=net_pnl,
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
                   t.duration_min, t.cost_spread, t.cost_slippage, t.cost_commission,
                   t.hour_bucket_et, o.units, o.side
            FROM trades t
            JOIN orders o ON t.order_id = o.order_id
            WHERE t.portfolio_id = ? AND t.exit_ts IS NOT NULL
            ORDER BY t.entry_ts
            """,
            [portfolio_id],
        )
