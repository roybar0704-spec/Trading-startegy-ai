# SPEC V1 — FROZEN
**סטטוס: קפוא. כל שינוי = גרסה חדשה דרך תהליך ניסוי מתועד. רעיונות חדשים → FUTURE_EXPERIMENTS.md**
כל ההגדרות ללונג; שורט = תמונת מראה מלאה.

## 1. יסודות
- נכס: XAUUSD | דאטה: Dukascopy Bid/Ask Ticks בלבד; כל הנרות (1M/5M/4H) נבנים ממנו.
- עוגן 4H: NY-Close — נרות ב-17:00/21:00/01:00/05:00/09:00/13:00 ET.
- מחיר מבנים: Mid. מחיר ביצוע: Bid/Ask.
- סשן: 08:30–10:30 America/New_York (DST אוטומטי). Warm-Up מבני: 90 יום.

## 2. Market Structure
- Swing: Fractal 3 נרות; מאושר רק בסגירת הנר השלישי (`confirmed_at`).
- BOS: סגירת נר מלאה מעבר ל-Swing מאושר. Wick בלבד = Liquidity Sweep (Wick מעבר + סגירה חזרה).
- BOS נמדד מול ה-Fractal המאושר האחרון.
- **מחזור-חיים של ההפניה (הבהרה מפורשת, אושרה במפורש ע"י המשתמש; ר' DECISIONS_LOG D-040/D-042):** BOS שובר את המבנה **באופן סופי** — ה-Swing שנשבר אינו יכול לייצר אירועי BOS/Sweep נוספים; רק Swing מאושר **חדש** מאותו סוג הופך להפניה הבאה. Sweep **אינו** שובר מבנה ואינו מאפס את ההפניה — הוא נחשב אירוע נזילות בלבד; אותו Swing נשאר ההפניה התקפה עד ש-BOS ישבור אותו או Swing חדש יאושר. הבהרה זו אינה משנה התנהגות מיושמת (v1.0 מומש כך מהתחלה) — היא סוגרת פער-ניסוח בטקסט הקפוא, לא Rule חדש.

## 3. HTF Bias — State Machine (4H)
Bullish ← BOS מאושר מעלה | Bearish ← BOS מאושר מטה | Neutral = מצב פתיחה בלבד.
Neutral → אין עסקאות. אין עסקה נגד Bias. היפוך Bias תוך-סשן: פוזיציה פתוחה ממשיכה (תג `bias_flip`), פקודות תלויות בכיוון הישן מבוטלות, Setups חדשים לפי המצב החדש.

## 4. 4H FVG
- תבנית 3 נרות סגורים; ללא מינימום גודל; תקף עד Mitigation 100% (נמדד על Mid, ברזולוציית 1M/Tick); ללא תפוגת זמן.
- דירוג: L1 רגיל | L2 ‎+Displacement | L3 ‎+Displacement+BOS.
- עדיפות בין כמה: BOS → Displacement → רגיל → הקרוב למחיר.
- Displacement: מודל D1 (BodyRatio) כברירת מחדל v1; D1–D5 = רמות ניסוי (Experiment-level), לא פרמטר Walk-Forward.

## 5. TS (Turtle Soup)
כניסה חלקית ל-FVG (‎<100%‎) + נר תגובה 5M שה-Wick שלו לקח Swing 5M מאושר ונסגר בכיוון האזור → `ts_flag`. חיזוק ל-Scoring בלבד; אינו תנאי.

## 6. הטריגר — רצף נעול (קריאה 2)
**Engagement:** מגע Mid ראשון בטווח ה-FVG (מותר לפני החלון).
**R (5M):** ‏(1) `R.low ≤ fvg.top`‏ (2) `R.close > R.open`‏ (3) Wick תחתון קיים; **Pool = R.low**‏ (4) בזמן סגירתו Mitigation < 100%. נר מאוחר העומד בתנאים מחליף את R. נר שנסגר מתחת ל-R.low (Close-Through) → איפוס ל-Zone-Engaged.
**S (5M, אחרי R):** `S.low < R.low` **וגם** `S.close > R.low`. רק אחרי סגירת S מתחילה סריקת iFVG.
**חלון (H1):** סגירת R, סגירת S והכניסה — כולם בתוך 08:30–10:30. Inversion אחרי סוף החלון → אין כניסה (`expired`).

## 7. iFVG
- מועמד: FVG דובי 1M (`c1.low > c3.high`), אזור `[c3.high, c1.low]`, נוצר מ-Engagement ואילך, ללא מינימום גודל.
- Inversion: נר 1M **נסגר** מעל `gap.top`, אחרי סגירת S. Wick-through = כלום.
- נלקח ה-Inversion הראשון; כמה Gaps באותו נר → הנבחר = בעל ה-top הגבוה. קצה הכניסה = `gap.top`.
- פסילה (לפני מילוי): 1M close < `gap.bottom` (Re-Inversion) | Mid < `S.low` | Mitigation 100% | היפוך Bias | סוף חלון/Blackout.
- **אין Re-Arm:** Setup = ניסיון אחד על iFVG אחד. אין iFVG עד סוף חלון → `no_ifvg` (נרשם).

## 8. מודלי כניסה (זרועות)
- **M1:** Limit ב-`gap.top`; בתוקף עד סוף חלון; מילוי כאשר `Ask ≤ limit`.
- **M2:** Market בסגירת נר ה-Inversion.
- **M4:** מגע ב-`gap.top` + נר דחייה 1M שנסגר בכיוון → Market בפתיחת הנר הבא.

**הבהרת סמנטיקה — Reference Entry Price מול Execution Price (אושרה במפורש ע"י המשתמש; ר' DECISIONS_LOG D-045):**
`OrderIntent.price` הוא **Reference Entry Price** — המחיר שעל בסיסו נוצרה כוונת הכניסה — **לא** מחיר הביצוע בפועל, ומאוכלס **תמיד**, בכל מודל כניסה (כולל Market): עבור M1 זהו מחיר ה-Limit (`gap.top`); עבור M2 זהו מחיר סגירת נר ה-Inversion; עבור M4 זהו מחיר `gap.top` (מקום המגע); עבור כל מודל כניסה עתידי — מחיר הייחוס המתאים לו ברגע יצירת הכוונה. מחיר הביצוע בפועל (Execution Price: Spread/Slippage/Gap) נקבע **אך ורק** ע"י FillSimulator בזמן המילוי (§12) ועשוי להיות שונה מה-Reference — זה תקין, ואינו נוגע לשלב אישור העסקה (§9).

## 9. Stop Loss — שלוש היפותזות מוצהרות (זרועות מחקר)
`sl_anchor ∈ {R_body, S_body, S_wick}`:
- R_body = `min(R.open,R.close) − buffer` | S_body = `min(S.open,S.close) − buffer` | S_wick = `S.low − buffer`.
- Buffer: פרמטר מוצהר. `min_stop_distance = k × median_spread(hour)`.
- **גאומטריה:** `entry − SL ≥ min_stop_distance`, אחרת `invalid_geometry`. `entry` = **Reference Entry Price** (`OrderIntent.price`, ר' §8) — RiskEngine בודק גאומטריה מול הערך הזה בלבד, לעולם לא מול מחיר ביצוע בפועל.
- **הבהרה — `median_spread(hour)` חייב להיות Point-in-Time (אושרה במפורש ע"י המשתמש; ר' DECISIONS_LOG D-049):** `median_spread(hour_et)` הנצרך כאן חייב להיגזר **אך ורק** מנתונים שהיו זמינים עד רגע ה-`now` הנוכחי בבקטסט (Rolling/Expanding SpreadReport) — לעולם לא מ-SpreadReport שנבנה על טווח הכולל נתונים עתידיים ביחס לאותו רגע. זו ברירת המחדל היחידה של v1; SpreadReport מסוג אחר (למשל אגרגט על פני כל התקופה) הוא זרוע-מחקר נפרדת בלבד ואינו רשאי לשנות את התנהגות v1.
- Grid מלא: {M1,M2,M4} × {R_body,S_body,S_wick} = 9 תיקים מבודדים על Setup Stream זהה; בתוך מודל כניסה — כניסה זהה לשלוש זרועות ה-SL. ההכרעה — בנתונים (Paired), ואז ננעל כחוק v1.2.

## 10. TP / Sizing / מכסה
- TP: 3R קבוע, סגירה מלאה.
- Sizing: 0.5% מהיתרה **הממומשת** בזמן הפקודה. Dynamic Sizing — כבוי (FE).
- מכסה: 2 **מילויים** ליום NY, לכל תיק בנפרד; פקודה לא ממולאת נרשמת ולא נספרת; כל הפקודות התלויות מתבטלות ב-10:30.
- Setups חמושים במקביל ≤ המכסה שנותרה; עדיפות לפי §4. כניסה חוזרת לאותו אזור אחרי סטופ — מותרת (+תג `same_zone_reentry`).
- **הבהרה — אכיפת מכסה היא פר-תיק, לא פר-Setup (אושרה במפורש ע"י המשתמש; ר' DECISIONS_LOG D-052):** מאחר שהמכסה מוגדרת "לכל תיק בנפרד", הבדיקה "Setups חמושים במקביל ≤ המכסה שנותרה" מתבצעת **בנפרד לכל אחד מ-9 התיקים** ברגע שה-Setup מגיע ל-ARMED — לא כבדיקה גלובלית יחידה על ה-Setup. תיק אחד עשוי להיחסם (`blocked_quota`) עבור Setup נתון בעוד תיק אחר (עם מכסה פנויה) ממשיך בו כרגיל. זו הבהרת-אכיפה בלבד (Journal/Data-Model), **אינה** משנה את חוק המכסה עצמו (2 מילויים/יום/תיק, ללא שינוי).

## 11. חדשות והחזקה
- Blackout: ‎±30 דק' סביב חדשות אדומות USD; אין Setups חדשים ואין פקודות חדשות; פקודות תלויות מתבטלות בתחילת Blackout (`blocked_news`); פוזיציה פתוחה ממשיכה (תג `news_cross`).
- Overnight/Weekend: מותר; תגים `overnight`/`weekend`. ימי חג/חצאי-ימים: תג `thin_liquidity`.
- היומן רושם `effective_window_minutes` לכל יום.

## 12. ביצוע ועלויות
- ספרד: אמיתי מהדאטה (קנייה ב-Ask, מכירה ב-Bid; SL לונג מול Bid, שורט מול Ask).
- Slippage: על יציאות Stop ‎0.10$‎ (×3 בחלון חדשות); Market — פרמטרי; Limit — אפס חיובי.
- רזולוציית מילוי: Ticks; Fallback 1M → SL-First. Gap-Through → מחיר זמין ראשון + Slippage.
- Execution Delay: 0ms ברירת מחדל; ריצות עמידות 250/500ms. Commission: 0 (פרמטרי).

## 13. פרוטוקול מחקר
**עקרונות (החלטות משתמש, קפואים):** תקופה קבועה לכל הזרועות · ≥150 עסקאות סף כשירות להסקה · Walk-Forward · Hold-Out חד-פעמי מופרד פיזית · Random Baseline באותם תנאים · Sensitivity · פונקציית מטרה אחת שננעלת לפני ריצה ראשונה · רישום מלא: כל ריצה = `(config_hash, data_version, code_version)` ב-Experiment Tracker, Append-Only.
**כל הערכים המספריים והמתודולוגיים** של הפרוטוקול (פונקציית המטרה עצמה, ספי Guards, סכמת ה-WF, אורך ה-Hold-Out, מפרט ה-Baseline, מודל העלויות) **אינם חלק מהחוקים הקפואים** — הם Research Assumptions: בחירות התחלתיות המרוכזות ב-`RESEARCH_ASSUMPTIONS_V1.md` (RA-01…RA-23), ניתנות להחלפה בנוהל מתועד בלי לגעת בלוגיקת האסטרטגיה.

## 14. State Machine (מחייב)
SCANNING → ZONE_ENGAGED → REACTION_SEEN → SWEEP_CONFIRMED → AWAITING_IFVG → ARMED → PENDING_ENTRY/WAIT_REJECTION → IN_TRADE → CLOSED.
גארדים גלובליים: Bias-flip / Mitigation-100% / Session-close / Blackout / Quota.
מצבים סופיים: `closed · expired · invalidated · blocked_news · blocked_quota · no_ifvg · invalid_geometry`. כל מעבר מתועד עם timestamp וסיבה. הדיאגרמה המלאה: `trigger_spec_state_machine_v1_1.md` §3.

**הבהרה — שני מפלסי תוצאה (אושרה במפורש ע"י המשתמש; ר' DECISIONS_LOG D-052, Journal/Data-Model בלבד, אינה משנה את ה-State Machine עצמה):** מתוך שבעת המצבים הסופיים, `armed · expired · invalidated · no_ifvg` הם **model-agnostic** — זהים וחלים על ה-Setup כולו, בלתי-תלויים בתיק (הם תוצאה של מנגנון ה-FVG/R/S/iFVG, המשותף ל-9 התיקים). לעומתם `closed · blocked_news · blocked_quota · invalid_geometry` הם **תלויי-תיק במהותם** (Sizing/Quota/גאומטריה נבדקים פר-תיק; RiskEngine.approve כבר מחזיר Rejection פר-תיק מ-Phase 2) — אין להם משמעות כתוצאה יחידה של Setup שלם. `Setup.outcome`/`setups.outcome` (Journal) מכיל **אך ורק** את ארבעת הערכים ה-model-agnostic; התוצאה התלויה-בתיק נשמרת בנפרד, פר-`(setup_id, portfolio_id)`.

## 15. Scoring & AI (v1)
Scoring: Log-Only; רכיבים — רמת FVG, TS, איכות Sweep, טריות Bias; שימוש יחיד — שובר שוויון בין Setups. AI: Analyst בלבד (ניתוח טרום-סשן, תיוג, Insights); אפס השפעה על החלטות.
