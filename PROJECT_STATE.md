# PROJECT STATE — Context Snapshot
**Anchor SHA:** 9db723c3fb690fdad6d2d9dce2e62b771f5bfc63
**Snapshot:** 2026-08-11
**חובת תחזוקה:** מסמך זה הוא שכבת Context בין הכלים, לא Source of
Truth. בכל סתירה מול Git או מסמכי Authority — **מסמך זה מפסיד**;
יש לאמת מחדש מול המקור ולעדכן מסמך זה בהתאם.
**סדר סמכות:** Git/Code → Tests/Evidence → DECISIONS_LOG →
KNOWN_ISSUES / RESEARCH_READINESS_REVIEW → מסמכי ARCHIVAL

## מצב מאומת

| טענה | Authority | סביבת אימות | תאריך |
|---|---|---|---|
| origin/main = 9db723c | Git | כל סביבה עם גישה ל-origin | 2026-08-11 |
| working tree נקי | Git | Windows (מכונת Roy) | 2026-08-11 |
| 170/170 tests | pytest | Windows בלבד | 2026-08-11 |
| קו B-8 מוזג ל-main | Git | כל סביבה | 2026-08-11 |
| docs-preservation = e8a33c3 | Git | כל סביבה | 2026-08-11 |

## פריטים פתוחים

| פריט | Authority | סטטוס |
|---|---|---|
| KI פתוחים/חלקיים | docs/KNOWN_ISSUES.md | ר' מסמך |
| Gates | docs/RESEARCH_READINESS_REVIEW.md | Performance + Documentation לא הוכחו |
| ניקוי ענפים | Git | טרם בוצע |
| היעדר CI | — | טרם נרשם כ-KI |

## Next Action

Performance Gate — הרצת `scripts/diagnostics/run_b8_performance_real_data.py`
מול דאטה אמיתי (`2024-01`…`2024-03`) על מחשב-הבית של Roy, ואחריה בדיקה
פורמלית של Documentation Gate. ר' `docs/RESEARCH_READINESS_REVIEW.md`
שורה 5 לתנאי-הסגירה המדויקים.

## תחולה

מסמך זה תקף רק כל עוד origin/main = 9db723c. אם ה-SHA השתנה — המסמך
מיושן עד עדכון.
