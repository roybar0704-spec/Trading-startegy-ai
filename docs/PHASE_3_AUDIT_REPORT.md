# Phase 3 — Final Audit Report (Code Gate)

**סטטוס:** Green-Conditional — **צד קודי סגור** (D-065, 2026-07-10, באישור משתמש מפורש).
**קפוא מ:** `5da3305` (Close Phase 3 (code side): Green-Conditional, per D-065).
**נוהל מכאן:** אין שינויי קוד נוספים ב-Phase 3 מלבד תיקוני-באג קריטיים. Phase 4 מתחיל רק לאחר שחסמי Research Readiness Review (KI-001, KI-002, KI-010) נפתרים מול דאטה אמיתי.

מסמך זה הוא ה-Audit הרשמי היחיד של Phase 3 בשלמותו — ארכיטקטורה סופית, כל ההחלטות, כל התקלות הפתוחות, כיסוי בדיקות-קבלה, hash-ים של Commits, כיסוי-קוד, ומטריצת Traceability מ-SPEC למימוש. לפרוזה המלאה של כל שורה — `docs/DECISIONS_LOG.md`/`docs/KNOWN_ISSUES.md` נשארים מקור-האמת; המסמך הזה הוא האינדקס המסכם.

---

## 1. ארכיטקטורה סופית

### 1.1 מבנה מודולים (`src/`, שורות קוד)

| שכבה (import-linter layer, מהנמוכה לגבוהה) | מודול | שורות | תפקיד |
|---|---|---|---|
| — | `src/core` | 271 | טיפוסי-ליבה חסרי-תלות (D-038): `Tick`,`Bar`,`FVG`,`Setup`,`SetupEvent`,`Order`,`Fill`,`ArmId`,`OrderIntent`,`IFVG` |
| — | `src/config` | 377 | `RulesV1`/`Parameters`/`RunConfig` (Pydantic v2, `extra=forbid`), `frozen_guard`, `config_hash` |
| session/data/journal | `src/session` | 140 | `SessionEngine` (חלון NY), `CalendarEngine` (Blackout) |
| session/data/journal | `src/data` | 871 | Downloader, Tick→Parquet, Validator, BarBuilder, `SpreadReport`+`ExpandingSpreadReport` |
| session/data/journal | `src/journal` | 51 | `DuckDBJournal` — append-only writer + `query()` לקריאה |
| store | `src/store` | 215 | `StateStore`+`MarketContext` — No-Lookahead by Construction (`as_of(ts)`) |
| displacement | `src/displacement` | 74 | D1 BodyRatio (D2–D5 מוצהרים, לא ממומשים) |
| structure/fvg | `src/structure` | 202 | Fractals, BOS/Sweep, Bias State Machine |
| structure/fvg | `src/fvg` | 213 | Detector (3-candle), Ranking (L1–L3), MitigationTracker |
| entry/risk/execution | `src/entry` | 591 | `SetupStream` (Model-agnostic State Machine), M1/M2/M4, `sl_geometry` |
| entry/risk/execution | `src/risk` | 142 | `RiskEngine` (geometry→quota→sizing), `Portfolio`, `sizing` |
| entry/risk/execution | `src/execution` | 282 | `FillSimulator` (Bid/Ask ריאליסטי, Execution Delay), `CostModel` |
| backtest | `src/backtest` | 837 | `Orchestrator` (לולאה דו-שלבית), `run_builder`, `context_snapshot`, `portfolio_arm` |
| ⛔ ללא-תלות-במנוע | `src/viz` | 162 | `build_trade_page` — קורא רק מה-Journal + Bars חיצוניים |
| **סה"כ** | | **4,429** | |

### 1.2 חוזי Architecture Gate (`pyproject.toml`, import-linter — 4/4 קיימים ונאכפים)
1. **Config has no engine dependencies** — `src.config` אסור לייבא `src.data`.
2. **core is dependency-free (D-038)** — `src.core` אסור לייבא `src.config`/`src.data`.
3. **Viz has no engine dependencies (T3.5)** — `src.viz` אסור לייבא `entry/risk/execution/structure/fvg/displacement/store/backtest` ישירות; קורא רק Journal+core.
4. **Engine layering (Phase 3)** — `{data,session,journal} <- store <- displacement <- {structure,fvg} <- {entry,risk,execution} <- backtest`.

### 1.3 זרימת ריצה (Orchestrator, לולאה דו-שלבית — H2/Race-09:00, D-063 מתוקן)
```
build_orchestrator(rules, parameters, run_config, bars_1m, bars_5m, bars_4h, ticks, ...)
  └─ Orchestrator.run():
       _write_run_identity_rows()                         # experiments/runs/portfolios (D-059)
       for ts, group in _merged_timeline():                # ממוין (ts, priority): bar1m→bar5m→bar4h→tick
           Stage 1  — לכל אירוע בקבוצה, לפי הסדר:
               _apply_1m / _apply_5m / _apply_4h / _apply_tick
                   → StructureEngine.step, FVGEngine.step_bar_close/on_price,
                     SetupStream.on_bar_close, spread_tracker.update, FillSimulator.on_tick
           Stage 2  — פעם אחת, על ה-State המעודכן במלואו:
               ctx = store.as_of(ts)
               for event in setup_stream.step(ctx):
                   engaged   → _buffer_engagement_snapshot   (ממתין ל-setups row)
                   armed     → _finalize_setup_journal + _record_snapshot("armed") + _open_orders_for_event
                   invalidated/expired/no_ifvg → _finalize_setup_journal (אם לא post_arm) + _cancel_for_setup
       journal.close()
```

### 1.4 סכימת DuckDB (18 טבלאות, כולן `CREATE TABLE IF NOT EXISTS`)
`experiments → runs → portfolios → {orders, setup_arm_outcomes} → trades`; `setups ← {orders, setup_arm_outcomes, context_snapshots, scores}`; `context_snapshots.order_id` Nullable FK ל-`orders` (D-058, model-agnostic לעומת per-arm). `setup_arm_outcomes`/`orders` נכתבות **פעם אחת בלבד, במצב סופי** (D-060) — לא Event Log מגורסן.

---

## 2. Traceability — SPEC → מימוש → בדיקות

| SPEC §, נושא | מודול מממש | AT מכסה |
|---|---|---|
| §1 יסודות (Mid לכל מבנה, Bid/Ask לביצוע) | `core/types.py` (`Tick.mid`), `execution/fill_simulator.py` | AT-2.1–2.4 |
| §2 Market Structure (Fractals/BOS/Sweep) | `structure/fractals.py`, `structure/bos_sweep.py` | AT-1.1, AT-1.2 |
| §3 HTF Bias State Machine | `structure/bias.py`, `structure/engine.py` | AT-1.3 |
| §4 4H FVG (זיהוי/דירוג/Mitigation) | `fvg/detector.py`, `fvg/ranking.py`, `fvg/mitigation.py` | AT-1.4, AT-1.5 |
| §5 TS (Turtle Soup) | מגולם בתוך רצף ה-S-candle ב-`entry/setup_stream.py` | AT-3.3 |
| §6 הטריגר — רצף נעול R→S→iFVG | `entry/setup_stream.py` (State Machine המלא) | AT-3.1–3.6, AT-3.8, AT-3.9 |
| §7 iFVG | `entry/setup_stream.py::_track_ifvg_candidates` | AT-3.4 |
| §8 מודלי כניסה (M1/M2/M4) | `entry/m1.py`, `entry/m2.py`, `entry/m4.py` | `test_entry_models.py`, `test_full_pipeline_9_arms.py` |
| §9 SL — שלוש היפותזות | `entry/sl_geometry.py` | `test_sl_geometry.py`, AT-2.6 |
| §10 TP/Sizing/מכסה | `entry/sl_geometry.py` (TP_RR), `risk/sizing.py`, `risk/engine.py`, `risk/portfolio.py` | AT-2.5, AT-2.7, AT-3.11 |
| §11 חדשות והחזקה | `session/calendar_engine.py`; תגי Overnight/Weekend/news_cross — **קבועים False, נדחו ל-T4.2 (KI-012)** | AT-3.9 |
| §12 ביצוע ועלויות | `execution/fill_simulator.py`, `execution/cost_model.py` | AT-2.1–2.4, AT-2.8 |
| §13 פרוטוקול מחקר (WF/Hold-Out/Baseline) | `config/models.py::RunConfig` מוצהר; **טרם נצרך בלוגיקת ריצה — Phase 4/5** | — |
| §14 State Machine (מחייב) | `entry/setup_stream.py` — זהה 1:1 למפרט | AT-3.1–3.9 |
| §15 Scoring & AI (Log-Only) | `Setup.score` קיים בטיפוס, **לעולם לא מאוכלס ב-Phase 3 — Phase 4 T4.3 בכוונה** | — |
| H2/Race-09:00 (עיבוד דו-שלבי) | `backtest/orchestrator.py::_merged_timeline` (D-063 תוקן) | `test_h2_merge_order.py` |
| Point-in-Time / No-Lookahead | `store/state_store.py::MarketContext.as_of`, `data/spread_report.py::ExpandingSpreadReport` (D-055) | AT-1.6 (Prefix-Consistency), AT-3.12 |
| Feature Store — Context Snapshots (T3.6) | `backtest/context_snapshot.py` | AT-3.13 |
| Viz בסיסי (T3.5) | `viz/trade_page.py` | `test_trade_page.py` |

---

## 3. כל ההחלטות (`docs/DECISIONS_LOG.md` — מקור האמת המלא)

**D-001–D-036 (Phase 0–2):** מתועדות ומאושרות בדוחות הסיום של Phase 0/1/2 בהתאמה; ללא שינוי ב-Phase 3.

**D-037–D-065 (Phase 3, כולן בטבלה המלאה ב-DECISIONS_LOG.md):**

| ID | תמצית | סוג |
|---|---|---|
| D-037 | עצמאות-ממקור-נתונים + שער Research Readiness Review לפני T3.4 | Process |
| D-038 | טיפוסי ליבה → `src/core` (Stability Rule Refactor) | Arch |
| D-039 | דפוס `NotImplementedError` עד חיווט מנוע אופציונלי (spread/session/calendar) | Arch |
| D-040 | פערי-פירוט SPEC §2 נסגרו בפרשנות הנדסית מפורשת | Rule (הבהרה) |
| D-041 | תיקון StateStore ל-Prefix-Consistency (גרסאות Swing/FVG) | Arch |
| D-042 | פרמטרי D1 Displacement — הזרקה מפורשת חובה, אין Default שקט | Arch |
| D-043 | תקדים: אסור Reach-Through לשדות פרטיים, גם בבדיקות — Accessor ציבורי תמיד | Process |
| D-044 | דיוק Sizing (RA-26) — ללא עיגול Lot-Step ב-v1 | RA |
| D-045 | Reference Entry Price מול מחיר-ביצוע — RiskEngine בודק גאומטריה מול הראשון בלבד | Rule (הבהרה) |
| D-046 | טיפוסי ליבה נוספים: `Side`/`ArmId`/`OrderIntent` | Arch |
| D-047 | סדר RiskEngine: גאומטריה→מכסה→Sizing | Arch |
| D-048 | שלוש פעולות היגיינה, Critical Review עצמי Phase 2 | Process |
| D-049 | `median_spread` חייב Point-in-Time (Rolling/Expanding) — הכרעה, טרם מומש בזמנו | Rule |
| D-050 | Execution Delay מומש (SPEC §12), היקף Entry+Exit — סוגר KI-009 | Rule |
| D-051 | Phase 2 נסגר רשמית (Green-Conditional) | Process |
| D-052 | פיצול Setup-vs-Arm outcome (Design Review לפני קוד Phase 3) | Rule + Arch |
| D-053 | תוקן: אכיפת חלון H1 על R/S/Inversion (נמצא בביקורת עצמית) | Arch |
| D-054 | תוקן: Blackout חוסם Engagement (נמצא באותה ביקורת) | Arch |
| D-055 | Expanding נבחר על Rolling; מומש בפועל — סוגר KI-007 | Rule + Arch |
| D-056 | RA-28: `initial_equity_usd=$10,000` (עמימות אמיתית שנפתרה) | RA |
| D-057 | `build_orchestrator` מומש — סוגר KI-016/KI-017 | Arch |
| D-058 | `context_snapshots.order_id` Nullable FK (עמימות שנפתרה) | Arch |
| D-059 | תוקן: `setups`/`experiments`/`runs`/`portfolios` מעולם לא נכתבו | Arch |
| D-060 | `setup_arm_outcomes` — כתיבה חד-פעמית במצב סופי, לא Event Log (סתירה שנפתרה) | Arch |
| D-061 | T3.5 Viz בסיסי מומש | Arch |
| D-062 | תוקן: מוני `RunResult.fills`/`orders_cancelled` מתים; הוכחת 9-תיקים מלאה | Arch |
| D-063 | תוקן: סדר H2 הפוך (`_ENTRY_ORDER`) — 4H לפני 1M/5M | Arch |
| D-064 | KI-020 נסגר — פייפליין מלא מ-4H גולמי, ללא זריעה | Arch |
| D-065 | Phase 3 (צד קודי) נסגר רשמית (Green-Conditional) | Process |

---

## 4. Known Issues — סטטוס סופי (`docs/KNOWN_ISSUES.md` — מקור האמת המלא)

### 4.1 סגורות (קוד) — 11
KI-004, KI-005, KI-006, KI-007, KI-009, KI-014, KI-016, KI-017, KI-020 — כולן נסגרו במהלך Phase 3, כל אחת עם בדיקת-רגרסיה ייעודית. (KI-004/KI-009 נסגרו ב-Phase 1/2 בהתאמה, נשארות ברשימה להשלמות.)

### 4.2 פתוחות — חסימת-סביבה בלבד (לא-קוד; חוסמות Research Readiness Review, לא Phase 3)
| ID | חומרה | תיאור תמציתי | חוסם |
|---|---|---|---|
| KI-001 | high | סביבת הפיתוח חוסמת רשת ל-`datafeed.dukascopy.com` | T3.4 |
| KI-002 | medium | `point_value=0.001` (XAUUSD) לא אומת מול דאטה אמיתי | T3.4 |
| KI-010 | high | לוח חדשות היסטורי אמיתי (RA-23) לא אותר/אומת | T3.4 |

### 4.3 פתוחות — קוד, נמוכות-חומרה או ב-Scope מוצהר של Phase 4 (לא חוסמות Phase 3)
| ID | חומרה | תיאור תמציתי | ייעוד |
|---|---|---|---|
| KI-003 | low | דיוק-זמן ל-`mitigation_pct` בין עדכוני-ביניים | v2 אם יידרש |
| KI-008 | low | ספי Validator (`gap_threshold`/`spike_z`) לא מוצהרים כ-RA | v2 אם יידרש |
| KI-011 | low | M4 מחזיר Intent יחיד בלבד למקרה-קצה נדיר (2 Setups, אותו נר) | לא מתוכנן |
| KI-012 | low | `trades.cost_spread`/`cost_slippage`/`tag_*` קבועים 0.0/False | **T4.2 (בכוונה)** |
| KI-013 | low | `trades.mae_r`/`mfe_r` = NULL | **T4.2 (בכוונה)** |
| KI-015 | medium | אינטראקציית מכסה בין Setups מרובים על אותו תיק, אותו יום | טרם נבדק |
| KI-018 | medium | `runs.config_hash`/`code_version`/`data_version` = placeholder "unknown" | חיווט אמיתי, T3.4/Phase 4 |
| KI-019 | low | פוזיציה פתוחה בתום-ריצה לא מקבלת שורת `setup_arm_outcomes` | מקרה-קצה מתועד |

**סה"כ KI פתוחות: 11 (3 חסימת-סביבה + 8 קוד-נמוך/מוצהר).**

---

## 5. כיסוי בדיקות-קבלה (Acceptance Tests)

| Phase | AT-IDs | סטטוס |
|---|---|---|
| Phase 0 | AT-0.1–AT-0.7 | ירוקות (מול Fixtures סינתטיים; מול דאטה אמיתי — חסום ע"י KI-001) |
| Phase 1 | AT-1.1–AT-1.6 (כולל Prefix-Consistency) | ירוקות |
| Phase 2 | AT-2.1–AT-2.8 | ירוקות |
| Phase 3 | AT-3.1–AT-3.9, AT-3.11, AT-3.12, AT-3.13 | ירוקות |
| Phase 3 | AT-3.10 (20 עסקאות מדגם, ידני מול דאטה אמיתי) | **לא-ישים — דורש T3.4/דאטה אמיתי** |

כל AT ממופה לקובץ בדיקה ספציפי תחת `tests/test_at{phase}_{n}_*.py`; המיפוי המלא ב-`docs/ACCEPTANCE_TESTS.md`.

---

## 6. Commit Log — Phase 3 (`0214d1a`..`5da3305`, 20 Commits)

| # | Hash (מלא) | תאריך | הודעה |
|---|---|---|---|
| 1 | `ff98a621c5483312b2351a774fe2fe230bb6cdd` | 2026-07-09 | D-052: split Setup outcome into model-agnostic vs per-arm (Design Review) |
| 2 | `0378e3757ca411020a3699701e1adaab7b4b537` | 2026-07-09 | T3.1: config loader (Pydantic v2) + Session/Calendar Engines |
| 3 | `eafab701059d294ae87404514060498b7ac58c0` | 2026-07-09 | T3.2: Setup Stream (model-agnostic Entry State Machine) |
| 4 | `addf3fe12e7038c26966e148ab1ba2d5cf739dc` | 2026-07-09 | T3.2: M1/M2/M4 Entry Models + SL-anchor geometry |
| 5 | `4e55a17e6bd31526dd0c6ed1ead9e483250448b` | 2026-07-09 | D-053: enforce H1 window gate on R/S/Inversion formation + Journal writer |
| 6 | `c769e55c67f059696f479a4b499f70b3474ede8` | 2026-07-09 | D-054: block Setup Engagement during News Blackout |
| 7 | `0f15ad7e9b8c93d01681df540e0a25aeee2a3db` | 2026-07-09 | T3.3: Backtest Orchestrator -- two-stage event loop, 9-arm wiring |
| 8 | `bac57a2ea9336075b9be9f19a1764d1d2ce1e95` | 2026-07-09 | Phase 3 (T3.1-T3.3): demo + benchmark |
| 9 | `b13805abf9f99645d99b7c5907b95efda328204` | 2026-07-09 | Critical Review: add zero-coverage same_zone_reentry test (SPEC S10) |
| 10 | `1d0690fa5ad6bed84c6b232fec141063e9a7a9f` | 2026-07-09 | Critical Review (T3.1-T3.3 checkpoint): log KI-014..KI-018 test/wiring gaps |
| 11 | `003619b2ca7aa770bcb27d210ceeeb793f438ac` | 2026-07-09 | Implement real Expanding SpreadReport, closing KI-007 (D-049/D-055) |
| 12 | `9d7010602752ff04d02903f6f9f0db577d1a4ea` | 2026-07-10 | Wire config/models.py into the Orchestrator via a run-builder, closing KI-016/KI-017 |
| 13 | `c7a2c7395a421a60929f9dcab90881deb5dfd88` | 2026-07-10 | T3.6 Context Snapshots + fix a chain of previously-invisible Journal bugs |
| 14 | `1d96021cd107e2e97413fbdb0a4ae25e68ecf0b` | 2026-07-10 | T3.5: basic per-trade Viz (trade page) |
| 15 | `6edbd775bf406bcbc41fc1fd255858c95532c90` | 2026-07-10 | Critical Review findings: fix dead RunResult counters, prove full 9-arm pipeline |
| 16 | `e17b4c75265e33e9301ad7e4543070de403d5ee` | 2026-07-10 | Fix H2/Race-09:00 bar ordering: _ENTRY_ORDER had 4H before 1M/5M (D-063) |
| 17 | `77d2adb874b2640bc5585a0c8d53100673fa32c` | 2026-07-10 | Remove dead _QUANTILES constant in spread_report.py |
| 18 | `899eccfa0284b8f9db760d0da157e165bdafee5` | 2026-07-10 | Close KI-020: prove the full pipeline from raw 4H bars, zero seeding |
| 19 | `a28a99ad33b83965265ef444143f0773cfe171c` | 2026-07-10 | Mark KI-005 closed (fix was already in place, status was never updated) |
| 20 | `5da3305f21e6caf4a4ae8a856ecd30f4c25cac53` | 2026-07-10 | Close Phase 3 (code side): Green-Conditional, per D-065 |

**Base (סוף Phase 2):** `0214d1a` — D-051: formally close Phase 2 (Green-Conditional, D-036 pattern).

---

## 7. כיסוי-קוד (Code Coverage)

נמדד בפועל (`pytest-cov`, 127 בדיקות, נוסף ל-`pyproject.toml` כתלות-dev ייעודית למסמך זה):

| מודול | Stmts | Miss | Cover |
|---|---|---|---|
| `src/backtest/orchestrator.py` | 264 | 10 | 96% |
| `src/backtest/context_snapshot.py` | 42 | 5 | 88% |
| `src/backtest/run_builder.py` | 51 | 0 | 100% |
| `src/config/models.py` | 164 | 0 | 100% |
| `src/entry/setup_stream.py` | 204 | 12 | 94% |
| `src/entry/sl_geometry.py` | 30 | 2 | 93% |
| `src/execution/fill_simulator.py` | 141 | 12 | 91% |
| `src/risk/engine.py` | 33 | 0 | 100% |
| `src/store/state_store.py` | 102 | 6 | 94% |
| `src/viz/trade_page.py` | 66 | 3 | 95% |
| `src/journal/duckdb_writer.py` | 19 | 1 | 95% |
| `src/data/bar_builder.py` | 52 | 19 | 63% *(ענפי-רשת-אמיתית, KI-001)* |
| `src/data/dukascopy_downloader.py` | 99 | 14 | 86% *(ענפי-רשת-אמיתית, KI-001)* |
| **סה"כ (`src/`)** | **2,090** | **125** | **94%** |

הפער העיקרי מתרכז במודולי Phase 0 (`bar_builder`/`dukascopy_downloader`) בענפים שדורשים גישת-רשת אמיתית (KI-001) — לא ניתן לכיסוי בסביבה זו. מודולי Phase 3 עצמם (Orchestrator/SetupStream/RiskEngine/Viz/Journal) בטווח 88–100%.

---

## 8. Quality Gates — סטטוס סופי (`bash scripts/ci.sh`)

| שער | תוצאה |
|---|---|
| Functional (pytest) | **127/127 ירוקות** |
| Code Quality (ruff) | All checks passed |
| Code Quality (pylint duplicate-code) | 10.00/10 |
| Architecture (import-linter) | 4/4 חוזים, 0 שבורים |
| Documentation | מסמך זה + DECISIONS_LOG/KNOWN_ISSUES/ACCEPTANCE_TESTS מעודכנים |
| Regression | 0 רגרסיה על Phase 0–2 |

---

## 9. חסמים שנותרו — Research Readiness Review בלבד (לא-קוד)

Phase 4 **אינו** מתחיל אוטומטית עם סגירת השער הקודי. שלושה פריטים בלבד חוסמים, כולם דורשים דאטה אמיתי מסביבה עם גישת-רשת:

1. **KI-001** — גישת רשת ל-`datafeed.dukascopy.com` (3 שנות Ticks + Warm-Up).
2. **KI-002** — אימות `point_value` מול דאטה אמיתי.
3. **KI-010** — לוח חדשות היסטורי אמיתי (RA-23).

הליך הפתיחה: `docs/RESEARCH_READINESS_REVIEW.md` — כל 9 הסעיפים חייבים GO, כולל T3.4 (ריצה אמיתית) ו-AT-3.10 (20 עסקאות מדגם, אישור-משתמש ידני). **דוח זה אינו מהווה את אותה סקירה** — הוא Audit של הצד הקודי בלבד.

---

*מסמך זה קפוא נכון ל-commit `5da3305`. כל שינוי עתידי (תיקון-באג קריטי בלבד, לפי הנחיית המשתמש) יתועד כרשומת D-0XX חדשה ב-DECISIONS_LOG.md ויחייב עדכון מקביל כאן.*
