# WORK ORDER — B-4: RA-10 Real Spread Report

מסמך ביצוע ל-Claude Code · Stage A, Blocker B-4 · מאושר ע"י Roy (Project Owner)
מקור סמכות: `PREFLIGHT_B4.md` v1 · `WORK_ORDER_PROTOCOL.md` v1.0 (FROZEN) · `RRR_COMPLETION_PLAN.md`
**כפוף ל-`WORK_ORDER_PROTOCOL.md`** — Lessons Learned + DoD Checklist בדו"ח הסיום (§3.9/§4).

---

## 0. הקשר ותפקיד

אתה Senior Quant Engineer בפרויקט מחקר XAUUSD דטרמיניסטי. ה-Backfill (Batch 1-7) הושלם במלואו — 39/39 חודשים אמיתיים קיימים ומאומתים (`BATCH7_CLOSURE_REPORT.md`). RRR (`docs/RESEARCH_READINESS_REVIEW.md`) נשאר NO-GO על 4 סעיפים פתוחים מתוך 9 (RA-10, AT-0.* מול דאטה אמיתי, Quality Gates, KI-010) — B-4 סוגר **רק** את סעיף 3 (RA-10).

**RA-10** (`docs/RESEARCH_ASSUMPTIONS_V1.md:28`): `costs.slippage_stop_usd = 0.10$` הוא הערכה שמרנית ראשונית, המתועדת מלכתחילה כ"יכויל מחדש מול דו"ח הספרד של Phase 0". `build_spread_report()` (`src/data/spread_report.py:77`) כבר קיים ומוכן — B-4 בונה עליו סקריפט-הרצה חדש, לא נוגע בו.

**זה כל ה-Scope. שום דבר מעבר לזה.**

## 1. כללים קשיחים

1. **אין שינויי Scope.** B-4 = RA-10/Slippage בלבד. **לא** `min_stop_k_spread` (למרות שהדוקסטרינג של `spread_report.py` מרמז שהמודול רלוונטי גם אליו — הוכרע במפורש ב-`PREFLIGHT_B4.md` §ד כ-B-נפרד עתידי, לא כאן). B-4 אינו סוגר RRR ואינו פותח Phase 4/T3.4.
2. **טווח-נתונים קבוע: `2022-10-01` עד `2025-06-30` בלבד (33 חודשים).** **אסור** להשתמש ביולי-דצמבר 2025 (חלון-Holdout, `config/run_default.yaml::holdout`) — הוכרע ב-D-073, ללא חריג. כל סקריפט שנכתב חייב לקבל את הטווח כפרמטר מפורש (לא Hardcoded "כל מה שיש ב-`data/ticks/`"), כדי שלא "יראה" בטעות את חודשי-ה-Holdout.
3. **אין שינויי קוד קיים.** `build_spread_report`/`SpreadReport`/`TickParquetStore` — ללא שינוי. B-4 מוסיף סקריפט-אורכסטרציה חדש בלבד (בדפוס `analyze_spikes.py`/`backfill_full_range.py`), לא נוגע בקוד-הליבה.
4. **אין שינויי Schema.** אם מתגלה שנדרש — עצור, דווח, המתן לאישור Roy.
5. **אין שינוי-ערך ל-`costs.slippage_stop_usd` ללא Decision Proposal מפורש ואישור Roy** — בדיוק כמו B-2/B-3 ("STOP → דיווח → אישור Roy → שינוי"), לא שינוי-אד-הוק תוך-כדי ניתוח. נוהל-העדכון המלא ב-`docs/RESEARCH_ASSUMPTIONS_V1.md:59-64` (5 צעדים) מחייב.
6. **הרצה בפועל — מחשב הבית בלבד**, בדיוק כמו כל ה-Backfill. `data/ticks/` gitignored, לא קיים ב-Sandbox. Claude מכין את הסקריפט; Roy מריץ; Evidence גולמי חוזר ל-Claude לאימות.
7. **אין Concat-מלא-בבת-אחת של 33 חודשי-Ticks לזיכרון ללא בדיקת-היתכנות מקדימה** (ר' `PREFLIGHT_B4.md` §ב.2 — סיכון-ביצועים לא-מאומת). הסקריפט חייב לתמוך בהרצה הדרגתית/מדידת-זיכרון, ולעצור-ולדווח אם המשאבים לא מספיקים — לא לקרוס בשקט ולא לחתוך-דאטה בשקט.
8. כל בדיקה/הרצה מתועדת בפלט אמיתי בלבד — Raw Paste, לא תמצית (הדפוס שנשמר לכל אורך ה-Backfill).
9. עבודה על branch: `stage-a/b4-ra10-spread-report`.

## 2. החלטות מאושרות מראש (אין לפתוח מחדש)

- Scope = RA-10/Slippage בלבד. לא `min_stop_k_spread`, לא KI-022, לא KI-010.
- טווח-נתונים = `2022-10-01`…`2025-06-30` (33 חודשים), Holdout (יולי-דצמבר 2025) לא ייגע (D-073).
- D הפנוי הבא לתיעוד סגירה: **D-074** (D-073 כבר נוצל לטובת החלטת ה-Scope עצמה, ב-Pre-Flight).
- ההרצה בפועל על מחשב הבית; אין ניסיון להריץ ב-Sandbox.

## 3. שלב 0 — Pre-flight

**בוצע.** `PREFLIGHT_B4.md` v1 (+עדכון לאחר ממצא-Holdout). הכרעה: **PROCEED**, שתי שאלות-Scope נפתרו (RA-10-בלבד; טווח 33-חודשים) — ר' שם §ד.

## 4. יישום — סדר קומיטים

**Commit 1 — סקריפט-מדידה (`scripts/diagnostics/run_full_spread_report.py`, Read-Only בעיצובו).**
- CLI: `--symbol`, `--start`, `--end` (חובה — ללא Default שמכסה את כל הטווח, כדי למנוע הרצה-בטעות על Holdout), `--ticks-dir` (כמו `analyze_spikes.py`).
- טוען כל חודש בנפרד דרך `TickParquetStore.read_month()` (ללא שינוי), מצרף רק עמודות `ts`/`bid`/`ask` (מזעור-Overhead-זיכרון, ר' §1.7).
- קורא ל-`build_spread_report(ticks, symbol)` (קיים, ללא שינוי) פעם אחת על כל הדאטה המצורף.
- מדפיס: `SpreadReport.to_markdown()` המלא (טבלה per-ET-hour: ticks/mean/p25/median/p75/p95) + סיכום-על (חציון-כללי על פני כל השעות, p95-כללי) + `row_count` כולל + רשימת-חודשים שנטענו בפועל (לאימות שהטווח נכון ולא חרג ל-Holdout).
- **Sanity check מובנה בסקריפט:** לפני ההדפסה, לוודא תכנותית ש-`max(months loaded) <= (2025, 6)` — אם לא, לזרוק שגיאה חד-משמעית ולא להדפיס פלט (הגנה-כפולה על גבול-ה-Holdout, לא רק הסתמכות על הפרמטרים שהוזנו נכון).

**Commit 2 — Evidence + ניתוח (לא קוד).**
- Roy מריץ על מחשב הבית: `uv run python scripts/diagnostics/run_full_spread_report.py --symbol XAUUSD --start 2022-10-01 --end 2025-06-30`, עם `Tee-Object` ללוג.
- Claude מאמת: `row_count` כולל תואם לסכום row_count-ים של 33 החודשים (מ-checkpoint.json/Closure Reports הקודמים); רשימת-החודשים שנטענו לא כוללת שום חודש אחרי 2025-06; טבלת-הספרד תקינה מבנית (24 שעות או פחות אם יש חסר-דגום, לא יותר).
- **ניתוח-השוואה (לא שינוי-קוד):** להציג את `costs.slippage_stop_usd=0.10` מול המדידה בפועל (למשל p95-spread בשעות-הרלוונטיות ליציאת-Stop) — **מתודולוגיית-ההשוואה המדויקת (איזה Percentile, אילו שעות רלוונטיות ליציאת-Stop) תוצג כהצעה לפני שהיא "נקבעת"**, כי אין לה הגדרה קיימת בשום מסמך — זו בדיוק הנקודה שדורשת Decision Proposal (§1.5), לא הנחה שקטה.

**Commit 3 (מותנה) — עדכון RA-10, רק אם ההכרעה קובעת שינוי.**
- אם הניתוח (Commit 2) מוביל להמלצת-שינוי: Decision Proposal מלא (ערך-נוכחי → ערך-מוצע → השפעה-צפויה) → **עצירה, המתנה לאישור Roy המפורש** → רק אחרי אישור: עדכון `config/parameters.yaml::costs.slippage_stop_usd` + `docs/RESEARCH_ASSUMPTIONS_V1.md` (שורת RA-10) + D-entry (D-074) לפי נוהל-5-הצעדים.
- אם ההכרעה היא "0.10 עדיין סביר, אין צורך בשינוי": D-entry (D-074) מתעד את **אישוש** RA-10 (לא שינוי) — עדיין רישום חובה, לא רשומה-מדלגת.
- **בשום מקרה לא משנים את הערך לפני שהוצג Decision Proposal ואושר.**

**Commit 4 — תיעוד סוגר.**
- `docs/RESEARCH_READINESS_REVIEW.md`: סעיף 3 (RA-10) מסומן GO, עם הפניה לפלט-הריצה + D-074.
- **חובה בדוח הסיום:** טבלת סטטוס RRR מעודכנת (9 הסעיפים) — להראות במפורש שנשאר NO-GO על שאר הסעיפים (AT-0.*, Quality Gates, KI-010), לא לרמז שסגירת-RA-10 = RRR=GO.

## 5. קריטריוני סגירה (B-4 AC)

- דו"ח-ספרד אמיתי הופק בפועל על `2022-10-01`…`2025-06-30` (33 חודשים), לא Holdout, לא Fixture.
- `row_count` כולל מאומת מול checkpoint.json/Closure Reports הקודמים.
- Decision Proposal הוצג לגבי RA-10 (שינוי או אישוש) והמתין לאישור Roy לפני כל עדכון בפועל.
- D-074 נכתב, בין אם RA-10 השתנה או אושש מחדש.
- `docs/RESEARCH_READINESS_REVIEW.md` סעיף 3 מעודכן ל-GO.
- טבלת-RRR מלאה (9 סעיפים) מופיעה בדוח-הסיום, ומראה במפורש שהיא **עדיין NO-GO** (אלא אם B-5/B-6/B-7 גם נסגרו במקביל — לא מתוכנן במסגרת B-4 עצמו).
- **הכרזת "Closed" רק בכפוף ל-DoD המלא (`WORK_ORDER_PROTOCOL.md` §4)** — קובץ סגירה: `WORK_ORDER_B4_CLOSURE.md`.

## 6. Non-Goals (חובה בכל תיעוד סוגר)

1. **B-4 אינו סוגר RRR** — 3 סעיפים נוספים (AT-0.*, Quality Gates, KI-010) נשארים פתוחים במפורש.
2. **B-4 אינו נוגע ב-`min_stop_k_spread`** — למרות הרמז בדוקסטרינג של `spread_report.py`. B נפרד עתידי, לא כאן.
3. **B-4 אינו סוגר KI-022** — כיול ה-Validator (Spike-threshold) הוא עבודה נפרדת (B-6), לא קשור למדידת-Spread לצורך RA-10.
4. **B-4 אינו נוגע ביולי-דצמבר 2025 (Holdout)** בשום שלב — לא לצורך RA-10, לא לצורך "השוואה מהירה", לא בשום תירוץ (D-073).

## 7. תנאי עצירה מיידית

- הסקריפט טוען (בטעות או לא) חודש כלשהו מיולי-דצמבר 2025 → עצור מיידית, אל תפרסם פלט, דווח.
- `row_count` שנטען לא תואם למצופה מ-checkpoint.json/Closure Reports → עצור, דווח, אל תנחש.
- כל המלצה לשנות `costs.slippage_stop_usd` לפני Decision Proposal מפורש ואישור Roy → אסור, עצור.
- נדרש שינוי Schema או נגיעה ב-`build_spread_report`/`spread_report.py` הקיים → עצור, דווח.
- בעיית-זיכרון/ביצועים בטעינת 33 חודשים בבת-אחת → עצור, דווח, הצע חלופה הדרגתית (לא לחתוך-דאטה בשקט).
- כל סטייה מסמך↔קוד נוספת שמתגלה → עצור, דווח, המתן.

## 8. דו"ח סיום (פורמט חובה — `WORK_ORDER_PROTOCOL.md` §3+§4)

זהה למבנה שהופעל בהצלחה ב-B-1/B-2/B-3 (11 סעיפים + DoD 9/9 + Lessons Learned + מדד-פרויקט), **בתוספת** טבלת סטטוס RRR מעודכנת (§5 לעיל) ואישור מפורש שארבעת ה-Non-Goals (§6) מופיעים בגוף הדוח. קובץ הסגירה: `WORK_ORDER_B4_CLOSURE.md`.
