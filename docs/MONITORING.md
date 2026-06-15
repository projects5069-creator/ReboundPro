# ReboundPro — Monitoring (בקרת-בריאות הצינור)

> **עיקרון-יסוד:** המוניטור בודק את **הצינור**, לא את **התוכן**. הוא מוודא שהדאטה
> **נכנס / נבנה / יוצא** תקין — הוא **לא** מנקד, לא מפרש תוצאות, ולא נוגע
> בהתפלגות-ה-recovery. הצצה בהתפלגות-התוצאות = הצצת-edge אסורה; ה-edge מוכרע ב-M4
> בלבד (MASTERPLAN §5). כאן — קלטים תפעוליים בלבד.
>
> **כמעט-READ-ONLY** מול ה-Google Sheet: כל טאבי-המחקר נקראים בלבד (`read_rows`).
> הטאב היחיד שהמוניטור **כותב** אליו הוא `health_log` — טאב-**בקרה** (לא נתוני-מחקר):
> שורה אחת לכל ריצה. בנוסף נכתב `health_log.jsonl` מקומי (append; ב-.gitignore).
> אם אין creds/Sheet — הכתיבה ל-Sheet מדלגת בשקט; ה-jsonl תמיד נכתב; הריצה לא נשברת.

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

## אוטומציה — `.github/workflows/health.yml` (3 ריצות/יום-חול)
| cron (UTC) | ET (EDT/EST) | flag | מטרה |
|------------|--------------|------|------|
| `0 13 * * 1-5` | 09:00 / 08:00 | `--morning` | לפני הפתיחה — "המערכת מוכנה ליום?" |
| `0 17 * * 1-5` | 13:00 / 12:00 | `--morning` | אמצע-מסחר — טריות/תקלות-intraday חיות |
| `30 23 * * 1-5` | 19:30 / 18:30 | `--evening` | אחרי הסגירה (~שעה אחרי daily.yml) — "האיסוף נכנס תקין?" |
- ה-flag נבחר אוטומטית לפי `github.event.schedule`. (אמצע-היום משתמש ב-`--morning` — הבדיקות זהות בכל המצבים; ה-mode משנה רק את הכותרת/תקציר, ו-`--evening` מוסיף פילוח-איסוף.)
- **מדיניות exit:** רק `exit=2` (תקלה) מכשיל את ה-run ושולח מייל-התראה מ-GitHub; `exit=1` (אזהרה) נרשם ל-`GITHUB_STEP_SUMMARY` אבל ה-run נשאר ירוק (כדי שאזהרות-legacy לא ישלחו מייל 3×/יום).
- הדוח המלא נכתב ל-**Actions → Summary** של כל ריצה.
- **הפעלה ידנית:** GitHub → Actions → *ReboundPro Health Monitor* → **Run workflow** → בחר `mode` (morning/evening) → Run. (`workflow_dispatch` — לבדיקה ראשונה בלי לחכות ל-cron.)
- אותם secrets/deps כמו `daily.yml`; לא נוגע ב-daily/intraday.

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

## health_log (טאב-בקרה ב-Sheet) + health_log.jsonl (מקומי)
- **טאב `health_log` ב-Sheet** (`config.HEALTH_LOG_HEADER`): שורה לכל ריצה — `run_at, mode, overall_status (healthy/warning/error), exit_code`, עמודה לכל אחת מ-10 הבדיקות עם ה-severity שלה (ok/warn/fail), ו-`summary_text`. key=`run_at` (append). זהו **הטאב היחיד שהמוניטור כותב** — שאר הטאבים read-only מהמוניטור.
- **`health_log.jsonl` מקומי**: `{ts, mode, expected_last_scan, overall, checks:[{id,status}]}` לכל ריצה (עקיבת-מגמות מקומית).

## דף System Health בדashboard (`pages/3_System_Health.py`)
קורא את טאב `health_log` ומציג (view-only, דרך `dashboard_common`):
- **באנר-סטטוס בעמוד-הבית** (`dashboard.py`): הריצה האחרונה — ✅/⚠️/❌, "בדיקה אחרונה לפני X", קישור-טקסט לדף. אם הבדיקה האחרונה >24ש' → דגל "הבקרה לא רצה לאחרונה" (בקרה-שלא-רצה = בעיה). אם אין health_log → "בקרה טרם רצה".
- **דף מלא:** מטריקות-על (סטטוס/exit/גיל/סה"כ ריצות) · גרף-מגמת `overall_status` לאורך זמן · טבלת-ריצות (חדש למעלה) עם סינון לפי mode ו-status.
- **בקרה תפעולית בלבד** — מציג מה הסוכן בדק ומתי, לא ניתוח-איכות-של-הנתונים ולא edge.

## גבול קשיח
בקרה בלבד. **אין ניקוד / פירוש-תוצאות / המלצה / הצצת-edge.** ה-edge מוכרע ב-M4.
