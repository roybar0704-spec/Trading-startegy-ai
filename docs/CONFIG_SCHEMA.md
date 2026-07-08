# CONFIGURATION SCHEMA
שלושה קבצים ב-`config/`. ולידציה ב-Pydantic v2; `config_hash = SHA256(canonical_json(merged) + data_version + code_version)`.
ערכים מחקריים (Guards, WF, Baseline, עלויות, ספים) ממופים ל-RA-IDs ב-`RESEARCH_ASSUMPTIONS_V1.md` — הם Initial Choices, לא חוקים.
**`rules_v1.yaml` קפוא** — ה-hash שלו נבדק בעליית המערכת; אי-התאמה = עצירה.

## config/rules_v1.yaml — FROZEN
```yaml
spec_version: "1.0"
instrument: XAUUSD
data_source: dukascopy_ticks          # מקור אמת יחיד
structure_price: mid
htf_anchor: NY_CLOSE_17ET             # נרות 4H: 17/21/01/05/09/13 ET

session:
  tz: America/New_York
  window: ["08:30", "10:30"]
  sequence_scope: R_S_entry_in_window # H1: סגירת R, סגירת S והכניסה בתוך החלון
  cancel_pending_at_close: true

bias:
  source_tf: 4H
  neutral_policy: no_trade
  on_flip: {open_position: keep_and_tag, pending_orders: cancel}

fvg_4h:
  min_size: null
  valid_until: full_mitigation        # 100%, נמדד על Mid
  age_limit: null
  ranking: [bos, displacement, plain, proximity]

trigger:                              # קריאה 2 — נעול
  reaction_r: {in_zone: true, body_direction: with_zone, lower_wick_required: true}
  r_replacement: latest_qualifier
  r_reset_on_close_through: true
  sweep_s: {low_below_r_low: true, close_back_above_r_low: true}
  ifvg:
    candidate: bearish_1m_fvg_since_engagement
    inversion: full_close_beyond_top
    after_s_close_only: true
    selection: first_inversion_then_highest_top
    rearm: false
  no_ifvg_outcome: logged

risk:
  sizing_pct: 0.005
  equity_base: realized_balance
  tp_rr: 3.0
  quota_fills_per_day: 2              # פר תיק, יום NY
  same_zone_reentry: allowed_tagged

news_filter:
  currency: [USD]
  impact: [red]
  blackout_min: {before: 30, after: 30}
  pending_on_blackout: cancel
  open_position_on_news: keep_and_tag

holding: {overnight: allowed_tagged, weekend: allowed_tagged}

execution:
  limit_fill: ask_leq_price_no_positive_slippage
  fallback_no_ticks: sl_first
  gap_through: first_available_price_plus_slippage
```

## config/parameters.yaml — פרמטרים + Grids מוצהרים
```yaml
sl_buffer_usd:      {default: 0.30, grid: [0.10, 0.20, 0.30, 0.50]}
min_stop_k_spread:  {default: 3.0,  grid: [2.0, 3.0, 4.0]}
displacement:
  model: {default: D1, experiment_levels: [D1, D2, D3, D4, D5]}
  d1:    {body_vs_avg_n: 10, ratio_min: {default: 1.5, grid: [1.25, 1.5, 2.0]}}
costs:
  slippage_stop_usd:   {default: 0.10}
  news_slip_mult:      {default: 3.0}
  slippage_market_usd: {default: 0.05}
  commission_per_unit: {default: 0.0}
  execution_delay_ms:  {default: 0, robustness: [250, 500]}
warmup_days: 90
tick_on_demand_band_usd: 1.00         # מרחק הפעלת רזולוציית Tick סביב SL/TP/גבול FVG
scoring_weights: {fvg_level: 0.4, ts: 0.2, sweep_quality: 0.2, bias_recency: 0.2}
```

## config/run_default.yaml
```yaml
experiment: "E1_arm_selection"
objective: "oos_wf_expectancy_r"      # נעול; שונה מהמוצהר ב-Experiment → חריגה
guards: {p_vs_baseline_max: 0.05, pf_min: 1.3, min_trades: 150, worst_quarter_r_min: -15}
period: {start: 2023-01-01, end: 2025-12-31}
holdout: {last_months: 6, unlocked: false}
walk_forward: {train_months: 9, test_months: 3}
arms:
  entry_models: [M1, M2, M4]
  sl_anchors: [R_body, S_body, S_wick]   # 9 תיקים, Stream זהה
baseline: {n_sims: 1000, seed: 42}
seed: 42
```

## סכימת Pydantic (מתאר)
```python
class RulesV1(BaseModel):    model_config = ConfigDict(frozen=True, extra="forbid")
class Parameters(BaseModel): model_config = ConfigDict(extra="forbid")   # grid מוצהר בלבד
class RunConfig(BaseModel):  model_config = ConfigDict(extra="forbid")
# extra="forbid" בכל מקום: שדה לא מוכר = שגיאה, לא התעלמות שקטה.
```
