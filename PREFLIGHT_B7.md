# PREFLIGHT_B7.md — KI-010: Real Economic-Calendar Source + Integration (Phase 1: BLS CPI+NFP)

**Blocker:** B-7 — KI-010 (לוח חדשות אמיתי, RA-23), הסעיף היחיד בחומרת `high` שעדיין פתוח, והחוסם היחיד ב-RRR שאינו תלוי ב-Backfill/Dukascopy.
**מבוצע לפי:** `WORK_ORDER_PROTOCOL.md` §1. **מסמך תכנון בלבד — לא בוצע שום שינוי קוד, לא בוצע Commit.**

---

## א. הנחות מאומתות (הנחה → ראיה)

1. **`src/core/types.py::NewsEvent` (שורות 158-166) קיים ומוכן, ללא צורך בשינוי-מבנה.** שדות נצרכים בפועל: `ts_utc, currency, impact, title, source`. **אין** שדה ל-Actual/Forecast/Previous — המערכת לא צורכת אותם. אומת ישירות בקוד (לא מהזיכרון).
   ראיה: `src/core/types.py:158-166`.

2. **`config/rules_v1.yaml` (FROZEN, שורות 44-47) כבר מגדיר את הסינון המדויק הנדרש:** `news_filter: {currency: [USD], impact: [red], blackout_min: {before: 30, after: 30}}`. **B-7 אינו נוגע בקובץ הזה בשום צורה** — הוא כבר קפוא ומלא-מספיק.
   ראיה: `config/rules_v1.yaml:44-47`.

3. **`src/session/calendar_engine.py::CalendarEngine` כבר data-source-independent (D-037), ללא צורך בשינוי.** `from_config(events, currencies, impacts, blackout_before_min, blackout_after_min)` מקבל `list[NewsEvent]` מוזרק, מסנן, ובונה חלונות-Blackout. `in_blackout(ts)`/`blackout_intervals_utc()`/`effective_window_minutes(...)` — כולם קיימים ועובדים. **B-7 אינו נוגע בקובץ הזה.**
   ראיה: `src/session/calendar_engine.py:1-87` (קריאה מלאה).

4. **`db/schema.sql::news_events` (שורות 164-171) כבר מגדיר את סכימת-האחסון המדויקת** (`ts_utc, currency, impact, title, source`, PK מורכב) — תואמת-בדיוק ל-`NewsEvent`. אין צורך בשינוי-Schema.
   ראיה: `db/schema.sql:164-171`.

5. **AT-3.9 (`tests/test_at3_9_blackout_engagement.py`) קיים וירוק, אך רץ אך ורק מול Fixture סינתטי** — בדיוק כמו כל AT-0.\* לפני B-5. B-7 הוא המקבילה-של-B-5 עבור לוח-החדשות: "הרצה מול דאטה אמיתי", לא בניית-מנגנון-חדש.
   ראיה: `tests/test_at3_9_blackout_engagement.py` קיים; KI-010 עצמו מצהיר זאת.

6. **`KI010_DECISION_DOC.md` כבר קיים בריפו (מחויב-Git, commit `4439dfb`).** סוקר 4 מקורות, ממליץ על מקור-ממשלתי **או** Trading-Economics, לא-ממליץ במפורש על Scraper.
   ראיה: `KI010_DECISION_DOC.md` (קריאה מלאה), commit `4439dfb`.

7. **`RA-23` (`docs/RESEARCH_ASSUMPTIONS_V1.md:56`) כבר מנוסח כ"בחירה זמנית הממתינה להכרעה":** "רשימת האירועים הסופית תיקבע אחרי בדיקת זמינות המקור... ותובא לאישור." **המשמעות: B-7 מעדכן RA-23 קיים, לא יוצר RA חדש.**
   ראיה: `docs/RESEARCH_ASSUMPTIONS_V1.md:56`.

8. **בדיקת-נגישות בפועל (Read-Only, `WebFetch`, מאושרת ע"י Roy) בוצעה וחשפה ממצא מהותי: ה-Sandbox חסום-רשת גורף.** נבדקו 6 Domains — `bls.gov`, `bea.gov`, `federalreserve.gov`, `census.gov`, `tradingeconomics.com`, ואפילו `en.wikipedia.org` (Baseline לא-פיננסי) — **כולם חסומים** (`EGRESS_BLOCKED`). מדיניות-ה-Proxy הרשמית (`$HTTPS_PROXY/__agentproxy/status` + README) מאשרת זו מדיניות-ארגונית מוצהרת ("do not retry or route around it"), לא תקלה. **זה מבטל את ההנחה המקורית שהייתה כאן (ש"אין חסימה גורפת") — תוקן.**
   ראיה: תוצאות `WebFetch` בפועל על 6 Domains (בשיחה); `curl $HTTPS_PROXY/__agentproxy/status`; `/root/.ccr/README.md`.

## ב. הנחות שלא ניתן לאמת (סיבה, השפעה, טיפול)

1. **פורמט-הפלט המדויק של עמודי-הלוח של BLS** (מבנה-HTML, פורמט תאריך/שעה מדויק) — לא אומת מול תוכן-גולמי-אמיתי (החסימה מנעה זאת מה-Sandbox; Roy דיווח "בדיקה ראשונית בוצעה" ממחשב-הבית אך לא הודבק תוכן-גולמי לשיחה).
   **סיבה שלא ניתן לאמת:** אין לי גישה-ישירה למקור; מסתמך על מוסכמות-BLS ידועות-כלליות (טבלת: Release name / Reference period / Release date / Release time, בשעון-ET).
   **השפעה:** תכנון-ה-Data-Contract (§Data Contract ב-`WORK_ORDER_B7.md`) הוא ברמת-הסכימה/העקרון, **לא** Regex/Parser סופי — זה ייקבע/יאומת בפועל ב-Commit 1, כשהדאטה-האמיתי ייאסף.
   **טיפול:** Commit 1 כולל צעד-אימות מפורש מול תוכן-אמיתי לפני שמשהו "נסגר".

2. **מחיר Trading Economics API** — לא רלוונטי עוד (מקור A נבחר, לא B). מוסר מרשימת-הנחות-פתוחות.

## ג. סטיות תיעוד↔קוד שהתגלו

**אין סטיות חדשות.** כל התשתית (`NewsEvent`, `CalendarEngine`, `rules_v1.yaml::news_filter`, `db/schema.sql::news_events`) עקבית במלואה עם עצמה ועם `KI010_DECISION_DOC.md`.

## ד. הכרעה

**PROCEED — הוכרע ע"י Roy: מקור A (ממשלתי רשמי, BLS), Phase 1 מינימלי.**

### הכרעות-Scope שאושרו

1. **מקור:** BLS בלבד (לא Fed/BEA/Census בשלב זה — Follow-up מפורש).
2. **סוגי-אירוע (Phase 1):** CPI + Employment Situation (NFP) בלבד — שני האירועים ה-USD-High-Impact המוסכמים-ביותר.
3. **RA:** עדכון RA-23 הקיים (לא RA חדש) — RA-23 עצמו כבר ניסח את ההכרעה הזו כ"ממתינה".
4. **ביצוע-אצירה:** מחשב-הבית בלבד (Sandbox חסום-רשת גורף, §א.8).

**שאר ה-Pre-Flight נקי — אין סתירה מהותית שנותרה. ממשיך ל-`WORK_ORDER_B7.md` (גרסה סופית, Phase 1).**
