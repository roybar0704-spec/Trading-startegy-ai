# PREFLIGHT_B5.md — AT-0.* מול דאטה אמיתי + Quality Gates מחדש

**Blocker:** B-5 — RRR סעיף 4 (נתוני Dukascopy אומתו מול דאטה אמיתי) + RRR סעיף 5 (Quality Gates ירוקים מחדש).
**מבוצע לפי:** `WORK_ORDER_PROTOCOL.md` §1. **מסמך תכנון בלבד — לא בוצע שום שינוי קוד, לא בוצע Commit.**

---

## א. הנחות מאומתות (הנחה → ראיה)

1. **RRR סעיף 4 דורש (חובה):** AT-0.1/AT-0.2/AT-0.6/AT-0.7 מול דאטה אמיתי בפועל, ו**ממליץ** (לא מחייב במפורש) גם AT-0.3–0.5, ובנוסף "3 שנות דאטה + 90 יום Warm-Up נקיים לפי הגדרת T0.4".
   ראיה: `docs/RESEARCH_READINESS_REVIEW.md:19`.

2. **RRR סעיף 5 דורש:** ששת שערי-האיכות ירוקים על מצב-הריפו הנוכחי, כולל Regression Phase 0-2, מאומת בפועל דרך `scripts/ci.sh`.
   ראיה: `docs/RESEARCH_READINESS_REVIEW.md:20`; `docs/QUALITY_GATES.md`; `scripts/ci.sh` קיים בפועל בריפו.

3. **T0.6 (PHASE_PLAN.md) קבע מלכתחילה, כחלק מ-Phase 0 המתוכנן, שני מסירות:** "דו"ח ספרד לפי שעה" (נסגר ב-B-4/D-074) **+ "הפרדה פיזית של `data/holdout/` (6 חודשים אחרונים)"** — כלומר ההפרדה הפיזית של יולי-דצמבר 2025 היא עבודה **מתוכננת מראש**, לא הרחבת-Scope שממציא B-5.
   ראיה: `docs/PHASE_PLAN.md:10`.

4. **"תת-שער קוד" של T0.4 כבר סגור:** AT-0.1–AT-0.7 ירוקות מול Fixtures סינתטיים — זהו הגדר קיים ולא-נוגע. B-5 עוסק אך ורק ב"תת-שער דאטה" (הרצה נוספת מול דאטה אמיתי, לא שינוי לבדיקות-ה-Fixtures הקיימות).
   ראיה: `docs/PHASE_PLAN.md:12-14` (D-036 — הגדר מפוצל קוד/דאטה).

5. **אימות ישיר (grep) של כל 7 בדיקות ה-AT-0.\* הקיימות — כולן משתמשות אך ורק בדאטה סינתטי/מפוברק, ללא נגיעה ב-`data/ticks/` האמיתי:**

   | AT | קובץ | מקור-דאטה נוכחי | סטטוס |
   |---|---|---|---|
   | AT-0.1 Download integrity | `tests/test_at0_1_download_integrity.py` | `FakeTransport` + `synthetic_hour_ticks` (`tests/fixtures/dukascopy_wire.py`) | Fixture בלבד |
   | AT-0.2 Cache immutability | `tests/test_at0_2_cache_immutability.py` | `FakeTransport` + `synthetic_hour_ticks` | Fixture בלבד |
   | AT-0.3 Gap detection | `tests/test_at0_3_gap_detection.py` | רשימת timestamps מפוברקת ידנית (`_ticks_df`) | Fixture בלבד |
   | AT-0.4 DST build | `tests/test_at0_4_dst_build.py` | ticks רציפים מפוברקים כל 30 שנ' (`_continuous_ticks`) | Fixture בלבד |
   | AT-0.5 4H anchor | `tests/test_at0_5_h4_anchor.py` | אין Ticks בכלל — חשבון-גבולות UTC/ET טהור | ללא-תלות-בדאטה (ר' §ד.3) |
   | AT-0.6 Bar↔Tick consistency | `tests/test_at0_6_bar_tick_consistency.py` | `random.Random(42)` — שעה אחת מפוברקת | Fixture בלבד |
   | AT-0.7 Holdout isolation | `tests/test_at0_7_holdout_isolation.py` | `TickParquetStore(tmp_path)` + `_month_ticks` (שורה בודדת לחודש, מפוברקת) | Fixture בלבד |

   ראיה: קריאה ישירה של כל 7 קבצי-הבדיקה (`grep -n` + `sed -n` על כל אחד), 2026-08-07.

6. **ממצא מפתח — קיים כבר בריפו (Sandbox הנוכחי) חודש-דאטה אמיתי, מאומת ותקף, שהושאר מ-B-3 (D-072):** `data/ticks/XAUUSD/2022/11.parquet`.
   ראיה: נבדק ישירות עכשיו —
   ```
   rows: 3,641,776
   columns: ['ts', 'bid', 'ask']
   bid range: 1616.477 .. 1786.367
   ask range: 1616.912 .. 1786.783
   ts range: 2022-11-01 00:00:00.059 UTC .. 2022-11-30 23:59:59.136 UTC
   sha256: df78f49b2aebfb76fd592c891c512594e8708ebccb0807e34f1ce1112d594092 (תואם לקובץ ה-`.sha256`-סייד-קאר)
   ```
   הערכים תואמים **בדיוק** לערכים שתועדו ב-D-070 (row_count, טווח-מחירים) — זהו אותו קובץ אמיתי, לא עותק-חדש. **המשמעות:** בניגוד ל-B-1..B-4 (שדרשו הרצה על מחשב-הבית **כי** לא היה שום דאטה-אמיתי ב-Sandbox), חלק מ-B-5 יכול לרוץ **כאן**, לא רק על מחשב-הבית — ר' פירוט ב-§ד.

7. **`data/raw/` (מטמון-Bytes-גולמי ברמת-שעה של `DukascopyDownloader`, `_cache_path`) אינו קיים ב-Sandbox הזה** — רק ה-Parquet המפוענח-הסופי (מס' 6 לעיל) קיים. `AT-0.2` (Cache Immutability) בודקת ספציפית את שכבת-המטמון הזו (הורדה חוזרת → אין קריאת-רשת נוספת, קובץ לא משתנה) — לא ניתן לבדוק אותה בפועל בלי גישה לתיקיית `data/raw/` האמיתית.
   ראיה: `ls data/` (Sandbox) — אין `raw/`; `src/data/dukascopy_downloader.py:108-166` (`cache_dir`, `_cache_path`, `_get_hour_raw`).

8. **`data/ticks/` ו-`data/raw/` שניהם gitignored** — לא ניתן להעביר דאטה-אמיתי מלא ל-Sandbox דרך git; מחשב-הבית נשאר מקור-האמת היחיד לדאטה המלא (39/39 חודשים + מטמון-raw מלא).
   ראיה: `.gitignore:1` (`/data/*`).

9. **`scripts/ci.sh` קיים ומוכן להרצה** — RRR סעיף 5 (Quality Gates) אינו תלוי בדאטה-אמיתי כלל (pytest/ruff/lint-imports/pylint-dup/benchmarks פועלים כולם מול הריפו והבדיקות הקיימות, לא מול `data/ticks/`) — **ניתן להריץ במלואו כאן ב-Sandbox**, ללא תלות במחשב-הבית.
   ראיה: `scripts/ci.sh` קיים; `docs/QUALITY_GATES.md` — אף שער לא מזכיר `data/ticks/` כתלות.

10. **D-071 כבר ביצע ניתוח-ראיות מקיף על גילוי-Gap/Spike מול הדאטה האמיתי (נובמבר 2022)** — 17/18 gaps תואמים rollover מתועד, ה-gap ה-18 תואם Thanksgiving, spikes מוסברים ברובם כאירועי-שוק מתועדים. זו כבר עדות אמיתית מול AT-0.3 (Gap detection), גם אם לא נכתבה כ"בדיקת AT-0.3 רשמית".
    ראיה: `docs/DECISIONS_LOG.md` D-071.

## ב. הנחות שלא ניתן לאמת (סיבה, השפעה, טיפול)

1. **האם `data/raw/` (מטמון-Bytes-רמת-שעה) עדיין קיים בשלמותו על מחשב-הבית**, או שנוקה/נמחק אי-שם לאורך 7 ה-Batches.
   **סיבה שלא ניתן לאמת:** אין גישה למחשב-הבית מכאן; אף Closure Report קודם לא דיווח במפורש על מצב `data/raw/`.
   **השפעה:** אם המטמון לא קיים/נוקה — AT-0.2 (Cache Immutability) לא ניתנת לבדיקה במתכונתה המקורית (הורדה-חוזרת-לא-משנה-קובץ) בלי הורדה חדשה אמיתית (חוזרת ל-KI-001-territory, אך KI-001 סגור/D-069, כך שזה ישים טכנית).
   **טיפול:** ייבדק כצעד ראשון בפועל (Roy, `ls`/`du` על `data/raw/`) לפני כתיבת סקריפט ה-AT-0.2 הסופי ב-Work Order.

2. **ביצועי `ci.sh` המלא (זמן-ריצה) על הריפו הנוכחי** — לא נמדד לאחרונה; ייתכן שגדל מאז המדידה האחרונה (Phase 3).
   **סיבה שלא ניתן לאמת:** אין Benchmark עדכני רשום.
   **השפעה:** נמוכה — Performance Gate (§2 ב-QUALITY_GATES.md) בודק תקציב-ריצה ל-Phases ספציפיים, לא ל-`ci.sh` עצמו כמכלול; סיכון-זמן בלבד, לא סיכון-נתונים.
   **טיפול:** להריץ ולמדוד בפועל, לדווח את הזמן, לא להניח.

## ג. סטיות תיעוד↔קוד שהתגלו

**אין סטיות חדשות שהתגלו מעבר לאלה שכבר תועדו (KI-022, KI-023) — שתיהן כבר known ואינן דורשות טיפול חדש כאן.**

## ד. הכרעה

**PROCEED — שלוש שאלות-הScope הוכרעו במלואן ע"י Roy (2026-08-07). ה-Scope הסופי של B-5:**

### הכרעה 1 — חלוקת-ביצוע Sandbox/מחשב-הבית

| AT | היכן רץ | סטטוס |
|---|---|---|
| AT-0.1 Download integrity | Sandbox | **GO** — מול `data/ticks/XAUUSD/2022/11.parquet` האמיתי |
| AT-0.2 Cache immutability | מחשב-הבית | **GO** — תלוי `data/raw/`; כל הרצה שדורשת סביבת-דאטה מלאה → מחשב-הבית |
| AT-0.3 Gap detection | — | **Covered by D-071 — לא Gate** (ר' הכרעה 3) |
| AT-0.4 DST build | Sandbox | **GO** — אותו קובץ אמיתי כולל את מעבר ה-Fall-Back (6.11.2022) |
| AT-0.5 4H anchor | — | **N/A — לא Gate** (ר' הכרעה 3) |
| AT-0.6 Bar↔Tick consistency | Sandbox | **GO אם ניתן עם הדאטה האמיתי הקיים; אחרת לתעד Fixture limitation במפורש בדוח-הסיום, לא להסתיר** |
| AT-0.7 Holdout isolation | Sandbox (עותק/Fixture) | **GO — בדיקת-מנגנון בלבד, ר' הכרעה 2** |

### הכרעה 2 — AT-0.7: בדיקת-מנגנון בלבד, לא הפרדה פיזית

**הוכרע: לא לבצע הפרדה פיזית אמיתית של Holdout (יולי-דצמבר 2025) במסגרת B-5.** מריצים רק את `separate_holdout`/`HoldoutGuard` הקיימים (ללא שינוי קוד) נגד עותק-דאטה-אמיתי או Fixture — ומוודאים שה-Guard חוסם גישה-ללא-Unlock כראוי. **ההפרדה הפיזית המלאה (אופציה B בטיוטה הקודמת) נדחית במפורש ל-Work Order נפרד עתידי (Hardening/KI-023)** — לא חלק מ-B-5, לא הבטחה-משתמעת שהיא "תיכלל בהמשך אוטומטית".

### הכרעה 3 — AT-0.3/AT-0.5: לא Gate

- **AT-0.3 — מסומן "Covered by D-071" — אינו Gate ל-B-5.** D-071 (§א.10) משמש כעדות-תוכן קיימת ומספקת; לא נכתבת בדיקה חדשה, לא רצה הרצה נוספת.
- **AT-0.5 — מסומן "N/A"** — בדיקת-זמן טהורה (UTC/ET boundary math), ללא תלות בדאטה כלל; כבר ירוקה, הרצה חוזרת לא מוסיפה דבר.

**אין סתירה מהותית שנותרה. ממשיך ל-`WORK_ORDER_B5.md` (גרסה סופית).**
