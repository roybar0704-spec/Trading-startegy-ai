# WORK_ORDER_B5_CLOSURE.md — B-5: AT-0.* מול דאטה אמיתי + Quality Gates מחדש

**סטטוס:** DRAFT — ממתין לבדיקה ואישור Roy. **טרם בוצע Commit 4.**
מקור סמכות: `WORK_ORDER_B5.md`, `PREFLIGHT_B5.md`, `WORK_ORDER_PROTOCOL.md` v1.0 (§3+§4).

---

## 1. סיכום מלא

B-5 סוגר שני סעיפי-RRR: סעיף 4 (AT-0.\* מול דאטה אמיתי) וסעיף 5 (Quality Gates מחדש). בוצע ב-3 קומיטים:

- **Commit 1** (`5992895`): `scripts/diagnostics/run_at0_real_data_checks.py` (AT-0.1/0.4/0.6) + `scripts/diagnostics/run_at0_7_holdout_mechanism_check.py` (AT-0.7, בדיקת-מנגנון) — הרצו ב-Sandbox מול נובמבר-2022 האמיתי.
- **Commit 2** (`63f5950`): `scripts/diagnostics/run_at0_2_cache_check.py` (AT-0.2) — הרצה על מחשב-הבית מול `data/raw/` האמיתי.
- **Commit 3** (`c97a66a`): `bash scripts/ci.sh` (Quality Gates מחדש) + `docs/KNOWN_ISSUES.md` (KI-024).

תוצאה: כל 7 ה-AT-0.\* טופלו לפי ההחלטה המאושרת (4 חובה + AT-0.3 Covered-by-D-071 + AT-0.5 N/A + AT-0.7 מנגנון-בלבד). Quality Gates רצו במלואם, סטטוס **PARTIAL** מדווח בשקיפות (לא GO גורף).

## 2. Evidence לכל AT

### AT-0.1 — Download integrity (Sandbox, נובמבר-2022 האמיתי)
```
tick count: 3,641,776
bid <= ask (all rows): True
timestamps non-decreasing (sorted): True
timestamps strictly unique (no duplicate ts): True
```
**PASS.** (הערה: דאטה אמיתי הפגין ייחודיות-מלאה של timestamps — טוב יותר מהצפוי; ר' Lessons Learned LL-3.)

### AT-0.2 — Cache immutability (מחשב-הבית, `data/raw/` האמיתי)
**PASS.** Roy אישר: "AT-0.2 Evidence התקבל ונבדק. תוצאה: PASS מלא."

**AT-0.2 Raw Evidence was verified during execution session. The raw console output is preserved in conversation evidence; no standalone artifact was committed.** (חריג מתועד ומאושר במפורש ע"י Roy — לא תקדים שקט; שאר ה-AT-ים ב-B-5/B-4 תיעדו Raw Evidence ישירות בתוך מסמכי ה-Closure.)

### AT-0.4 — DST build (Sandbox, נובמבר-2022 האמיתי, Fall-Back 2022-11-06)
```
2022-11-04 (last EDT trading day before fall-back): bars=252 no_duplicate_bars=True non_5min_gaps=0 08:30_ET_bar_present=True
2022-11-07 (first EST trading day after fall-back): bars=276 no_duplicate_bars=True non_5min_gaps=1 08:30_ET_bar_present=True
  gap details (informational): [(2022-11-07 21:55 UTC, 2022-11-07 23:00 UTC)]
  NOTE: gap not near the DST transition hour -- consistent with the known daily-rollover
  gap pattern already documented in D-071 (17:00 ET rollover), not a DST defect.
```
**PASS.**

### AT-0.6 — Bar↔Tick consistency (Sandbox, נובמבר-2022 האמיתי, החודש כולו)
```
bars built: 29,929; independent ground-truth buckets: 29,929
mismatched bars: 0 / 29,929
```
**PASS.** (כיסוי מלא של כל ברי-1M בחודש האמיתי — חזק יותר מהבדיקה המקורית שכיסתה שעה אחת בלבד.)

### AT-0.7 — Holdout isolation, בדיקת-מנגנון בלבד (Sandbox, עותק זמני של נובמבר-2022 האמיתי)
```
separate_holdout() moved 1 month(s)
PASS: main store cannot read the moved (holdout) month (FileNotFoundError)
PASS: HoldoutGuard raised HoldoutAccessDenied without holdout_unlock=True
Loaded 243,019 real ticks via HoldoutGuard.load(holdout_unlock=True)
All returned rows fall within the requested window: True
```
**PASS (מנגנון בלבד).** לא בוצעה הפרדה-פיזית-אמיתית של יולי-דצמבר 2025 — נדחתה במפורש ל-Follow-up (KI-023/Hardening עתידי), כפי שהוחלט מראש.

### AT-0.3 — Gap detection
**Covered by D-071 — לא Gate.** לא נכתבה בדיקה חדשה (הוחלט מראש).

### AT-0.5 — 4H anchor
**N/A — לא Gate.** בדיקת-זמן טהורה, ללא תלות בדאטה (הוחלט מראש).

## 3. Evidence — Quality Gates (Commit 3)

ר' `WORK_ORDER_B5_QUALITY_GATES_EVIDENCE.md` (קובץ נפרד, מחויב ב-Commit 3) לפלט המלא של `bash scripts/ci.sh`. תמצית:

| שער | סטטוס |
|---|---|
| Functional | **PARTIAL** — pytest 149/149 ✅; חסום ע"י KI-010 (high, open, לא נוצר ב-B-5, שייך ל-B-7) |
| Performance | לא הורץ (הוחלט במפורש) |
| Code Quality | ✅ PASS |
| Architecture | ✅ PASS |
| Documentation | לא נבדק פורמלית ב-Commit 3 |
| Regression | **PARTIAL** — pytest+Prefix-Consistency ✅; Golden Regression ללא Implementation (KI-024 חדש, medium, Follow-up) |

**Functional Gate מוצהר PARTIAL, לא GO — במפורש בגלל KI-010, לא תקלה חדשה, לא ב-Scope של B-5.**
**Golden Regression מוצהר Follow-up בלבד (KI-024) — לא Blocker, לא נפתח Work Order חדש.**

## 4. פלט בדיקות מלא (לפני/אחרי, לכל Commit)

`pytest -q`: **149 passed** — זהה בשלושת הקומיטים (Commit 1, 2, 3), אין רגרסיה בשום שלב.
`ruff check` — נקי בכל שלושת הקומיטים.
`pylint --enable=duplicate-code src` — 10.00/10 (Commit 3).
`lint-imports` — 4/4 חוזים נשמרו (Commit 3).

## 5. Acceptance Tests שנוספו/עודכנו

**אין AT חדש נוסף ל-`docs/ACCEPTANCE_TESTS.md` בכוונה** — B-5 מריץ מחדש את הקריטריונים הקיימים של AT-0.1/0.2/0.4/0.6/0.7 מול דאטה אמיתי דרך סקריפטי-אבחון (לא pytest חדש), בדיוק כפי ש-B-3/B-4 עשו. שלוש הסקריפטים החדשים (`scripts/diagnostics/run_at0_real_data_checks.py`, `run_at0_7_holdout_mechanism_check.py`, `run_at0_2_cache_check.py`) הם תיעוד-ריצה, לא תוספת לחוזה-הקבלה הפורמלי.

## 6. Known Issues שנסגרו/נפתחו

- **נפתח: KI-024** (medium, Golden Regression — אין Implementation, Follow-up בלבד, לא Blocker).
- **לא נסגר, לא נוצר-חדש: KI-010** (high, open, קדם ל-B-5, שייך ל-B-7 — מוזכר כאן לשקיפות בלבד).
- **לא נסגר, לא רלוונטי-שינוי: KI-022, KI-023** (ללא שינוי סטטוס ב-B-5).

## 7. Decision Records שנוספו

**D-075** (הצעה — ר' פירוט וניסוח מוצע בהודעה הנפרדת, טרם נכתב ל-`DECISIONS_LOG.md`).

## 8. סטטוס: נסגר במלואו / חלקית

**שתי ההכרעות שהיו פתוחות אושרו ע"י Roy:** (1) AT-0.2 Raw Evidence — חריג מתועד ומאושר (ר' §2). (2) RRR סעיף 4 — **GO with explicit limitations documented** (ר' §9 ב-`docs/RESEARCH_READINESS_REVIEW.md`, ור' פירוט למטה).

B-5 עונה במלואו לכל קריטריוני ה-AC (`WORK_ORDER_B5.md` §5), **פרט לכך שסעיף-RRR 5 (Quality Gates) נשאר NO-GO במכוון** — לא Blocker של B-5 עצמו (B-5 לא התחייב לסגור את שער-5 במלואו, רק להריץ אותו מחדש ולדווח בשקיפות). **פריט DoD אחד נותר פתוח** — ר' §11 סעיף 6 (צירוף `PREFLIGHT_B5.md` בפועל ל-Git).

## 9. חריגות והפתעות (כולל ממצאי Pre-Flight)

1. **חודש-דאטה-אמיתי כבר קיים ב-Sandbox** (D-072/B-3) — אפשר להריץ AT-0.1/0.4/0.6/0.7-מנגנון כאן, לא רק על מחשב-הבית. שינוי-תבנית ראשון מסוגו בפרויקט (B-1..B-4 דרשו מחשב-הבית תמיד).
2. **באג בסקריפט AT-0.6 שלי, שנתפס ותוקן לפני הצגה ל-Roy:** ה-Ground-Truth הראשונה חישבה `ts.min()` במקום רצפת-הדקה (`bucket * 60s`) — גרם ל-29,885/29,929 "כשלים" מדומים. תוקן ואומת מחדש (0 mismatches) לפני שהוצג. מתועד כאן במפורש, לא הוסתר.
3. **דאטה אמיתי לא הפגין timestamps כפולים כלל ב-AT-0.1** — בניגוד להנחה המקורית שלי ב-Pre-Flight (שדאטה אמיתי "עלול" להכיל כפילויות).
4. **פער-Golden-Regression התגלה כלוואי של הרצת Quality Gates** — לא היה ידוע לפני B-5.
5. **פער-Evidence ל-AT-0.2** — נפתר: Roy אישר חריג מתועד (ר' §2).

## 10. Lessons Learned (חובה)

- **LL-1 (מה גילינו):** (א) חודש-דאטה-אמיתי כבר זמין ב-Sandbox משנה את מודל-הביצוע ל-Blockers עתידיים שלא דורשים 39/39 חודשים במלואם. (ב) Golden Regression מעולם לא מומש (KI-024). (ג) `data/raw/` (מטמון גולמי) קיים ותקין על מחשב-הבית ואפשר לבדוק Cache-Immutability בלי הורדה חיה, בעזרת Transport-רעל.
- **LL-2 (הנחות שהתבררו נכונות):** BarBuilder תואם במדויק ל-Ground-Truth בלתי-תלוי על פני חודש שלם אמיתי (29,929/29,929). `separate_holdout`/`HoldoutGuard` פועלים נכון על סכימת-דאטה אמיתית, לא רק Fixture. ה-Gap היחיד שנמצא ב-AT-0.4 תואם בדיוק לתבנית ה-Rollover המתועדת כבר ב-D-071.
- **LL-3 (הנחות שהיו שגויות):** ההנחה ב-Pre-Flight ש-AT-0.1 "עלול" למצוא timestamps כפולים בדאטה אמיתי לא התממשה — הדאטה האמיתי ייחודי-לחלוטין. חיובי, לא שלילי, אך ההנחה המקורית הייתה לא-מדויקת.
- **LL-4 (עדכוני-מסמכים נדרשים):** `docs/RESEARCH_READINESS_REVIEW.md` סעיפים 4+5 (מוצע כאן, ממתין לאישור). `docs/DECISIONS_LOG.md` D-075 (מוצע, טרם נכתב). `docs/KNOWN_ISSUES.md` KI-024 (בוצע, Commit 3). כל פריט מטופל — אין אובדן-ידע שקט.

## 11. DoD Checklist מול `WORK_ORDER_PROTOCOL.md` §4

1. ✅ **כל ה-AC מולאו** (`WORK_ORDER_B5.md` §5), פרט לכך ש-RRR סעיף 5 נשאר NO-GO במכוון (לא AC-דרישה של B-5 עצמו).
2. ✅ **כל הבדיקות עברו בפועל, פלט אמיתי בלבד** — לכל AT/Gate יש Raw Output מתועד ישירות במסמך זה, **חוץ מ-AT-0.2**: שם ה-Raw Evidence הופיע בשיחת-ההרצה עצמה (session execution) ולא הודבק כחפץ עצמאי במסמך — חריג מתועד ומאושר במפורש ע"י Roy (ר' §2), לא סטייה שקטה.
3. ✅ לא נוספו KI חדשים ללא תיעוד (KI-024 מתועד במלואו).
4. ✅ Decision Log — D-075 מאושר בניסוח (ר' הודעה נפרדת), נכתב ל-`docs/DECISIONS_LOG.md` כחלק מ-Commit 4.
5. ✅ Lessons Learned נכתב במלואו (§10).
6. ❌ **`PREFLIGHT_B5.md` נשמר ומצורף לדוח הסיום** — **טרם מחויב ל-Git** (עדיין untracked, כפי שהנחית לא לכלול אותו ב-Commit 4). זהה בדיוק לשאלה שעלתה ב-B-4 Closure — יש להכריע אם "מצורף" דורש Commit בפועל.
7. ✅ לא נוצרו סטיות חדשות מה-SPEC/Rules/Architecture.
8. ✅ Self-Review אדוורסרי בוצע: אין Lookahead (סקריפטים קריאה-בלבד, לא מוזרקים לשום לוגיקת-החלטה); אין סוגיית Point-in-Time (לא נוגעים ב-MarketContext); דטרמיניזם שלם (אין אקראיות, נתונים אמיתיים קבועים); אין שינוי-Interfaces; אין סחף ארכיטקטוני (כל הסקריפטים תחת `scripts/diagnostics/`, אותו דפוס כמו `analyze_spikes.py`/`run_full_spread_report.py`); סיכון-רגרסיה — אפס (149/149 קבוע בכל קומיט).
9. ✅ חוב טכני פתוח כ-Follow-up מתועד: KI-024 (medium, Follow-up, יעד לא-מוגדר), KI-023 (medium, יעד B-6/Hardening), KI-010 (high, יעד B-7).

**סטטוס: "Partially Closed" — פריט DoD אחד בלבד נותר פתוח (סעיף 6 לעיל: צירוף `PREFLIGHT_B5.md` בפועל ל-Git). כל שאר קריטריוני ה-DoD (1-5, 7-9) מלאים.**

## 12. מדד פרויקט (Project Status)

- **Stage נוכחי:** Stage A.
- **Blockers פתוחים:** B-6 (KI-022), B-7 (KI-010).
- **Blockers שנסגרו:** B-1, B-2, B-3, B-4, **B-5 (בכפוף להכרעות §2/§8 לעיל)**.
- **Known Issues פתוחים (11):** KI-003, KI-008, KI-011, KI-012, KI-013, KI-019, KI-021 (כולם low) · KI-010 (high) · KI-022, KI-023, KI-024 (medium, KI-024 חדש).
- **Known Issues שנסגרו (13):** KI-001, KI-002, KI-004, KI-005, KI-006, KI-007, KI-009, KI-014, KI-015, KI-016, KI-017, KI-018, KI-020.
- **RRR:** לפני B-5 — 5/9 GO. אחרי B-5 (מוצע) — **6/9 GO** (סעיף 4 מוצע GO; סעיף 5 נשאר NO-GO במכוון).
- **Top-3 סיכונים פתוחים:** (1) KI-010 (high) — חוסם RRR סעיף 5+7, ללא הכרעת-מקור עדיין. (2) Quality Gates שער-5 לא-ירוק במלואו — תלוי בסגירת KI-010+KI-024+הרצת Performance Gate. (3) KI-023 — אין מנגנון-אכיפת-Holdout מרכזי, כל סקריפט עתידי הנוגע ב-`data/ticks/` צריך לבנות הגנה בעצמו.
