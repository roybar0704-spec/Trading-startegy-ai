# PREFLIGHT_B1 — Pre-Flight Review, Blocker B-1 (Reproducibility Spine)

**מבוצע לפי:** `WORK_ORDER_PROTOCOL.md` §1 + `WORK_ORDER_B1.md` §3.
**Branch:** `stage-a/b1-reproducibility-spine`.
**Base commit:** `d7b302f` (Commit 0 — אימוץ הפרוטוקול, D-066).

## פקודות בסיס שהורצו בפועל

```
$ git rev-parse HEAD
d7b302f9b56964054a0dac23293865a72700d3e7
$ git status --porcelain
(ריק — עץ נקי)
$ git branch --show-current
stage-a/b1-reproducibility-spine
```

**הערת סביבה (לא ממצא תיעוד↔קוד):** קונטיינר טרי — `.venv` היה קיים אך ריק (uv-managed, לא סונכרן). הורץ `uv sync --extra dev` לפני כל בדיקה. לאחר הסנכרון:

```
$ uv run pytest
........................................................................ [ 56%]
.......................................................                  [100%]
127 passed in 4.22s
```

127/127 ירוק — תואם בדיוק את מספר הבדיקות המתועד בסוף Phase 3 (D-064: "כל 127 הבדיקות עדיין ירוקות"). בסיס אמיתי, לא מהזיכרון.

```
$ uv run lint-imports
Analyzed 54 files, 91 dependencies.
Config has no engine dependencies KEPT
core is dependency-free (D-038) KEPT
Viz has no engine dependencies (T3.5) KEPT
Engine layering (...) KEPT
Contracts: 4 kept, 0 broken.
```

`import-linter` (מוגדר ב-`pyproject.toml`) ירוק במלואו — 4/4 חוזים.

## א. הנחות מאומתות (הנחה → ראיה)

| # | הנחה (מ-WORK_ORDER_B1.md) | ראיה |
|---|---|---|
| A1 | בטבלת `runs` קיימות העמודות `config_hash, code_version, data_version, split_type, seed` | `db/schema.sql:5-14` — `CREATE TABLE IF NOT EXISTS runs (... config_hash TEXT NOT NULL, code_version TEXT NOT NULL, data_version TEXT NOT NULL, ... split_type TEXT NOT NULL, seed BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL);` — כל חמש העמודות קיימות. |
| A2 | `config_hash()` קיימת ב-`src/config/models.py` ויש לה unit test | `src/config/models.py:323-334` — `def config_hash(rules, parameters, run_config, data_version, code_version) -> str`. בדיקה: `tests/test_config_models.py:41` — `test_config_hash_deterministic_and_sensitive_to_input`. |
| A3 | חתימת `build_orchestrator` בקוד תואמת ל-`INTERFACES.md` | קוד: `src/backtest/run_builder.py:107-120`. תיעוד: `docs/INTERFACES.md:146-150`. שתי החתימות זהות פרמטר-פרמטר (`rules, parameters, run_config, *, bars_1m, bars_5m, bars_4h, ticks, news=(), spread_warmup_ticks=(), journal=None, run_id="run"`). |
| A4 | קיים fixture מלא של D-064 (סגירת KI-020) שישמש בסיס ל-AT-3.14 | `tests/test_full_pipeline_from_raw_4h_bars.py` — `_raw_4h_bars()` (4H גולמי, ללא `store.put`), `_scenario(journal=None)` בונה Orchestrator מלא דרך `build_orchestrator`. שלוש בדיקות קיימות כבר משתמשות בו. |
| A5 | `RunIdentity` שייך ל-`src/core/types.py`, נטול-תלויות (D-038) | `src/core/types.py:1-13` — docstring המודול: "This module has zero dependencies on the rest of `src`" + חוזה import-linter "core is dependency-free (D-038)" (`pyproject.toml`), אומת ירוק ב-`lint-imports` לעיל. |
| A6 | `_write_run_identity_rows` כותבת כרגע placeholders "unknown"/0 | `src/backtest/orchestrator.py:164-166` — `"config_hash": "unknown", "code_version": "unknown", "data_version": "unknown", ..., "split_type": "unknown", "seed": 0`. תואם KI-018 המתועד. |
| A7 | רשימת טבלאות קבועה של ה-Journal (לצורך פונקציית הייצוא הקנוני ב-AT-3.14) | `src/journal/duckdb_writer.py:16-21` — `_KNOWN_TABLES` (18 טבלאות: experiments, runs, portfolios, sessions, bias_history, fvg_registry, setups, orders, setup_arm_outcomes, trades, equity_curve, news_events, scores, ai_annotations, baseline_runs, feature_registry, trade_features, context_snapshots). |
| A8 | המספר הפנוי הבא ב-DECISIONS_LOG הוא D-067 (D-066 תפוס ע"י אימוץ הפרוטוקול) | `docs/DECISIONS_LOG.md` שורה אחרונה: `D-066` (אימוץ WORK_ORDER_PROTOCOL, ר' Commit 0). אין D-067 בקובץ. |
| A9 | המספר הפנוי הבא ב-ACCEPTANCE_TESTS.md בסדרת 3.x הוא AT-3.14 | `docs/ACCEPTANCE_TESTS.md` — האחרון בסדרה הוא AT-3.13 (שורה 44). AT-3.14 אינו קיים. |
| A10 | אין עמודות שעון-קיר אמיתיות (non-deterministic) בטבלאות ה-Journal הרלוונטיות לתרחיש D-064 | `grep -rn "datetime.now(\|utcnow()" src/` → 3 תוצאות בלבד: `dukascopy_downloader.py:198` (לא-Journal, הורדת דאטה), `holdout.py:117` (`accessed_at` — Guard לא קשור ל-Journal), ו-`orchestrator.py:143`: `created_at = min(all_ts) if all_ts else datetime.now(UTC)` — ה-fallback ל-`datetime.now` מופעל **רק** אם `all_ts` ריק; בתרחיש D-064 יש bars אמיתיים, ולכן בפועל `created_at = min(all_ts)` — נגזר-דאטה, דטרמיניסטי, לא שעון-קיר. שאר עמודות ה-`_ts`/`_at` בסכימה (`placed_at`, `filled_at`, `entry_ts` וכו') נכתבות מ-timestamps של Bar/Tick, לא מ-`datetime.now()`. **מסקנה: אין צורך ברשימת החרגה לצורך הייצוא הקנוני של AT-3.14** — כל השדות בטבלאות הרלוונטיות דטרמיניסטיים ביחס לקלט הקבוע. |
| A11 | `data/` כולה ב-`.gitignore` (`/data/`, שורה 1) | `.gitignore:1`. משמעות: `data/registry/runs.jsonl` **וגם** `.gitkeep` הנלווה (כפי שמתואר ב-Commit 3) לא ייכנסו לריפו כברירת מחדל — טופל בחלק ג' (סטייה לא-חוסמת). |

## ב. הנחות שלא ניתן לאמת מראש (סיבה, השפעה, טיפול)

| # | הנחה | סיבה שלא ניתן לאמת עכשיו | השפעה על התוכנית | אופן טיפול |
|---|---|---|---|---|
| B1 | `git rev-parse HEAD` / `git status --porcelain` יעבדו בתוך `detect_code_version()` באותה סביבת-הרצה של הבדיקות (Commit 3/4) | תלוי בזמינות `git` בתוך תהליך הבדיקה בקונטיינר בזמן ריצה — לא נכשל היום כי הפונקציה עוד לא קיימת | אם ייכשל: `detect_code_version()` תזרוק `RuntimeError` (התנהגות מוצהרת, לא כשל שקט) | בדיקה בזמן-ריצה (unit test ל-`detect_code_version` ב-Commit 3 יריץ אותה בפועל ויוודא שלא זורקת בסביבה הזו) |
| B2 | ל-`config_hash()` הקיימת יש כל הפרמטרים הדרושים זמינים בתוך `run_builder` בזמן הקריאה (`rules`, `parameters`, `run_config` כבר בהיקף הפונקציה) | לא ממומש עדיין | נמוכה — כל שלושת האובייקטים כבר פרמטרים מוצהרים של `build_orchestrator` הקיימת | ייבדק ישירות ב-Commit 3 (קריאה אמיתית + assert בטסט) |

## ג. סטיות תיעוד↔קוד שהתגלו

| # | סטייה | חומרה | חוסמת? |
|---|---|---|---|
| **C1** | **`runs.seed` מוגדר `BIGINT NOT NULL` בסכימה הקפואה (`db/schema.sql:13`), אך `WORK_ORDER_B1.md` §2 קובע במפורש "seed = NULL לריצות מנוע", Commit 1 מגדיר `RunIdentity.seed: int \| None = None`, §5 (AC) קובע "seed רשאי להיות NULL", ו-Commit 4/AT-3.14 דורש `assert` מפורש "seed IS NULL".** כתיבת `NULL` לעמודה `NOT NULL` תיכשל בפועל (constraint violation) ב-DuckDB. אין דרך למלא את הדרישה כפי שהיא מנוסחת בלי לשנות את הסכימה (הפיכת `seed` ל-nullable). | **חמורה** | **כן — עוצר** |
| C2 | `WORK_ORDER_B1.md` Commit 3 מנסח "`config_hash = config_hash(params)`" — קיצור לא מדויק. החתימה האמיתית (`src/config/models.py:323`) דורשת חמישה ארגומנטים: `config_hash(rules, parameters, run_config, data_version, code_version)`. | קלה | לא — הבהרה טכנית בלבד; כל הערכים כבר בהיקף `run_builder`, אין תלות חדשה |
| C3 | `data/` כולה ב-`.gitignore` (`/data/`). Commit 3 מתאר "צור תיקייה + `.gitkeep`" עבור `data/registry/` כמשתמע-לשמר בריפו, אך כרגע שום קובץ בתוך `data/` לא נכנס ל-git בברירת מחדל. | קלה | לא — טיפול טכני נדרש (למשל `git add -f data/registry/.gitkeep` או חריג ממוקד ב-`.gitignore` ל-`data/registry/`), לא סתירה מהותית |

## ד. הכרעה

### STOP

**C1 הוא סתירה מהותית בין מסמך העבודה לסכימה הקפואה, ומפעיל במפורש שני כללי עצירה:**
- `WORK_ORDER_B1.md` §1 כלל 2: *"אין שינויי Schema. אם מתגלה שנדרש שינוי סכימה — עצור, כתוב `PREFLIGHT_REPORT.md`, אל תמשיך."*
- `WORK_ORDER_PROTOCOL.md` §5: *"נדרש שינוי סכימה"* — עצירה מיידית.

לא בוצע ולא יבוצע שום שינוי קוד/סכימה. אין commit נוסף מעבר ל-Commit 0 (שכבר בוצע) עד הכרעת Roy.

---

## Decision Proposal — `runs.seed` NOT NULL מול דרישת `seed=NULL`

**תיאור:** `WORK_ORDER_B1.md` מניח ש-`seed` יכול להיכתב כ-`NULL` לריצות מנוע (נטול-RNG), ובכך "לסמן ביושר" שאין Seed רלוונטי, במקום ה-placeholder הנוכחי `0` (D-059/KI-018) שהוא ערך-סתמי מטעה לא פחות מ-"unknown". הסכימה הקפואה מגדירה את העמודה כ-`BIGINT NOT NULL`.

**ראיות:**
- `db/schema.sql:13` — `seed BIGINT NOT NULL`.
- `WORK_ORDER_B1.md` §2 — "seed = NULL לריצות מנוע; אינווריאנט: המנוע נטול-RNG, כל אקראיות עתידית חייבת לצרוך את `runs.seed`".
- `WORK_ORDER_B1.md` §4 Commit 1 — `seed: int | None = None`.
- `WORK_ORDER_B1.md` §5 — "שורת `runs` נושאת ערכים אמיתיים בכל חמשת השדות (seed רשאי להיות NULL)".
- `WORK_ORDER_B1.md` §4 Commit 4 — "Assert: ... `seed IS NULL`".

**חלופות מלאות:**

1. **שינוי סכימה: `ALTER seed` ל-nullable (`BIGINT`, ללא `NOT NULL`).** תואם במדויק את כוונת ה-Work Order. דורש אישור מפורש של Roy לשינוי סכימה (הן CLAUDE.md `config/rules_v1.yaml` בלבד מוגן-hash, אך `db/schema.sql` הוא Journal schema רגיל — לא "קפוא" באותו מובן, ובכל זאת B-1 §1.2 אוסר על עצמי לגעת בו ללא אישור מפורש). שינוי מינימלי (עמודה אחת, `runs` בלבד), backward-compatible (ריצות קיימות עם `seed=0` ממשיכות להיטען תקין). אין השפעה על מבנה FK/PK.
2. **שינוי RunIdentity/AT-3.14 כך ש-`seed` יכתב כ-`0` (או ערך-Sentinel מוצהר אחר) במקום `NULL`, ללא שינוי סכימה.** משמר את הסכימה הקפואה כמות-שהיא, אך סוטה מהניסוח המפורש של Work Order §2/§5/Commit-4 ("seed=NULL", "seed IS NULL") — ידרוש עדכון-נגד לאותם סעיפים במסמך העבודה עצמו (או אישור-חריג מפורש להחיל `seed=0` כ"הערך שמייצג נטול-Seed" במקום `NULL`). משאיר את אותה עמימות שכבר קיימת היום (`0` מטעה באותה מידה כמו "unknown", כפי ש-KI-018 עצמו מציין).
3. **דחיית B-1 (Partially Closed) עד הכרעה, המשך רק בחלקים שאינם תלויים ב-`seed`.** לא מעשי — Commit 1 (`RunIdentity`) כבר מגדיר `seed: int | None`, ו-AT-3.14 (Commit 4, קריטריון הסגירה המרכזי) בנוי סביב `seed IS NULL`. כמעט כל B-1 תלוי בהכרעה הזו.

**המלצה:** חלופה 1 — שינוי סכימה ממוקד וקטן ביותר (`seed BIGINT NOT NULL` → `seed BIGINT`), עם Decision Record ייעודי (D-067, לפני שאר B-1) המתעד את הסיבה (הפער בין הכוונה התיעודית "0 הוא placeholder מטעה" ל"NULL הוא ערך-אמת עבור נטול-Seed"). זו הדרך היחידה שמקיימת בדיוק את מה שה-Work Order והבדיקה (AT-3.14) דורשים, ואינה יוצרת סתירה-נגד בתוך המסמכים.

**ממתין לאישור Roy** — לא בוצע/יבוצע שום שינוי קוד או סכימה עד הכרעה מפורשת.
