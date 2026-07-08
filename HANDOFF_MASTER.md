# HANDOFF MASTER — XAUUSD Research Platform
**סגירת תכנון רשמית: 2026-07-08 | Spec: V1 Frozen | נקודת התחלה: Phase 0 בלבד**
חבילה זו (17 קבצים) = **מקור האמת היחיד**. כל מסמך, טיוטה או גרסה מחוץ לחבילה — Superseded. אין צורך בהיסטוריית השיחות.

---

## 1. מפת הקבצים — מה כל קובץ ולאן הוא הולך בריפו

| קובץ | מיקום בריפו | תפקיד |
|---|---|---|
| CLAUDE.md | שורש | **חוקת העבודה** — 10 חוקי-על + כללי הנדסה + עץ ריפו + דוח סיום Phase |
| HANDOFF_MASTER.md | שורש | המסמך הזה — אינדקס-על |
| SPEC_V1_FROZEN.md | docs/ | **חוקי האסטרטגיה** — קפוא |
| trigger_spec_state_machine_v1_1.md | docs/ | פירוט הטריגר המלא + דיאגרמת ה-State Machine — חלק מה-Spec (SPEC §14 מפנה אליו), קפוא |
| ARCHITECTURE.md | docs/ | שכבות, מודולים, לולאת האירועים הדו-שלבית, עיצוב 9 הזרועות |
| INTERFACES.md | docs/ | חוזי המודולים — חתימות מחייבות |
| PHASE_PLAN.md | docs/ | Phases 0–6: משימות, שערים, תוצרי עבודה (Demo לכל שלב) |
| ACCEPTANCE_TESTS.md | docs/ | AT-0.1 … AT-6.2 — הגדרת "עובד" לכל משימה |
| QUALITY_GATES.md | docs/ | ששת שערי האיכות + תקציבי ביצועים + Health Report |
| KNOWN_ISSUES.md | docs/ | מעקב תקלות — תנאי ה-Functional Gate |
| RESEARCH_ASSUMPTIONS_V1.md | docs/ | RA-01…RA-23 — בחירות מחקריות התחלתיות + נוהל החלפה |
| FEATURE_SPEC_V1.md | docs/ | ה-Feature Store: Snapshots, Registry, EAV, מיפוי כל ה-Features |
| DECISIONS_LOG.md | docs/ | D-001…D-033 — היסטוריית כל ההחלטות; Append-Only |
| FUTURE_EXPERIMENTS.md | docs/ | FE-01…FE-15 — רשימת החניה לרעיונות; Append-Only |
| CONFIG_SCHEMA.md | docs/ | תוכן שלושת קבצי ה-YAML (rules/parameters/run) + סכימת Pydantic |
| db_schema.sql | db/schema.sql | DDL מלא ל-DuckDB כולל Feature Store |
| PHASE0_KICKOFF.md | docs/ | **נקודת ההתחלה** — הפרומפט המדויק, התוצרים, נקודות העצירה |

## 2. סדר קריאה ל-Claude Code
**קריאת עומק (חובה לפני משימה ראשונה):** ‏1) CLAUDE.md ‏2) SPEC_V1_FROZEN ‏3) trigger_spec_state_machine ‏4) ARCHITECTURE ‏5) INTERFACES ‏6) PHASE_PLAN ‏7) ACCEPTANCE_TESTS (‏AT-0.*) ‏8) QUALITY_GATES.
**עיון לפי צורך:** RESEARCH_ASSUMPTIONS · FEATURE_SPEC · CONFIG_SCHEMA · db_schema · DECISIONS_LOG · FUTURE_EXPERIMENTS · KNOWN_ISSUES.
**אחרון:** PHASE0_KICKOFF — ומתחילים.

## 3. נקודת ההתחלה המדויקת
**Phase 0 בלבד** — משימות T0.1–T0.6 שב-PHASE_PLAN, בדיקות AT-0.1–AT-0.7. הפרומפט להדבקה: PHASE0_KICKOFF.md. אין מעבר ל-Phase 1 ללא דוח תלת-חלקי + אישור משתמש מפורש.

## 4. החוקים המחייבים את Claude Code (תמצית — הנוסח המחייב: CLAUDE.md)
1. ‏SPEC = חוק; אין להוסיף/לשנות/לפרש חוקי אסטרטגיה. ‏2. עמימות = עצירה ושאלה; אפס הנחות. ‏3. זוהתה הטיה (Lookahead/Snooping/סטטיסטית) = עצירה, הסבר, חלופות. ‏4. רעיון חדש → FUTURE_EXPERIMENTS בלבד. ‏5. עבודה לפי Phases; שערים לפני מעבר. ‏6. שני סוגי אמת: Rules קפואים / RA ניתנות להחלפה בנוהל בלבד. ‏7. Working Software — כל Phase מסתיים בתוצר ניתן להדגמה. ‏8. Stability — אין Refactor למודול מאושר בלי תיעוד מראש + AT מחדש. ‏9. Feature Store תיאורי בלבד; לעולם לא מזין החלטות. ‏10. ‏Quality Gates נבדקים בפקודות, לא בהצהרות.
**כללי הנדסה:** גישה לנתונים רק דרך ‏MarketContext.as_of · עיבוד דו-שלבי לכל timestamp · ‏UTC פנימי · ‏Mid למבנים, Bid/Ask לביצוע · ‏SL-First בהיעדר Ticks · דטרמיניזם מלא (hash+seed) · **אסור לגעת:** ‏config/rules_v1.yaml, ‏data/holdout/, אופטימיזציה מחוץ ל-Grid המוצהר.

## 5. מעמד המסמכים

**קפואים (אסור לשנות):**
- SPEC_V1_FROZEN.md · trigger_spec_state_machine_v1_1.md · ‏config/rules_v1.yaml (משייווצר) — שינוי = גרסת Spec חדשה בהחלטת משתמש בלבד.

**Append-Only (מוסיפים, לא משכתבים):**
- DECISIONS_LOG.md · FUTURE_EXPERIMENTS.md · KNOWN_ISSUES.md (שינוי סטטוס מותר, מחיקה אסורה).

**ניתנים לעדכון — בתנאים:**
- ARCHITECTURE / PHASE_PLAN / ACCEPTANCE_TESTS / INTERFACES / FEATURE_SPEC / QUALITY_GATES — באישור משתמש + שורת DECISIONS_LOG (Documentation Gate).
- RESEARCH_ASSUMPTIONS_V1 — אך ורק בנוהל ההחלפה שבתוכו; לעולם לא באמצע Experiment.
- config/parameters.yaml, run_default.yaml — בתוך ה-Grids המוצהרים בלבד.
- README, benchmarks, קוד — שוטף, תחת השערים.

## 6. Checklist לפני תחילת העבודה
- [ ] כל 17 הקבצים במקומם לפי טבלת סעיף 1; ‏`git init` + קומיט ראשון.
- [ ] סביבה: ‏Python 3.11+, חיבור אינטרנט (Dukascopy), התקנת תלויות.
- [ ] קריאת העומק (סעיף 2) הושלמה.
- [ ] שלושת קבצי ה-YAML נוצרו **כלשונם** מ-CONFIG_SCHEMA.md (חלק מ-T0.1).
- [ ] `pytest -q` ו-`ruff check` רצים נקי על השלד.
- [ ] אושר: אין נגיעה ב-rules_v1.yaml וב-data/holdout/.

## 7. Checklist סיום כל Phase
- [ ] כל ה-AT של ה-Phase ירוקות + ‏Regression מלא (כל ה-Phases הקודמים).
- [ ] Demo הודגם: ‏`scripts/demo_phaseN.py`.
- [ ] ששת ה-Quality Gates ירוקים — כל אחד בפקודת האימות שלו.
- [ ] DECISIONS_LOG + כל מסמך מושפע עודכנו; ‏KNOWN_ISSUES ללא critical/high פתוחים.
- [ ] דוח סיום תלת-חלקי הוגש: עבודה · Quality Gates · Project Health.
- [ ] התקבל אישור משתמש מפורש. **רק אז** — Phase הבא.

## 8. סיכונים ידועים בכניסה לפיתוח
1. **Volume = Tick/Quote proxy** (זהב OTC) — משפיע על מודל D2 ועל volume-features; מגבלה מתועדת בכל דו"ח.
2. **זמינות לוח חדשות היסטורי (RA-23)** — ייבחן ב-Phase 0; עצירה לגיטימית אם המקור בעייתי.
3. **צביר חדשות 08:30 (H5)** — מכווץ את החלון האפקטיבי בימי NFP/CPI; ‏effective_window_minutes נרשם — לכייל ציפיות כמות עסקאות.
4. **מדגם קטן** — ‏150 עסקאות × 9 זרועות; מנוהל ע"י עיצוב זוגי + מטרה נעולה + Hold-Out, אך נשאר הסיכון המחקרי המרכזי.
5. **RA-10 (Slippage) לא מכויל** עד דו"ח הספרד של Phase 0.
6. **תקציבי ביצועים (D-032) לא מכוילים** עד המדידה הראשונה על חומרת היעד.
7. **שבע הגדרות Feature בסטטוס proposed (D-029)** — נדרש אישור משתמש לפני Phase 4.
8. **מעברי DST** — מכוסים ב-AT-0.4, נשארים אזור רגישות.
9. **פער בקטסט-לייב** — מנוהל ע"י עלויות ריאליות, שמרנות מילוי וריצות Delay ‏250/500ms; לא ניתן לאיפוס מלא.
10. **תוצאת BE בלתי-אפשרית תחת חוקי v1** — שדה שמור ל-FE-11; אינו באג.

## 9. Research Assumptions — תמצית (הנוסח המחייב + נוהל ההחלפה: RESEARCH_ASSUMPTIONS_V1.md)
**A. הסקה (RA-01–09):** מטרה = ‏Expectancy(R) ב-OOS · ‏p<0.05 מול Baseline (Paired Bootstrap) · ‏PF≥1.3 · רבעון גרוע ≥ ‎−15R · ‏WF ‏9M/3M · ‏Hold-Out ‏6 חודשים, נגיעה אחת · ‏Baseline ‏N=1000 עם דגימת מרחקי SL · ‏Sensitivity ‏±20% · השוואה זוגית.
**B. עלויות (RA-10–14):** ‏Slippage-Stop ‏0.10$ (×3 בחדשות) · ‏Market ‏0.05$ · עמלה 0 · ‏Delay ‏0ms + עמידות 250/500.
**C. ספים (RA-15–20):** ‏Buffer ‏0.30$ · ‏Min-Stop ‏k=3×ספרד · ‏D1 ‏1.5×avg-10 · ‏Warm-Up ‏90 יום · רצועת Tick ‏1.00$ · משקולות Scoring.
**D. נתונים (RA-21–23):** ⚠️ **עוגן 4H = NY-Close — החלפתו = Experiment מלא חדש** · בסיס הון = יתרה ממומשת · לוח חדשות = CSV "אדום" USD.

---
**סטטוס: שלב התכנון סגור. D-001–D-033 מתועדים. השלב הבא — Claude Code, Phase 0, לפי PHASE0_KICKOFF.md.**
