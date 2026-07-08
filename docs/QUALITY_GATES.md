# QUALITY GATES
**מעמד:** Process (D-031). Phase מסומן Completed רק כשכל ששת השערים ירוקים. תוצאות השערים = חלק ב' של דוח סיום ה-Phase. אף שער אינו נבדק "בהצהרה" — לכל סעיף יש פקודת אימות.

## 1. Functional Gate
- [ ] `pytest -q` — כל בדיקות הקבלה של ה-Phase ירוקות (רשימת AT-IDs בדוח).
- [ ] `docs/KNOWN_ISSUES.md` — אפס פריטים פתוחים בחומרה critical/high.
- [ ] ה-Demo רץ מקצה לקצה: `scripts/demo_phaseN.py`.

## 2. Performance Gate
- [ ] Benchmark נמדד ונרשם (זמן ריצה + זיכרון שיא): `scripts/bench_phaseN.py` — הפלט נשמר ב-`benchmarks/`.
- [ ] עמידה בתקציב (טבלה למטה), או סטייה ≤ ‎+20% מה-Baseline הרשום הקודם; כל חריגה = סיבה מתועדת ב-DECISIONS_LOG.
- [ ] אין צוואר בקבוק ידוע שלא נרשם ב-KNOWN_ISSUES עם חומרה.

**תקציבים התחלתיים (D-032 — יכוילו במדידה הראשונה על חומרת היעד):**
| מדד | תקציב |
|---|---|
| Phase 0: המרת 3 שנות Ticks + בניית כל הנרות | ≤ 60 דק' |
| טעינת חודש Parquet | ≤ 5 שנ' |
| Phase 3: בקטסט 3 חודשים, זרוע אחת | ≤ 5 דק' |
| Phase 4: בקטסט 3 שנים × 9 זרועות | ≤ 60 דק' |
| Phase 5: Random Baseline N=1000 | ≤ 30 דק' |
| זיכרון שיא בכל ריצה | ≤ 8GB |

## 3. Code Quality Gate
- [ ] `ruff check src tests` נקי — כולל חוקי Docstrings לממשקים ציבוריים.
- [ ] אפס `TODO(critical)`. **קונבנציה:** כל TODO חייב תיוג — `TODO(critical|minor): ...`; ‏critical חוסם את השער, ‏minor נרשם כחוב טכני ב-Health Report. ‏TODO לא מתויג = כשל שער.
- [ ] אין שכפול קוד מהותי: `pylint --disable=all --enable=duplicate-code src` נקי.
- [ ] כל מודול: Docstring ברמת המודול + Docstring לכל פונקציה/מחלקה ציבורית.

## 4. Architecture Gate
- [ ] `lint-imports` (import-linter) — חוזי השכבות עוברים:
  - שכבות: ‏data ← store ← {structure, fvg, displacement} ← entry ← {risk, execution} ← backtest ← journal.
  - {features, ai, viz, stats, validation, scoring} **אסורים לייבוא על-ידי מודולי המנוע** — אכיפה אוטומטית של חוק-על 9.
  - קונפיג נצרך רק דרך מודלי Pydantic.
- [ ] אפס תלות מעגלית (נאכף באותו כלי).
- [ ] אפס חריגה מ-ARCHITECTURE.md; חריגה מוצדקת = עדכון המסמך + שורת DECISIONS_LOG **לפני** המיזוג.

## 5. Documentation Gate
- [ ] DECISIONS_LOG מעודכן בכל החלטה שהתקבלה ב-Phase.
- [ ] כל מסמך שהושפע עודכן (ARCHITECTURE / PHASE_PLAN / FEATURE_SPEC / RA לפי הצורך; **SPEC לעולם לא** — הוא קפוא).
- [ ] README והוראות ההפעלה משקפים את היכולות החדשות.

## 6. Regression Gate
- [ ] **מלוא** חבילת הבדיקות — כולל כל ה-Phases הקודמים — ירוקה.
- [ ] Prefix-Consistency ירוק (תמידי, מ-Phase 1).
- [ ] Golden Regression (מ-Phase 3): יומן תקופת המדגם זהה ביט-לביט; שינוי מכוון = הסבר + Golden חדש באישור משתמש.

---

## Project Health Report — חלק ג' של דוח הסיום
1. מה הושלם. ‏2. מה נשאר (מול PHASE_PLAN). ‏3. סיכונים פתוחים. ‏4. חוב טכני (`TODO(minor)` + KNOWN_ISSUES בחומרה medium/low). ‏5. המלצות להמשך.
