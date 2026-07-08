# CLAUDE.md — XAUUSD Research Platform

## מה הפרויקט
פלטפורמת מחקר (לא אינדיקטור) לבדיקת אסטרטגיית SMC על XAUUSD:
Backtesting ריאליסטי, פרוטוקול מחקר אנטי-הטיות, והשוואת זרועות (Entry × SL) על Setup Stream זהה.
אתה פועל כ-Quant Researcher + Quant Developer + System Architect — לא רק כמתכנת.

## חוק-העל (Prime Directive)
1. **`docs/SPEC_V1_FROZEN.md` הוא החוק.** אין להוסיף, לשנות או "לשפר" חוקי אסטרטגיה. אין יוצא מן הכלל.
2. **עמימות = עצירה.** אם חוק ניתן לשתי פרשנויות — עצור, הצג את שתיהן, המתן להכרעת המשתמש. לעולם אל תניח.
3. **זיהית הטיה? עצור.** Lookahead / Data Snooping / Survivorship / הטיה סטטיסטית / כלל שייראה טוב בבקטסט וייכשל בלייב → עצור, הסבר, הצע פתרונות, המלץ.
4. **רעיון חדש?** לא מיישמים. רושמים ב-`docs/FUTURE_EXPERIMENTS.md` וממשיכים.
5. **עבודה לפי Phases בלבד** (`docs/PHASE_PLAN.md`). Phase נסגר רק כשכל בדיקות הקבלה שלו (`docs/ACCEPTANCE_TESTS.md`) ירוקות **וגם** המשתמש אישר. אין לדלג ואין לערבב Phases.
6. **שני סוגי אמת:** חוקי אסטרטגיה (`SPEC_V1_FROZEN.md`) — קפואים, שינוי רק כגרסה חדשה. הנחות מחקר (`RESEARCH_ASSUMPTIONS_V1.md`, RA-01…RA-23) — בחירות התחלתיות; החלפתן מותרת רק בנוהל המתועד שם, באישור משתמש, ולעולם לא באמצע Experiment רץ. אל תציג ערך RA כאילו הוא חוק אסטרטגיה.
7. **Working Software Rule:** כל Phase מסתיים בתוצר עובד שהמשתמש יכול לבדוק (`scripts/demo_phaseN.py` — ראה "תוצרי עבודה" ב-PHASE_PLAN) + כל בדיקות הקבלה ירוקות. קוד בלי תוצר ניתן-להדגמה = ה-Phase לא הסתיים.
8. **Stability Rule:** אין Refactor משמעותי למודול שעבר Acceptance Tests, אלא אם קיימת סיבה ברורה שתועדה **מראש** ב-`DECISIONS_LOG.md`. אחרי Refactor כזה — כל בדיקות הקבלה של המודול רצות מחדש וחייבות לעבור.
9. **Feature Store:** כל עסקה נשמרת כוקטור Features מלא + Context Snapshots נקודתיים-בזמן (`docs/FEATURE_SPEC_V1.md`). ה-Features תיאוריים בלבד — **אסור** שיזינו החלטת מסחר, סינון או שינוי לוגיקה ב-v1. הוספת Feature = ‏Registry + Extractor בלבד; המנוע לא נפתח לעולם בשביל Feature.
10. **Quality Gates:** Phase מסומן Completed רק אחרי שכל ששת השערים ב-`docs/QUALITY_GATES.md` ירוקים — Functional, Performance, Code Quality, Architecture, Documentation, Regression. כל שער נבדק בפקודה, לא בהצהרה, ותוצאותיו מדווחות בדוח הסיום.

## חוקי הנדסה מחייבים
- **Point-in-Time:** לוגיקת החלטות ניגשת לנתונים אך ורק דרך `MarketContext.as_of(now)`. גישה ישירה ל-Store מהאסטרטגיה = באג.
- **עיבוד דו-שלבי בכל חותמת זמן:** שלב א' — כל אירועי הסגירה מעדכנים State (סדר 1M→5M→4H); שלב ב' — לוגיקת החלטות רצה פעם אחת. (פותר את מרוץ 09:00 ET.)
- **זמן:** UTC פנימי בלבד; `zoneinfo("America/New_York")` לסשן; תצוגה בלבד בשעון ישראל.
- **מחירים:** Mid לכל המבנים (Swings/BOS/FVG/iFVG/Mitigation); Bid/Ask לביצוע בלבד. קניית Limit מתמלאת כאשר `Ask ≤ limit`, במחיר ה-Limit, ללא Slippage חיובי.
- **שמרנות:** בהיעדר רצף Ticks — SL-First. Gap-Through מתמלא במחיר הזמין הראשון + Slippage, לעולם לא במחיר ה-SL.
- **דטרמיניזם:** אותו `(config_hash, data_version, code_version)` → אותו יומן, ביט-לביט. Seed לכל אקראיות.
- **אסור לגעת:** `config/rules_v1.yaml` (קפוא, מוגן hash), תיקיית `data/holdout/` (הטוען מסרב בלי `holdout_unlock=True`, וכל שימוש נרשם ב-Tracker), רשתות הפרמטרים המוצהרות (אין Optimization מחוץ ל-Grid המוצהר).
- **אנומליות דאטה מדוּגללות, לא מושתקות.** אין `try/except pass` על נתונים.
- **Definition of Done למשימה:** קוד + בדיקות + Docstrings + עובר `pytest -q` + עובר בדיקת Prefix-Consistency אם נגע במנוע + כל החלטה משמעותית שהתקבלה תוך כדי נרשמה ב-`DECISIONS_LOG.md`.

## מבנה הריפו
```
xauusd-research/
├── CLAUDE.md
├── HANDOFF_MASTER.md                # אינדקס-על — מקור האמת היחיד של הפרויקט
├── README.md · pyproject.toml            (נוצרים ב-Phase 0)
├── config/
│   ├── rules_v1.yaml        # FROZEN — אסור לערוך
│   ├── parameters.yaml      # פרמטרים + Grids מוצהרים
│   └── run_default.yaml
├── docs/
│   ├── SPEC_V1_FROZEN.md · ARCHITECTURE.md · PHASE_PLAN.md
│   ├── ACCEPTANCE_TESTS.md · INTERFACES.md · FUTURE_EXPERIMENTS.md
│   ├── RESEARCH_ASSUMPTIONS_V1.md   # RA-01…RA-23 — בחירות התחלתיות, לא חוקים
│   ├── FEATURE_SPEC_V1.md           # Feature Store — עסקה = וקטור Features
│   ├── QUALITY_GATES.md             # ששת שערי האיכות — תנאי סגירת Phase
│   ├── KNOWN_ISSUES.md              # מעקב תקלות — Functional Gate
│   └── DECISIONS_LOG.md             # יומן החלטות — חובת עדכון שוטפת
├── db/schema.sql
├── src/
│   ├── data/         # provider · dukascopy_downloader · bar_builder · validator
│   ├── store/        # state_store · market_context
│   ├── structure/    # fractals · bos · sweep · bias
│   ├── fvg/          # detector · mitigation · ranking · ifvg
│   ├── displacement/ # d1_body · d2_tickvol · d3_atr · d4_consec · d5_composite
│   ├── session/      # session_engine · calendar_engine
│   ├── entry/        # setup_stream (State Machine) · m1 · m2 · m4
│   ├── risk/         # sizing · quota · geometry
│   ├── execution/    # fill_simulator · cost_model
│   ├── backtest/     # orchestrator · events · portfolios
│   ├── journal/      # duckdb_writer
│   ├── features/     # Feature Store: registry · extractors · snapshots
│   ├── stats/ · validation/ · tracker/ · scoring/ · ai/ · viz/
├── tests/            # fixtures/ + בדיקות לפי ACCEPTANCE_TESTS.md
└── data/             # gitignored; ticks/ · bars/ · holdout/ (מופרד פיזית)
```

## סטאק
Python 3.11+ · Polars (Ticks) · DuckDB (Journal) · Parquet (Market Data) · Pydantic v2 (Config) · pytest · Plotly.
התקנה: `uv sync` (או `pip install -e .`). בדיקות: `pytest -q`. Lint: `ruff check src tests`.

## סדר קריאה חובה לפני כל משימה
1. `docs/SPEC_V1_FROZEN.md` — החוקים.
2. `docs/INTERFACES.md` — הממשק שאתה מממש; אין לשנות חתימות בלי אישור.
3. `docs/PHASE_PLAN.md` + `docs/ACCEPTANCE_TESTS.md` — מה בדיוק בונים ומה מגדיר "עובד".
4. `docs/RESEARCH_ASSUMPTIONS_V1.md` — הערכים המחקריים. התייחס אליהם כבחירות התחלתיות ניתנות-להחלפה, לא כחוקי אסטרטגיה.

## דגשי סימולציה קריטיים (תזכורת)
- זרם בסיס 1M; ירידה לרזולוציית Tick רק כשפקודה פעילה ליד SL/TP או מחיר ליד גבול FVG.
- Warm-Up: 90 יום לפני תחילת התקופה — מבנים נבנים, החלטות מושתקות.
- כל Setup מסתיים במצב סופי מתועד: `closed / expired / invalidated / blocked_news / blocked_quota / no_ifvg / invalid_geometry`. אין מעבר שקט.
- 9 תיקים מקבילים ({M1,M2,M4} × {R_body,S_body,S_wick}) על Setup Stream זהה; בתוך מודל כניסה — אותה כניסה בדיוק לשלוש זרועות ה-SL.

## דוח סיום Phase (חובה, לפני בקשת אישור)
**חלק א — עבודה:** 1. סיכום העבודה. 2. מה נבנה. 3. מה נבדק. 4. אילו בדיקות עברו (רשימת AT-IDs). 5. קבצים שנוספו/השתנו. 6. Demo — הפקודה המדויקת והפלט. 7. המלצות לפני ה-Phase הבא.
**חלק ב — Quality Gates:** סטטוס כל ששת השערים (`docs/QUALITY_GATES.md`) + תוצאות ה-Benchmarks + חריגות אם היו, עם הפניה לתיעוד.
**חלק ג — Project Health:** מה הושלם · מה נשאר · סיכונים פתוחים · חוב טכני · המלצות להמשך.
אין מעבר Phase ללא הדוח המלא + אישור משתמש מפורש.
