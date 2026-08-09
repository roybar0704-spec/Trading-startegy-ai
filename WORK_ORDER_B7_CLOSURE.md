# WORK_ORDER_B7_CLOSURE.md — B-7: KI-010 Real Economic-Calendar Integration (Phase 1: BLS CPI+NFP)

**סטטוס: B-7 (Work Order) Closed במלואו.** **KI-010 עצמו: Partially Closed** (לא Closed מלא — ר' §4). מקור סמכות: `PREFLIGHT_B7.md`, `WORK_ORDER_B7.md`, `WORK_ORDER_PROTOCOL.md` v1.0 (§3+§4), `KI010_DECISION_DOC.md`.

**הבחנה קריטית (אושרה במפורש ע"י Roy, נשמרת כאן ללא עמעום):** "B-7" (ה-Work Order) ו-"KI-010" (הבעיה הבסיסית) הם שני דברים שונים. ה-Work Order בוצע **במלואו** לפי התוכנית שאושרה מראש (6 קומיטים, DoD מלא — ר' §9), ולכן **הבלוקר B-7 עצמו נסגר**. אך ה-**החלטה המהותית** שהתקבלה בתוך ה-Work Order (Decision Proposal, Commit 5, אופציה B) קבעה במפורש ש-**KI-010 נשאר Partially Closed** — לא Closed. אין לקרוא "B-7 Closed" כאילו הוא אומר "KI-010 Closed". תקדים זהה בדיוק ל-B-6 (B-6 Closed במלואו; KI-008 נותר Partially Closed בתוכו).

---

## 1. Scope שבוצע

**Phase 1 בלבד** (לפי `WORK_ORDER_B7.md` §1, לא הורחב ולא צומצם):
- מקור: **BLS** (ממשלתי, Public Domain).
- סוגי-אירוע: **CPI** + **Employment Situation (NFP)** בלבד.
- טווח: `2022-10-07`…`2025-06-11` — **33 חודשים**.
- **66 NewsEvent אמיתיים** (33 CPI + 33 Employment Situation).
- Holdout (יולי-דצמבר 2025) הוחרג במכוון — לא נכלל בדאטה, לא נגוע.

**Non-Goals שנשמרו (`WORK_ORDER_B7.md` §1):** אין Fed/BEA/Census; אין שינוי ב-`CalendarEngine`; אין שינוי ב-`config/rules_v1.yaml`; אין שינוי ב-`NewsEvent`; אין Feed חי; אין Scraping מ-ForexFactory/Investing.com.

## 2. Evidence מלא

### נתוני המקור
```
SHA-256 (data/news/bls_calendar.csv): 5ecaa281fe93e11cdf418bff7e4d589f43ceaba13fd5f357b0dceec50be444c6
```
(אומת מחדש כרגע, ב-Closure עצמו — תואם בדיוק ל-Evidence שהוצג ב-Commit 2.)

### בדיקות-תוכן (מ-Commit 2/4, מאומתות)
| בדיקה | תוצאה |
|---|---|
| סה"כ שורות | 66 |
| CPI | 33 |
| Employment Situation | 33 |
| כפילויות | 0 |
| שורות מחוץ לטווח Tick-Data (2022-10-01…2025-12-31) | 0 |
| סדר כרונולוגי | PASS |
| שעה בכל הרשומות | 08:30 ET, ללא יוצא-מן-הכלל |

### Loader + CalendarEngine (Commit 3-4)
- `src/data/news_loader.py::load_bls_csv()` — Fail-Loud, ET→UTC עם DST (`zoneinfo("America/New_York")`), נבדק ב-18 בדיקות-יחידה (`tests/test_news_loader.py`), כולל `test_real_bls_calendar_csv_loads_cleanly` שטוען את ה-CSV האמיתי-והמלא.
- ET→UTC + DST: אומת עם שני מקרי-קצה אמיתיים סביב מעבר-שעון 2023-03-12 (EST -5 לפני, EDT -4 אחרי) — `test_dst_transition_shifts_the_utc_offset`.
- `CalendarEngine.from_config(...)` (הקיים-והבלתי-משתנה) הופעל בפועל מול ה-66 אירועים האמיתיים ומול `config/rules_v1.yaml::news_filter` ה-FROZEN בפועל (`scripts/diagnostics/run_b7_calendar_real_data_check.py`, Commit 4):

```
in_blackout(event time exactly): True
in_blackout(15min before): True
in_blackout(15min after): True
in_blackout(45min before, outside the +/-30min window): False
in_blackout(45min after, outside the +/-30min window): False
```

### פלט בדיקות מלא (מורץ מחדש עכשיו, ב-Closure עצמו — לא רק מצוטט מ-Commits קודמים)
```
$ uv run pytest
167 passed in 4.78s

$ uv run ruff check src tests scripts
All checks passed!
```

### Holdout
`data/holdout/` לא נקרא בשום סקריפט/בדיקה של B-7. ה-CSV עצמו מסתיים ב-`2025-06-11`, לפני תחילת חלון-ה-Holdout (יולי 2025) — הוחרג במכוון, לא ב-מקרה.

## 3. Git / Commit Chain — כל ששת השלבים

| # | Hash | תוכן |
|---|---|---|
| Commit 1 | `f2d7a18cc2ab1ad6271bab4177d753b7cbfd9714` | `scripts/tools/fetch_bls_calendar.py` — כלי-אצירה אוטומטי (Stdlib, Fail-Loud). קוד בלבד, ללא דאטה, ללא הרצה-אמיתית (Sandbox). |
| Commit 2 | `00577fa0bdf681349e5f2c4ea26e7659a571dd06` | `data/news/bls_calendar.csv` (66 אירועים אמיתיים) + חריגת `.gitignore` (`!/data/news`). אצירה **ידנית** ע"י Roy — האצירה האוטומטית נחסמה (ר' §7). |
| Commit 3 | `3427d0a70dbf80043d0c97dfffa7ddd95b4f5cde` | `src/data/news_loader.py` + `tests/test_news_loader.py` (18 בדיקות). |
| Commit 4 | `2aa18aadc753caf36ee089b1a4397186094a85c5` | `scripts/diagnostics/run_b7_calendar_real_data_check.py` — הוכחת אינטגרציה מלאה מול `CalendarEngine` האמיתי ודאטה אמיתי. |
| Commit 5 | `22b24599020aad9ee1c1fdc131354602ac15ddc0` | Decision Proposal (אופציה B) + `RA-23` + `D-077` + עדכון `KI-010`/RRR סעיף 7. |
| Commit 6 | (זה המסמך — טרם בוצע) | `WORK_ORDER_B7_CLOSURE.md` — תיעוד-סוגר. |

## 4. הכרעת KI-010

**KI-010 = PARTIALLY CLOSED.**

**מה נסגר במלואו:**
- מקור-נתונים אמיתי (BLS) אותר, נבחר, ותועד (`KI010_DECISION_DOC.md`).
- CSV אמיתי נאצר ונשמר (`data/news/bls_calendar.csv`, 66 אירועים).
- Loader עובד (`src/data/news_loader.py`, 18/18 בדיקות עוברות).
- `CalendarEngine` Integration הוכחה מול דאטה אמיתי (לא Fixture סינתטי) — זו הייתה הבעיה המקורית של KI-010, ונפתרה במלואה.
- News blackout behavior (±30 דק') הוכח בפועל מול `config/rules_v1.yaml` האמיתי.

**מה נשאר פתוח:**
Coverage של USD Red News מעבר ל-CPI/NFP. Phase 1 מכסה **2 מתוך 7** סוגי-אירוע High-Impact-USD המוכרים (`KI010_DECISION_DOC.md` §3). `docs/SPEC_V1_FROZEN.md` שורה 67 מגדיר Blackout סביב "חדשות אדומות USD" **באופן גנרי**, לא מוגבל-לסוג — Backtest שירוץ על הדאטה הזה **לא** יחסום סביב FOMC/GDP/Core PCE/ISM/Retail Sales אמיתיים.

## 5. RRR סעיף 7

**GO with explicit limitations** (עודכן ב-Commit 5, תקדים שורות 3-4 באותו RRR — B-4/D-074, B-5/D-075).

ה-GO מתייחס במפורש ל-**"Real USD/red economic-calendar pipeline — Phase 1 (CPI + Employment Situation)"** — למנגנון ולסוגי-האירוע שנבדקו בפועל בלבד. **אין** לפרש GO זה כטענה ל-Coverage מלא של כל USD Red News.

## 6. Follow-up

**B-8 (טרם הוגדר כ-Work Order, טרם בוצע כל עבודה)** — הרחבת Coverage ל-:
- FOMC Rate Decision
- GDP
- Core PCE
- ISM PMI
- Retail Sales

מקורות-נתונים להרחבה זו (Fed/BEA/Census או חלופה) ייבדקו בנפרד ב-Pre-Flight של B-8 — לא נבחרו ולא נבדקו כאן. **לא בוצעה שום עבודה על ה-Follow-up הזה בפועל** — זהו רישום-כוונה בלבד.

## 7. מה לא השתנה

- `src/session/calendar_engine.py` — **לא שונה** לאורך כל B-7.
- `src/core/types.py::NewsEvent` — **לא שונה**.
- `config/rules_v1.yaml` — **נשאר FROZEN**, לא נגוע.
- `data/news/bls_calendar.csv` — **לא שונה** מאז Commit 2 (SHA-256 זהה, אומת ב-§2).
- `db/schema.sql` — **לא שונה**.
- `data/holdout/` — **לא נגוע** בשום שלב.

**הערה נוספת (שקיפות מלאה, לא הוסתרה בשום שלב):** `scripts/tools/fetch_bls_calendar.py` (Commit 1) כלל בשלב-ביניים תיקון-Headers (User-Agent/Accept) שנוסה כפתרון ל-403 ממחשב-הבית של Roy; אומת (ע"י Roy, `curl.exe -I` עצמאי) שהחסימה היא Akamai Bot-Manager WAF ברמת-שרת, לא בעיית-Header — התיקון הוחזר (`git checkout`) בדיוק למצב Commit 1 המקורי **לפני** Commit 2, ולא נכלל בשום Commit. הקובץ נשאר מתועד כניסיון-אוטומציה שנחסם, לא כחלק ממסלול-הייצור.

## 8. Closure Criteria

| Criterion | Status |
|---|---|
| Real BLS data | PASS |
| CPI coverage | PASS |
| Employment Situation coverage | PASS |
| Loader | PASS |
| ET→UTC/DST | PASS |
| CalendarEngine integration | PASS |
| Blackout behavior | PASS |
| Holdout isolation | PASS |
| Full USD Red News coverage | **NOT COMPLETE** |
| KI-010 | **PARTIALLY CLOSED** |
| RRR-7 | **GO with explicit limitations** |

## 9. DoD Checklist מול `WORK_ORDER_PROTOCOL.md` §4

1. ✅ כל ה-Acceptance Criteria של ה-Work Order (`WORK_ORDER_B7.md` §4, Definition of Done) מולאו — פריטים 1-7 שם בוצעו במלואם; פריט 8 (DoD מלא + Closure Report) הוא זה שלפניך.
2. ✅ כל הבדיקות הרלוונטיות עברו בפועל, פלט אמיתי בלבד — 167/167 עכשיו (§2), אין רגרסיה.
3. ✅ לא נוספו Known Issues חדשים ללא תיעוד — KI-010 עצמו עודכן (לא חדש); אין KI חדש שנפתח ב-B-7.
4. ✅ Decision Log עודכן — D-077 (Commit 5).
5. ✅ Lessons Learned נכתב במלואו (§10 למטה).
6. ✅ `PREFLIGHT_B7.md` — עדיין untracked בריפו (כמו `PREFLIGHT_B5.md`/`WORK_ORDER_B5.md`); לא נכלל בשום Commit של B-7 (Non-Goal מפורש שלא נדון עדיין — ר' §11 להלן, פתוח כשאלה מפורשת לפני שה-Commit ייסגר).
7. ✅ לא נוצרו סטיות חדשות מה-SPEC/Rules/Architecture — Non-Goals כולם נשמרו במלואם (§1, §7).
8. ✅ Self-Review אדוורסרי בוצע: **Lookahead** — לא רלוונטי (לוח-חדשות היסטורי קבוע, לא נתון מתעדכן-בדיעבד — נדון מפורשות ב-`KI010_DECISION_DOC.md` §1). **Point-in-time** — `CalendarEngine.in_blackout(ts)` נבדק פר-timestamp מפורש (exact/±15/±45 דק'), אין נגישות-לעתיד. **דטרמיניזם** — `load_bls_csv()` ממיין דטרמיניסטית (`test_output_is_deterministic_and_sorted_regardless_of_input_order`), אין רנדומיות. **Interfaces** — `NewsEvent`/`CalendarEngine.from_config` לא שונו כלל; `news_loader.py` הוא מודול חדש בלבד, לא שינוי-חוזה. **סחף ארכיטקטוני** — אפס; `CalendarEngine` נשאר data-source-independent (D-037) כפי שהיה. **סיכון-רגרסיה** — אפס; 167/167 יציב בכל קומיט.
9. ✅ חוב טכני שנותר נפתח כ-Follow-up מתועד: **B-8** (הרחבת Coverage ל-5 סוגי-אירוע נותרים — §6), עדיפות high (KI-010 עצמו high), יעד לא-נקבע (Work Order עתידי נפרד).

**DoD מלא 9/9 — B-7 (ה-Work Order) Closed. KI-010 עצמו Partially Closed בתוכו (§4) — לא סתירה: התקדים המדויק הוא B-6/KI-008.**

## 10. Lessons Learned (חובה)

- **LL-1 (מה גילינו):** ה-Sandbox חוסם גישת-רשת כללית (allowlist בלבד ל-package-registries+anthropic.com) — לא רק ל-Dukascopy (KI-001 המוכר), אלא לכל דומיין כללי, כולל בסיס-ייחוס נייטרלי (Wikipedia). זהו סוג-חסימה **שונה** מהחסימה שהתגלתה בהמשך במחשב-הבית של Roy (Akamai Bot-Manager WAF ברמת-שרת-היעד עצמו, לא ברמת-Sandbox) — שני מנגנוני-חסימה נפרדים ובלתי-תלויים, אובחנו ותועדו בנפרד.
- **LL-2 (הנחות שאומתו):** ההנחה המרכזית של `KI010_DECISION_DOC.md` — ש-`NewsEvent`/`CalendarEngine` לא צריכים Actual/Forecast/Surprise, רק תאריך+שעה+USD+red — התאמתה במלואה: לא נדרש שום שינוי-Interface לאורך כל B-7.
- **LL-3 (הנחות שהיו שגויות):** (א) ההנחה הראשונית ש-Header-fix (User-Agent/Accept) יפתור 403 ממחשב-הבית הייתה שגויה — האבחון-הנכון (Akamai WAF, לא client-fingerprint) התגלה רק אחרי בדיקת `curl.exe -I` גולמית של Roy. (ב) ה-CSV הראשוני (64 שורות) שסופק ע"י Roy החסיר בפועל את אוקטובר-2022 (טווח-Tick-Data האמיתי מתחיל שם) — זוהה ע"י בדיקת-אימות עצמאית, לא הונח כנכון.
- **LL-4 (עדכוני-מסמכים):** `docs/RESEARCH_ASSUMPTIONS_V1.md` RA-23 (בוצע, Commit 5). `docs/DECISIONS_LOG.md` D-077 (בוצע, Commit 5). `docs/KNOWN_ISSUES.md` KI-010 (בוצע, Commit 5). `docs/RESEARCH_READINESS_REVIEW.md` סעיף 7 (בוצע, Commit 5). `KI010_DECISION_DOC.md` — נבדק במפורש, **לא עודכן** (אין צורך ממשי, נשאר מסמך-ההכרעה המקורי, כפי שאושר ע"י Roy). **B-8 (הרחבת Coverage) נפתח כ-Follow-up מפורש, לא כ-KI נוסף** — KI-010 עצמו נושא את הסטטוס partially-closed.

## 11. סעיף פתוח שדורש הכרעה — `PREFLIGHT_B7.md`/`WORK_ORDER_B7.md` (untracked)

שני הקבצים האלה נותרו untracked לאורך כל B-7 (כמו ב-B-5), אך **לא עודכנו** לשקף את השתלשלות-האירועים בפועל (חסימת-Akamai, פנייה-לאצירה-ידנית, תיקון-אוקטובר-2022, Revert-ה-Headers). זו שאלה שטרם הוצגה במפורש — כמו ב-B-6 (שם Roy אישר במפורש להכליל את `PREFLIGHT_B6.md`/`WORK_ORDER_B6.md` ב-Commit הסוגר, בניגוד ל-B-5). **לא הוכרע כאן, לא נעשה דבר בקשר לזה בשקט.** מוצג להכרעתך: לכלול את שני הקבצים (מעודכנים או כפי-שהם) ב-Commit 6, או להשאירם untracked כמו ב-B-5.

## 12. מדד פרויקט (Project Status)

- **Stage נוכחי:** Stage A.
- **Blockers פתוחים:** B-8 (טרם הוגדר כ-Work Order — Follow-up בלבד, לא Blocker פעיל).
- **Blockers שנסגרו:** B-1, B-2, B-3, B-4, B-5, B-6, **B-7**.
- **Known Issues פתוחים (11):** KI-003, KI-008 (partially, gap_threshold בלבד), KI-011, KI-012, KI-013, KI-019, KI-021 (כולם low) · **KI-010 (high, partially closed)** · KI-023, KI-024 (medium).
- **Known Issues שנסגרו (14):** KI-001, KI-002, KI-004, KI-005, KI-006, KI-007, KI-009, KI-014, KI-015, KI-016, KI-017, KI-018, KI-020, KI-022.
- **RRR:** סעיף 7 עודכן ל-GO with explicit limitations (מתוך 9 סעיפים) — **הפסיקה הכוללת עדיין NO-GO** (סעיף 5, Quality Gates, נשאר NO-GO במפורש מ-B-5/D-075, לא תלוי ב-B-7).
- **Top-3 סיכונים פתוחים:** (1) KI-010 (high, partially closed) — Coverage חלקי, Follow-up B-8 טרם הוגדר. (2) Quality Gates שער-5 עדיין לא-ירוק במלואו (תלוי גם ב-KI-024, גם ב-Performance Gate שטרם רץ). (3) KI-023 — אין מנגנון-אכיפת-Holdout מרכזי; B-7 לא נגע ב-Holdout כלל, אך הסיכון הכללי נותר פתוח כפי שהיה.
