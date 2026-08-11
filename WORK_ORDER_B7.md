# WORK ORDER — B-7: KI-010 Real Economic-Calendar Integration (Phase 1: BLS CPI+NFP)

מסמך ביצוע ל-Claude Code · Stage A, Blocker B-7 · מאושר-עקרונית ע"י Roy (Project Owner) — **ממתין לאישור סופי על מסמך זה לפני כל שינוי/הרצה**
מקור סמכות: `PREFLIGHT_B7.md` v2 (הכרעה: PROCEED — מקור A/BLS, Phase 1 מינימלי) · `WORK_ORDER_PROTOCOL.md` v1.0 (FROZEN) · KI-010, RA-23, `KI010_DECISION_DOC.md`
**כפוף ל-`WORK_ORDER_PROTOCOL.md`** — Lessons Learned + DoD Checklist בדו"ח הסיום (§3.9/§4).

---

## 0. הקשר ומטרה

KI-010 (`high`) הוא הסעיף היחיד-בחומרת-high שנותר פתוח, וגם **סעיף-RRR פורמלי (7)**: "לוח חדשות אמיתי (CSV, אדום, USD) אותר ואומת; `CalendarEngine` הורץ מולו בפועל, לא רק מול Fixture סינתטי." B-7 סוגר את שני התנאים, ב-**Phase 1 מינימלי**: מקור BLS בלבד, אירועי CPI+NFP בלבד — לא 6-7 לוחות מלאים. הרחבה עתידית (Fed/BEA/Census) = Follow-up מפורש, לא חלק מ-B-7 עצמו.

## 1. Scope מדויק

**בסקופ:**
- אצירת לוח-פרסומים היסטורי **אמיתי** של BLS — CPI + Employment Situation (NFP) בלבד — לטווח `2022-10-03`…`2025-12-31`.
- מודול-טעינה חדש (`src/data/news_loader.py`) הממיר את הדאטה-הגולמי ל-`list[NewsEvent]`.
- הרצה בפועל של `CalendarEngine.from_config(...)` הקיים מול הדאטה-האמיתי — הוכחת Blackout-Windows אמיתיים.
- עדכון `RA-23` (לא RA חדש — RA-23 עצמו ניסח את ההכרעה כ"ממתינה", `PREFLIGHT_B7.md` §א.7).
- עדכון `docs/KNOWN_ISSUES.md` (KI-010) ו-`docs/RESEARCH_READINESS_REVIEW.md` (סעיף 7).

**Non-Goals (חובה בכל תיעוד סוגר):**
1. **אין Fed/BEA/Census בשלב זה** — Follow-up מפורש (KI חדש או הרחבת-B-7 עתידית, ייקבע ב-Closure).
2. **אין שינוי ב-`src/session/calendar_engine.py`** — data-source-independent כבר, לא נדרש.
3. **אין שינוי ב-`config/rules_v1.yaml`** — FROZEN, `news_filter` כבר מגדיר את כל הדרוש.
4. **אין שינוי ב-`src/core/types.py::NewsEvent`** — הסכימה כבר תואמת.
5. **אין Feed חי/עדכון-שוטף** — הורדה/אצירה חד-פעמית בלבד (כפי ש-`KI010_DECISION_DOC.md` §1 כבר קבע).
6. **אין Scraping מ-ForexFactory/Investing.com** — נפסל במפורש.

## 2. רשימת קבצים

| קובץ | פעולה | הערה |
|---|---|---|
| `scripts/tools/fetch_bls_calendar.py` | חדש | כלי-אצירה אוטומטי (Stdlib בלבד — `urllib.request`+`html.parser`), רץ על מחשב-הבית, מייצר את ה-CSV. Fail-Loud על 0-התאמות/שגיאת-פרסור. |
| `data/news/bls_calendar.csv` | חדש | דאטה-גולמי-אמיתי, פלט-הכלי, מ-Commit 2 (הרצה בפועל). **חריגת-gitignore אושרה ובוצעה** (`!/data/news`, מאושר ומחויב-Commit). |
| `src/data/news_loader.py` | חדש | קוד-Production — CSV→`list[NewsEvent]`. |
| `tests/test_news_loader.py` | חדש | בדיקות-יחידה (CSV סינתטי-קטן, לא הדאטה-האמיתי). |
| `docs/RESEARCH_ASSUMPTIONS_V1.md` | עדכון | RA-23 — מקור סופי + Phase-1-Scope. |
| `docs/KNOWN_ISSUES.md` | עדכון | KI-010 — closed (Phase 1) או partially-closed, ר' §6. |
| `docs/RESEARCH_READINESS_REVIEW.md` | עדכון | סעיף 7. |
| `docs/DECISIONS_LOG.md` | עדכון | D-077. |
| `.gitignore` | עדכון-נקודתי | חריגה ל-`data/news/`. |

## 3. Data Contract

### פורמט Raw Input (מוצע — יאומת מול תוכן-אמיתי ב-Commit 2)
CSV פשוט, יופק אוטומטית ע"י `scripts/tools/fetch_bls_calendar.py` (Commit 1) בהרצה על מחשב-הבית (Commit 2), מתוך עמודי-הלוח הרשמיים של BLS (`bls.gov/schedule/news_release/{YEAR}_sched.htm`, שנים 2022-2025):
```csv
date,time_et,release,source
2022-10-13,08:30,CPI,BLS:2022_sched.htm
2022-11-04,08:30,Employment Situation,BLS:2022_sched.htm
...
```
**⚠️ פורמט-ה-HTML-הגולמי-בפועל טרם אומת מול תוכן אמיתי** (`PREFLIGHT_B7.md` §ב.1) — הכלי נבנה Fail-Loud (לא CSV-חלקי-בשקט אם הפרסור נכשל); ייתכן שיידרש תיקון-Parser בהרצה חוזרת, בלי שינוי ל-Data-Contract עצמו.

### המרה ל-`NewsEvent`
| שדה `NewsEvent` | מקור | לוגיקה |
|---|---|---|
| `ts_utc` | `date`+`time_et` | פרשנות כ-Local Wall-Clock ב-`America/New_York` (`zoneinfo`, DST-aware) → המרה ל-UTC. **תואם למוסכמת-הפרויקט** (`zoneinfo("America/New_York")` לסשן, UTC פנימי — CLAUDE.md). |
| `currency` | קבוע | `"USD"` — כל פרסומי-BLS הם דאטה-אמריקאי. |
| `impact` | קבוע (Phase 1) | `"red"` — CPI ו-NFP שניהם High-Impact מוסכם-כמעט-אוניברסלית (`KI010_DECISION_DOC.md` §3). |
| `title` | `release` | ישיר ("CPI"/"Employment Situation"). |
| `source` | `"BLS:{YEAR}_sched.htm"` | **מדויק-לפי-מקור, לא קבוע** — Traceability מלא לעמוד-המקור-המדויק שממנו נחלץ כל אירוע (חידוד שאושר ע"י Roy). |

### Timezone handling
BLS מפרסם תמיד בשעון-מזרחי (ET, לא מצוין-מפורש-כ-EST/EDT בעמודים — משתמע מהקונטקסט). פרשנות כ-`America/New_York` local-time מטפלת אוטומטית ב-EST/EDT לפי התאריך (`zoneinfo`, לא offset קבוע) — עקבי עם `src/data/bar_builder.py`/כל שאר הפרויקט.

### Impact mapping
Phase 1: **קבוע** (`red` לכל שורה) — אין עדיין Whitelist-מדורג, כי שני סוגי-האירועים היחידים (CPI, NFP) שניהם High-Impact. Whitelist-אמיתי (מיפוי-שם-אירוע→impact) יידרש רק ב-Phase 2 (Fed/BEA/Census, שם יש טווח-חשיבות רחב יותר) — לא כאן.

## 4. Definition of Done

1. Roy אצר CSV-גולמי אמיתי (BLS, CPI+NFP, `2022-10-03`…`2025-12-31`) ממחשב-הבית.
2. `src/data/news_loader.py` נכתב, נבדק ביחידה (CSV סינתטי-קטן).
3. `CalendarEngine.from_config(...)` הופעל בפועל מול ה-`list[NewsEvent]` האמיתי שנטען מה-CSV — Blackout-Windows אמיתיים אומתו (לפחות תאריך-CPI ידוע אחד + תאריך-NFP ידוע אחד, בדיקת `in_blackout()` בתוך/מחוץ לחלון).
4. RA-23 עודכן (מקור=BLS, Phase-1-Scope=CPI+NFP, Follow-up=Fed/BEA/Census).
5. D-077 נכתב.
6. `docs/KNOWN_ISSUES.md`/`docs/RESEARCH_READINESS_REVIEW.md` עודכנו — **סטטוס-הסגירה המדויק (closed מלא מול partially-closed, ר' §6) יוכרע ב-Closure, לא כאן.**
7. `pytest -q`/`ruff` ירוקים, אין רגרסיה.
8. DoD מלא (`WORK_ORDER_PROTOCOL.md` §4) ב-`WORK_ORDER_B7_CLOSURE.md`.

## 5. שאלת-הכרעה פתוחה ל-Closure (לא עכשיו): סגירת KI-010 מלאה מול חלקית

RRR סעיף 7 מנוסח כ"לוח חדשות אמיתי אותר ואומת" — לא מפרש "כל סוגי-האירועים". **שאלה לגיטימית שתידון ב-Closure (Commit אחרון), לא כאן:** האם Phase-1 (CPI+NFP בלבד, לא Fed/BEA/Census) מספיק לסמן KI-010 closed + RRR-7 GO, או שנדרש "partially closed" (כמו KI-008 ב-B-6) עד שההרחבה תבוצע. **לא מוכרע כאן — יוצג כ-Decision Proposal לפני Commit-הסגירה.**

## 6. תוכנית Commit (מאושרת, 6 שלבים)

**Commit 1 — `scripts/tools/fetch_bls_calendar.py` (Sandbox, קוד בלבד, ללא דאטה, ללא הרצה-אמיתית).**
- Stdlib-בלבד (`urllib.request`+`html.parser`), Fail-Loud, Evidence מובנה (row-count/checksum/פילוח/טווח-תאריכים).

**Commit 2 — הרצה בפועל (מחשב-הבית, Roy) + `data/news/bls_calendar.csv` + `.gitignore` + Evidence מלא.**
- Roy מריץ את הכלי, שולח Raw-Evidence (הפלט המלא של הכלי — לא רק ה-CSV).
- Claude מאמת: מספר-שורות סביר (~78, 2 אירועים/חודש × ~39 חודשים), תאריכים בטווח הנכון בלבד, אין כפילויות, checksum.

**Commit 3 — `src/data/news_loader.py` + `tests/test_news_loader.py` (Sandbox, קוד בלבד).**
- מימוש + בדיקות-יחידה מול CSV-סינתטי-קטן (לא הדאטה-האמיתי).

**Commit 4 — הרצה מול הדאטה-האמיתי (Sandbox, אחרי ש-Commit 2 מספק את ה-CSV).**
- `news_loader.load_bls_csv(...)` → `CalendarEngine.from_config(...)` → אימות Blackout על תאריכים-אמיתיים-ידועים. Raw Evidence.

**Commit 5 — Decision Proposal (עצירה) + RA-23 + D-077.**
- כולל ההכרעה מ-§5 (closed מלא/חלקי).

**Commit 6 — תיעוד סוגר** (`WORK_ORDER_B7_CLOSURE.md`).

---

**לא בוצע שום שינוי/הרצה.** ממתין לאישורך הסופי על התוכנית (כולל §3 Data Contract ו-§2 שאלת ה-`.gitignore`) לפני שמתחילים ב-Commit 1.
