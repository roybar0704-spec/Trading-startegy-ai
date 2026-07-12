# WORK ORDER — B-1: Reproducibility Spine

מסמך ביצוע ל-Claude Code · Stage A, Blocker B-1 · מאושר ע"י Roy (Project Owner)
מקור סמכות: Final Engineering Decision Document (Pre-Phase-4 Gate) + ארבע מיקרו-החלטות שאושרו.
**כפוף ל-`WORK_ORDER_PROTOCOL.md` v1.0** — Pre-Flight Review חובה (§1) + Lessons Learned בדו"ח הסיום (§3.9).

---

## 0. הקשר ותפקיד

אתה Senior Quant Engineer בפרויקט מחקר XAUUSD דטרמיניסטי. עליך לבצע את B-1 בלבד: חיווט זהות ריצה אמיתית + רישום ריצות מינימלי + בדיקת דטרמיניזם ברמת ריצה. המטרה: סגירת KI-018 ועמידה ב-SPEC §13 וב-CLAUDE.md (דטרמיניזם ביט-לביט, רישום כל ריצה).

מסמכי הסמכות בריפו (סדר עדיפות): `SPEC_V1_FROZEN.md` → `ARCHITECTURE.md` → `INTERFACES.md` → `CLAUDE.md` → `DECISIONS_LOG.md` → `KNOWN_ISSUES.md` → `RESEARCH_ASSUMPTIONS_V1.md` → `ACCEPTANCE_TESTS.md` → `PHASE_PLAN.md`. אם מסמך בריפו סותר מסמך אחר או את ה-Work Order הזה — עצור ודווח.

## 1. כללים קשיחים

1. אין שינויי Scope. אין Refactoring שאינו נדרש. אין "שיפורים".
2. **אין שינויי Schema.** אם מתגלה שנדרש שינוי סכימה — עצור, כתוב `PREFLIGHT_REPORT.md`, אל תמשיך.
3. כל Commit מגובה ב-Decision Record (D-066, ראה סעיף 6) ומפנה אליו בהודעת ה-Commit.
4. כל שינוי מלווה בעדכון המסמכים הרלוונטיים באותו Commit או ב-Commit התיעוד הסוגר.
5. **כל בדיקה מורצת בפועל.** אסור לדווח על בדיקה שלא הורצה. פלט pytest אמיתי בלבד.
6. קומיטים קטנים; החבילה ירוקה בסוף כל Commit.
7. עבודה על branch: `stage-a/b1-reproducibility-spine`.

## 2. החלטות מאושרות מראש (אין לפתוח מחדש)

- מיקום החיווט: `run_builder` בלבד — לא ה-Orchestrator (שימור D-037/D-057).
- `config_hash` מחושב אוטומטית בתוך `run_builder` מ-`params` באמצעות `config_hash()` הקיימת (KI-016). הקורא אינו מספק אותו; אם סופק ערך — `ValueError`.
- `code_version` מזוהה מ-git: `<sha>` או `<sha>+dirty`; כשל git → חריגה קולנית. override מפורש מותר לטסטים בלבד.
- `seed = NULL` לריצות מנוע; אינווריאנט: המנוע נטול-RNG, כל אקראיות עתידית חייבת לצרוך את `runs.seed`.
- Registry זמני עד T5.5: `data/registry/runs.jsonl`, append-only.
- `RunIdentity` מתווסף ל-`build_orchestrator`; `INTERFACES.md` מתעדכן באותו Commit.

## 3. שלב 0 — Pre-flight (חובה לפני כל עריכה)

**תוצר חובה (פרוטוקול §1): `PREFLIGHT_B1.md`** בארבעה חלקים — (א) הנחות מאומתות + ראיה `file:line`/פלט פקודה לכל אחת; (ב) הנחות שלא ניתן לאמת + סיבה + אופן טיפול; (ג) סטיות תיעוד↔קוד שהתגלו + חומרה; (ד) הכרעה `PROCEED`/`STOP`. אין commit קוד לפני הכרעת PROCEED.

הרץ ותעד:

```bash
git rev-parse HEAD && git status --porcelain
pytest -q                      # בסיס ירוק + מספר בדיקות
lint-imports || true           # אם מוגדר
```

אמת מול הקוד (לא מול הזיכרון):
- [ ] בטבלת `runs` קיימות העמודות `config_hash, code_version, data_version, split_type, seed` (לפי KI-018/D-059 הן קיימות עם placeholders "unknown"). אם חסרות — עצור (כלל 2).
- [ ] `config_hash()` קיימת ב-`src/config/models.py` ויש לה unit test (KI-016).
- [ ] חתימת `build_orchestrator` בקוד תואמת ל-`INTERFACES.md`.
- [ ] אתר את ה-fixture המלא של D-064 (סגירת KI-020) — הוא הבסיס ל-AT-3.14.
- [ ] בדוק אם יש בטבלאות ה-Journal עמודות שעון-קיר (created_at וכד'). אם יש — רשום אותן לרשימת ההחרגה של הייצוא הקנוני.
- [ ] בדוק את המספר הפנוי הבא ב-DECISIONS_LOG (אם קיים D-066 — קח את הבא) ואת המספר הפנוי ב-AT-3.x.

כל אי-התאמה בין המסמכים לקוד → עצור, `PREFLIGHT_REPORT.md`, המתן לאישור Roy.

## 4. יישום — סדר קומיטים

**Commit 0 (חד-פעמי) — אימוץ הפרוטוקול:** הוספת `WORK_ORDER_PROTOCOL.md` לריפו (לצד מסמכי הפרויקט) + D-entry האימוץ לפי הטיוטה שבפרוטוקול §6, במספר הפנוי הבא. ה-D של B-1 (סעיף 6 כאן) מקבל את המספר שאחריו — עדכן הפניות בהתאם.

**Commit 1 — `src/core/types.py`: RunIdentity (+ unit test).**
Frozen dataclass, ללא תלויות (שימור D-038):

```python
@dataclass(frozen=True)
class RunIdentity:
    data_version: str
    split_type: str              # {"in_sample","walk_forward_train","walk_forward_test","holdout","baseline","fixture"}
    seed: int | None = None
    code_version: str | None = None   # None => זיהוי אוטומטי מ-git
    config_hash: str | None = None    # חייב להישאר None; מחושב פנימית
```

בדיקות: יצירה תקינה; אי-שינוי (frozen); ערכי ברירת מחדל.

**Commit 2 — helper גרסת דאטה (+ unit tests).**
מקם במודול data קיים מתאים או `src/data/versioning.py`:
- `data_version_for_files(paths) -> str`: manifest ממוין של `(relpath, sha256)` על תוכן הקבצים → sha256 של ה-manifest (JSON קנוני).
- `data_version_for_ticks(ticks) -> str`: sha256 על סריאליזציה קנונית של רצף ה-ticks שבזיכרון (עבור fixtures — שימור D-037: גם ריצה סינתטית מקבלת data_version אמיתי).
בדיקות: רגישות לשינוי תוכן; אינווריאנטיות לסדר קלט הקבצים; יציבות בין קריאות.

**Commit 3 — חיווט `run_builder` + עדכון `INTERFACES.md` + עדכון טסטים קיימים.**
- `detect_code_version()`: `git rev-parse HEAD` + בדיקת dirty (`git status --porcelain`) → `"<sha>"` או `"<sha>+dirty"`; כשל → `RuntimeError`.
- `build_orchestrator(..., identity: RunIdentity, registry_path: Path | None = None)`:
  - `identity.config_hash is not None` → `ValueError("config_hash is computed internally")`.
  - resolve: `config_hash = config_hash(params)`; `code_version = identity.code_version or detect_code_version()`.
  - כתיבת הערכים האמיתיים לשורת `runs` (מחליף את כתיבת ה-"unknown"; אפס שינוי סכימה).
  - לאחר אתחול Journal מוצלח — append שורה ל-registry (ברירת מחדל `data/registry/runs.jsonl`; צור תיקייה + `.gitkeep`):
    `{"ts_utc": ISO8601Z, "run_id", "experiment_id", "config_hash", "code_version", "data_version", "split_type", "seed", "objective_id": "RA-01"}`
- עדכון כל אתרי הקריאה בטסטים: `RunIdentity(data_version=data_version_for_ticks(<fixture ticks>), split_type="fixture")`, `registry_path=tmp_path/...`, ו-`code_version` override קבוע בטסטים.
- טסטים שמצפים ל-"unknown" — עדכן לציפייה לערכים אמיתיים.
- `INTERFACES.md`: חתימה חדשה + טיפוס `RunIdentity` (סעיף 6.4).

**Commit 4 — AT-3.14 (משיכה ממוקדת של AT-5.3) + עדכון `ACCEPTANCE_TESTS.md`.**
מפרט הבדיקה:
1. בנה והרץ את pipeline ה-fixture של D-064 **פעמיים מאפס** (אפס state משותף), עם אותו `RunIdentity` (כולל `code_version` override קבוע) ואותם קלטים.
2. פונקציית ייצוא קנוני בתוך קובץ הטסט (לא ב-src): רשימת טבלאות קבועה מתוך סכימת ה-Journal; לכל טבלה `SELECT * ORDER BY <PK>`; החרגת עמודות שעון-קיר אם נמצאו ב-Pre-flight; סריאליזציה ל-CSV; sha256 על השרשור.
3. Assert: hash זהה בין שתי הריצות.
4. Assert: בשורת `runs` אין "unknown" באף שדה; `config_hash == config_hash(params)`; `seed IS NULL`; שורת registry קיימת ונפרסת תקין.

**Commit 5 — תיעוד סוגר: D-066 + KI-018 Closed + הפניה צולבת KI-016.**

## 5. קריטריוני סגירה (B-1 AC)

- שורת `runs` נושאת ערכים אמיתיים בכל חמשת השדות (seed רשאי להיות NULL).
- AT-3.14 ירוק.
- רשומת registry נכתבת בכל ריצה.
- כל חבילת הבדיקות ירוקה (בסיס + חדשות); import-linter ירוק אם מוגדר.
- `INTERFACES.md`, `ACCEPTANCE_TESTS.md`, `DECISIONS_LOG.md`, `KNOWN_ISSUES.md` עודכנו.
- **הכרזת "Closed" רק בכפוף ל-Definition of Done המלא (פרוטוקול §4) — כל תשעת הסעיפים מסומנים בדו"ח.**

## 6. טקסטים מוכנים להדבקה (התאם מספור/תאריך לריפו)

### D-066 — חיווט זהות ריצה ורישום ריצות מינימלי (סוגר KI-018)
**סטטוס:** מאושר (Roy) · **שלב:** Stage A / B-1
**החלטה:** `config_hash` מחושב אוטומטית ב-`run_builder` מ-`params` (הקורא אינו מספק); `code_version` מ-git עם סימון `+dirty` וכשל קולני; `data_version` באמצעות helper אחוד לקבצים ול-fixtures (שימור D-037); `split_type` מתוך אוצר ערכים סגור כולל `"fixture"`; `seed=NULL` לריצות מנוע + אינווריאנט "מנוע נטול-RNG; כל אקראיות עתידית תצרוך את `runs.seed`"; רישום append-only של כל ריצה ב-`data/registry/runs.jsonl` עד החלפתו ב-Experiment Tracker (T5.5); `RunIdentity` נוסף ל-`build_orchestrator` ותועד ב-INTERFACES.
**רציונל:** SPEC §13 ("כל ריצה = config_hash, data_version, code_version, רישום Append-Only") ו-CLAUDE.md §דטרמיניזם מחייבים זהות אמיתית לפני T3.4; placeholders "unknown" (D-059/KI-018) הפכו את היומן לבלתי-ניתן-לשחזור עקרונית.
**השלכות:** אפס שינוי סכימה; שינוי חתימת `build_orchestrator` (מתועד); טסטים קיימים עודכנו מציפיית "unknown" לערכים אמיתיים; אכיפת "SHA נקי" לריצות מחקר נעשית בשער RRR/T3.4, לא בקוד.
**תנאי פתיחה מחדש:** T5.5 מחליף את ה-registry; הוספת RNG כלשהו למנוע.

### KI-018 — עדכון סטטוס
**סטטוס: Closed (Stage A / B-1, D-066).** חיווט אמיתי של `config_hash / code_version / data_version / split_type / seed` דרך `run_builder`; מאומת ב-AT-3.14 (דטרמיניזם דו-ריצתי + היעדר "unknown"). ראה D-066. הפניה: KI-016 (פונקציית `config_hash` שחוברה כעת למסלול הריצה).

### ACCEPTANCE_TESTS.md — תוספת
**AT-3.14 — דטרמיניזם דו-ריצתי (Scoped pull-forward של AT-5.3):** שתי ריצות זהות מאפס על fixture D-064 → ייצוא קנוני זהה (sha256) של כל טבלאות ה-Journal; שורת `runs` ללא "unknown"; רשומת registry תקינה. הערה: AT-5.3 המלא (סקייל אמיתי) נותר ב-Phase 5.

### INTERFACES.md — דלתא
עדכון חתימת `build_orchestrator(..., identity: RunIdentity, registry_path: Path | None = None)` + הגדרת `RunIdentity` (שדות וסמנטיקה כבסעיף 4/Commit 1, כולל האיסור על אספקת `config_hash`).

## 7. תנאי עצירה מיידית

- נדרש שינוי סכימה · סתירה מסמך↔קוד · כשלי בדיקות שאינם נובעים מהשינוי שלך · כל דבר מחוץ ל-Scope של B-1. בכל אחד מאלה: עצור, כתוב דו"ח, המתן ל-Roy.

## 8. דו"ח סיום (פורמט חובה)

1. רשימת כל הקבצים שהשתנו. 2. diff מלא לכל קובץ (`git diff main...HEAD`). 3. פלט הרצת הבדיקות המלא (לפני/אחרי, כולל מספרים). 4. Acceptance Tests שנוספו. 5. Known Issues שנסגרו. 6. ה-Decision Records שנוספו. 7. הכרזה: B-1 נסגר במלואו / חלקית + מה נשאר בדיוק. 8. חריגות/הפתעות אם היו (כולל ממצאי Pre-flight).
9. **Lessons Learned (פרוטוקול §3.9):** LL-1 מה התגלה שלא היה ידוע לפני תחילת העבודה; LL-2 הנחות שאומתו; LL-3 הנחות שהתבררו כשגויות; LL-4 עדכונים נדרשים ל-ARCHITECTURE / SPEC / DECISIONS_LOG / KNOWN_ISSUES / ACCEPTANCE_TESTS — כל פריט מבוצע בקומיט התיעוד הסוגר או נפתח כ-Follow-up מפורש. אין אובדן ידע שקט.
10. **DoD Checklist חתום (פרוטוקול §4):** תשעת הסעיפים מסומנים אחד-אחד; כל סעיף חסר → ההכרזה היא "Partially Closed" עם פירוט מדויק.
11. **מדד פרויקט (פרוטוקול §3.11):** Stage נוכחי · Blockers פתוחים/סגורים · KIs פתוחים/סגורים · % התקדמות משוער של Stage A · Top-3 סיכונים שנותרו.
