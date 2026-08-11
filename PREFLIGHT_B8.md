# PREFLIGHT_B8.md — RRR + Quality Gates Closure

**Blocker:** B-8 — סגירת כל הפערים שמונעים מ-`docs/RESEARCH_READINESS_REVIEW.md` להגיע לפסיקת GO/NO-GO סופית ומתועדת (Performance Gate, Golden Regression/KI-024, Documentation Gate, מילוי 9 שורות RRR + הכרעת KI-010/Functional-Gate) — **בלי** להתחיל T3.4 עצמו.
**מבוצע לפי:** `WORK_ORDER_PROTOCOL.md` §1. **מסמך תכנון בלבד — לא בוצע שום שינוי קוד, לא בוצע Commit.**
**מקור סמכות:** Project Gate Audit (B-8, לפני-Preflight זה), `docs/QUALITY_GATES.md`, `docs/RESEARCH_READINESS_REVIEW.md`, `docs/ACCEPTANCE_TESTS.md`, `RRR_COMPLETION_PLAN.md` (מסמך-תכנון קיים מלפני B-4).

---

## א. הנחות מאומתות (הנחה → ראיה)

1. **RRR עצמו הוא 9 שורות פורמליות, לא 3.** נכון לרגע זה: 1✅ 2✅ 3✅ 4✅(עם הסתייגויות) **5❌** 6✅ 7⚠️(GO עם הסתייגויות, B-7/D-077) 8✅ 9❓(לא נענה במפורש). פסיקה כוללת: NO-GO — קובעת שורה 5 בלבד (AND על כל 9).
   ראיה: קריאה מלאה של `docs/RESEARCH_READINESS_REVIEW.md` (9 שורות + פסיקה).

2. **`bash scripts/ci.sh` ירוק במלואו כרגע, בפועל (לא מצוטט):**
   ```
   ruff check: All checks passed!
   pylint duplicate-code: rated 10.00/10
   lint-imports: Contracts: 4 kept, 0 broken.
   pytest -q: 167 passed
   frozen-config integrity: rules_v1.yaml OK (hash תואם)
   ```
   Code-Quality Gate + Architecture Gate + מרכיב-הבדיקות של Functional/Regression Gates — ירוקים בפועל.
   ראיה: הרצת `bash scripts/ci.sh` (הרגע, ב-Audit שקדם ל-Preflight זה).

3. **`scripts/ci.sh` אינו כולל Performance Gate בכלל** — אין קריאה ל-`bench_phaseN.py` בתוכו.
   ראיה: `scripts/ci.sh` (קריאה מלאה).

4. **כל ארבעת קבצי ה-Benchmark (`benchmarks/*.json`) מבוססים דאטה סינתטי, נמדדו לפני שדאטה אמיתי היה קיים בפרויקט (2026-07-08/09/10, לפני Batch 7).** `phase0_bench.json` מצהיר במפורש: *"Must be re-measured against a real 3-year download before this budget is treated as calibrated (D-032)."* `bench_phase1/2/3.py` כולם בנויים על Bars מוחזרים-ידנית (`_quiet_bars()`), לא קוראים מ-`data/ticks/`.
   ראיה: קריאת 4 קבצי `benchmarks/*.json` + `bench_phase0.py`/`bench_phase3.py` (קריאה מלאה).

5. **Golden Regression אינו קיים בריפו בכלל.** `grep -rln "golden" tests/ scripts/` → אפס תוצאות. KI-024 (medium, open) מאשר את הפער.
   ראיה: `grep -rln "golden" tests/ scripts/` (הרצה בפועל, 0 תוצאות); `docs/KNOWN_ISSUES.md` KI-024.

6. **`_canonical_export(db_path) -> str` כבר קיים ומוכח** ב-`tests/test_at3_14_determinism.py:52-66` — SHA256 על סריאליזציה קנונית (CSV-ish, `ORDER BY` PK) של כל 18 טבלאות ה-Journal. כבר מוכח דטרמיניסטי ביט-לביט על התרחיש של D-064 (AT-3.14) ועל תרחיש-9-הזרועות (AT-3.15, פונקציה עצמאית נפרדת).
   ראיה: `tests/test_at3_14_determinism.py:52-66,80`.

7. **`README.md` מיושן בפועל.** שורה 15: "Phase 0: code-complete, data-pending" (הדאטה כבר קיים, 39/39). שורה 16: "Phase 1: in progress" (Phase 1 סגור, Phase 2/3 Green-Conditional). אין אזכור ל-Stage A (B-1…B-7), אין אזכור ל-RRR, אין `demo_phase2/3.py`/`bench_phase2/3.py` ברשימת הפקודות.
   ראיה: קריאה מלאה של `README.md` (49 שורות).

8. **`build_orchestrator(journal=None)` אינו כותב ל-`data/registry/runs.jsonl` בכלל.** `src/backtest/run_builder.py:188-190`: `if journal is not None: ... registry_path=...` — כשה-`journal` הוא `None`, ה-`if` לא מתקיים, שום כתיבה לא מתרחשת.
   ראיה: `src/backtest/run_builder.py:137-206` (קריאה מלאה).

9. **`Orchestrator` תומך `journal=None` באופן מלא, ללא קריסה.** כל מתודות ה-`_record_*`/`_finalize_setup_journal` שומרות `if self.journal is None: return` (או מקבילה) — מאומת ב-`src/backtest/orchestrator.py` (שורות 89, 145-149, 246, 287-288, 306, 322).
   ראיה: `src/backtest/orchestrator.py` (grep על `journal`, 20+ מופעים נבדקו).

10. **`data/ticks/XAUUSD/` ב-Sandbox הזה מכיל חודש אמיתי אחד בלבד — נובמבר 2022 (20MB).** `2024-01`/`02`/`03` (הטווח שאושר ל-Performance Diagnostic) **אינם קיימים כאן**, אך מאומתים-ומתועדים על מחשב-הבית (`BATCH4_CLOSURE_REPORT.md`: 3,059,497 / 2,126,396 / 2,733,576 ticks, checksums).
    ראיה: `find data/ticks/XAUUSD -type f` (הרצה בפועל: רק `2022/11.parquet`+`.sha256`); `BATCH4_CLOSURE_REPORT.md` שורות 25-27.

11. **`2024-01`…`2024-03` הם In-Sample, לא Holdout.** `config/run_default.yaml::holdout = {last_months: 6}` על התקופה `2023-01-01`…`2025-12-31` → Holdout = `2025-07`…`2025-12`. `2024-01`…`2024-03` רחוקים ממנו לגמרי.
    ראיה: `config/run_default.yaml` (קריאה מלאה).

12. **AT-3.10 חסום מבנית עד RRR=GO, לא ניתן לביצוע כחלק מ-B-8.** `docs/PHASE_PLAN.md` שורה 46 (מצוטט מדויק): *"20 עסקאות מדגם מאומתות ידנית... חסום ע"י Research Readiness Review."* 20 העסקאות חייבות לבוא מריצת-T3.4 עצמה (רשומה, אמיתית) — לא מ-Diagnostic.
    ראיה: `docs/PHASE_PLAN.md` שורה 46; `docs/ACCEPTANCE_TESTS.md` AT-3.10.

## ב. הנחות שלא ניתן לאמת מה-Sandbox

1. **זמן-ריצה/Peak-RSS בפועל של ה-Performance-Diagnostic** — לא ניתן למדוד ב-Sandbox (חסר דאטה ל-2024-01..03). ייבדק אך ורק כשהמשתמש ירוץ אותו על מחשב-הבית, מול פקודה מדויקת שתסופק.
   **טיפול:** הסקריפט נכתב ונבדק-מקומית (ייבוא נקי, `--help`, בדיקת-Sanity על נובמבר-2022 אם רלוונטי) ב-Sandbox; ההרצה-המלאה-בפועל והEvidence שלה — על מחשב-הבית, Commit נפרד.

2. **האם קיימת כפילות-קוד ממשית בין `_canonical_export` (AT-3.14) לבין מה שיידרש ל-Golden Regression** — לא ניתן לדעת בוודאות לפני מימוש בפועל. Roy אישר במפורש: פתרון מינימלי קודם (ייבוא/שכפול-מקומי-קטן אם נדרש), ולא Extraction ל-`src/backtest/canonical_export.py` ללא אישור נפרד.
   **טיפול:** אם בזמן המימוש (Commit נפרד, טרם מאושר) תתגלה כפילות ממשית — עצירה והצגה לפני שינוי-מבני, כפי שהוסכם.

## ג. סטיות תיעוד↔קוד שהתגלו

**אין סטיות חדשות בקוד/Interfaces.** הפערים שזוהו (Performance לא-נמדד-על-אמיתי, Golden לא-קיים, README מיושן, RRR חסר-שורות) הם **פערי-סגירה מוכרים ומתועדים מראש** (KI-024, RRR §5 עצמו, `RRR_COMPLETION_PLAN.md`) — לא ממצא חדש/מפתיע. הממצא היחיד שהיה חדש הוא **עמימות-הפרשנות של KI-010 מול Functional Gate** (§QUALITY_GATES.md §1 "0 open ב-high" מול KI-010 `high`/`partially closed`) — טופל כ-Decision Proposal נפרד (D-078, לא שינוי-קוד), הוכרע ע"י Roy: פרשנות A.

## ד. הכרעה

**PROCEED** — הוכרע ע"י Roy, עם הגבולות הבאים (כולם מחייבים, ר' Scope Lock §8 להלן):

### הכרעות-Scope שאושרו

1. **שם:** B-8 — RRR + Quality Gates Closure. הרחבת News Coverage נשארת Follow-up **לא-ממוספר**, מחוץ ל-B-8.
2. **KI-010/Functional Gate:** פרשנות A מוכרעת — `partially closed` (עם הסתייגות מתועדת) אינו נחשב `open` לצורך Functional Gate. **D-078 יתועד ב-`docs/DECISIONS_LOG.md` כחלק מ-B-8 (Commit נפרד, טרם בוצע). `docs/QUALITY_GATES.md` עצמו לא משתנה כטקסט.** B-7 לא נפתח מחדש; KI-010 נשאר `partially closed`.
3. **Performance Diagnostic:** `scripts/diagnostics/run_b8_performance_real_data.py` (חדש) — כתיבה+בדיקות-מקומיות בלבד ב-Sandbox; **ההרצה בפועל על מחשב-הבית של Roy בלבד**, טווח `2024-01`…`2024-03` נעול, `journal=None`, פלט `benchmarks/phase3_bench_real.json` (חדש, לא דורס), אין כתיבה ל-Registry, אין שינוי ל-`bench_phase3.py` הקיים.
4. **Golden Regression:** מתודולוגיה מאושרת — תרחיש D-064, `_canonical_export()` (שימוש/שכפול מינימלי, **לא** Extraction ל-מודול-משותף ללא אישור נפרד), `tests/golden/at3_14_baseline.sha256` + `tests/test_golden_regression.py` חדשים. שינוי-מכוון של ה-Golden בעתיד = אישור מפורש + Commit נפרד.
5. **Documentation Gate:** עדכון `README.md` — Documentation-only, ללא שינוי-סטטוס-טכני מהותי, ללא ערכי-RA חדשים, ללא שכפול KI/D-entry (הפניה בלבד), כולל הוספת 4 שורות-פקודה (`demo_phase2/3.py`, `bench_phase2/3.py`).
6. **RRR:** הכנת טיוטות ל-9 השורות מותרת; **שורה 5 לא תסומן GO סופי לפני שהוכחו בפועל שלושת ה-Gates (Performance/Regression/Documentation)** — במפורש: Code-Quality✅, Functional✅(D-078), Performance/Regression/Documentation — **ממתינים לביצוע בפועל**, לא מוצגים כבוצעו. שורה 9 — ניסוח מבוסס Evidence-קיים-בלבד, לא בדיקה-עתידית כאילו בוצעה.
7. **AT-3.10:** לא מבוצע ב-B-8. סדר: B-8 → RRR=GO → T3.4 → עסקאות → AT-3.10.

### Scope Lock (§8, מחייב לאורך כל B-8)

B-8 **אינו** רשאי: להרחיב News Coverage · לגעת ב-Holdout (`data/holdout/`, יולי-דצמבר 2025) · לשנות `config/rules_v1.yaml` · לשנות אסטרטגיית-מסחר · להתחיל T3.4 · לבצע Refactor שאינו הכרחי ל-Golden Regression (כולל: לא Extraction ל-`canonical_export.py` ללא אישור נפרד) · להכניס שינויים שקטים מעבר ל-Scope המאושר כאן.

**שאר ה-Pre-Flight נקי — אין סתירה מהותית שנותרה.**
