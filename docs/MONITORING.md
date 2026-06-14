# ReboundPro — Monitoring (בקרת-בריאות הצינור)

> **עיקרון-יסוד:** המוניטור בודק את **הצינור**, לא את **התוכן**. הוא מוודא שהדאטה
> **נכנס / נבנה / יוצא** תקין — הוא **לא** מנקד, לא מפרש תוצאות, ולא נוגע
> בהתפלגות-ה-recovery. הצצה בהתפלגות-התוצאות = הצצת-edge אסורה; ה-edge מוכרע ב-M4
> בלבד (MASTERPLAN §5). כאן — קלטים תפעוליים בלבד.
>
> **READ-ONLY** מול ה-Google Sheet (רק `sheets_manager.read_rows`). הקובץ היחיד
> שנכתב הוא `health_log.jsonl` מקומי (append, לעקיבת-מגמות; ב-.gitignore).

## הרצה
```bash
# בוקר — "המערכת חיה ומוכנה ליום?"
uv run --with pytz --with pandas --with numpy --with yfinance --with exchange_calendars \
       --with finvizfinance --with requests --with gspread --with google-auth \
       python health_monitor.py --morning

# ערב — "האיסוף של היום נכנס תקין?" (כולל פילוח מה-נאסף היום)
uv run ... python health_monitor.py --evening

# דוח מלא (ללא תקציר מצב-ספציפי)
uv run ... python health_monitor.py
```
*(ה-venv של הפרויקט לא כולל את ה-deps — חובה `uv run --with …`. creds נטענים מ-`.env`.)*

## Exit codes (לחיווט cron/alert)
| code | משמעות | פעולה |
|------|--------|-------|
| **0** | ✅ בריא | כלום |
| **1** | ⚠️ אזהרה | לבדוק, לא דחוף |
| **2** | ❌ תקלה | לטפל (runbook למטה) |

ה-exit-code = החומרה המקסימלית מבין כל הבדיקות.

## 10 הבדיקות (5 עמודי-ניטור)

### עמוד טריות (Freshness)
1. **scanner-freshness** — ה-scan_date האחרון ב-watchlist == יום-המסחר האחרון הצפוי (XNYS; אחרי 18:30 ET נספר היום, אחרת אתמול). מפגר → **❌**.
2. **intraday-freshness** — יש שורות `source=intraday` מיום-המסחר הפתוח האחרון. שוק היה פתוח ואין → **⚠️**.
3. **sheet-freshness** — 6 הטאבים נגישים; טאב-ליבה (watchlist) ריק → **❌**.

### עמוד נפח/שלמות (Volume/Completeness)
4. **volume-anomaly** — מועמדים/יום בטווח-סביר (0 → ⚠️; חריג ×5/÷5 מהממוצע ההיסטורי כש-≥3 ימים → ⚠️).
5. **continuity** — אין ימי-מסחר חסרים בין ה-scan הראשון לאחרון (gap → **❌**). בודק רק בתוך תקופת-האיסוף הפעילה (לא לפני ההשקה).
6. **post-analysis-progress** — ספירת pending/ok/partial/halt; שורה תקועה ב-`pending_forward` אף שחלפו ימי-מסחר (אמורה כבר להבשיל) → **⚠️**.

### עמוד סכימה (Schema) — השמירה מבאג TAB_TIMESERIES
7. **schema-drift** — ה-header החי של כל טאב == הסכימה הצפויה (`config.WATCHLIST_HEADER` / `post_analysis_collector.HEADER` / `scanner.SUMMARY_HEADER` / `fundamentals.FUND_HEADER` / `catalyst.NEWS_HEADER` / `config.TIMESERIES_HEADER`). שדה חסר/עודף/סדר-שונה → **❌**. טאב ריק → דילוג (אינפורמטיבי).

### עמוד בריאות-שדות (Field health)
8. **field-completeness** — % שורות עם שדות-הקשר ריקים (`drop_kind`/`vix_level`/`prior_decline_20d_pct`). מעל 50% → **⚠️** (אולי scanner לא כותב).
9. **duplicates + sanity-bounds** — מפתח (scan_date,ticker) כפול → **❌**; ערך מחוץ-לטווח (price≤0 / rsi∉[0,100] / drop_pct_from_open>0) → **⚠️**.

### עמוד תפעול + זיהום (Ops)
10. **contamination-trend** — כמה `split_halt_flag=True` (contamination %). **מדווח כמגמה בלבד (תמיד ✅)** — תקין שקיים זיהום, רק עוקבים; ההחרגה בפועל ב-M4.

## Runbook — מה לעשות כשאדום
- **scanner-freshness ❌** — ה-EOD scanner לא רץ. בדוק GitHub Actions `daily.yml` (הרצה אחרונה/שגיאה) ואת ה-cron. הרצה ידנית: `python scanner.py`.
- **intraday-freshness ⚠️** — הסורק התוך-יומי לא רץ או `source` ריק. בדוק `intraday.yml` + ה-pinger ב-cron-job.org.
- **continuity ❌** — יום-מסחר חסר. בדוק אם ה-workflow נכשל באותו יום; אפשר השלמה: `python scanner.py --date YYYY-MM-DD`.
- **post-analysis-progress ⚠️ (תקועות)** — `post_analysis_collector` לא רץ. הרצה: `python post_analysis_collector.py`.
- **schema-drift ❌** — ה-header החי לא תואם לקוד. אם **חסרות עמודות חדשות** בלבד (כמו אחרי הוספת-שדות) — ייפתר אוטומטית בכתיבה הבאה של אותו collector (upsert כותב את ה-HEADER המלא); להאצה: הרץ את ה-collector הרלוונטי. אם יש **עמודות עודפות / סדר-שונה** — בדיקה ידנית (ייתכן שינוי-שם ידני ב-Sheet).
- **field-completeness ⚠️** — שדות-הקשר ריקים. לשורות ישנות: `python scanner.py --backfill-context`. לחדשות: ודא ש-scanner/gradual כותבים את השדות.
- **duplicates ❌** — מפתח כפול ב-watchlist. חריג (ה-upsert אמור למנוע) — בדיקה ידנית של ה-Sheet.

## health_log.jsonl
כל הרצה מוסיפה שורת-JSON: `{ts, mode, expected_last_scan, overall, checks:[{id,status}]}` — לעקיבת-מגמות לאורך זמן (למשל עלייה ב-contamination% או הישנות אזהרה).

## גבול קשיח
בקרה בלבד. **אין ניקוד / פירוש-תוצאות / המלצה / הצצת-edge.** ה-edge מוכרע ב-M4.
