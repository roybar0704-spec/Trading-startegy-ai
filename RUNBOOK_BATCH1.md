# RUNBOOK — Batch 1 Execution (מחשב הבית בלבד)

**מטרה:** להריץ את Batch 1 (`2022-10-03` … `2022-12-31`) מקצה-לקצה, Copy/Paste בלבד, בלי החלטות תוך-כדי. כל שלב כולל את ה-Output הצפוי ותנאי-STOP מפורש — אם משהו לא תואם, **עצור ואל תמשיך לשלב הבא**.

**הנחות עבודה (תקן אם שונה אצלך):** הריפו משוכפל תחת `C:\Users\User\Trading-startegy-ai`, PowerShell כ-Shell. אם אתה עובד ב-Git Bash — הפקודות של Git/Python זהות; רק פקודות ה-Hash/דיסק (מסומנות למטה) שונות מעט.

---

## שלב 0 — פתיחת סביבת העבודה

```powershell
cd C:\Users\User\Trading-startegy-ai
git status
```
**צפוי:** `On branch claude/xauusd-research-handoff-1amry4` (או ה-branch שאתה עובד עליו), `nothing to commit, working tree clean`.
**STOP אם:** יש שינויים לא-committed לא-מוכרים לך — אל תמשיך, תבדוק קודם מה זה.

---

## שלב 1 — Git Verification

```powershell
git fetch origin
git checkout claude/xauusd-research-handoff-1amry4
git pull origin claude/xauusd-research-handoff-1amry4
git rev-parse HEAD
```
**צפוי:** ה-SHA האחרון חייב להיות **לפחות** `4439dfb05a2b13999f42195057a3c1575fa5fe9d` (או קומיט מאוחר יותר על אותו branch — לא ענף/היסטוריה שונה).

```powershell
Get-FileHash scripts\backfill_full_range.py -Algorithm SHA256
```
*(ב-Git Bash: `sha256sum scripts/backfill_full_range.py`)*
**צפוי:** `7201A3587BFF07E33C3684AE835463DA1FF016007B87F5BC4A2F24D841573225` (לא תלוי-אותיות-גדולות/קטנות).
**STOP אם:** ה-Hash לא תואם — זו לא הגרסה המאומתת של הסקריפט, אל תריץ.

---

## שלב 2 — Environment Verification

```powershell
python --version
```
**צפוי:** `Python 3.11` ומעלה.

```powershell
Get-PSDrive C | Select-Object Used,Free
```
*(ב-Git Bash: `df -h .`)*
**צפוי:** מינימום **10GB פנויים**.
**STOP אם:** פחות מ-10GB — לפנות מקום קודם.

---

## שלב 3 — בדיקת Dependencies

```powershell
uv sync --extra dev
uv run python -c "import polars, pyarrow, duckdb, pydantic, httpx, h2; print('DEPS OK')"
```
**צפוי:** השורה האחרונה — `DEPS OK`.
**STOP אם:** שגיאת Import כלשהי — `httpx`/`h2` קריטיים במיוחד (הם ה-`BrowserLikeTransport` שפותר את KI-001; בלעדיהם חוזרים לחסימת ה-429 המקורית).

---

## שלב 4 — Backup לנובמבר 2022 (לפני שנוגעים בכלום)

```powershell
New-Item -ItemType Directory -Force -Path "data\backup_pre_batch1" | Out-Null
Copy-Item "data\ticks\XAUUSD\2022\11.parquet" "data\backup_pre_batch1\11.parquet.bak"
Copy-Item "data\ticks\XAUUSD\2022\11.parquet.sha256" "data\backup_pre_batch1\11.parquet.sha256.bak"
Get-ChildItem "data\backup_pre_batch1"
```
**צפוי:** שני הקבצים המגובים מופיעים ברשימה, בגודל זהה למקור (`11.parquet` ≈ 20,503,102 bytes).
**STOP אם:** `data\ticks\XAUUSD\2022\11.parquet` לא קיים אצלך בכלל — זה אומר שהמכונה הזו לא זהה למה שדווח קודם; תבדוק לפני שממשיכים (ר' שלב 5, ייתכן שזה בסדר אם יש לך checkpoint משלך).

---

## שלב 5 — Dry Run (חובה, ללא רשת)

```powershell
python scripts\backfill_full_range.py --symbol XAUUSD --start 2022-10-03 --end 2022-12-31 --dry-run
```

**שני תוצאות אפשריות — שתיהן תקינות, פשוט תדע מה קורה:**

- **אם אין `checkpoint.json` קיים אצלך (או שהוא לא מכיר את נובמבר):**
  ```
  Already completed (checkpoint): 0; pending: 3
    2022-10: pending
    2022-11: pending
    2022-12: pending
  ```
  זה תקין — נובמבר יתעדכן-מחדש בבטחה (התוכן זהה, `write_month` לא יכתוב שוב בפועל, רק "יאמת ויסמן" ב-checkpoint). זה עולה כ-720 קריאות-רשת נוספות (לא מזיק, רק זמן).

- **אם יש אצלך `checkpoint.json` מריצת D-069 המקורית (מהמחשב הזה):**
  ```
  Already completed (checkpoint): 1; pending: 2
    2022-10: pending
    2022-11: completed
    2022-12: pending
  ```
  גם זה תקין — פחות עבודה, נובמבר לא יורד שוב.

**STOP אם:** משהו אחר לגמרי מופיע (למשל שגיאה, או חודשים לא-קשורים) — אל תמשיך, זה אומר שמשהו לא כמצופה בסביבה.

---

## שלב 6 — הרצת Batch 1 בפועל

**רק אחרי ששלב 5 נראה כמו אחת משתי התוצאות למעלה, בדיוק.**

```powershell
python scripts\backfill_full_range.py --symbol XAUUSD --start 2022-10-03 --end 2022-12-31 --pacing-seconds 2 *>&1 | Tee-Object -FilePath "data\backfill_state\batch1_run_output.log"
```
*(`Tee-Object` שומר את הפלט לקובץ **וגם** מציג אותו על המסך בו-זמנית — כך אין צורך להעתיק ידנית בסוף.)*

**צפוי בסיום (שורה אחרונה בפלט):**
```
=== BACKFILL RUN COMPLETE === months_succeeded=<N> months_failed=0 transport_calls=<X> 429s=0 errors=0
```
**STOP אם:** `months_failed` **לא** אפס, או `429s`/`errors` גבוהים — **אל תריץ שוב אוטומטית**, תעצור ותדווח את הפלט המדויק לפני שממשיכים ל-Batch 2 (בהתאם לפרוטוקול STOP שכבר נהוג בפרויקט).

**זמן משוער:** כ-1.5-2.5 שעות (3 חודשים, אולי 720 קריאות נוספות אם נובמבר יורד מחדש — ר' שלב 5). אפשר להריץ ברקע/להשאיר לרוץ.

---

## שלב 7 — שמירת Evidence אחרי סיום

```powershell
# 1. Checkpoint
Copy-Item "data\backfill_state\checkpoint.json" "data\backfill_state\checkpoint_after_batch1.json"
Get-Content "data\backfill_state\checkpoint.json"

# 2. Requests log (כל קריאת-רשת אמיתית)
Copy-Item "data\backfill_state\logs\requests.jsonl" "data\backfill_state\logs\requests_batch1.jsonl"

# 3. Hash + גודל לכל קובץ Parquet חדש
Get-ChildItem "data\ticks\XAUUSD\2022\*.parquet" | ForEach-Object {
    Write-Host $_.FullName $_.Length
    Get-FileHash $_.FullName -Algorithm SHA256
}

# 4. מצב דיסק אחרי
Get-PSDrive C | Select-Object Used,Free

# 5. סריקת Gap/Spike על אוקטובר+דצמבר (Read-Only, לא נוגע בקוד)
uv run python scripts\diagnostics\analyze_spikes.py
```

**לשמור/לצלם-מסך:** פלט שלבים 1-5 למעלה + `data\backfill_state\batch1_run_output.log` (משלב 6) — זה חבילת ה-Evidence המלאה של Batch 1, בדיוק כפי ש-`BACKFILL_RUN_PLAN.md` §"בדיקות חובה" דורש לפני מעבר ל-Batch 2.

---

**סיכום — מה לשלוח בחזרה אחרי הריצה:** פלט שלב 6 (השורה `BACKFILL RUN COMPLETE`), תוכן `checkpoint_after_batch1.json`, ותוצאת `analyze_spikes.py`. **אל תריץ Batch 2 עד שאלה נבדקו ואושרו.**
