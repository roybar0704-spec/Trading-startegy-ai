# ACCEPTANCE TESTS
פורמט: Given / When / Then. כל בדיקה = pytest אוטומטי אלא אם סומן [ידני].

## Phase 0
- **AT-0.1 Download integrity:** יום ידוע → מספר Ticks > 0, Bid ≤ Ask בכל שורה, זמנים מונוטוניים.
- **AT-0.2 Cache immutability:** הורדה חוזרת אינה משנה קבצים; `data_version` יציב.
- **AT-0.3 Gap detection:** פיד עם חור מלאכותי של 7 דקות → מדוגלל; סופ"ש → לא מדוגלל.
- **AT-0.4 DST build:** שבוע מעבר מרץ + נובמבר → נר 08:30 ET קיים ורציף; אפס נרות כפולים/חסרים סביב המעבר.
- **AT-0.5 4H anchor:** גבולות נרות = 17/21/01/05/09/13 ET בדיוק, גם בחורף וגם בקיץ.
- **AT-0.6 Bar↔Tick consistency:** OHLC של נר 1M = min/max/first/last של ה-Ticks (Mid) שלו.
- **AT-0.7 Holdout isolation:** טעינת טווח החופף ל-holdout ללא דגל → חריגה; עם דגל → נרשם ב-Tracker.

## Phase 1
- **AT-1.1 Fractal timing:** Fixture סינתטי → Swing מזוהה עם `confirmed_at` = סגירת נר 3; שאילתת as_of לפני כן לא מחזירה אותו.
- **AT-1.2 BOS vs Sweep:** סגירה מעבר → BOS; Wick מעבר + סגירה חזרה → Sweep, לא BOS.
- **AT-1.3 Bias transitions:** רצף BOS מעורב → היסטוריית מצבים תואמת טבלת המעברים; מצב פתיחה Neutral.
- **AT-1.4 FVG lifecycle:** יצירה רק על 3 נרות סגורים; `mitigation_pct` מתעדכן על 1M; 100% → invalidated.
- **AT-1.5 Ranking:** Fixture עם Displacement+BOS → L3; עדיפות §4 נבחרת נכון בין 3 FVG.
- **AT-1.6 Prefix-Consistency:** ריצה על Fixture דו-שבועי מלא מול ריצות קטומות בכל שעה → יומן החלטות זהה עד נקודת הקטיעה. **חובה ב-CI לתמיד.**

## Phase 2
- **AT-2.1 Limit fill:** קניית Limit ב-P → מילוי רק כאשר Ask ≤ P, במחיר P.
- **AT-2.2 SL sides:** SL לונג נבחן מול Bid; שורט מול Ask (Fixture ספרד רחב מוכיח).
- **AT-2.3 SL-First fallback:** נר 1M שנוגע SL+TP ללא Ticks → SL.
- **AT-2.4 Gap-Through:** פער מעל SL → מילוי במחיר הזמין הראשון + Slippage; לעולם לא במחיר SL.
- **AT-2.5 Sizing:** הון 10,000, סטופ 2.00$ → 25 יח' (0.5% = 50$); מבוסס יתרה ממומשת בלבד.
- **AT-2.6 Geometry:** entry−SL < min_stop → `invalid_geometry`, אין פקודה.
- **AT-2.7 Quota:** מילוי שלישי באותו יום NY נחסם; פקודה שלא מולאה לא נספרת אך נרשמת.
- **AT-2.8 Execution Delay (D-050):** `execution_delay_ms=0` (ברירת מחדל) → מילוי זהה בדיוק להתנהגות ללא Delay. `execution_delay_ms>0` → מילוי (כניסה/יציאה) לא מתרחש עד שחלף ה-Delay מרגע שהתנאי התקיים לראשונה; המחיר נשאר מעוגן ל-`order.price`/`sl`/`tp` (D-018), אך עלויות תלויות-זמן (חדשות) מחושבות לפי זמן הביצוע בפועל, לא זמן ה-Trigger.

## Phase 3
- **AT-3.1 R rules:** ארבעה Fixtures — חסר Wick / גוף דובי / לא נגע ב-FVG / תקין → רק התקין = R.
- **AT-3.2 R replacement + reset:** מועמד R חדש מחליף; נר Close-Through מתחת R.low → חזרה ל-ZONE_ENGAGED.
- **AT-3.3 S rules:** low<R.low בלי close>R.low → לא Sweep; שניהם → SWEEP_CONFIRMED.
- **AT-3.4 iFVG:** Inversion בסגירה בלבד (Wick-through לא); לפני סגירת S לא נספר; ראשון נבחר; Multi-gap → top הגבוה.
- **AT-3.5 פסילות:** Re-Inversion / שבירת S.low / Mitigation-100% / Bias-flip / Blackout → מצב סופי נכון ב-`setups.outcome` (model-agnostic) **וגם** קסקדה נכונה ל-`setup_arm_outcomes` (D-052): כל תיק עם פקודה תלויה-לא-ממומשת מקבל `invalidated`/`blocked_news` בשורה שלו + ביטול הפקודה בפועל.
- **AT-3.6 H1:** R לפני 08:30 או Inversion אחרי 10:30 → אין כניסה (`expired`), גם אם השאר תקין.
- **AT-3.7 Race 09:00:** Fixture עם סגירת 1M+5M+4H סימולטנית → עיבוד דו-שלבי; החלטה על מצב מעודכן; דטרמיניסטי בריצות חוזרות. **סדר Stage 1 מפורש (D-063):** לחותמת-זמן משותפת, סדר העיבוד הוא 1M→5M→4H בדיוק (לא רק "סדר קבוע כלשהו") — מוודא ב-`tests/test_h2_merge_order.py` ישירות על `_merged_timeline()`.
- **AT-3.8 no_ifvg:** רצף מלא בלי אף FVG דובי 1M → `no_ifvg` ביומן.
- **AT-3.9 Blackout cancel:** Limit תלוי בתחילת Blackout → מבוטל `blocked_news`.
- **AT-3.10 [ידני] אימות 20 עסקאות:** דפי Viz מול היומן מול הגרף — המשתמש מאשר שהלוגיקה = הכוונה. **שער חובה.**
- **AT-3.11 Per-arm quota admission (D-052):** Setup מגיע ל-ARMED; תיק A במכסה מלאה (2 מילויים היום), תיק B פנוי → `setup_arm_outcomes` מראה `blocked_quota` לתיק A ו-`pending`/המשך רגיל לתיק B, על אותה שורת `setups` בדיוק (`setups.outcome` נשאר `armed`, לא מושפע). מוודא ששני התיקים עצמאיים לחלוטין — אין דליפת חסימה בין תיקים.
- **AT-3.12 median_spread Point-in-Time (D-049, סוגר KI-007):** `ExpandingSpreadReport.median_spread(hour_et)` בכל רגע `t` תלוי אך ורק ב-Ticks שהוזנו ל-`update()` עד `t` — הזנת Ticks נוספים "בעתיד" (אחרי `t`) לא משנה את הערך שכבר הוחזר ב-`t` (בדיקת אי-תלות-בסדר-עתידי, ברמת יחידה). ברמת Orchestrator: `_apply_tick` מזין את ה-Tracker **לפני** שכל בקשת `median_spread` לאותו timestamp נענית (Stage 1 לפני Stage 2); הזרקת Tick עם ספרד קיצוני **אחרי** רגע ה-ARM של Setup לא משפיעה על תוצאת ה-Geometry Check שכבר בוצעה עבורו. שעה (`hour_et`) ללא תצפיות עדיין → `KeyError` (אנומליה גלויה, לא ברירת מחדל שקטה).
- **AT-3.13 Context Snapshots + Trade Page (T3.6/T3.5, D-058/D-059/D-060):** ריצה מלאה מקצה-לקצה עם `DuckDBJournal` אמיתי (לא `journal=None`) — `setups`/`experiments`/`runs`/`portfolios`/`orders`/`setup_arm_outcomes`/`trades`/`context_snapshots` כולן נכתבות ללא הפרת FK. ארבע קינדי ה-Snapshot (`engagement`/`armed`/`entry`/`exit`) נוצרות לפי סדר הזמן הנכון; `order_id` הוא `NULL` ל-engagement/armed ומאוכלס ל-entry/exit; ה-Payload של `armed` משקף אך ורק מה שהיה ידוע ברגע ה-Arm (לא R/S/iFVG "מהעתיד" בעת engagement). `build_trade_page` בונה `Figure` עם נרות + אזור FVG + אזור iFVG + הדגשת R/S + קווי entry/SL/TP + סמני כניסה/יציאה, קורא אך ורק מה-Journal + Bars חיצוניים (D-037, לא ממצב-מנוע חי).
- **AT-3.14 דטרמיניזם דו-ריצתי (Stage A / B-1, D-067, סוגר KI-018; Scoped pull-forward של AT-5.3):** שתי ריצות זהות מאפס (state משותף אפס) על ה-fixture המלא של D-064 (`tests/test_full_pipeline_from_raw_4h_bars.py::_scenario`), עם אותו `RunIdentity` (כולל `code_version` override קבוע לטסטים) — ייצוא קנוני (SHA256 על `SELECT * FROM <table> ORDER BY <PK>` לכל אחת מ-18 הטבלאות המוצהרות ב-Journal schema, ללא עמודות שעון-קיר — אף לא אחת נדרשה, ר' `PREFLIGHT_B1.md` §א/A10) זהה בין שתי הריצות. שורת `runs`: אין "unknown" באף שדה; `config_hash == config_hash(rules, parameters, run_config, data_version, code_version)` המחושב-מחדש באופן עצמאי (לא רק "לא unknown"); `seed IS NULL`. רשומת `data/registry/runs.jsonl` קיימת בכל ריצה, נפרסת תקין, ותואמת את שורת `runs`. מוודא בפועל, לא בהנחה, את CLAUDE.md ("אותו `(config_hash, data_version, code_version)` → אותו יומן, ביט-לביט") דרך החיווט האמיתי (D-064), לא ב-Mock. `tests/test_at3_14_determinism.py`.
- **AT-3.15 דטרמיניזם דו-ריצתי, Multi-Arm מלא (Stage A / B-2, סוגר חלק מ-KI-015):** שתי ריצות זהות-מאפס על תרחיש 9-הזרועות של D-062 (`tests/test_full_pipeline_9_arms.py::_scenario`, מיובא ולא-משוכפל) — שלוש זרועות ממלאות (אחת לכל מודל-כניסה), שש נשארות לא-מושפעות — מפיקות ייצוא קנוני זהה (SHA256, פונקציה מקומית עצמאית, לא ייבוא חוצה-קובץ מ-AT-3.14) של כל 18 טבלאות ה-Journal. מרחיב את AT-3.14 (B-1, תרחיש חד-מילוי) לתרחיש-ריבוי אמיתי, כולל אימות ש-counters לפי-מופע (`RiskEngine._order_seq`, `SetupStream._seq`) לא דולפים בין שתי ריצות עצמאיות. `tests/test_at3_15_multiarm_determinism.py`.
- **AT-3.16 אינטראקציית מכסה, >2 Setups ל-ARMED על אותו תיק/יום (Stage A / B-2, D-069, סוגר את שארית KI-015):** 3 Setups נפרדים (אזורי-FVG שונים לחלוטין, מחיר יורד לאורך הזמן כדי לא להפעיל בטעות את נוסחת ה-Mitigation של `src/fvg/mitigation.py` על אזורים שטרם הגיעו) מגיעים ל-ARMED על אותו תיק (M2/S_wick), אותו יום מסחר NY. שני הראשונים ממולאים (וסוגרים נקי, TP) בפועל — לא מדומים דרך seeding — וצורכים את מכסת ה-2-מילויים/יום; השלישי נדחה ב-`RiskEngine.approve()` עם `blocked_quota` (D-047/D-052), מאומת גם ישירות מול שורת `setup_arm_outcomes` ביומן. הבדיקה הראשונה חשפה כשל אמיתי (לא ארטיפקט-פיקסצ'ר): `M4EntryModel._watching` דלף setup_id שכבר לא היה שביר דרך `SetupStream.get_setup` אחרי אירוע `invalidated post_arm=True` (S-low-break), כי `Orchestrator.run()` מעולם לא קרא ל-`on_event` על ההסתעפות `invalidated/expired/no_ifvg` — רק על `armed`. תוקן (Option A, אישור Roy): שורה פונקציונלית אחת ב-`Orchestrator.run()` — קריאה ל-`_open_orders_for_event` (בדיוק הקריאה הקיימת שכבר משמשת את הסתעפות ה-`armed`) גם על ההסתעפות הזו, ללא מנגנון חדש וללא צימוד Orchestrator↔M4. אומת ש-Revert של השורה הזו משחזר בדיוק את אותה קריסה (`KeyError`). `tests/test_at3_16_quota_arm_interaction.py`.

## Phase 4
- **AT-4.1 Paired entries:** בתוך מודל כניסה — timestamp ומחיר כניסה זהים לשלוש זרועות SL, לכל Setup.
- **AT-4.2 Arm isolation:** מכסה/הון/Equity נפרדים; מילוי בזרוע אחת לא משפיע על אחרת.
- **AT-4.3 Metrics correctness:** יומן 10 עסקאות ידוע → WR/PF/Expectancy/MaxDD/Streak/MAE/MFE = חישוב יד.
- **AT-4.4 effective_window:** יום עם חדשות 08:30 → ‎90−30=60 דקות אפקטיביות נרשמות. (30 דק' לפני האירוע חופפות לטרום-חלון.)

## Phase 5
- **AT-5.1 WF split:** 3 שנים → חלונות 9/3 ללא חפיפה וללא זליגת Train→Test.
- **AT-5.2 Baseline fairness:** התפלגות מרחקי SL של ה-Baseline ≈ של הזרוע (KS-test sanity); אותם פילטרים/מכסה/RR.
- **AT-5.3 Reproducibility:** שתי ריצות עם אותו (config,data,code,seed) → יומן זהה ביט-לביט; שינוי פרמטר → hash חדש.
- **AT-5.4 Objective lock:** ניסיון להריץ עם objective שונה מהמוצהר ב-Experiment → חריגה.

## Phase 6
- **AT-6.1 Analyst is read-only:** בהינתן Snapshot — הפלט מובנה (סכמת JSON); אפס כתיבה ל-State/Orders.
- **AT-6.2 דף עסקה:** כל 12 שכבות הסימון מופיעות (Swings, BOS, Sweep, 4H FVG, Displacement, TS, R-Wick, S-Sweep, iFVG, Entry, SL, TP).
