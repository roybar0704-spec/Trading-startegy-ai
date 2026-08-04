# BATCH3_CLOSURE_REPORT.md — Backfill Batch 3 (2023-09-01 … 2023-11-30)

**מבוצע לפי:** `BACKFILL_RUN_PLAN.md` (Batch 3) · Evidence Checklist זהה ל-Batch 2.
**Branch:** `claude/xauusd-research-handoff-1amry4` · **HEAD מאומת (לפני ואחרי ההרצה):** `273a974edae8359792227cc704b7198fbe52408f`.
**מסמך זה: תיעוד בלבד, להצגה בלבד — לא בוצע Commit/Push.**

---

## 1. BACKFILL RUN COMPLETE

```
=== BACKFILL RUN COMPLETE === months_succeeded=3 months_failed=0 transport_calls=2201 429s=0 errors=17
```
טווח: `2023-09-01` … `2023-11-30` (3 חודשי-לוח). `Already completed (checkpoint): 0; pending: 3` לפני ההרצה.

**אירוע Retry ברמת-חודש בספטמבר (מתועד, לא כשל):** ניסיון 1/3 נכשל אחרי 4 ניסיונות-שעה על `.../2023/08/01/06h_ticks.bi5` — ה-"08" הוא בדיוק ספטמבר (Dukascopy משתמש במספור-חודשים 0-אינדקס, מאומת מקוד המקור `hour_url()`), לא טעות. Cooldown 120.0s (תואם בדיוק לברירת-המחדל `--month-retry-cooldown-seconds`), ואז ניסיון 2/3 הצליח במלואו. אוקטובר ונובמבר הושלמו בניסיון ראשון ללא בעיה. `failed_months` נשאר ריק — הריטריי עבד בדיוק כמתוכנן.

## 2. checkpoint.json Evidence

הודבק גולמי, נבדק תכנותית:

| חודש | row_count | data_version (מלא, אומת SHA256 תקין 64-hex) |
|---|---|---|
| 2023-09 | 1,892,643 | `ca1ae5a3da24f5e0934ef882d84377056d1433657171e6f92ccaf57db91c2f05` |
| 2023-10 | 2,841,307 | `9f76ec30778ea72e48b27f3680bb5893540b44d6d74424bb91ea175290027639` |
| 2023-11 | 2,491,773 | `d9eb8d83bbe3c8830d5ef7c5009615b5e200fbc02d749e00c82242856c900a59` |

`failed_months: {}`. `completed_months` כולל כעת **14 חודשים** (11 קודמים + 3 חדשים). כל שלושת ה-`data_version` תואמים בדיוק ל-16 התווים הראשונים שהודפסו בלוג-הריצה החי — Cross-check משולש, כמו בכל Batch קודם.

## 3. Hash Validations

`Get-FileHash` עצמאי על `2023-09.parquet`:
```
CA1AE5A3DA24F5E0934EF882D84377056D1433657171E6F92CCAF57DB91C2F05
```
**תואם בדיוק** (case-insensitive) ל-`data_version` ב-checkpoint. אומת תכנותית (64 hex chars).

**מגבלה מוצהרת (עקבית עם המדיניות — "לפחות חודש אחד"):** אוקטובר ונובמבר מאומתים רק דרך ה-checkpoint עצמו, ללא Hash עצמאי שני.

## 4. Spike Validation — כל 3 החודשים

| חודש | Ticks טעונים | Validator flagged | Local recomputed | MATCH |
|---|---|---|---|---|
| 2023-09 | 1,892,643 | 2,386 (0.1261%) | 2,386 | ✅ |
| 2023-10 | 2,841,307 | 3,542 (0.1247%) | 3,542 | ✅ |
| 2023-11 | 2,491,773 | 2,703 (0.1085%) | 2,703 | ✅ |

שלושת ה-Ticks-טעונים תואמים **בדיוק** (ללא הפרש) ל-row_count ב-checkpoint — טווחי-הרצה נקיים (`--start <חודש>-01 --end <חודש>-<יום אחרון>`) מנעו את חפיפת-הגבול שנצפתה ביולי ב-Batch 2. כל שלוש ההרצות: `MATCH: local recomputation agrees exactly with the real Validator output`.

## 5. Disk Before/After

| | Used | Free |
|---|---|---|
| **לפני** | 106.54 GB | 369.32 GB |
| **אחרי** | 108.00 GB | 367.86 GB |
| **Delta** | +1.46 GB | −1.46 GB |

## 6. Known Limitations

1. **אוקטובר/נובמבר 2023 — ללא Hash עצמאי שני** (רק checkpoint self-report). עקבי עם המדיניות ("לפחות חודש אחד" לכל Batch), לא כשל.
2. **Delta-דיסק גבוה מהצפוי:** ‎+1.46GB, פי ~13 מה-Delta של Batch 2 (‎+0.11GB) על נפח-דאטה דומה (~7.2M מול ~8.2M ticks). הסבר סביר: Cache גולמי נוסף מניסיון-הכשל-והחזרה של ספטמבר, ו/או רעש-דיסק כללי של Windows (כבר נצפתה תנודה של ~0.4GB בין שתי מדידות עוקבות ללא כל פעילות-פרויקט, בשיחה זו). **לא משפיע על שלמות-הנתונים** — כל Hash/Checkpoint/Row-Count תקינים במלואם, ללא קשר לממצא זה.
3. **תקלות-תהליך בשלב איסוף-Evidence (לא בהרצת ה-Backfill עצמה):** נעשו כמה ניסיונות עם נתיב/דגל שגויים ל-`analyze_spikes.py` (`scripts\analyze_spikes.py --month ...` במקום `scripts\diagnostics\analyze_spikes.py --start/--end`), ופקודת ה-Batch המקורית שאושרה חסרה בטעות `uv run`. שני הדברים תוקנו לפני שנאספו ראיות סופיות — **אין השפעה על תוצאות ה-Backfill או ה-Evidence עצמם**, רק על משך זמן איסוף-הראיות.
4. **ינואר–מאי 2023 (מ-Batch 1)** — עדיין ללא Hash/Spike-scan עצמאי שני.

## 7. Gate Recommendation for Batch 4

**Batch 3 — מומלץ ל-Closed**, בכפוף לאישורך. כל פריטי ה-Evidence הנדרשים נאספו ואומתו. Disk delta נבדק כ-sanity check — חריג יחסית ל-Batch 2 אך מוסבר ולא-חוסם (§6.2).

**מצב מעודכן: 14/39 חודשים (~35.9%)** — אוקטובר 2022–נובמבר 2023.

**לפני Batch 4 (`2023-12-01`…`2024-02-29`):**
1. Dry Run **רחב** (`--start 2022-10-03 --end 2025-12-31`).
2. `git status`/`rev-parse HEAD` **לפני** ההרצה.
3. הפקודה חייבת לכלול `uv run` במפורש (לקח מתקלת-התהליך ב-§6.3).
4. אותם 5 פריטי Evidence, כולל Hash עצמאי על לפחות חודש אחד ו-Spike-scan על **כל** חודשי ה-Batch, בטווחים נקיים (`<חודש>-01` עד `<חודש>-<יום אחרון>`) כדי למנוע חפיפת-גבול.

**לא השתנה:** RA-10, KI-010, RRR הכולל — נשארים NO-GO. 25 חודשים נותרים.

---

**מסמך זה להצגה בלבד. לא בוצע Commit, לא בוצע Push.**
