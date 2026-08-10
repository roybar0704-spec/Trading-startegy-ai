# RESEARCH READINESS REVIEW — חובה לפני T3.4

**מעמד:** שער חובה, לא הצהרתי (D-037). ריצת בקטסט אמיתית ראשונה (T3.4, PHASE_PLAN.md) וכל עבודה ב-Phase 4–5
אסורות עד שהסקירה הזו הושלמה בפועל והניבה **GO**. בדיקות טכניות ירוקות (pytest/ruff/Quality Gates) **אינן
תחליף** לסקירה הזו — הן תנאי הכרחי אחד מתוכה, לא מספיק.

**נוהל כשל:** אם סעיף כלשהו למטה = NO-GO → עוצרים את הפרויקט לפני T3.4. לא ממשיכים "באופן זמני", לא עוקפים
"רק כדי לבדוק". מפיקים את הדוח הזה במלואו, עם כל סעיף שסומן NO-GO וסיבתו, ומציגים למשתמש לפני כל המשך.

---

## Checklist (למלא בכל הרצה של הסקירה)

| # | סעיף | דרוש להיות GO | עדות/הפניה |
|---|---|---|---|
| 1 | **KI-001 נסגר?** (חסימת רשת ל-Dukascopy) | גישת רשת אמיתית קיימת; `DukascopyDownloader` הורץ בפועל מול `datafeed.dukascopy.com` והביא דאטה אמיתי | הפניה ל-KNOWN_ISSUES.md, סטטוס KI-001 |
| 2 | **KI-002 נסגר?** (סקאלת `point_value` ל-XAUUSD לא מאומתת) | `point_value` אומת מול דאטה אמיתי (למשל: מחיר Bid/Ask גולמי מפוענח נופל בטווח סביר ליום מסחר ידוע ב-XAUUSD) | הפניה ל-KNOWN_ISSUES.md, סטטוס KI-002 |
| 3 | **RA-10 כויל?** (Slippage-Stop) — ✅ **GO** (B-4, D-074) | דו"ח ספרד **אמיתי** (לא סינתטי) הופק ל-3 שנות הדאטה; RA-10 עודכן או אושר מחדש מול המדידה, ונרשם ב-RESEARCH_ASSUMPTIONS_V1.md + DECISIONS_LOG לפי הנוהל שם | `scripts/diagnostics/run_full_spread_report.py`, D-074, `docs/RESEARCH_ASSUMPTIONS_V1.md` RA-10. **הבהרה מוצהרת:** הדו"ח כיסה `2022-10-01`…`2025-06-30` (33/39 חודשים) — **לא** את מלוא 39 החודשים; יולי-דצמבר 2025 הוחרגו במכוון כחלון-Holdout (D-073), לא נמדדו לצורך RA-10. `costs.slippage_stop_usd`: `0.10`→`0.70` (p95-Spread, Proxy — לא מדידת-Slippage ישירה, ר' D-074). |
| 4 | **נתוני Dukascopy אומתו?** — ✅ **GO with explicit limitations documented** (B-5, D-075) | AT-0.1/AT-0.2/AT-0.6/AT-0.7 (ומומלץ גם AT-0.3–0.5) הורצו **מול הדאטה האמיתי בפועל**, לא רק מול Fixtures סינתטיים; 3 שנות דאטה + 90 יום Warm-Up נקיים לפי הגדרת T0.4 | `scripts/diagnostics/run_at0_real_data_checks.py` (AT-0.1/0.4/0.6, Sandbox, נובמבר-2022 האמיתי — 3,641,776 ticks, 29,929/29,929 ברים תואמים), `scripts/diagnostics/run_at0_7_holdout_mechanism_check.py` (AT-0.7, בדיקת-מנגנון על עותק-דאטה-אמיתי — **לא** הפרדה-פיזית, ר' KI-023), `scripts/diagnostics/run_at0_2_cache_check.py` (AT-0.2, מחשב-הבית, `data/raw/` אמיתי — PASS אושר ע"י Roy). D-075. **הבהרות מוצהרות:** (א) הכיסוי הוא **חודש-דוגמה אמיתי אחד** (נובמבר 2022, המאומת-כבר ב-D-070/D-072) לכל AT-0.1/0.4/0.6/0.7 — לא הורץ כ-AT פורמלי על פני כל 39 החודשים; "3 שנות דאטה נקיות" מכוסה בנפרד ע"י אימות-Spike/Gap שבוצע לכל אחד מ-39 החודשים בפועל בזמן ה-Backfill (Batch 1-7 Closure Reports). (ב) AT-0.7 הוא **בדיקת-מנגנון בלבד** — Holdout הפיזי (יולי-דצמבר 2025) עדיין לא הופרד בפועל, ר' KI-023. (ג) AT-0.3 מכוסה ע"י D-071 (לא Gate); AT-0.5 מסומן N/A (ללא-תלות-בדאטה, לא Gate). |
| 5 | **Quality Gates עדיין ירוקים?** — ❌ **NO-GO (עדכון: B-8, D-079/D-080)** | כל ששת השערים (QUALITY_GATES.md) ירוקים על מצב הריפו הנוכחי, כולל Regression על Phase 0–2 | `bash scripts/ci.sh` (Sandbox, HEAD=`40df439`): Code-Quality ✅, Architecture ✅, Functional **✅ GO** (pytest 170/170; KI-010 high/partially-closed אינו נחשב open לצורך Functional Gate — הכרעה מפורשת, D-078), Regression **✅ GO** (pytest+Prefix-Consistency ✅; Golden Regression **קיים ועובר** — `tests/test_golden_regression.py`, KI-024 closed, מאומת גם תחת TZ=Asia/Jerusalem, ר' D-080), Performance **עדיין לא נמדד מול דאטה אמיתית** (Diagnostic script קיים — B-8 Commit 2 — אך טרם הורץ בפועל על 2024-01..03), Documentation **עדיין לא נבדק פורמלית**. **שער 5 אינו GO** — שני תת-סעיפים בלבד נותרו פתוחים: Performance (הרצה-בפועל) ו-Documentation (בדיקה פורמלית). Functional ו-Regression כבר GO. |
| 6 | **KI-007 נסגר?** (Point-in-Time SpreadReport, D-049) | `SpreadReport` המוזרק לריצה אמיתית הוא Rolling/Expanding בפועל — נבדק שאין שימוש ב-SpreadReport שמכיל נתונים עתידיים ביחס לכל נקודת-זמן בבקטסט | הפניה ל-KNOWN_ISSUES.md, סטטוס KI-007 + בדיקה ייעודית |
| 7 | **KI-010 נסגר?** (לוח חדשות אמיתי, RA-23) — ⚠️ **GO with explicit limitations documented (B-7, D-077)** | לוח חדשות אמיתי (CSV, אדום, USD) אותר ואומת; `CalendarEngine` הורץ מולו בפועל, לא רק מול Fixture סינתטי | `src/data/news_loader.py`, `data/news/bls_calendar.csv` (BLS, 66 אירועים אמיתיים), D-077, RA-23. **הבהרה מוצהרת:** ה-GO מתייחס ל-**Pipeline** (Data Contract/Loader/CalendarEngine Integration מוכחים במלואם מול דאטה אמיתי) ול-**Phase 1 בלבד** — CPI + Employment Situation (NFP), 2 מתוך 7 סוגי-אירוע High-Impact-USD מוכרים (`KI010_DECISION_DOC.md` §3). **אינו** Coverage מלא של כל "חדשות אדומות USD" לפי `docs/SPEC_V1_FROZEN.md` שורה 67 — Core PCE/GDP/FOMC Rate Decision/ISM PMI/Retail Sales עדיין לא מכוסים; Backtest על דאטה זה לא יחסום סביבם. Follow-up: B-8. |
| 8 | **KI-006 נסגר?** (`Portfolio.apply_realized_pnl` מחווט) | `Orchestrator`/Journal flow קורא בפועל ל-`apply_realized_pnl` בכל סגירת עסקה; Sizing מריצה אמיתית משתמש בהון ממומש-בפועל, לא רק בהון ההתחלתי | הפניה ל-KNOWN_ISSUES.md, סטטוס KI-006 + בדיקה ייעודית |
| 9 | **סיבה כלשהי שלא להתחיל Backtesting אמיתי?** | בדיקה פתוחה: אנומליות דאטה לא-פתורות, חריגה מהחלטות RA-01–09, שינוי לא-מתועד ב-Rules/RA, כל דגל אדום אחר | שיפוט מפורש, לא רק "אין" כברירת מחדל |

## פסיקה

**GO** רק אם **כל תשעת** הסעיפים GO. סעיף אחד NO-GO ⇒ הפסיקה הכוללת NO-GO.

## תוצר

- **GO:** מתועד כאן (תאריך + חתימת-הרצה config_hash/data_version/code_version) ונרשם ב-DECISIONS_LOG; T3.4 יכול להתחיל.
- **NO-GO:** דוח מפורט לפי הטבלה למעלה — כל סעיף שנכשל, למה, ומה התנאי המדויק לסגירתו — מוצג למשתמש. הפרויקט
  עוצר לפני T3.4 עד שהתנאים נסגרים ומתבצעת סקירה חוזרת.
