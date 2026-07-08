# FEATURE SPEC — Version 1 (Feature Store)
**מעמד:** תוספת ארכיטקטונית (D-028). אינה משנה אף חוק אסטרטגיה. ה-Features תיאוריים בלבד — אסור שיזינו החלטות מסחר ב-v1.

## עקרון הליבה: Snapshot עכשיו, Feature אחר-כך
בכל Setup נלכדים **Context Snapshots** נקודתיים-בזמן (engagement / armed / entry / exit) — צילום מלא של מה שהיה *ידוע* באותו רגע (confirmed_at ≤ ts). כל Feature מחושב מה-Snapshot, לא מהשוק — ולכן:
1. **אפס Lookahead מובנה** גם ב-Features עתידיים.
2. **Feature חדש בעתיד מחושב רטרואקטיבית** על כל ההיסטוריה — בלי להריץ אף בקטסט מחדש.

## ארכיטקטורה
- `feature_registry` — כל Feature רשום: שם, טיפוס, הגדרה, גרסה, סטטוס (approved/proposed).
- `trade_features` — אחסון EAV: ‏(trade_id, feature, value). **אין סכימה קשיחה** — הוספת Feature = שורת Registry + Extractor, אפס מיגרציות, אפס נגיעה במנוע.
- `context_snapshots` — ה-JSON הנקודתי-בזמן.
- תצוגה רחבה לאנליטיקה: ‏DuckDB PIVOT ‏(`v_trades_wide`).

```python
class FeatureExtractor(Protocol):
    name: str; dtype: Literal["num","text"]; version: int
    def compute(self, trade: Trade, snaps: dict[str, Snapshot],
                journal: JournalRead) -> float | str | None   # None = NA מפורש
```

## מיפוי ה-Features הנדרשים

### Trade Information
| Feature | מקור |
|---|---|
| trade_id, entry/exit time, direction, entry/exit px, SL, TP | טבלת trades (קיים) |
| planned_rr | קבוע 3.0 (חוק) |
| result | ‏win/loss נגזר; **BE לא יכול להתרחש תחת חוקי v1** (אין ניהול Break-Even) — ערך שמור ל-FE-11 |
| profit_r | קיים (result_r) |
| profit_ccy | Extractor: ‏units×(exit−entry)−costs |

### Market Structure
| Feature | מקור |
|---|---|
| htf_bias | snapshot@entry |
| bos_direction | ‏BOS האחרון שקבע את ה-Bias (snapshot) |
| choch | ⚠️ מוצע (ראה הגדרות למטה) |
| sweep_confirmed | תמיד True בעסקה (חוק הטריגר); נשמר לשלמות |
| sweep_type | ⚠️ מוצע |
| swing_used, fractal_used | מזהי ה-Swing שנלקח (R.low) וה-Fractal של ה-BOS (snapshot) |

### FVG Information
| Feature | מקור |
|---|---|
| htf_fvg_type (L1/L2/L3), fvg_tf, bos_generated_fvg | fvg_registry (קיים) |
| fvg_age | שעות מ-confirmed_at עד engagement |
| fvg_size | ‏top−bottom ב-$ |
| mitigation_pct_at_engagement | snapshot@engagement |
| ts_present | setups.ts_flag (קיים) |
| displacement_score | ⚠️ מוצע |

### Entry Information
| Feature | מקור |
|---|---|
| entry_model, stop_model | portfolios (קיים) |
| ifvg_size, ifvg_time | setups.ifvg (קיים) |
| reaction_candle_size, reaction_wick_size | ‏R: ‏high−low, ‏min(o,c)−low |
| confirmation_time | ⚠️ מוצע |

### Market Environment
| Feature | מקור |
|---|---|
| spread_at_entry / at_exit | snapshot (Bid/Ask בפועל) |
| slippage_applied | trades.cost_slippage (קיים) |
| volume | ⚠️ מוצע (TickVolume proxy — מגבלה מתועדת) |
| atr | ⚠️ מוצע: ‏ATR(14) על 4H ועל 5M, נקודתי-בזמן |
| volatility_score | ⚠️ מוצע |
| session, day_of_week, hour_bucket_et | נגזרות זמן; session=NY_AM קבוע ב-v1 + חצאי-שעה |
| minutes_to_nearest_red_news | חתום (לפני/אחרי); בתוך Blackout בלתי-אפשרי לפי חוק |
| overnight, weekend_exposure | תגים קיימים |

### Performance
| Feature | מקור |
|---|---|
| mae_r, mfe_r, time_in_trade | trades (קיים) |
| distance_to_stop_usd, distance_to_target_usd | ‏|entry−SL|, ‏|TP−entry| |

## ⚠️ הגדרות מוצעות — ממתינות לאישורך (D-029)
אף אחת לא חוסמת את Phase 0; כולן נדרשות רק ב-Phase 4.
1. **CHoCH** = BOS שהיפך את מצב ה-Bias (flip), להבדיל מ-BOS ממשיך-מגמה. ה-Feature: האם ה-Bias ששלט בעסקה נולד מ-CHoCH או מהמשכיות. נגזר מ-bias_history — אפס לוגיקה חדשה במנוע.
2. **sweep_type** ∈ ‏{r_wick_only, r_wick+fractal_5m, r_wick+htf_level} — האם S.low לקח, בנוסף ל-Wick של R, גם Fractal 5M מאושר או רמת 4H.
3. **displacement_score** = הערך הרציף של D1 ‏(body/avg-10), לא רק הדגל הבינארי.
4. **volatility_score** = ‏ATR(14,5M) חלקי החציון שלו ב-90 הימים הקודמים (נקודתי-בזמן) — ציון משטר תנודתיות.
5. **volume** = TickVolume של R, של S ושל נר ה-Inversion (שלושה שדות).
6. **confirmation_time** = שני משכים: ‏engagement→S.close ו-S.close→Inversion.
7. **ATR** = תקופה 14, על 4H ועל 5M (יירשם כ-RA-24 עם אישורך; ‏volatility_score → RA-25).

## בדיקות קבלה (מתווספות ל-Phase 4)
- **AT-F.1 שלמות:** לכל עסקה סגורה — כל Feature בסטטוס approved קיים (ערך או NA מפורש). אפס חורים שקטים.
- **AT-F.2 אפס זליגה:** כל Feature מחושב אך ורק מ-Snapshot שה-ts שלו ≤ רגע הלכידה; בדיקה: שינוי דאטה *אחרי* ה-Snapshot לא משנה אף Feature.
- **AT-F.3 אנליטיקה:** ‏`stats.by(feature, metric)` — ‏WR לפי Bias, TS מול בלי-TS, Expectancy לפי שעה/יום, Profit לפי Entry/Stop Model — מול חישוב יד על יומן מדגם.

## נוהל הוספת Feature עתידי
הגדרה → שורת Registry ‏(proposed) → אישור משתמש ‏(approved) → Extractor + בדיקה → חישוב רטרואקטיבי מה-Snapshots. המנוע לא נפתח לעולם בשביל Feature.
