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

## אוטומציה — `.github/workflows/health.yml` (3 ריצות/יום-מסחר)
| cron (UTC) | ET (EDT/EST) | flag | מטרה |
|------------|--------------|------|------|
| `0 13 * * 1-5` | 09:00 / 08:00 | `--morning` | ~½ש' לפני הפתיחה — "המערכת מוכנה ליום?" |
| `30 17 * * 1-5` | 13:30 / 12:30 | `--morning` | אמצע-מסחר — טריות/תקלות-intraday חיות |
| `0 1 * * 2-6` | 21:00 / 20:00 (יום-ET קודם) | `--evening` | ~5ש' אחרי הסגירה (EOD בוודאי הסתיים) — "האיסוף נכנס תקין?" |
- **DOW של הערב (`2-6`, קריטי):** `01:00 UTC` של יום X = `21:00 ET` של יום X-1, אז הריצה הערבית רצה בשלישי–שבת UTC כדי לכסות מסחר של **שני–שישי**. `1-5` היה מחמיץ את ערב-שישי (נופל בשבת UTC) ומבזבז את "שני" (נופל בראשון ET, ללא מסחר).
- **הערת-DST:** ה-cron קבוע ב-UTC; ניו-יורק זזה שעה בין EDT (קיץ) ל-EST (חורף), אז היחס-לשוק זז שעה פעמיים בשנה — לא קריטי לבדיקת-בריאות. השעות **בפרו (UTC-5)**: 08:00 / 12:30 / 20:00.
- מעבר הערב מ-23:30 ל-01:00 UTC נותן ~5ש' (במקום שעה) אחרי daily.yml (22:30) — כדי ש-EOD מתעכב לא ידווח "חסר" בטעות.
- ה-flag נבחר אוטומטית לפי `github.event.schedule` (13:00+17:30 → `--morning`, 01:00 → `--evening`). הבדיקות זהות בכל המצבים; ה-mode משנה רק כותרת/תקציר, ו-`--evening` מוסיף פילוח-איסוף.
- **מדיניות exit:** רק `exit=2` (תקלה) מכשיל את ה-run ושולח מייל-התראה מ-GitHub; `exit=1` (אזהרה) נרשם ל-`GITHUB_STEP_SUMMARY` אבל ה-run נשאר ירוק (כדי שאזהרות-legacy לא ישלחו מייל 3×/יום).
- הדוח המלא נכתב ל-**Actions → Summary** של כל ריצה.
- **הפעלה ידנית:** GitHub → Actions → *ReboundPro Health Monitor* → **Run workflow** → בחר `mode` (morning/evening) → Run. (`workflow_dispatch` — לבדיקה ראשונה בלי לחכות ל-cron.)
- אותם secrets/deps כמו `daily.yml`; לא נוגע ב-daily/intraday.

### ⚠️ ה-trigger בפועל = pinger ב-cron-job.org (לא ה-cron הנייטיב של GitHub)
ה-`schedule` הנייטיב של GitHub Actions **לא יורה בריפו הזה** (אומת 2026-06-15: `event=schedule` total_count=0 ל-health/daily/intraday מאז יצירת הריפו — GitHub cron הוא best-effort ולא אמין, במיוחד בריפו חדש ובזמני `:00`). לכן ה-intraday מופעל דרך **pinger ב-cron-job.org** שקורא לנקודת-הקצה של `workflow_dispatch`, ויש להוסיף את **health** לאותו מנגנון. ה-`schedule` נשאר מוגדר ב-workflow כגיבוי לא-מזיק. ה-mode-selection (`Select mode by schedule`, שורה ~61) כבר נופל ל-`inputs.mode` כש-`github.event.schedule` ריק → אפס שינוי-קוד נדרש.

**3 ה-jobs ב-cron-job.org (אותו PAT/header של ה-intraday pinger; PAT עם הרשאת `Actions: read & write`):**

| job | שעה (UTC) | ימים | body `inputs.mode` |
|-----|-----------|------|--------------------|
| pre-open    | `13:00` | Mon–Fri (1-5) | `morning` |
| mid-session | `17:30` | Mon–Fri (1-5) | `morning` |
| post-close  | `01:00` | **Tue–Sat (2-6)** | `evening` |

לכל job ב-cron-job.org:
- **URL:** `https://api.github.com/repos/projects5069-creator/ReboundPro/actions/workflows/health.yml/dispatches`
- **Method:** `POST`
- **Timezone:** UTC · **Headers:** `Accept: application/vnd.github+json` · `Authorization: Bearer <PAT>` · `X-GitHub-Api-Version: 2022-11-28` · `User-Agent: reboundpro-pinger`
- **Body (post-close→`evening`):** `{"ref":"main","inputs":{"mode":"morning"}}`
- **DOW של ה-01:00 = 2-6** (שלישי–שבת UTC) — אותו היגיון כמו ה-cron: `01:00 UTC` של יום X = `21:00 ET` של X-1, כדי לכסות מסחר שני–שישי.

## 10 הבדיקות (5 עמודי-ניטור)

### עמוד טריות (Freshness)
1. **scanner-freshness** — ה-scan_date האחרון ב-watchlist == יום-המסחר האחרון הצפוי (XNYS; אחרי 18:30 ET נספר היום, אחרת אתמול). מפגר → **❌**.
2. **intraday-freshness** — **תלוי-שוק:** אם **היום** אינו יום-מסחר (סופ"ש/חג, XNYS) → **🌙 מצב-רגוע** (severity=ok, לא משפיע על exit) — "שוק סגור, לא צפוי intraday". אם **היום** יום-מסחר ויש שורות `source=intraday` → **✅**; יום-מסחר ו-0 שורות → **⚠️**. (כך "שוק סגור" לעולם לא מציג ⚠️ צהוב שמאמן את העין להתעלם.)
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
- **טאב `health_log` ב-Sheet** (`config.HEALTH_LOG_HEADER`): שורה לכל ריצה — `run_at, mode, overall_status (healthy/warning/error), exit_code`, עמודה לכל אחת מ-10 הבדיקות עם ה-severity שלה (ok/warn/fail), `summary_text`, ו-**`details_text`** (כל 10 שורות-ההסבר המלאות, מופרדות בשורה — מזין את ה-expander בדף). key=`run_at` (append). זהו **הטאב היחיד שהמוניטור כותב** — שאר הטאבים read-only מהמוניטור.
- **`health_log.jsonl` מקומי**: `{ts, mode, expected_last_scan, overall, checks:[{id,status}]}` לכל ריצה (עקיבת-מגמות מקומית).

## דף System Health בדashboard (`pages/3_System_Health.py`)
קורא את טאב `health_log` ומציג (view-only, דרך `dashboard_common`):
- **באנר-סטטוס בעמוד-הבית** (`dashboard.py`): הריצה האחרונה — ✅/⚠️/❌, "בדיקה אחרונה לפני X", קישור-טקסט לדף. אם הבדיקה האחרונה >24ש' → דגל "הבקרה לא רצה לאחרונה" (בקרה-שלא-רצה = בעיה). אם אין health_log → "בקרה טרם רצה".
- **דף מלא:** מטריקות-על (סטטוס/exit/גיל/סה"כ ריצות) · גרף-מגמת `overall_status` לאורך זמן · טבלת-ריצות (חדש למעלה) עם סינון לפי mode ו-status · **expander "פירוט מלא לכל ריצה"** — לחיצה על ריצה פותחת את כל 10 הבדיקות עם אייקון + הסבר מלא (מ-`details_text`), כולל 🌙 ל"שוק סגור". כך רואים בדיוק מה הסוכן בדק ומצא בכל בדיקה.
- **בקרה תפעולית בלבד** — מציג מה הסוכן בדק ומתי, לא ניתוח-איכות-של-הנתונים ולא edge.

## גבול קשיח
בקרה בלבד. **אין ניקוד / פירוש-תוצאות / המלצה / הצצת-edge.** ה-edge מוכרע ב-M4.
