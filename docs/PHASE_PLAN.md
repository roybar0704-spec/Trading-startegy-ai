# PHASE PLAN
כלל: Phase נסגר רק כשמתקיימים ארבעתם — (א) כל בדיקות הקבלה ירוקות, (ב) **תוצר עובד הודגם למשתמש** (Working Software Rule, טבלת "תוצרי עבודה" בתחתית), (ג) **כל ששת ה-Quality Gates ירוקים** (QUALITY_GATES.md), (ד) אישור משתמש. אין התחלת Phase הבא לפני כן.

## Phase 0 — Data Pipeline
- T0.1 שלד ריפו: pyproject, מבנה תיקיות, ruff+pytest, CI מקומי.
- T0.2 DukascopyDownloader: bi5+LZMA, Retry, Cache immutable, hash לקבצי מקור.
- T0.3 Tick→Parquet חודשי + `data_version`.
- T0.4 Validator: חורים, סופ"ש, DST, spike-flagging (דגלול, לא מחיקה).
- T0.5 BarBuilder 1M/5M/4H (עוגן NY-Close) — נבנה מ-Ticks בלבד.
- T0.6 דו"ח ספרד לפי שעה + הפרדה פיזית של `data/holdout/` (6 חודשים אחרונים).

**Gate (מפוצל — D-036):**
- **תת-שער קוד (סגור):** AT-0.1–AT-0.7 ירוקות מול Fixtures סינתטיים שמדמים במדויק את פורמט ה-wire של Dukascopy; כל שאר Quality Gates ירוקים.
- **תת-שער דאטה (פתוח, KI-001/KI-002):** 3 שנות דאטה אמיתי נקיות + דו"ח ספרד אמיתי מוצג למשתמש + כיול RA-10 — טרם קיימים (סביבת הפיתוח חוסמת רשת ל-Dukascopy). **אינו חוסם Phase 1–2** (הבדיקות שלהם מתוכננות על Fixtures סינתטיים לפי ACCEPTANCE_TESTS.md ואינן תלויות בדאטה אמיתי). **חוסם באופן מוחלט את T3.4 ואת Phase 4–5** — ר' "Research Readiness Review" לפני Phase 3 למטה.

## Phase 1 — State Store + Structure Engines
**עקרון מחייב לכל מודול בפאזה זו (D-037, ר' ARCHITECTURE.md): עצמאות ממקור נתונים.** כל מודול חייב לפעול ללא שינוי קוד בין Fixture סינתטי לבין דאטה אמיתי מ-Dukascopy — ההבדל היחיד מותר להיות מקור הקלט (איזה `DataProvider`/`Bar`/`Tick` מוזרק), לעולם לא ענפי קוד שונים.
- T1.1 State Store + MarketContext (as-of, read-only).
- T1.2 Fractals (confirmed_at = סגירת נר 3), BOS (close-through), Sweep.
- T1.3 Bias State Machine + bias_history.
- T1.4 FVG Engine: זיהוי, Mitigation חי (Mid, 1M/Tick), דירוג L1–L3, עדיפות.
- T1.5 Displacement D1 (BodyRatio) בלבד; ממשק D2–D5 מוכן, לא ממומש.
- T1.6 בדיקות Fixtures סינתטיות + Prefix-Consistency ב-CI.
**Gate:** AT-1.*; Prefix-Consistency ירוק על Fixture דו-שבועי; אין בקוד שום ענף/תנאי שמבחין בין מקור נתונים סינתטי לאמיתי.

## Phase 2 — Execution Layer
- T2.1 Cost Model: ספרד מהדאטה, Slippage-Stop (×3 בחדשות), Delay, Commission.
- T2.2 Fill Simulator: Limit (Ask≤P), Market, SL/TP על Ticks, SL-First fallback, Gap-Through.
- T2.3 Risk Engine: Sizing ממומש 0.5%, min_stop, גאומטריה, מכסה פר-תיק.
- T2.4 Portfolio isolation (הון/מכסה/Equity לכל זרוע).
**Gate:** AT-2.*; תרחישי מילוי ידניים תואמים חישוב יד.

## Phase 3 — End-to-End צר (M2 × S_body בלבד)
- T3.1 Session+Calendar Engines: חלון, Blackout, ביטולים, effective_window, day_roll.
- T3.2 Setup Stream: ה-State Machine המלא (R/S/iFVG, כל הפסילות, כל התוצאות הסופיות).
- T3.3 Orchestrator דו-שלבי + Journal writer.

**⛔ שער חובה לפני T3.4 — Research Readiness Review (D-037):** ריצת בקטסט אמיתית ראשונה (T3.4) אסורה עד שהושלמה סקירת מוכנות-מחקר מסודרת ומתועדת לפי `docs/RESEARCH_READINESS_REVIEW.md`. אם סעיף כלשהו בסקירה נכשל — עוצרים את הפרויקט לפני T3.4 ומפיקים דוח מפורט במקום להמשיך. אין לדלג על השער הזה גם אם הבדיקות הטכניות (pytest/ruff) ירוקות.

- T3.4 ריצה מלאה על 3 חודשי In-Sample עם זרוע אחת: M2 × S_body. **דורש Research Readiness Review = GO.**
- T3.5 Viz בסיסי: דף עסקה עם כל הסימונים.
- T3.6 Context Snapshots: לכידה נקודתית-בזמן ב-engagement/armed/entry/exit לכל Setup — התשתית של ה-Feature Store (FEATURE_SPEC_V1).
**Gate:** AT-3.*; **20 עסקאות מדגם מאומתות ידנית על הגרף מול היומן** + אישור משתמש שהלוגיקה = הכוונה.

## Phase 4 — כל הזרועות + סטטיסטיקה
- T4.1 M1, M4; זרועות SL R_body/S_wick; 9 תיקים על Stream זהה (כניסה זהה בתוך מודל).
- T4.2 Statistics Engine: כל המדדים, פילוחים (שעה/Setup/זרוע/רבעון/תגים), MAE/MFE.
- T4.3 Scoring Log-Only.
- T4.4 Feature Extractors: כל ה-Features המאושרים ב-FEATURE_SPEC מחושבים מה-Snapshots → Registry + trade_features.
- T4.5 Analytics API: ‏`stats.by(feature, metric)` — סינון/קיבוץ/השוואה גנרי לכל Feature. חובה ב-Demo: ‏WR לפי Bias, TS מול בלי-TS, Expectancy לפי שעה ויום, Profit לפי Entry/Stop Model.
**Gate:** AT-4.* + AT-F.*; דו"ח השוואה זוגי 9 זרועות על In-Sample.

## Phase 5 — Validation & Research Protocol
- T5.1 Walk-Forward Splitter (9M/3M).
- T5.2 Hold-Out Guard (Loader מסרב; שימוש נרשם).
- T5.3 Random Baseline זוגי (N=1000, דגימת מרחקי SL מהזרוע) + Bootstrap p-value.
- T5.4 Sensitivity ±20% + Stability רבעוני.
- T5.5 Experiment Tracker: config_hash, Append-Only, פונקציית מטרה נעולה.
**Gate:** AT-5.*; דו"ח Baseline מלא; Reproducibility ירוק.

## Phase 6 — AI Analyst + Viz מלא
- T6.1 AI Analyst: ניתוח טרום-סשן מובנה מ-Snapshot; תיוג עסקאות; Insights. Read-Only.
- T6.2 Dashboard: Equity, פילוחים, השוואת זרועות.
**Gate:** AT-6.*.

## אחרי Phase 5 בלבד: ריצות המחקר האמיתיות לפי הפרוטוקול → הכרעת זרועות → נעילת v1.2.

## תוצרי עבודה — Working Software Rule
| Phase | Demo | מה המשתמש רואה |
|---|---|---|
| 0 | `scripts/demo_phase0.py --month 2024-03` | טעינת חודש דאטה, דו"ח ולידציה, דו"ח ספרד לפי שעה, נרות 4H מיושרי NY-Close |
| 1 | `scripts/demo_phase1.py --period ...` | גרף אינטראקטיבי: Swings, BOS, Sweeps, ציר Bias, FVG L1–L3 מסומנים על תקופת מדגם |
| 2 | `scripts/demo_phase2.py` | דו"ח תרחישי מילוי: Limit / Market / SL-First / Gap-Through / Sizing — מול חישוב יד |
| 3 | `scripts/demo_phase3.py` | עסקאות M2×S_body על הגרף: R, S, iFVG, Entry, SL, TP + היומן המלא |
| 4 | `scripts/demo_phase4.py` | דשבורד השוואת 9 הזרועות על In-Sample |
| 5 | `scripts/demo_phase5.py` | דו"ח Walk-Forward + Baseline + p-value + הוכחת Reproducibility |
| 6 | `scripts/demo_phase6.py` | ניתוח AI טרום-סשן לדוגמה + דשבורד מלא |

הערה: הדוגמאות "לראות זיהוי FVG" ו"לראות Market Structure" חיות שתיהן ב-Demo של Phase 1 — שני המנועים נבנים באותו שלב ומודגמים יחד על אותו גרף.
