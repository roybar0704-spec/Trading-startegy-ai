# WORK_ORDER_B6_CLOSURE.md — B-6: KI-022 Validator Spike-Sensitivity Controlled Calibration

**סטטוס:** Closed. מקור סמכות: `PREFLIGHT_B6.md`, `WORK_ORDER_B6.md`, `WORK_ORDER_PROTOCOL.md` v1.0 (§3+§4).

---

## 1. סיכום מלא

B-6 ביצע ניסוי-כיול מבוקר (אופציה D: Grid-Sweep + הצלבה מול דוח-הספרד האמיתי, לפי `WORK_ORDER_B6.md`) עבור `Validator.spike_z_threshold`, וחיווט את התוצאה דרך Config — לא כשינוי-קבוע-שקט. בוצע ב-4 קומיטים:

- **Commit 1** (`6e93e18`): `scripts/diagnostics/run_b6_spike_grid_sweep.py` — Grid-Sweep ראשוני (Sandbox, נובמבר-2022 האמיתי).
- **Commit 2** (`8cf2fb1`): `scripts/diagnostics/run_b6_spread_crossref.py` — הצלבה מול דוח-הספרד האמיתי (Sandbox, אותו חודש).
- **Commit 3** (`0da9815`): `docs/RESEARCH_ASSUMPTIONS_V1.md` (RA-29) + `docs/DECISIONS_LOG.md` (D-076) — תיעוד-ההכרעה (8.0→12.0), אחרי הרחבת-אימות למחשב-הבית על 2 חודשים נוספים (2024-02 שקט, 2024-11 תנודתי) שהראתה ממצא עקבי בשלושתם.
- **Commit 4** (`355d18c`): Config-Wiring מלא — `config/parameters.yaml`, `src/config/models.py` (`ValidatorParams`), `src/data/validator.py` (`DEFAULT_SPIKE_Z_THRESHOLD` 8.0→12.0), `scripts/demo_phase0.py` (הזרקה מפורשת), `tests/test_config_models.py`.

תוצאה: KI-022 closed במלואו. KI-008 closed-חלקית (spike_z_threshold בלבד; gap_threshold נשאר Follow-up).

## 2. Evidence מלא

### שלב A — Grid-Sweep (Commit 1, נובמבר-2022 האמיתי)
```
threshold=  8.0  flagged= 2,998  (0.0823%)  median_move=0.2305  p95_move=0.5645
threshold= 10.0  flagged=   973  (0.0267%)  median_move=0.3250  p95_move=0.9405
threshold= 12.0  flagged=   381  (0.0105%)  median_move=0.4400  p95_move=1.3350
threshold= 14.0  flagged=   185  (0.0051%)  median_move=0.5850  p95_move=1.8600
```
(רשת מלאה: 4.0–16.0 — ר' Commit 1 המקורי לפלט המלא. threshold=8.0 תואם בדיוק ל-D-071.)

### שלב B — הצלבה מול דוח-הספרד האמיתי (Commit 2, אותו חודש)
```
  thr   flagged   median_move   move/hr_median   %move<hr_p95   %in_wide_hrs
  8.0     2,998        0.2305           0.5425         93.90%          5.74%
 10.0       973        0.3250           0.7547         83.14%          6.06%
 12.0       381        0.4400           1.0142         62.20%          8.92%
 14.0       185        0.5850           1.3345         37.30%         13.51%
```

### הרחבת-אימות — 2 חודשים נוספים (מחשב-הבית, אותה מתודולוגיה, thresholds 8/10/12/14 בלבד)

| חודש | thr | flagged | median_move | move/hr_median | %move<hr_p95 |
|---|---|---|---|---|---|
| 2024-02 (שקט) | 8.0 | 1,993 | 0.2250 | 0.6875 | 87.16% |
| | 12.0 | 328 | 0.4105 | 1.2773 | 42.68% |
| 2024-11 (תנודתי) | 8.0 | 13,282 | 0.2900 | 0.7354 | 87.28% |
| | 12.0 | 2,738 | 0.4215 | 1.0671 | 60.23% |

**ממצא עקבי בשלושת החודשים:** ב-8.0, 87%-94% מהספייקים המדוגללים קטנים מ-p95-הספרד האמיתי של שעתם. ב-12.0, `move/hr_median>1` בעקביות — לא ארטיפקט-חודש-בודד.

### Config-Wiring (Commit 4) — הוכחת-זרימה מקצה-לקצה
```
$ uv run python scripts/demo_phase0.py --month 2024-03
== frozen config integrity ==
rules_v1.yaml hash: ba14c88a...
validator.spike_z_threshold (from config/parameters.yaml, RA-29): 12.0
```

## 3. פלט בדיקות מלא (לכל קומיט)

`pytest -q`: **149 passed** בכל ארבעת הקומיטים — זהה, אין רגרסיה. `ruff check src tests scripts`: נקי בכל קומיט. Audit מלא (לפני Commit 4) אישר: `Validator(` נבנה ב-8 מקומות בלבד בכל הריפו, ללא נקודת-בנייה נסתרת; `tests/test_at0_3_gap_detection.py` (היחיד שבונה `Validator()` בסוויטת-הבדיקות) מזריק רק `gap_threshold`, לא נוגע ב-`spike_z_threshold` — אפס השפעה על הבדיקות משינוי-הקבוע.

## 4. Acceptance Tests שנוספו/עודכנו

**אין AT חדש** (אין AT פורמלי לזיהוי-Spikes כלל, מאומת ב-Pre-Flight). `tests/test_config_models.py::test_real_config_files_load_cleanly` הורחב ב-Assert אחד (`params.validator.spike_z_threshold.default == 12.0`).

## 5. Known Issues שנסגרו/נפתחו

- **KI-022 — Closed** (D-076, RA-29, Commit `355d18c`).
- **KI-008 — Partially Closed.** `spike_z_threshold` נסגר ונרשם כ-RA-29. **`gap_threshold` נשאר open — Follow-up נפרד, לא נבדק/כויל ב-B-6.**
- **אין KI חדש שנפתח ב-B-6.**

## 6. Decision Records שנוספו

**RA-29** (`docs/RESEARCH_ASSUMPTIONS_V1.md`, סעיף C) + **D-076** (`docs/DECISIONS_LOG.md`) — שניהם נכתבו ב-Commit 3, ללא שינוי נוסף כאן.

## 7. סטטוס: נסגר במלואו

**B-6 Closed במלואו** — כל קריטריוני ה-AC (`WORK_ORDER_B6.md` §5, גזור מהתוכן) מולאו: Grid-Sweep + הצלבה בוצעו (Sandbox+מחשב-הבית, 3 חודשים), Decision Proposal הוצג ואושר לפני כל שינוי, Config-Wiring מלא בוצע (לא קבוע-שקט), RA-29/D-076 נרשמו, KI-022 closed, KI-008 partially-closed בניסוח-מדויק (לא-גורף).

## 8. חריגות והפתעות

1. **Audit (לפני Commit 4) חשף פער אמיתי:** `validate_full_range.py`/`analyze_spikes.py` היו ממשיכים "בשקט" על ברירת-מחדל 8.0 אם `DEFAULT_SPIKE_Z_THRESHOLD` לא היה מתעדכן — בדיוק התבנית ש-KI-008 תיעד מלכתחילה. זה הוביל להכרעה לעדכן גם את הקבוע (לא רק את ה-Config), כדי שלא ייווצר פער-Config-מול-Kod.
2. **Evidence-חוזר על 3 משטרי-תנודתיות (לא רק נובמבר-2022) חיזק משמעותית את אמינות-הממצא** — לא היה מתוכנן-מראש בהיקף כזה ב-Pre-Flight המקורי (שהניח שלב-1 יספיק); ההרחבה בוצעה כי Roy ביקש אימות נוסף לפני נעילה, והתבררה כמחזקת ולא-סותרת.
3. **בחירת-מיקום RA-29 בטבלה שונתה** מ-Draft (סעיף D המוצע) לסעיף C בפועל (עמודת-Config תואמת יותר) — הוסבר ואושר בזמנו.

## 9. Lessons Learned (חובה)

- **LL-1 (מה גילינו):** `spike_z_threshold` לא היה מחווט לשום נתיב-Config כלל (בשונה מ-`costs.slippage_stop_usd`/RA-10) — פער-ארכיטקטורה אמיתי, לא רק פער-תיעוד. Audit מלא (`grep`) הוא הדרך היחידה לוודא-בפועל שאין נקודת-בנייה נסתרת לפני שינוי-קבוע גלובלי.
- **LL-2 (הנחות שאומתו):** RA-08 (עקרון-±20%/רמה-מול-שיא) התאים כתקדים-מתודולוגי טוב לניתוח Grid-Sweep, גם כשלא הוצהר-מראש כחל על כיול-Validator. הצלבה מול דוח-הספרד האמיתי של B-4 (`build_spread_report`) עבדה כפרוקסי-כלכלי סביר ועקבי על פני 3 חודשים שונים.
- **LL-3 (הנחות שהיו שגויות):** ההנחה שחודש-דוגמה אחד (נובמבר-2022) יספיק לכיול-אמין הייתה שגויה-בזהירות-מוצדקת — Roy דרש (ובצדק) הרחבה ל-2 חודשים נוספים לפני נעילה, שחיזקה משמעותית את מהימנות-ההחלטה.
- **LL-4 (עדכוני-מסמכים):** `docs/RESEARCH_ASSUMPTIONS_V1.md` RA-29 (בוצע, Commit 3). `docs/DECISIONS_LOG.md` D-076 (בוצע, Commit 3). `docs/KNOWN_ISSUES.md` KI-022/KI-008 (בוצע, Commit 5 — כאן). **`gap_threshold` הלא-רשום נשאר Follow-up מפורש** (KI-008 עצמו, לא נפתח KI נוסף). `docs/RESEARCH_READINESS_REVIEW.md` — נבדק במפורש ולא עודכן, כי B-6/KI-022 אינו סעיף-RRR פורמלי (אושר מראש, `WORK_ORDER_B6.md` §7).

## 10. DoD Checklist מול `WORK_ORDER_PROTOCOL.md` §4

1. ✅ כל ה-AC מולאו (`WORK_ORDER_B6.md` §5-6).
2. ✅ כל הבדיקות עברו בפועל, פלט אמיתי בלבד — 149/149 בכל קומיט, Raw Evidence בכל שלב.
3. ✅ לא נוספו KI חדשים ללא תיעוד.
4. ✅ Decision Log עודכן (D-076, Commit 3).
5. ✅ Lessons Learned נכתב במלואו (§9).
6. ✅ **`PREFLIGHT_B6.md` נשמר ומצורף לדוח הסיום** — מחויב ל-Git באותו Commit כמו דוח-זה (הוחלט במפורש ע"י Roy, בניגוד למצב-הביניים שהיה ב-B-5).
7. ✅ לא נוצרו סטיות חדשות מה-SPEC/Rules/Architecture.
8. ✅ Self-Review אדוורסרי בוצע: Lookahead — לא רלוונטי (כיול-Validator על דאטה היסטורי, לא לוגיקת-החלטה חיה; `Validator` עצמו לא מוזרק ל-Orchestrator, אומת ב-Audit); Point-in-time — לא רלוונטי (אותו טעם); דטרמיניזם — שלם (אין רנדומיות, `config/parameters.yaml` נטען דטרמיניסטית); Interfaces — לא שונו (רק שדה חדש נוסף ל-`Parameters`, לא נשבר חוזה קיים); סחף ארכיטקטוני — אפס (עוקב אחר דפוס `costs.*`/RA-10 הקיים בדיוק); סיכון-רגרסיה — אפס (149/149 קבוע לכל אורך).
9. ✅ חוב טכני פתוח כ-Follow-up מתועד: `gap_threshold` הלא-רשום (KI-008, low, יעד לא-מוגדר); Sweep-מלא-על-39-חודשים ואימות-Slippage-ישיר (RA-29, מגבלות מוצהרות, יעד עתידי אם יידרש).

**DoD מלא 9/9 — Closed, לא Partially Closed.**

## 11. מדד פרויקט (Project Status)

- **Stage נוכחי:** Stage A.
- **Blockers פתוחים:** B-7 (KI-010).
- **Blockers שנסגרו:** B-1, B-2, B-3, B-4, B-5, **B-6**.
- **Known Issues פתוחים (11):** KI-003, KI-008 (**partially**, gap_threshold בלבד), KI-011, KI-012, KI-013, KI-019, KI-021 (כולם low) · KI-010 (high) · KI-023, KI-024 (medium).
- **Known Issues שנסגרו (14):** KI-001, KI-002, KI-004, KI-005, KI-006, KI-007, KI-009, KI-014, KI-015, KI-016, KI-017, KI-018, KI-020, **KI-022**.
- **RRR:** 6/9 GO — **ללא שינוי כתוצאה מ-B-6** (כמתוכנן, KI-022 מעולם לא היה סעיף פורמלי).
- **Top-3 סיכונים פתוחים:** (1) KI-010 (high) — עדיין חוסם RRR סעיפים 5+7, B-7 טרם החל. (2) Quality Gates שער-5 עדיין לא-ירוק במלואו (תלוי ב-KI-010/KI-024/Performance-Gate, מ-B-5). (3) KI-023 — אין מנגנון-אכיפת-Holdout מרכזי; כל סקריפט עתידי הנוגע ב-`data/ticks/` (כולל B-6, שלא נגע בכלל ב-Holdout) צריך לבנות הגנה בעצמו עד שיטופל.
