# B-1 Closure Report — Stage A / Blocker B-1 (Reproducibility Spine)

**מבוצע לפי:** `WORK_ORDER_PROTOCOL.md` v1.0 §3/§4 · `WORK_ORDER_B1.md` §8 · Sub-Order "WORK ORDER — B-1 Closure" (Closure בלבד, ללא שינויי קוד).
**Branch:** `claude/xauusd-research-handoff-j5para`. **B-1 diff range:** `bbce7cc..f5aacdb`. **Closure-task commit:** נדחף בסוף מסמך זה, ראה עדכון SHA.

---

## 1. רשימת כל הקבצים שהשתנו (B-1, Commits 0–5 + follow-ups)

```
.gitignore
PREFLIGHT_B1.md                              (חדש)
WORK_ORDER_B1.md                             (חדש)
WORK_ORDER_PROTOCOL.md                       (חדש)
data/registry/.gitkeep                       (חדש)
db/schema.sql
docs/ACCEPTANCE_TESTS.md
docs/DECISIONS_LOG.md
docs/INTERFACES.md
docs/KNOWN_ISSUES.md
src/backtest/orchestrator.py
src/backtest/run_builder.py
src/core/types.py
src/data/versioning.py                       (חדש)
tests/fixtures/orchestrator.py
tests/test_at3_14_determinism.py             (חדש)
tests/test_full_pipeline_9_arms.py
tests/test_full_pipeline_from_raw_4h_bars.py
tests/test_run_builder.py
tests/test_run_identity.py                   (חדש)
tests/test_versioning.py                     (חדש)

21 files changed, 842 insertions(+), 41 deletions(-)
```

**בנוסף, במסגרת Closure Task זה עצמו (תיעוד בלבד, ר' §8 להלן):**
```
docs/KNOWN_ISSUES.md      (KI-021 נוסף — ממצא Self-Review, משימה 3)
PYTEST_OUTPUT_B1.txt      (חדש — פלט אימות משימה 1)
WORK_ORDER_B1_CLOSURE.md  (חדש — קובץ זה)
```

## 2. Diff מלא

ה-diff המלא של B-1 (21 קבצים, 842+/41-) נשלח כקובץ מצורף בסבב קודם (`B1_full_diff.patch`, `bbce7cc..HEAD` בזמנו). התוכן לא השתנה מאז — אין commits חדשים ב-B-1 עצמו בין אז לעכשיו, רק תוספת ה-Closure Task (KI-021 + שני קבצים חדשים, ר' §1).

## 3. פלט הרצת הבדיקות המלא (משימה 1)

**בוצע בקלון טרי ועצמאי** (לא בעותק העבודה הקיים) — משוכפל ישירות מול ה-remote האמיתי (`roybar0704-spec/Trading-startegy-ai`), לא מהעותק המקומי:

```
Timestamp (UTC): 2026-07-21T09:51:11Z
git rev-parse HEAD: f5aacdb0ac36b79b0ab713eaddfbf781688d7056
Expected SHA: f5aacdb0ac36b79b0ab713eaddfbf781688d7056  ✓ תואם
git status --porcelain: (ריק — עץ נקי)

139 passed in 4.09s   (הרצה verbose מלאה, 139/139 שורות PASSED בפועל — ר' PYTEST_OUTPUT_B1.txt)
```

הפלט המלא (163 שורות, כולל רשימת כל 139 הטסטים בשמם ותוצאתם) נשמר ב-`PYTEST_OUTPUT_B1.txt` (שורש הריפו).

## 4. Acceptance Tests שנוספו/עודכנו

**AT-3.14 — דטרמיניזם דו-ריצתי** (`docs/ACCEPTANCE_TESTS.md`, `tests/test_at3_14_determinism.py`) — ללא שינוי מאז ה-Closing Report הקודם; מאומת ירוק שוב בהרצה העצמאית של משימה 1 (`tests/test_at3_14_determinism.py::test_at3_14_two_from_scratch_runs_produce_identical_canonical_export PASSED`).

## 5. Known Issues שנסגרו/נפתחו

- **KI-018 → Closed** (D-068, AT-3.14) — ללא שינוי מאז ה-Commit 5 הקודם.
- **KI-021 → נפתח** (Self-Review B-1 Closure, משימה 3 של Work Order זה): `_append_registry_record` (`src/backtest/run_builder.py`) כותבת ל-`data/registry/runs.jsonl` ללא נעילת-קובץ — סיכון תיאורטי לשיזור-רשומות בכתיבה מקבילה (לא קיים היום, אין ריצות-מקבילות ב-Stage A). חומרה: low. Follow-up: לטפל אם/כש-Phase 4/5 יריצו ריצות מקבילות, או כחלק מ-T5.5 (Experiment Tracker).

## 6. Decision Records שנוספו

ללא D-entries חדשים ב-Closure Task זה עצמו — D-066/D-067/D-068 כבר תועדו בקומיטים הקודמים של B-1. Closure Task זה תיעוד/אימות בלבד, לא החלטה ארכיטקטונית חדשה.

## 7. הכרזה

**B-1 נסגר במלואו — Closed** (לא Partially Closed). כל תשעת סעיפי ה-DoD מתקיימים בפועל (ר' §10).

## 8. חריגות והפתעות

1. **ממצא Self-Review אמיתי (KI-021):** בניגוד לסבב הקודם (שבו ה-Self-Review לא העלה ממצאים חדשים), מעבר אדוורסרי אמיתי הפעם — כולל קריאת קוד ישירה בקלון טרי, לא הסתמכות על זיכרון-שיחה — חשף פער אמיתי (נעילת-קובץ חסרה ב-Registry). נפתח כ-KI, לא תוקן בשקט, בדיוק כפי שהפרוטוקול דורש.
2. **פער תפעולי לא-קשור לקוד:** בסבב קודם (בקשת Roy ל-tag `stage-a-b1-closed`) — דחיפת ה-tag ל-`origin` נכשלה עם `403` (הרשאה חסומה ל-tag-push, לא תקלת רשת). ה-tag קיים מקומית בלבד. לא קשור ל-DoD/AC של B-1 עצמו (§5 ב-WORK_ORDER_B1.md לא כולל דרישת tag), אך מתועד כאן להשלמת השקיפות.
3. **סביבה טרייה בכל הרצה:** כל אימות בקלון טרי דרש `uv sync --extra dev` — עקבי עם מה שתועד ב-`PREFLIGHT_B1.md`, לא ממצא חדש.

## 9. Lessons Learned

- **LL-1 (מה התגלה שלא היה ידוע לפני תחילת העבודה):** ה-Placeholder `seed=0` (D-059/KI-018) התגלה כמתנגש עם ערך-Seed אמיתי-אפשרי (0 הוא Seed חוקי) — עולה רק תוך-כדי Pre-Flight ל-B-1, כי אף אחד לא בדק את הסמנטיקה מול הסכימה הקפואה קודם. הוביל ל-STOP + Decision Proposal + D-067 (שינוי סכימה יחיד, מאושר). בנוסף, ה-Self-Review של Closure Task זה חשף פער נוסף שלא היה ידוע: `_append_registry_record` נטולת-נעילה (KI-021).
- **LL-2 (הנחות שהתבררו כנכונות):** כל שאר הנחות ה-Pre-Flight (`PREFLIGHT_B1.md` §א) אומתו במדויק — חתימת `build_orchestrator`, קיום `config_hash()`+טסט, ה-fixture של D-064 כבסיס ל-AT-3.14, רשימת 18 טבלאות ה-Journal, אין עמודות שעון-קיר רלוונטיות, המספור הפנוי (D-067→D-068, AT-3.14).
- **LL-3 (הנחות שהתבררו כשגויות):** הנחת ה-Work Order ש-`seed=NULL` ניתן ליישום ללא שינוי סכימה — התבדתה (D-067). הניסוח המקוצר "`config_hash(params)`" ב-Work Order המקורי לא תאם את חתימת חמשת-הארגומנטים האמיתית (C2, סטייה קלה לא-חוסמת).
- **LL-4 (עדכונים נדרשים למסמכים, בעקבות הממצאים):**
  - D-067/D-068 ב-DECISIONS_LOG.md — **בוצע** (קומיטים `c964eb9`, `5a3dd83`).
  - KI-018 Closed + הפניה צולבת ל-KI-016 — **בוצע** (קומיט `5a3dd83`).
  - AT-3.14 ב-ACCEPTANCE_TESTS.md — **בוצע** (קומיט `2c17f6b`).
  - INTERFACES.md (RunIdentity + חתימת `build_orchestrator`) — **בוצע** (קומיט `3dab914`, תוקן `1192199`).
  - KI-018 Follow-up (make_orchestrator עוקף build_orchestrator) קיבל עדיפות+יעד מפורשים — **בוצע** (קומיט `f5aacdb`, ביקורת Lead Architect).
  - KI-021 (ממצא Self-Review זה) — **בוצע כרגע**, ב-Closure Task עצמו (§5 לעיל), עם עדיפות (low) ויעד (Phase 4/5 ריצות-מקבילות או T5.5).
  **אין אובדן ידע שקט — כל פריט LL-4 מטופל.**

## 10. DoD Checklist חתום (PROTOCOL §4)

1. ✅ **כל ה-AC של B-1 מולאו** — `runs` נושאת ערכים אמיתיים בכל 5 השדות; AT-3.14 ירוק (אומת שוב, הרצה עצמאית); רשומת Registry נכתבת בכל ריצה עם Journal; חבילה מלאה ירוקה (139/139, אומת בקלון טרי); INTERFACES/ACCEPTANCE_TESTS/DECISIONS_LOG/KNOWN_ISSUES מעודכנים.
2. ✅ **כל הבדיקות עברו בפועל** — פלט אמיתי, verbose, בקלון טרי-ועצמאי מול ה-remote: `139 passed in 4.09s`, כל שורה מפורטת (`PYTEST_OUTPUT_B1.txt`).
3. ✅ **לא נוספו KI חדשים ללא תיעוד** — KI-021 (הממצא היחיד שהתגלה) תועד באופן מלא, לא הושאר שקוף.
4. ✅ **Decision Log עודכן** — D-066/D-067/D-068 קיימים ומלאים; אין D-entry נוסף נדרש ב-Closure Task זה עצמו.
5. ✅ **Lessons Learned נכתב במלואו** — §9 לעיל, LL-1..LL-4, כל אחד מעוגן ב-D-entry/KI קונקרטי.
6. ✅ **`PREFLIGHT_B1.md` נשמר ומצורף** — קיים בשורש הריפו (קומיט `811a7af`), מוזכר ומקושר כאן.
7. ✅ **אין סטיות חדשות מ-SPEC/Rules/Architecture** — KI-021 הוא ממצא-חוסן תפעולי ב-Infra של Stage A (Registry), לא נגיעה ב-SPEC/כללי-אסטרטגיה; לא נדרש חריג.
8. ✅ **Self-Review אדוורסרי בוצע** — §8 + §5 לעיל: חמש הזוויות (lookahead/point-in-time/דטרמיניזם/Interfaces/סחף-ארכיטקטוני) נבדקו בפועל בקלון טרי, ממצא אמיתי אחד עלה (KI-021) ותועד, לא תוקן בשקט.
9. ✅ **חוב טכני שנותר תועד עם עדיפות ויעד** — KI-018 Follow-up (Low, יעד B-3 Pre-Flight); KI-021 (Low, יעד Phase 4/5 ריצות-מקבילות או T5.5); KI-019 (low, מקרה-קצה מתועד, לא קשור ל-B-1 עצמו).

**כל תשעת הסעיפים מסומנים ✅ → B-1 מוכרז Closed.**

## 11. מדד פרויקט

**Stage נוכחי:** Stage A. **Blockers:** B-1 סגור (1/7); B-2..B-7 טרם החלו. **Known Issues:** 10 סגורים / 11 פתוחים (KI-021 חדש התווסף בסבב זה; KI-018 היה כבר סגור קודם). **התקדמות Stage A משוערת:** ~14% (1/7). **Top-3 סיכונים שנותרו:** (1) שאר Stage A (B-2..B-7) — טרם הוגדרו/בוצעו, היקף לא ידוע; (2) KI-021 (Registry ללא נעילה) — לא חוסם היום, אך צריך מעקב לפני ריצות-מקבילות אמיתיות; (3) ה-tag `stage-a-b1-closed` קיים מקומית בלבד, לא ב-`origin` — נדרשת פעולת-הרשאה חיצונית להשלמה.

---

**B-1 סגור במלואו. Closure Task זה הושלם — עצירה מלאה, ממתין להנחיה מפורשת של Roy לפני כל עבודה נוספת (כולל B-2).**
