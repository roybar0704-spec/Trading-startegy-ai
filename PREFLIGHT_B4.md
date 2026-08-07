# PREFLIGHT_B4.md — RA-10: Real Spread Report

**Blocker:** B-4 — RA-10 Calibration Input (Real Spread Report על 39 חודשי-דאטה).
**מבוצע לפי:** `WORK_ORDER_PROTOCOL.md` §1. **מסמך תכנון בלבד — לא בוצע שום שינוי קוד.**

---

## א. הנחות מאומתות (הנחה → ראיה)

1. **`build_spread_report(ticks: pl.DataFrame, symbol: str) -> SpreadReport` קיים ומוכן, ללא צורך בשינוי.**
   ראיה: `src/data/spread_report.py:77-107`.

2. **חוזה-קלט מדויק:** הפונקציה דורשת DataFrame עם עמודות `ts`/`bid`/`ask` בלבד (`ts` — timezone-aware, מומר ל-ET דרך `.dt.convert_time_zone`).
   ראיה: `src/data/spread_report.py:79-84`.

3. **`TickParquetStore.read_month(symbol, year, month) -> pl.DataFrame` קיים לטעינת כל חודש בנפרד**, ו-`months_between(start, end)` קיים לאיטרציה על טווח.
   ראיה: `src/data/tick_store.py:78-82`, `src/data/tick_store.py:91-101`.

4. **39/39 חודשי-Parquet קיימים בפועל על מחשב הבית** — `checkpoint.json` אישר תכנותית `Missing=∅, Extra=∅, Duplicates=0` בסיום Batch 7.
   ראיה: `BATCH7_CLOSURE_REPORT.md` §2.

5. **⚠️ קריטי לביצוע:** בדיוק כמו ה-Backfill — **`data/ticks/` הוא gitignored ואינו קיים ב-Sandbox הזה.** כל הרצה בפועל של הסקריפט חייבת לקרות **על מחשב הבית**, לא כאן. אני יכול להכין את הסקריפט ולבדוק את הלוגיקה, אך לא להריץ אותו על הדאטה האמיתי.
   ראיה: מבנה-הריפו ב-`CLAUDE.md` ("`data/` gitignored"), מאומת בפועל דרך היעדר `data/ticks/` ב-Sandbox לאורך כל שיחת ה-Backfill.

6. **הערך הנוכחי:** `costs.slippage_stop_usd = 0.10` (default), מוגדר ב-`config/parameters.yaml:7`, סכימה ב-`src/config/models.py:211-214` (`CostsParams.slippage_stop_usd: CostDefault`).

7. **`config/parameters.yaml` אינו קפוא** (בניגוד ל-`config/rules_v1.yaml`) — עדכון ערך-Default שם הוא בתחום-הפעולה החוקי של הכרעת-RA, לא דורש שינוי-חוק-אסטרטגיה.
   ראיה: `CLAUDE.md` §"אסור לגעת" — רק `config/rules_v1.yaml` מוזכר כקפוא; `config/parameters.yaml` מתואר במפורש כ"פרמטרים + Grids מוצהרים" (בר-שינוי לפי נוהל-RA).

8. **הרשומה המתועדת של RA-10 כבר מצפה לצעד הזה בדיוק:** "יכויל מחדש מול דו"ח הספרד של Phase 0".
   ראיה: `docs/RESEARCH_ASSUMPTIONS_V1.md:28`.

9. **נוהל-עדכון RA מוגדר במפורש ב-5 צעדים** (הצעה מנומקת → אישור משתמש → רישום → סגירת/פתיחת Experiment → RA-21 חריג לא-רלוונטי כאן).
   ראיה: `docs/RESEARCH_ASSUMPTIONS_V1.md:59-64`.

10. **`SpreadReport.to_markdown()` קיים** — מפיק טבלה קריאה-לאדם ישירות מהאובייקט, שימושי כפלט-Evidence.
    ראיה: `src/data/spread_report.py:62-74`.

## ב. הנחות שלא ניתן לאמת (סיבה, השפעה, טיפול)

1. **האם קיים "Experiment רץ" כרגע שהיה חוסם עדכון-RA** (נוהל-RA צעד 4: "אין שינוי RA באמצע Experiment רץ").
   **סיבה שלא ניתן לאמת:** אין מנגנון-Tracker פעיל בקוד לבדוק מולו (ר' §ג.1 למטה) — לא ניתן לשאול "יש Experiment רץ?" בפועל.
   **השפעה:** נמוכה בפועל — אין Phase 4/5, אין ריצת-Backtest שהופקה אי-פעם עם R-multiples מתועדים (T3.4 מעולם לא בוצע).
   **טיפול:** מניח היעדר-Experiment רץ בהיעדר-ראיה-לסתור, אך מציין זאת כאן במפורש לאישורך — לא כברירת-מחדל שקטה.

2. **ביצועי `build_spread_report` על נפח-הדאטה המלא** (39 חודשים, ~170-190M Ticks מצטבר, לפי סכימת ה-row_count-ים מכל 7 ה-Closure Reports).
   **סיבה שלא ניתן לאמת:** אין Benchmark קיים בקוד לפונקציה הזו על נפח כזה; `TickParquetStore.read_month` טוען חודש-בחודש (לא Batch), וריכוז-כל-הטיקים ל-DataFrame אחד (`pl.concat`) לפני ה-`group_by` עלול לדרוש זיכרון משמעותי.
   **השפעה:** סיכון-ביצועים/זיכרון בזמן-ריצה, לא סיכון-נתונים.
   **טיפול:** הסקריפט החדש יבנה עם Accumulation הדרגתי (per-month spread-extraction, לא concat-כל-הטיקים-ואז-group_by) — פרט-עיצוב שיוצג ב-Work Order, לא כאן.

## ג. סטיות תיעוד↔קוד שהתגלו

1. **נוהל-עדכון RA (צעד 3) מפנה ל-"Experiment Tracker"** ("רישום ב-Experiment Tracker: RA-xx: old → new") — **אך `src/tracker` לא קיים בריפו כלל** (מאומת: `Glob src/tracker` לא מחזיר תוצאה; `PROJECT_STATE_REPORT.md` §1.5 מאשר זאת עצמאית).
   **חומרה:** נמוכה, לא-חוסמת — זו סטייה **קיימת-וידועה מראש**, לא תגלית חדשה. כל הפרויקט כבר עובד סביבה: כל הכרעת-RA/D-entry עד כה נרשמה ישירות ב-`docs/DECISIONS_LOG.md` (למשל D-070, D-071) ולא ב-Tracker שלא קיים.
   **טיפול מוצע:** לרשום את עדכון-RA-10 (אם ייקבע) ב-`docs/DECISIONS_LOG.md`, באותו דפוס בדיוק כמו כל שאר ה-D-entries — לא לחכות לבניית `src/tracker` (Phase 5, לא בסקופ B-4).

2. **Docstring של `spread_report.py` (שורה 5) קובע שהמודול הוא "calibration input for RA-10 (slippage) **and min_stop**"** — כלומר לפי הקוד עצמו, דו"ח-הספרד רלוונטי גם ל-`min_stop_k_spread` (`config/parameters.yaml`), לא רק ל-RA-10.
   **חומרה:** לא-חוסמת, אך **שאלת-Scope של ממש** — לא סטייה טכנית.

## ד. הכרעה

**PROCEED — שתי שאלות-Scope נפתרו במלואן, שתיהן באישורך המפורש:**

1. **Scope צר (RA-10/Slippage בלבד, לא `min_stop_k_spread`)** — אושר.

2. **טווח-נתונים (ממצא נוסף שהתגלה אחרי כתיבת ה-Pre-Flight המקורי, לא כאן מלכתחילה):** `config/run_default.yaml` מגדיר `holdout: {last_months: 6}` על תקופת `2023-01-01`…`2025-12-31` — כלומר יולי-דצמבר 2025 הם חלון-Holdout מושגי, שחופף לחלק מ-39 חודשי ה-Backfill. **הוכרע (D-073):** B-4 ירוץ אך ורק על `2022-10-01`…`2025-06-30` (33 חודשים) — Holdout נשאר בלתי-נגוע, ללא חריג עקרוני ל"נתוני-מבנה-שוק". ר' `docs/DECISIONS_LOG.md` D-073.

**שאר ה-Pre-Flight נקי — אין סתירה מהותית שנותרה.** ממשיך ל-`WORK_ORDER_B4.md`.
