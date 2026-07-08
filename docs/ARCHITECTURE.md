# ARCHITECTURE — v1.1 Final
(מחליף את v1.0; משלב את החלטות ה-Freeze. החוקים עצמם: SPEC_V1_FROZEN.md)

## שכבות
```
Research: Statistics · Validation · Tracker · AI Analyst · Viz
   ▲
Journal (DuckDB): experiments · runs · portfolios · setups · orders · trades ·
                  fvg_registry · bias_history · news · sessions · equity · scores
   ▲ (כתיבה מהסימולטור בלבד)
Backtest Orchestrator:
   Event Loop (UTC) — עיבוד דו-שלבי לכל timestamp
   ├─ Session Engine (NY) ←→ Calendar Engine (Blackout)
   ├─ Structure: Fractals · BOS · Sweep · Bias-SM   (per TF)
   ├─ FVG Engine (detect · mitigation · ranking) + iFVG
   ├─ Displacement (D1 default; D2–D5 רמות ניסוי)
   ├─ Setup Stream — ה-State Machine (model-agnostic)
   ├─ Entry Arms: M1 · M2 · M4  →  SL Arms: R_body · S_body · S_wick
   ├─ Risk (0.5% realized · quota · geometry) — לכל תיק
   └─ Fill Simulator + Cost Model (Bid/Ask ticks · slippage · delay)
        ▲ MarketContext.as_of(now)  ← Point-in-Time State Store
   ▲
Data: DukascopyDownloader(bi5+LZMA, cache immutable) → Validator → BarBuilder(anchor=NY-Close) → Parquet
```

## עקרונות (מחייבים)
1. **No-Lookahead by Construction:** כל אובייקט נגזר נושא `created_at / confirmed_at / invalidated_at`; האסטרטגיה רואה רק `confirmed_at ≤ now` דרך MarketContext.
2. **עיבוד דו-שלבי** בכל timestamp: (א) כל סגירות הנרות מעדכנות State בסדר 1M→5M→4H; (ב) החלטות רצות פעם אחת. פותר את מרוץ 09:00 ET.
3. **זרם בסיס 1M + Tick-on-Demand:** ירידה לרזולוציית Tick רק כשפקודה פעילה ליד SL/TP או מחיר ליד גבול FVG. דטרמיניסטי ומהיר.
4. **Multi-Portfolio Paired Design:** 9 תיקים ({M1,M2,M4}×{R,S,Wick}) על Setup Stream זהה. בתוך מודל כניסה — כניסה זהה לשלוש זרועות SL → השוואה זוגית טהורה של עוגן הסטופ. לכל תיק: הון, מכסה ו-Equity Curve משלו.
5. **Reproducibility:** ריצה = `(config_hash, data_version, code_version)`; Append-Only Tracker; Seed לכל אקראיות.
6. **Hold-Out פיזי:** `data/holdout/` נפרד; Loader מסרב בלי דגל מתועד.

## לולאת האירועים (פסאודו)
```python
for ts, events in merged_feed:              # כרונולוגי, UTC
    clock.now = ts
    for e in ordered(events):               # שלב א: 1M→5M→4H, ואז Ticks
        apply_to_state(e)                   # מבנים / mitigation / fills(SL,TP)
    session.on_ts(ts)                       # open/close/day_roll/ביטולים
    if session.in_window and not calendar.blackout(ts):   # שלב ב
        ctx = store.as_of(ts)
        for setup_event in setup_stream.step(ctx):        # State Machine
            for arm in arms:                              # 9 תיקים
                intent = arm.entry.on_event(setup_event, ctx)
                if intent:
                    order = arm.risk.approve(intent.with_sl(arm.sl_anchor), ctx)
                    if order: fill_sim.place(order, portfolio=arm)
```

## זרימת נתונים (Phase 0)
Dukascopy bi5 → פענוח LZMA → Tick Parquet חודשי (immutable, hash) → Validator (חורים, סופ"ש, DST, spikes מדוגללים) → BarBuilder 1M/5M/4H (עוגן NY-Close) → דו"ח ספרד לפי שעה (מזין `min_stop_distance` ו-Cost Model).

## מודולים — אחריות בשורה
| מודול | אחריות |
|---|---|
| data | הורדה, ולידציה, בניית נרות, גרסוּה |
| store | State Store + MarketContext (as-of) |
| structure | Fractals, BOS, Sweep, Bias-SM |
| fvg | זיהוי, Mitigation חי, דירוג, iFVG |
| displacement | D1–D5 פלאגביליים |
| session / calendar | חלון NY, Blackout, effective_window, תגי חג |
| entry | Setup Stream (State Machine) + M1/M2/M4 |
| risk | Sizing ממומש, מכסה, גאומטריה |
| execution | Fill Simulator + Cost Model |
| backtest | Orchestrator, Events, Portfolios |
| journal | כתיבה טרנזקציונית ל-DuckDB |
| stats | כל המדדים + פילוחים + MAE/MFE |
| validation | WF, Hold-Out Guard, Random Baseline (זוגי), Sensitivity |
| tracker | config_hash, רישום ריצות Append-Only |
| scoring / ai / viz | Log-Only Scoring · Analyst · Plotly per-trade |

## בדיקות-על
Prefix-Consistency (גלאי Lookahead, חובה ב-CI) · Golden Regression · DST Boundaries · Race-09:00 · Cost Sanity · Reproducibility (שתי ריצות זהות → יומן זהה).
פירוט מלא: ACCEPTANCE_TESTS.md.
