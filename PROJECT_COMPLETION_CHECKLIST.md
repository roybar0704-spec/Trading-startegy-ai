# PROJECT COMPLETION CHECKLIST — XAUUSD Research Platform

**מעמד:** ה-Checklist התפעולי הסמכותי לקביעה האם הפרויקט מתקרב לסיום (`CLAUDE.md`, סעיף "Tests passing ≠ PROJECT COMPLETE").
**עוגן ראיות:** `adcdcb9a869a65e30cbed6645e32afc37082f171` (`origin/main`)
**נוצר:** 2026-08-19 · **מקור:** READ-ONLY AUDIT מלא מול `origin/main`

> **הפרויקט אינו PROJECT COMPLETE, ו-RRR הוא NO-GO.**
> אין להכריז על סיום רק משום שהבדיקות עוברות, Phase 0–3 ירוקים, הדאטה קיים, ה-Hold-Out קיים,
> הקוד יציב, או ש-RRR נראה חיובי. נדרש מילוי מלא ומאומת של כל הקריטריונים למטה.

## מוסכמות סימון

`[x]` = הושלם **ומגובה בראיה** · `[ ]` = לא הושלם
**סטטוסים:** `COMPLETE` · `PARTIAL` · `NOT STARTED` · `BLOCKED` · `REQUIRES VERIFICATION` · `NOT YET RECORDED`
בספק — `[ ]` עם `REQUIRES VERIFICATION`. קיום רכיב אינו הוכחת השלמה.

---

## 1. Governance

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 1.1 | `docs/SPEC_V1_FROZEN.md` קיים וקפוא | COMPLETE | `git ls-tree origin/main -- docs` | לא | — |
| 1.2 | `DECISIONS_LOG` מעודכן, ללא כפילויות | COMPLETE | 87 רשומות `D-001…D-087`; `uniq -d` ריק | לא | עדכון שוטף |
| 1.3 | `KNOWN_ISSUES` מתוחזק | PARTIAL | 24 KI; 8 פתוחים/חלקיים | לא | ר' §16 |
| 1.4 | `ACCEPTANCE_TESTS` מוגדרים | PARTIAL | 47 AT מוגדרים; 36 עם קובץ ייעודי | לא | ר' §15 |
| 1.5 | `QUALITY_GATES` — ששת השערים ירוקים | **BLOCKED** | RRR שורה 5 = ❌ NO-GO (D-079/D-080) | **כן** | Performance + Documentation Gates |
| 1.6 | `RESEARCH_READINESS_REVIEW` = GO | **BLOCKED** | שורה 5 NO-GO ⇒ פסיקה כוללת NO-GO | **כן** | ר' §17 |
| 1.7 | `WORK_ORDER_PROTOCOL.md` נאכף | PARTIAL | `PREFLIGHT_B10.md §5` — Commit #1 בוצע ללא PREFLIGHT קודם; מתועד | לא | `PREFLIGHT_B9.md` retroactive חסר (GOV-3) |
| 1.8 | `CLAUDE.md` משקף את מבנה הריפו בפועל | PARTIAL | B-10 Commit #1 (`c2bfc4b`) תיקן את עץ הריפו | לא | S2/S3/S4 — ר' §1.9 |
| 1.9 | אי-דיוקים ידועים ב-`CLAUDE.md` | **NOT YET FIXED** | S2: `RA-01…RA-23` בשורות 14+53, בפועל עד **RA-29** · S3: בלוק `docs/` מונה 11 מתוך 16 (חסר `RESEARCH_READINESS_REVIEW.md` בין השאר) · S4: `benchmarks/` נעדר מהעץ (4 קבצים tracked) | לא | **Commit #2 נפרד — טעון אישור Roy** |
| 1.10 | `README.md` מעודכן | PARTIAL | `README:19` = "Stage A (B-1…B-7): Closed"; בפועל B-8/B-9/B-10 הושלמו | לא | עדכון |
| 1.11 | `PROJECT_STATE.md` — הכרעת גורל | **REQUIRES VERIFICATION** | ר' **U3** למטה | לא | הכרעת Roy |

- [ ] **1. Governance** — `PARTIAL`. חוסמים: 1.5, 1.6.

## 2. Git / Reproducibility

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 2.1 | `origin/main` מזוהה ומאומת | COMPLETE | `adcdcb9a869a65e30cbed6645e32afc37082f171` | לא | — |
| 2.2 | זהות ריצה: `config_hash`/`code_version`/`data_version`/`split_type`/`seed` | COMPLETE | D-068, `src/backtest/run_builder.py`, AT-3.14 | לא | — |
| 2.3 | Registry ריצות append-only | PARTIAL | `data/registry/runs.jsonl` (D-068, זמני עד T5.5) | לא | T5.5 Experiment Tracker |
| 2.4 | Golden Regression | COMPLETE | `tests/test_golden_regression.py`, `tests/golden/at3_14_baseline.sha256` (KI-024) | לא | — |
| 2.5 | Config מוקפא ומוגן hash | COMPLETE | `config/rules_v1.yaml` + `.sha256`, `src/config/frozen_guard.py` | לא | — |
| 2.6 | תלויות נעולות | COMPLETE | `uv.lock` tracked | לא | — |
| 2.7 | CI אוטומטי | **NOT STARTED** | אין `.github/workflows`; קיים `scripts/ci.sh` (POSIX בלבד) | לא | לא נרשם כ-KI |
| 2.8 | ניקוי ענפים | NOT STARTED | 4 ענפי remote ישנים: `b8-integration`, `ki-001-proxy-check-qtdhjg`, `docs-preservation`, `j5para` | לא | הכרעת Roy |
| 2.9 | הכרעת 4 קבצי untracked | **REQUIRES VERIFICATION** | `B-10_v5_DRYRUN.ps1` · `B-10_v5_WRITE.ps1` · `B-10_v6_WRITE.ps1` · `qg.txt` — **אין לגעת בהם אוטומטית** | לא | הכרעה נפרדת של Roy |

- [ ] **2. Git / Reproducibility** — `PARTIAL`.

## 3. Real Market Data

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 3.1 | גישת רשת ל-Dukascopy | COMPLETE | KI-001 closed (D-069), `src/data/browser_transport.py` | לא | — |
| 3.2 | `point_value` מאומת | COMPLETE | KI-002 closed (D-070), נובמבר 2022, 3,641,776 ticks | לא | — |
| 3.3 | 39 חודשי דאטה מלאים | **PASS WITH CAVEATS** | 33 Research + 6 Hold-Out — אומת עצמאית ע"י Claude Code (D-089, ר' §13.3/§13.8): כל 39 החודשים קיימים בפועל בסביבה זו (33 מתחת ל-`data/ticks` + 6 מתחת ל-`data/holdout`, בדיקה ישירה), **לא** "קובץ Parquet אחד בלבד" כפי שנרשם קודם — אותה קביעה קודמת הייתה שגויה/מיושנת. שני פערים פרוצדורליים נותרים (HEAD היסטורי בזמן B.2 = STRONGLY INFERRED; פלט Dry-Run היסטורי = INCONCLUSIVE) — ר' §13.3; אינם נוגעים לשלמות/נכונות הדאטה עצמו | לא | אופציונלי בלבד — ר' §13.3 |
| 3.4 | Validator — חורים/ספייקים | COMPLETE | `src/data/validator.py`; AT-0.3 | לא | — |
| 3.5 | ספי Validator כ-RA מתועדים | PARTIAL | `spike_z_threshold` = RA-29 (D-076); **`gap_threshold` לא רשום** (KI-008) | לא | לרשום כ-RA |
| 3.6 | ראיית דאטה-אמיתי ל-AT-0.* | PARTIAL | RRR שורה 4 = GO with explicit limitations (B-5, D-075) | לא | — |
| 3.7 | לוח חדשות אמיתי | PARTIAL | `data/news/bls_calendar.csv`, 66 אירועים; KI-010 — 2/7 סוגי-אירוע | **ר' §17** | Coverage Expansion (Open Future Work, D-084) |

- [ ] **3. Real Market Data** — `PARTIAL`.

## 4. Bar Building

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 4.1 | BarBuilder 1M/5M/4H מ-Ticks בלבד | COMPLETE | T0.5, `src/data/bar_builder.py` | לא | — |
| 4.2 | עוגן NY-Close ל-4H | COMPLETE | AT-0.5 (`test_at0_5_h4_anchor.py`) | לא | — |
| 4.3 | DST | COMPLETE | AT-0.4 (`test_at0_4_dst_build.py`) | לא | — |
| 4.4 | עקביות Bar↔Tick | COMPLETE | AT-0.6 (`test_at0_6_bar_tick_consistency.py`) | לא | — |
| 4.5 | Timezone — UTC פנימי, NY לסשן | COMPLETE | `tests/test_session_engine.py` · `tests/test_market_context_session.py` · D-080 (DuckDB TZ determinism) | לא | — |

- [x] **4. Bar Building** — `COMPLETE`. כל חמשת הפריטים מגובים בקובצי בדיקה או ב-D-entry, לא בהצהרת דרישה.

## 5. Strategy Specification

> **כל חוק כאן חייב להגיע מ-`docs/SPEC_V1_FROZEN.md` או `docs/trigger_spec_state_machine_v1_1.md` בלבד.**
> חוקים לא אומתו אחד-אחד ב-audit הנוכחי — הוא היה ברמת מבנה ומצב, לא ברמת חוק בודד.

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 5.1 | SPEC קפוא וקיים | COMPLETE | `docs/SPEC_V1_FROZEN.md` | לא | — |
| 5.2 | State Machine של ה-Trigger | COMPLETE | `docs/trigger_spec_state_machine_v1_1.md`, `src/entry/setup_stream.py` | לא | — |
| 5.3 | מיפוי חוק-אחר-חוק: SPEC → קוד → AT | **REQUIRES VERIFICATION** | לא בוצע ב-audit זה | לא | מיפוי מפורש נדרש |
| 5.4 | כל Setup מגיע למצב סופי מתועד | COMPLETE | 7 מצבים סופיים (`CLAUDE.md`); AT-3.5, AT-3.8 | לא | — |

- [ ] **5. Strategy Specification** — `PARTIAL` (5.3 טעון אימות).

## 6. Phase Gates

| Phase | תוכן | סטטוס | ראיה | חוסם? |
|---|---|---|---|---|
| **Phase 0** — Data Pipeline | T0.1–T0.6 | PARTIAL | תת-שער קוד סגור (AT-0.1–0.7); תת-שער דאטה — KI-001/KI-002 סגורים מאז | לא |
| **Phase 1** — State Store + Structure | T1.1–T1.6 | COMPLETE | AT-1.1–AT-1.6 ירוקות | לא |
| **Phase 2** — Execution Layer | T2.1–T2.4 | Green-Conditional | AT-2.1–AT-2.8 ירוקות; ר' **U2** | לא |
| **Phase 3** — End-to-End צר | T3.1–T3.6 | Green-Conditional (קוד) | AT-3.* ירוקות; **T3.4 לא בוצע** | **כן** |
| **T3.4** — ריצת בקטסט אמיתית ראשונה | M2 × S_body, 3 חודשי In-Sample | **BLOCKED** | דורש RRR = GO | **כן** |
| **Phase 4** — כל הזרועות + סטטיסטיקה | T4.1–T4.5 | **NOT STARTED** | `src/features`, `src/stats`, `src/scoring` לא קיימים | — |
| **Phase 5** — Validation & Protocol | T5.1–T5.5 | **NOT STARTED** | `src/validation`, `src/tracker` לא קיימים | — |
| **Phase 6** — AI + Viz מלא | T6.1–T6.2 | **NOT STARTED** | `src/ai` לא קיים | — |

### 6.A — כלל סגירת Phase (`PHASE_PLAN.md:2`)

> *"Phase נסגר רק כשמתקיימים ארבעתם — (א) כל בדיקות הקבלה ירוקות, (ב) **תוצר עובד הודגם למשתמש** (Working Software Rule), (ג) **כל ששת ה-Quality Gates ירוקים**, (ד) אישור משתמש."*

- [ ] 6.A.1 — (א) בדיקות קבלה ירוקות
- [ ] 6.A.2 — (ב) **Working Software Rule** — Demo הודגם למשתמש
- [ ] 6.A.3 — (ג) ששת ה-Quality Gates ירוקים — **BLOCKED**, ר' §1.5
- [ ] 6.A.4 — (ד) אישור משתמש מפורש

**Demo נדרש לכל Phase** (`PHASE_PLAN.md`, טבלת "תוצרי עבודה"):

| Phase | Demo | סטטוס |
|---|---|---|
| 0 | `scripts/demo_phase0.py --month 2024-03` | קיים · הדגמה למשתמש — `REQUIRES VERIFICATION` |
| 1 | `scripts/demo_phase1.py --period ...` | קיים · הדגמה למשתמש — `REQUIRES VERIFICATION` |
| 2 | `scripts/demo_phase2.py` | קיים · הודגם (D-036/D-051) |
| 3 | `scripts/demo_phase3.py` | קיים · הודגם מקצה-לקצה (Gate קודי, 2026-07-10) |
| 4 | `scripts/demo_phase4.py` | **לא קיים** — Phase 4 לא התחיל |
| 5 | `scripts/demo_phase5.py` | **לא קיים** — Phase 5 לא התחיל |
| 6 | `scripts/demo_phase6.py` | **לא קיים** — Phase 6 לא התחיל |

### 6.B — Phase 3: השער המלא (`PHASE_PLAN.md:46`) — **לא סגור**

> *"**Gate (מלא, לא-סגור עדיין):** AT-3.*; **20 עסקאות מדגם מאומתות ידנית על הגרף מול היומן** + אישור משתמש שהלוגיקה = הכוונה. חסום ע"י Research Readiness Review (KI-001/KI-010)."*

- [ ] 6.B.1 — כל `AT-3.*` הרלוונטיים ירוקים — `PARTIAL` (ר' §15)
- [ ] 6.B.2 — **20 עסקאות מדגם** נבחרו מריצה אמיתית — `NOT STARTED` (דורש T3.4)
- [ ] 6.B.3 — **אימות ידני על הגרף מול היומן** — `NOT STARTED` · זהו **AT-3.10**, המוגדר ב-`ACCEPTANCE_TESTS.md` כ-**`[ידני]` · "שער חובה"**
- [ ] 6.B.4 — **אישור משתמש שהלוגיקה = הכוונה** — `NOT STARTED` · סמכות Roy
- [ ] 6.B.5 — חסימה: RRR = NO-GO ⇒ T3.4 חסום ⇒ 6.B.2–6.B.4 חסומים

**סטטוס Phase 3: `REQUIRES VERIFICATION / NOT COMPLETE`.** הצד הקודי סגור כ-Green-Conditional (2026-07-10); **השער המלא אינו סגור.**

### 6.C — Phase 4: קריטריוני Gate (`PHASE_PLAN.md:54`)

> *"**Gate:** AT-4.* + AT-F.*; דו"ח השוואה זוגי 9 זרועות על In-Sample."*

- [ ] 6.C.1 — `AT-4.1` … `AT-4.4` ירוקים — `NOT STARTED`
- [ ] 6.C.2 — `AT-F.*` — **`UNRESOLVED`**, המשפחה אינה מוגדרת ב-`ACCEPTANCE_TESTS.md`. ר' **U5**
- [ ] 6.C.3 — **דו"ח השוואה זוגי של 9 הזרועות על In-Sample** — `NOT STARTED`
- [ ] 6.C.4 — Demo `scripts/demo_phase4.py` — דשבורד השוואת 9 זרועות — `NOT STARTED`
- [ ] 6.C.5 — ארבעת תנאי §6.A

### 6.D — Phase 5: קריטריוני Gate (`PHASE_PLAN.md:62`)

> *"**Gate:** AT-5.*; דו"ח Baseline מלא; Reproducibility ירוק."*

- [ ] 6.D.1 — `AT-5.1` … `AT-5.4` ירוקים — `NOT STARTED`
- [ ] 6.D.2 — **דו"ח Baseline מלא** — `NOT STARTED`
- [ ] 6.D.3 — **Reproducibility ירוק** — `NOT STARTED`
- [ ] 6.D.4 — Demo `scripts/demo_phase5.py` — Walk-Forward + Baseline + p-value + הוכחת Reproducibility — `NOT STARTED`
- [ ] 6.D.5 — ארבעת תנאי §6.A

### 6.E — Phase 6: קריטריוני Gate (`PHASE_PLAN.md:67`)

> *"**Gate:** AT-6.*."*

- [ ] 6.E.1 — `AT-6.1` · `AT-6.2` ירוקים — `NOT STARTED`
- [ ] 6.E.2 — Demo `scripts/demo_phase6.py` — ניתוח AI טרום-סשן + דשבורד מלא — `NOT STARTED`
- [ ] 6.E.3 — ארבעת תנאי §6.A

> `PHASE_PLAN.md:69` — **"אחרי Phase 5 בלבד: ריצות המחקר האמיתיות לפי הפרוטוקול → הכרעת זרועות → נעילת v1.2."**

- [ ] **6. Phase Gates** — `PARTIAL`. חוסמים: T3.4 · השער המלא של Phase 3 (§6.B) · Quality Gates (§6.A.3).

## 7. Costs / Execution

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 7.1 | Cost Model | COMPLETE | `src/execution/cost_model.py`, T2.1 | לא | — |
| 7.2 | Fill Simulator — Limit/Market/SL-First/Gap-Through | COMPLETE | AT-2.1–AT-2.4 | לא | — |
| 7.3 | Execution Delay | COMPLETE | D-050, AT-2.8 (KI-009 closed) | לא | — |
| 7.4 | RA-10 (Slippage-Stop) מכויל מול דאטה אמיתי | COMPLETE | RRR שורה 3 = GO (B-4, D-074); `0.10$` → `0.70$` | לא | — |
| 7.5 | Point-in-Time SpreadReport | COMPLETE | KI-007 closed (D-055), `ExpandingSpreadReport`, AT-3.12 | לא | — |
| 7.6 | פירוק עלויות בפועל ביומן | **PARTIAL** | KI-012: `cost_spread`/`cost_slippage` = `0.0` קבוע | לא | T4.2 |

- [ ] **7. Costs / Execution** — `PARTIAL`.

## 8. Trade Analytics

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 8.1 | `result_r` / R-multiple | COMPLETE | `Orchestrator._close_trade()`; לא מושפע מ-KI-012 | לא | — |
| 8.2 | `apply_realized_pnl` מחווט | COMPLETE | KI-006 closed (T3.3) | לא | — |
| 8.3 | Journal persistence | COMPLETE | `src/journal/duckdb_writer.py`, 18 טבלאות, AT-3.14 | לא | — |
| 8.4 | MAE / MFE | **NOT STARTED** | T4.2 | לא | Phase 4 |
| 8.5 | תיוג עסקאות (`tag_overnight`/`weekend`/`news_cross`/…) | **NOT STARTED** | KI-013 — קבוע `False` | לא | T4.2 |
| 8.6 | פילוחים (שעה/Setup/זרוע/רבעון/תגים) | **NOT STARTED** | T4.2 | לא | Phase 4 |

- [ ] **8. Trade Analytics** — `PARTIAL`.

## 9. Validation

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 9.1 | `Validator` על דאטה אמיתי | COMPLETE | D-071, D-072, B-3 | לא | — |
| 9.2 | כיול ספי Validator | PARTIAL | RA-29 (D-076); `gap_threshold` פתוח (KI-008) | לא | — |
| 9.3 | Regression Gate — מלוא החבילה ירוקה | COMPLETE | **179 passed** (אומת) | לא | — |
| 9.4 | Prefix-Consistency | COMPLETE | AT-1.6 (`test_at1_6_prefix_consistency.py`) | לא | — |
| 9.5 | Random Baseline + Bootstrap p-value | **NOT STARTED** | T5.3 | לא | Phase 5 |
| 9.6 | Sensitivity ±20% + Stability רבעוני | **NOT STARTED** | T5.4 | לא | Phase 5 |
| 9.7 | אימות ידני מתועד | **REQUIRES VERIFICATION** | אין רישום מרוכז של קבלות ידניות | לא | הגדרת מנגנון |

- [ ] **9. Validation** — `PARTIAL`.

## 10. Features / Statistics / Scoring

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 10.1 | Context Snapshots | COMPLETE | T3.6, `src/backtest/context_snapshot.py`, `tests/test_context_snapshots.py` | לא | — |
| 10.2 | `src/features` — Registry + Extractors | **NOT STARTED** | התיקייה לא קיימת. T4.4, `docs/FEATURE_SPEC_V1.md` | לא | Phase 4 |
| 10.3 | `src/stats` — Statistics Engine | **NOT STARTED** | התיקייה לא קיימת. T4.2 | לא | Phase 4 |
| 10.4 | `src/scoring` — Scoring Log-Only | **NOT STARTED** | התיקייה לא קיימת. T4.3 | לא | Phase 4 |
| 10.5 | Analytics API `stats.by(feature, metric)` | **NOT STARTED** | T4.5 | לא | Phase 4 |
| 10.6 | AT-4.1 / AT-4.2 / AT-4.3 / AT-4.4 | **NOT STARTED** | אין קובצי בדיקה | לא | Phase 4 |
| 10.7 | Features תיאוריים בלבד — לא מזינים החלטה | **REQUIRES VERIFICATION** | חוק-על 9; ייאכף בעת המימוש | לא | אכיפה ב-Phase 4 |

- [ ] **10. Features / Statistics / Scoring** — `NOT STARTED`.

## 11. Tracking / Visualization

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 11.1 | Trade Page (Viz בסיסי) | COMPLETE | T3.5, `src/viz/trade_page.py`, `tests/test_trade_page.py` | לא | — |
| 11.2 | `src/tracker` — Experiment Tracker | **NOT STARTED** | התיקייה לא קיימת. T5.5 | לא | Phase 5 |
| 11.3 | Dashboard (Equity, פילוחים, השוואת זרועות) | **NOT STARTED** | T6.2 | לא | Phase 6 |
| 11.4 | דוחות מחקר / Diagnostics | PARTIAL | `scripts/diagnostics/` (14 סקריפטים) | לא | — |
| 11.5 | AT-6.2 | **NOT STARTED** | אין קובץ בדיקה | לא | Phase 6 |

- [ ] **11. Tracking / Visualization** — `PARTIAL`.

## 12. AI

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 12.1 | `src/ai` — AI Analyst | **NOT STARTED** | התיקייה לא קיימת. T6.1 | לא | Phase 6 |
| 12.2 | גבולות AI — Read-Only, ללא השפעה על מסחר | **NOT STARTED** | T6.1 מגדיר Read-Only | לא | אכיפה במימוש |
| 12.3 | הפרדת נתונים / מניעת דליפה בשכבת AI | **NOT STARTED** | — | לא | Phase 6 |
| 12.4 | AT-6.1 | **NOT STARTED** | אין קובץ בדיקה | לא | Phase 6 |

- [ ] **12. AI** — `NOT STARTED`.

## 13. Hold-Out / Walk-Forward

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 13.1 | חלוקת Development / Hold-Out | COMPLETE | 33 Research (`2022/10–2025/06`) + 6 Hold-Out (`2025/07–12`) | לא | — |
| 13.2 | **Track A** — אכיפה Fail-Closed בקוד | COMPLETE | D-085; `TickParquetStore.holdout_range` חובה; T1–T6 PASS | לא | T7 = ACCEPTED WITH ENVIRONMENTAL LIMITATION |
| 13.3 | **Track B** — הפרדה פיזית בפועל | **PASS WITH CAVEATS** | D-089: 33+6=39 ללא חפיפה/חורים (V5/V9/V10), Hash מאומת מול פרובננס בלתי-תלוי `BATCH7_CLOSURE_REPORT.md` (V4/V11, קומיט מ-5 ימים לפני ה-Move), Fail-Closed מאומת מול קוד אמיתי (V6/V7/V12) — שתי ריצות עצמאיות (2026-08-11/12). **פערים נותרים, לא CONFIRMED:** HEAD היסטורי בזמן B.2 = STRONGLY INFERRED בלבד (`a28ba8c104fa2886074e517e7cb5f101c4b1045d`); פלט ה-Dry-Run ההיסטורי = INCONCLUSIVE (הפקודה רצה, הפלט לא נלכד) | לא | אופציונלי בלבד — Capture חוזר של HEAD/Dry-Run על מחשב-הבית אינו תנאי לנכונות (ר' D-089) |
| 13.4 | **Track C** — Sanity סופי לפני T3.4 | **NOT STARTED** | לא התחיל | לא | לפני T3.4 |
| 13.5 | `HoldoutGuard` — Loader מסרב, שימוש נרשם | COMPLETE | `src/data/holdout.py`; T5.2 מוקדם | לא | — |
| 13.6 | Walk-Forward Splitter (9M/3M) | **NOT STARTED** | T5.1 | לא | Phase 5 |
| 13.7 | Freeze points מוגדרים | **NOT STARTED** | — | לא | לפני Final Run |
| 13.8 | ניתוח עצמאי של `B2_postflight_raw_output.txt` | **COMPLETE** | בוצע במלואו ע"י Claude Code (D-089) — כולל `docgate_step4.txt` (התמלול המקורי הרחב יותר), אימות-Provenance מול `BATCH7_CLOSURE_REPORT.md`, ושחזור-Timeline מול Git History | לא | — |
| 13.9 | הערכה סופית על ה-Hold-Out | **NOT STARTED** | רק אחרי RRR GO ו-Phase 5 | לא | Final Run |

- [ ] **13. Hold-Out / Walk-Forward** — `PARTIAL`.

## 14. Multi-Arm Research

9 תיקים: `{M1, M2, M4} × {R_body, S_body, S_wick}` על Setup Stream זהה.

| # | דרישה | סטטוס | ראיה / מקור | חוסם? | פעולה נותרת |
|---|---|---|---|---|---|
| 14.1 | M2 מומש | COMPLETE | `src/entry/m2.py` | לא | — |
| 14.2 | M1 מומש | COMPLETE | `src/entry/m1.py` | לא | — |
| 14.3 | M4 מומש | COMPLETE | `src/entry/m4.py` | לא | — |
| 14.4 | שלוש זרועות SL | COMPLETE | `src/entry/sl_geometry.py` | לא | — |
| 14.5 | 9 תיקים רצים יחד ומבודדים | COMPLETE (Fixtures) | D-062, `tests/test_full_pipeline_9_arms.py` | לא | — |
| 14.6 | דטרמיניזם רב-זרועות | COMPLETE | D-087, AT-3.15 | לא | — |
| 14.7 | אינטראקציית מכסה | COMPLETE | D-087, AT-3.16; חשף וסגר באג M4 אמיתי | לא | — |
| 14.8 | **9 זרועות מול דאטה אמיתי** | **NOT STARTED** | רק M2×S_body נבדקה מול דאטה אמיתי (B-3) | לא | T4.1 |
| 14.9 | השוואת זרועות / Robustness | **NOT STARTED** | אחרי Phase 4–5 | לא | — |
| 14.10 | כל הזרועות מדווחות, כולל כושלות | **REQUIRES VERIFICATION** | חוק — אין להשמיט זרוע בגלל תוצאה | לא | אכיפה בדיווח |

- [ ] **14. Multi-Arm Research** — `PARTIAL`.

## 15. Acceptance Tests

**47 AT מוגדרים ב-`docs/ACCEPTANCE_TESTS.md`. 36 עם קובץ בדיקה ייעודי. 11 ללא (כולם Phase 4–6).**

| קבוצה | AT-IDs | קובץ ייעודי | סטטוס |
|---|---|---|---|
| Phase 0 | AT-0.1 … AT-0.7 | 7/7 | COMPLETE |
| Phase 1 | AT-1.1 … AT-1.6 | 6/6 | COMPLETE |
| Phase 2 | AT-2.1 … AT-2.8 | 8/8 | COMPLETE |
| Phase 3 | AT-3.1–3.6, 3.8, 3.9, 3.12, 3.14, 3.15, 3.16 | 12/12 | COMPLETE |
| Phase 3 — ללא קובץ ייעודי | **AT-3.7 · AT-3.11 · AT-3.13** | 0/3 | **REQUIRES VERIFICATION** — ר' **U1** |
| Phase 3 — **ידני במפורש** | **AT-3.10** | לא ישים | `ACCEPTANCE_TESTS.md`: *"**[ידני]** אימות 20 עסקאות … **שער חובה**"*. **היעדר קובץ בדיקה הוא לפי התכנון, לא פער.** `NOT STARTED` — דורש T3.4. ר' §6.B.3 |
| Phase 4 | AT-4.1 … AT-4.4 | 0/4 | NOT STARTED |
| **AT-F.\*** | לא מוגדרת | — | **UNRESOLVED** — `PHASE_PLAN:54` מתנה בה את שער Phase 4, אך המשפחה **אינה מוגדרת** ב-`ACCEPTANCE_TESTS.md`. ר' **U5** |
| Phase 5 | AT-5.1 … AT-5.4 | 0/4 | NOT STARTED |
| Phase 6 | AT-6.1 · AT-6.2 | 0/2 | NOT STARTED |

**ריצה מאומתת:** `uv run pytest` → **`179 passed`** (עוגן `adcdcb9`).
⚠️ `pyproject.toml` מגדיר `addopts = "-q"`. הפעלת `pytest -q` נוספת ⇒ `-qq` ⇒ **שורת הסיכום מושתקת**. `README:32` ו-`QUALITY_GATES.md:5` עדיין מורים `pytest -q`.

- [ ] **15. Acceptance Tests** — `PARTIAL`. 36/47 עם קובץ · 3 טעונים אימות (U1) · AT-3.10 ידני-בתכנון · 10 טרם החלו · `AT-F.*` לא מוגדרת (U5).

## 16. Known Issues

### 16.A — KI רשמיים ב-`docs/KNOWN_ISSUES.md`

**24 KI רשמיים בסך הכול: `KI-001` … `KI-024`. מהם 16 סגורים · 8 פתוחים/חלקיים · אפס `critical`.**
הטבלה הבאה מציגה את **8 הפתוחים/חלקיים בלבד**; 16 הסגורים אינם מפורטים כאן.

| ID | חומרה | סטטוס | תמצית | חוסם? |
|---|---|---|---|---|
| **KI-010** | **high** | partially closed | News Coverage — 2 מתוך 7 סוגי-אירוע High-Impact-USD. חסרים Core PCE, GDP, FOMC, ISM PMI, Retail Sales | **RRR שורה 7** — מוסדר בפרשנות D-078 |
| KI-008 | low | partially closed | `gap_threshold` (5min) לא רשום כ-RA | לא |
| KI-003 | low | open | `effective_ts` של עדכוני mitigation ביניים | לא |
| KI-011 | low | open | M4 מחזיר `OrderIntent` יחיד; שני Setups באותו נר | לא |
| KI-012 | low | open | `cost_spread`/`cost_slippage` = `0.0`; ייסגר ב-T4.2 | לא |
| KI-013 | low | open | תגי עסקה קבועים `False`; ייסגר ב-T4.2 | לא |
| KI-019 | low | open | מקרה-קצה מתועד, לא חוסם | לא |
| KI-021 | low | open | Registry ללא נעילה; רלוונטי בריצות מקבילות | לא |

**Functional Gate** דורש אפס פריטים פתוחים בחומרה `critical`/`high`. **KI-010 הוא ה-`high` הפתוח היחיד**, ופרשנות D-078 היא שמאפשרת מעבר.

---

### 16.B — פריטים שזוהו אך **טרם נרשמו** ב-`docs/KNOWN_ISSUES.md`

> ⚠️ **שני הפריטים הבאים אינם חלק מ-24 ה-KI הרשמיים.** הם אינם מופיעים ב-`docs/KNOWN_ISSUES.md`,
> אין להם מזהה רשמי מוקצה, ואין לספור אותם במניין ה-KI. הם מתועדים כאן בלבד, כחוב תיעודי פתוח.
> **רישומם ב-`docs/KNOWN_ISSUES.md` טעון אישור מפורש של Roy ולא בוצע.**

| מזהה זמני | סטטוס | תמצית |
|---|---|---|
| **KI-025** *(מוצע)* | **NOT YET RECORDED** | Boundary Ambiguity — `XAUUSD_HOLDOUT_RANGE.end = 2025-12-31T00:00:00Z` הוא גבול חצי-פתוח `[start, end)`; מנגנון החודש-השלם ו-`months_between()` הוכחו כלא-מושפעים בהרצה חיה |
| **KI-026** *(מוצע)* | **NOT YET RECORDED** | היעדר Transaction/Rollback סביב `separate_holdout()` ב-`run_separate_holdout.py`; לולאת ה-Post-Flight אינה בודקת קיום `.sha256` ביעד |

- [ ] **16. Known Issues** — `PARTIAL`. 24 רשמיים (8 פתוחים/חלקיים) + 2 פריטים שטרם נרשמו — **טעון אישור Roy**.

## 17. Final Research Readiness (RRR)

`docs/RESEARCH_READINESS_REVIEW.md` — שער חובה לפני T3.4. **GO רק אם כל תשעת הסעיפים GO.**

| # | סעיף | סטטוס |
|---|---|---|
| 1 | KI-001 נסגר? | ✅ GO (D-069) |
| 2 | KI-002 נסגר? | ✅ GO (D-070) |
| 3 | RA-10 כויל? | ✅ GO (B-4, D-074) |
| 4 | נתוני Dukascopy אומתו? | ⚠️ GO with explicit limitations (B-5, D-075) |
| 5 | **Quality Gates ירוקים?** | ❌ **NO-GO** (B-8, D-079/D-080) — Performance + Documentation |
| 6 | KI-007 נסגר? | ✅ GO (D-055) |
| 7 | KI-010 נסגר? | ⚠️ GO with explicit limitations (B-7, D-077/D-078) |
| 8 | KI-006 נסגר? | ✅ GO (T3.3) |
| 9 | סיבה כלשהי שלא להתחיל? | שיפוט פתוח — טעון הכרעה מפורשת |

> **פסיקה נוכחית: NO-GO.** סעיף אחד NO-GO ⇒ הפסיקה הכוללת NO-GO. **T3.4 חסום.**

- [ ] **17. RRR** — `BLOCKED`. פעולה נותרת: לסגור Performance Gate ו-Documentation Gate, ואז להריץ RRR מחדש.

## 18. Final Run / Freeze / Archive

**רק אחרי RRR GO ואחרי Phase 5.**

- [ ] 18.1 Freeze של `config` — `NOT STARTED`
- [ ] 18.2 Freeze של הדאטה + `data_version` מתועד — `NOT STARTED`
- [ ] 18.3 רישום commit ה-Git של הריצה — `NOT STARTED`
- [ ] 18.4 רישום הסביבה (Python, `uv.lock`, OS) — `NOT STARTED`
- [ ] 18.5 הרצת המחקר הסופי — `NOT STARTED`
- [ ] 18.6 הרצה חוזרת ואימות Reproducibility ביט-לביט — `NOT STARTED`
- [ ] 18.7 הערכת Hold-Out סופית (חד-פעמית) — `NOT STARTED`
- [ ] 18.8 ארכוב הראיות — `NOT STARTED`
- [ ] 18.9 דוח מחקר סופי — `NOT STARTED`
- [ ] 18.10 הכרזת **PROJECT COMPLETE** — `NOT STARTED`, **סמכות Roy בלבד**

- [ ] **18. Final Run / Freeze / Archive** — `NOT STARTED`.

---

## פריטים לא-פתורים (UNRESOLVED)

| ID | נושא | סטטוס | נדרש |
|---|---|---|---|
| **U1** | האם **AT-3.7 · AT-3.11 · AT-3.13** מכוסים בפועל בבדיקות קיימות? | **REQUIRES VERIFICATION** | מיפוי מפורש `AT → קובץ/פונקציה → ראיה`. **אין להסיק כיסוי משם או מהפניה בתיעוד.** רמז קיים: D-052 מזכיר AT-3.11 ב-`tests/test_orchestrator.py` — **לא אומת**. **הבהרה:** `AT-3.10` הוסר מ-U1 — `ACCEPTANCE_TESTS.md` מגדיר אותו במפורש כ-**`[ידני]`**, ולכן היעדר קובץ בדיקה הוא לפי התכנון (ר' §6.B.3) |
| **U2** | `PHASE_PLAN.md:44` — מעמד "Green-Conditional" ל-Phase 2/3 | **REQUIRES VERIFICATION** | `PREFLIGHT_B10 C-7` קובע שהנימוק המתועד **אינו הפער בפועל**. הפער האמיתי לא הוגדר. **אין לשנות את המסמך ללא אישור Roy** |
| **U3** | `PROJECT_STATE.md` — DG-3/DG-4 | **REQUIRES VERIFICATION** | המסמך מיושן: מצהיר `origin/main = 9db723c` (בפועל `adcdcb9`), `170/170 tests` (בפועל **179**), Evidence Anchor `79b55be`. **אין לעדכן/להקפיא/למחוק ללא אישור Roy** |
| **U4** | שרשרת אישורים | **RESOLVED** | Roy הוא הסמכות הסופית. המלצת ChatGPT או Claude Project **אינה מחליפה** אישור מפורש של Roy לשינוי מהותי. מעוגן ב-`CLAUDE.md` |
| **U5** | `AT-F.*` — סתירה בין `PHASE_PLAN.md` ל-`ACCEPTANCE_TESTS.md` | **REQUIRES VERIFICATION / UNRESOLVED** | `PHASE_PLAN.md:54` מגדיר את שער Phase 4 כ-**"AT-4.* + AT-F.*"**, אך משפחת `AT-F.*` **אינה מוגדרת כלל** ב-`docs/ACCEPTANCE_TESTS.md` (`grep -c 'AT-F\.'` → `0`). שער Phase 4 מותנה אפוא במשפחת בדיקות שאינה קיימת. **אין ליצור כעת בדיקות AT-F · אין לשנות `ACCEPTANCE_TESTS.md` · אין להכריע מה אמורה המשפחה לכלול.** מתועד בלבד; הכרעה בסמכות Roy |

---

## FINAL DEFINITION OF DONE

הפרויקט **אינו** Finished רק משום ש:
בדיקות עוברות · הקוד רץ · הבקטסט רווחי · ה-Demo עבד · Claude Code דיווח הצלחה · Phase 0–3 ירוקים · הדאטה קיים · ה-Hold-Out קיים · RRR נראה חיובי.

**PROJECT COMPLETE** מתקיים רק כאשר **כל** התנאים הבאים מתקיימים **ומגובים בראיה**:

1. ארכיטקטורה שלמה
2. דאטה אמיתי נדרש קיים ומאומת
3. כל ה-Acceptance Tests הרלוונטיים עוברים
4. אפס פריטים חוסמים בחומרה `critical`/`high`
5. Hold-Out מופרד פיזית ומוגן
6. בקטסט דטרמיניסטי וניתן-לשחזור
7. עלויות / Spread / Slippage מכוילים
8. MAE/MFE ואנליטיקת עסקאות נדרשת
9. Validation
10. Scoring
11. Tracker
12. שכבת AI לפי המפרט
13. ויזואליזציה נדרשת
14. כל ה-Known Issues מקבלים disposition
15. `DECISIONS_LOG` מעודכן
16. ה-Checklist הזה מלא
17. **RRR = GO**
18. תהליך Freeze / Reproducibility / Archive סופי הושלם

**ההכרזה הסופית היא בסמכות Roy בלבד.**
