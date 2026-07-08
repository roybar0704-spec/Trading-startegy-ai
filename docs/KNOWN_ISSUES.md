# KNOWN ISSUES
מעקב תקלות פתוחות. **Functional Gate דורש אפס פריטים פתוחים בחומרה critical/high.** פריטי medium/low מותרים אך מדווחים כחוב טכני ב-Project Health Report של כל Phase.

| ID | תיאור | חומרה | מודול | נפתח (Phase/תאריך) | סטטוס |
|---|---|---|---|---|---|
| KI-001 | סביבת הפיתוח (Claude Code sandbox) חוסמת גישת רשת ל-`datafeed.dukascopy.com` (403 ברמת ה-egress proxy). לא ניתן להוריד 3 שנות Ticks אמיתיים, לא ניתן להפיק דו"ח ספרד אמיתי לכיול RA-10/min_stop, ולא ניתן להריץ AT-0.1/AT-0.2/AT-0.7 מול דאטה אמיתי (רק מול Fixtures סינתטיים שמדמים את פורמט ה-wire במדויק). כל שאר T0.1–T0.6 מומשו ונבדקו במלואם. | high | data | Phase 0 / 2026-07-08 | open |
| KI-002 | `point_value=0.001` (סקאלת המרת המספר השלם הגולמי במבנה ה-tick של Dukascopy למחיר USD עבור XAUUSD) מבוסס על מוסכמה ציבורית מוכרת בכלי Dukascopy קוד-פתוח, אך לא אומת מול הורדה אמיתית (ר' KI-001). דורש אימות בפעם הראשונה שיש גישת רשת אמיתית. | medium | src/data/dukascopy_downloader.py | Phase 0 / 2026-07-08 | open |
| KI-003 | `StateStore` (D-041) שומר היסטוריית גרסאות מלאה ל-Swing/FVG כדי ש-`as_of(ts)` יהיה נכון-לזמן-אמת גם בשאילתות רטרואקטיביות — אך `effective_ts` של גרסת FVG נגזר מ-`invalidated_at`/`confirmed_at` בלבד. עדכוני `mitigation_pct` **ביניים** (לא-סופיים, לפני 100%) אינם נושאים חותמת-זמן עצמאית, ולכן `as_of(ts)` שנשאל בין שני עדכוני מיטיגציה עשוי להחזיר ערך "מאוחר מדי" (לא future-lookahead מוחלט, אך לא מדויק-לזמן). לא נבדק/נחשף ב-Phase 1 כי הבדיקות שם לא מזינות Ticks אמיתיים ל-`on_price`. | low | src/store/state_store.py, src/fvg/mitigation.py | Phase 1 / 2026-07-08 | open |

**נוהל:** תקלה שהתגלתה ולא תוקנה מיידית → שורה כאן לפני כל בקשת אישור Phase. סגירת תקלה → סטטוס `closed` + בדיקה שמכסה אותה. אסור למחוק שורות — היסטוריה מלאה.
