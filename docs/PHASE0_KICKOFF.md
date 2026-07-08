# PHASE 0 — KICKOFF

## דרישות סביבה
- מכונה עם חיבור אינטרנט (הורדת Dukascopy), ‏Python 3.11+, ‏git.
- העתק את כל קבצי החבילה לריפו לפי העץ שב-CLAUDE.md (המסמכים → ‏docs/, הסכימה → ‏db/schema.sql, ‏CLAUDE.md בשורש).

## הפרומפט ל-Claude Code (העתק כלשונו)
```
קרא את CLAUDE.md במלואו ופעל לפיו — כולל תשעת חוקי-העל.
בצע את Phase 0 בלבד, לפי docs/PHASE_PLAN.md, משימות T0.1–T0.6.
לפני כל משימה קרא את docs/SPEC_V1_FROZEN.md ואת docs/ACCEPTANCE_TESTS.md (AT-0.1–AT-0.7).
בכל עמימות — עצור ושאל אותי. אל תניח הנחות.
אל תיגע ב-config/rules_v1.yaml וב-data/holdout/.
בסיום: דוח סיום Phase תלת-חלקי כמוגדר ב-CLAUDE.md (עבודה + Quality Gates + Project Health) + הרצת scripts/demo_phase0.py מולי.
אין להתקדם ל-Phase 1 ללא אישור מפורש שלי.
```

## מה חייב לצאת מ-Phase 0
1. שלוש שנות Ticks (Bid/Ask) + 90 ימי Warm-Up, ב-Parquet חודשי immutable + ‏data_version.
2. דו"ח ולידציה: חורים, סופ"ש, מעברי DST, ‏spikes מדוגללים.
3. נרות 1M/5M/4H בנויים מה-Ticks; עוגן 4H = ‏NY-Close מאומת (AT-0.5).
4. **דו"ח ספרד לפי שעה** — ישמש לכיול RA-10 (Slippage) ול-min_stop; יוצג לאישורך.
5. ‏data/holdout/ (6 חודשים אחרונים) מופרד פיזית + Guard פעיל (AT-0.7).
6. ‏demo_phase0.py רץ ומציג הכל.

## נקודות עצירה צפויות (לגיטימיות)
- זמינות לוח חדשות היסטורי (RA-23) — אם המקור בעייתי, Claude Code יעצור ויציג חלופות.
- אנומליות דאטה חריגות — יוצגו, לא יושתקו.
- כיול RA-10 מול הספרד הנמדד — הצעה תובא אליך, שינוי יירשם ב-Tracker וביומן ההחלטות.
