# RESEARCH ASSUMPTIONS — Version 1
**הגדרה:** כל ערך מספרי או בחירה מתודולוגית שמקורם בהמלצת Claude ולא בהחלטה ישירה של המשתמש.
**מעמד:** בחירה התחלתית (Initial Choice) — לא אמת מוחלטת. כל סעיף ניתן להחלפה בנוהל שבסוף המסמך, **בלי לגעת בלוגיקת האסטרטגיה** (SPEC_V1_FROZEN).

**לא נכללים כאן (החלטות משתמש, חלק מהחוקים):** סף 150 עסקאות להסקה · Sizing ‏0.5% · TP ‏3R · מכסה 2 מילויים/יום · Blackout ‏±30 דק' · חלון 08:30–10:30 · רצף הטריגר · שלוש זרועות ה-SL כהיפותזות.
**אושרו במפורש ואינם RA:** Mid למבנים · SL-First · Gap-Through שמרני · פתרונות H1–H7.

---

## A. פרוטוקול הסקה סטטיסטית

| ID | הנחה + ערך v1 | נימוק | Config |
|---|---|---|---|
| RA-01 | פונקציית מטרה ראשית: Expectancy(R) מצרפי ב-OOS של ה-Walk-Forward | מדד יחיד, קשור ישירות לרווח ליחידת סיכון; חלופות: Expectancy/MaxDD, PF, t-stat | `run.objective` |
| RA-02 | מובהקות מול Baseline: p < 0.05, Paired Bootstrap | קונבנציה מקובלת; עם ~150 עסקאות אין כוח סטטיסטי לסף מחמיר יותר | `guards.p_vs_baseline_max` |
| RA-03 | Profit Factor מינימלי: 1.3 ב-OOS | מרווח ביטחון מעל 1.0 שיישחק בלייב (עלויות/סליפג' לא צפויים) | `guards.pf_min` |
| RA-04 | רבעון גרוע ביותר: ≥ ‎−15R | חוסם אסטרטגיה שכל רווחיה מתקופה אחת | `guards.worst_quarter_r_min` |
| RA-05 | Walk-Forward: Train ‏9M / Test ‏3M מתגלגל | איזון בין עומק אימון לכמות חלונות OOS; חלופות: 12/3, Anchored-Expanding | `walk_forward` |
| RA-06 | Hold-Out: 6 חודשים אחרונים, נגיעה אחת | גדול מספיק לאימות, קטן מספיק שלא לגזול דאטה | `holdout` |
| RA-07 | Random Baseline: N=1000, seed=42; דגימת מרחקי SL מהתפלגות הזרוע הנבחנת | דגימת המרחקים שומרת הוגנות עלויות-ל-R בין אסטרטגיה לרעש | `baseline` |
| RA-08 | Sensitivity: הפרעה ±20% לשכני Grid | סף שרירותי סביר לזיהוי "רמה" מול "שיא בודד" | — |
| RA-09 | מבחן השוואת זרועות: Paired Bootstrap על Setup Stream זהה | מנצל את העיצוב הזוגי; חלופות: Wilcoxon, t זוגי | — |

## B. מודל עלויות וביצוע

| ID | הנחה + ערך v1 | נימוק | Config |
|---|---|---|---|
| RA-10 | Slippage יציאת Stop: ‏0.70$ (מכויל, B-4/D-074) | **Proxy שמרני, לא מדידה ישירה של Slippage בפועל:** p95 של התפלגות-Spread אמיתית ב-XAUUSD על פני 33 חודשים (2022-10–2025-06, `scripts/diagnostics/run_full_spread_report.py`) — 137,407,787 Ticks אמיתיים. אימות-Slippage ישיר (מדידת מילוי-Stop בפועל, לא Spread) נשאר עבודה עתידית, לא בוצע כאן. | `costs.slippage_stop_usd` |
| RA-11 | מכפיל Slippage בחלון חדשות: ×3 | ספייקים בזהב סביב פרסומים | `costs.news_slip_mult` |
| RA-12 | Slippage כניסת Market: ‏0.05$ | כניסה בשוק רגוע < יציאת Stop | `costs.slippage_market_usd` |
| RA-13 | Commission: ‏0 | תלוי-ברוקר; ייקבע כשיוגדר ברוקר יעד | `costs.commission_per_unit` |
| RA-14 | Execution Delay: ‏0ms + ריצות עמידות 250/500ms | בקטסט נקי + בדיקת שבריריות ללייב | `costs.execution_delay_ms` |

*(הספרד עצמו נמדד מ-Bid/Ask אמיתיים — עובדה, לא הנחה.)*

## C. ספים נומריים ביישום

| ID | הנחה + ערך v1 | נימוק | Config |
|---|---|---|---|
| RA-15 | SL Buffer ברירת מחדל: ‏0.30$ (Grid מוצהר: 0.10–0.50) | נקודת פתיחה; ההכרעה בתוך ה-Grid | `sl_buffer_usd` |
| RA-16 | Min-Stop: ‏k=3 × ספרד חציוני לפי שעה | סטופ קטן מפי-3 ספרד = רעש ביצוע | `min_stop_k_spread` |
| RA-17 | Displacement D1: גוף ≥ ‏1.5× ממוצע 10 נרות | הגדרה מינימלית סבירה; Grid מוצהר | `displacement.d1` |
| RA-18 | Warm-Up מבני: 90 יום | מספיק למבנה 4H בשל; מונע Neutral מלאכותי | `warmup_days` |
| RA-19 | רצועת Tick-on-Demand: ‏1.00$ | מרחק הפעלת רזולוציית Tick סביב SL/TP/גבולות | `tick_on_demand_band_usd` |
| RA-20 | משקולות Scoring: ‏0.4/0.2/0.2/0.2 | Log-Only — סיכון אפס להחלטות ב-v1 | `scoring_weights` |
| RA-28 | הון התחלתי לכל תיק (Portfolio.initial_equity): ‏$10,000 | ערך נוח, עגול, זהה לכל 9 התיקים; **אינו משפיע על איתותים או על תוצאות ב-R** — Sizing הוא אחוזי מהיתרה הממומשת (RA-22), כך שה-R-multiples והתוצאות היחסיות בלתי-תלויים לחלוטין בבחירה זו — משפיע רק על סקאלת ה-$ בדוחות/Drawdown-ב-$. אושר במפורש ע"י המשתמש (ר' DECISIONS_LOG D-056), לאחר עצירה על עמימות אמיתית (הערך לא הוצהר בשום config/RA קודם — כל בדיקות Phase 2/3 השתמשו ב-$10,000 כערך-נוחות בלבד, ללא הצהרה רשמית) | `initial_equity_usd` |
| RA-26 | דיוק Sizing: ללא עיגול (יחידות Float מדויקות, ללא Lot Step) | שלב מחקר בודק את ביצועי האסטרטגיה עצמה, לא מגבלות ברוקר; Lot Step/מגבלות מעבר-ללייב = ניסוי/RA נפרד עתידי, לא חלק מ-v1 (אושר במפורש ע"י המשתמש, ר' DECISIONS_LOG D-044) | `src/risk/sizing.py` (Phase 2) |
| RA-29 | Validator Spike-Detection: spike_z_threshold=12.0 (מכויל, B-6/D-076) | מכויל בניסוי-כיול מבוקר (Grid-Sweep + הצלבה מול דוח-ספרד אמיתי, לא Fixtures) על 3 חודשים אמיתיים ממשטרי-תנודתיות שונים (2022-11 חדשותי, 2024-02 שקט, 2024-11 תנודתי). ב-8.0 (המקורי): 87%-94% מהספייקים המדוגללים קטנים מ-p95-הספרד האמיתי של שעתם (Spread Proxy, לא הוכחה כלכלית ישירה). ב-12.0: יחס move/hr_median>1 בעקביות בשלושת החודשים, עם הפחתה של ~87% בכמות הדגלים שאינם מציגים חריגה ביחס ל-p95-spread-proxy — פחות אגרסיבי מ-14.0. **Scope limitation:** Calibration validated on 3 representative months only. No full 39-month sweep performed. **Method limitation:** Decision based on spread-proxy validation, not direct economic outcome validation; no full False-Negative check performed (no complete ground-truth of real market events). | `config/parameters.yaml::validator.spike_z_threshold` (Config-Wiring מלא, Commit 4 — לא קבוע-קוד) |

## D. הנחות הגדרת נתונים — רגישות מיוחדת

| ID | הנחה + ערך v1 | הערת רגישות |
|---|---|---|
| RA-21 | עוגן נרות 4H: NY-Close (17:00 ET) | ⚠️ **שינוי משנה אילו FVG קיימים בכלל** — החלפה אינה סוויץ' פרמטר אלא Experiment מלא חדש. הוצג ואומץ כי זו הקונבנציה שסוחרי SMC רואים בגרפים |
| RA-22 | בסיס הון ל-Sizing: יתרה ממומשת (ללא PnL צף) | משנה גדלי פוזיציה, לא איתותים; שמרני ושחזורי |
| RA-23 | לוח חדשות: CSV היסטורי, סיווג "אדום", USD בלבד — מקור סופי: **BLS** (ממשלתי, Public Domain, `KI010_DECISION_DOC.md` §2-3). **Phase 1 (B-7/D-077):** CPI + Employment Situation (NFP) בלבד, `2022-10-07`…`2025-06-11` (66 אירועים אמיתיים, 33 חודשים) | ⚠️ **Coverage חלקי מוצהר, לא מלא.** מכסה 2 מתוך 7 סוגי-אירוע High-Impact-USD המוכרים בקונצנזוס-שוק (`KI010_DECISION_DOC.md` §3: NFP, CPI, Core PCE, GDP, FOMC Rate Decision, ISM PMI, Retail Sales — 5 חסרים). `docs/SPEC_V1_FROZEN.md` שורה 67 מגדיר Blackout סביב "חדשות אדומות USD" באופן גנרי, לא מוגבל-לסוג-אירוע — Backtest שירוץ על דאטה זה **לא** יחסום סביב FOMC/GDP/Core PCE/ISM/Retail Sales אמיתיים. Pipeline (Data Contract/Loader/CalendarEngine Integration) מוכח במלואו ואינו תלוי בפער הזה. Open Future Work — לא משויך ל-B-8; קשור ל-D-078 ותנאי-הפקיעה שלו (ר' D-084) |

---

## נוהל החלפת Research Assumption
1. הצעה מנומקת: ערך נוכחי → ערך מוצע → השפעה צפויה.
2. אישור משתמש מפורש.
3. רישום ב-Experiment Tracker: ‏`RA-xx: old → new`, תאריך, נימוק.
4. ה-Experiment הנוכחי נסגר; נפתח Experiment חדש עם ה-RA המעודכן. **אין שינוי RA באמצע Experiment רץ** — ריצות ישנות נשארות תקפות תחת ה-hash שלהן.
5. RA-21 (עוגן 4H): תמיד Experiment מלא חדש, כולל בנייה מחדש של כל המבנים.
