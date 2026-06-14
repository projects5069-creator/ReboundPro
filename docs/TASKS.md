# ReboundPro — Tasks

## ✅ DONE
- **M0** — נעילת אסטרטגיה + קריטריון M4.
- **M1** — EOD collector (scanner + post_analysis).
- **M2** — intraday scanner + market-hours guard + fundamentals + news.
- **Dashboard** — פרוס (Streamlit Cloud).
- **cron-job.org** — פעיל (טריגר intraday).
- **קריטריון M4** — נעול (pre-registration).
- **M3.1 — מעקב מדורג** (`intraday_timeseries.py` + טאב `intraday_timeseries`): שורת-זמן לכל מניה במעקב, רזולוציה מדורגת D0–D3 כל 10ד' / D4–D20 ~3 נק'/יום (open/mid/close), key=(scan_date,ticker,timestamp), upsert בטוח לריצה-חוזרת, רוכב על טריגר ה-intraday הקיים. לא נוגע ב-post_analysis. צעד נוסף ב-`intraday.yml`.
- **M3.2 — כרטיס מניה** (טאב "🃏 Stock Card" ב-dashboard): בחירת ticker+scan_date · גרף intraday_timeseries (price/pct) · תוצאות forward מ-post_analysis · תעודת-זהות פונדמנטלית בסגנון Finviz (Valuation/Margins/Debt/Short/52W/Ownership) · חדשות מ-news_snapshot. view-only.
- **M3.3 — תיקוני-תצוגה רוחביים**: `%` בתא · פסיקי-אלפים · עיגול 2-ספרות (helper `styled()` עם Styler) · חשיפת שדות-המסלול התוך-יומי ב-watchlist (first_cross_*/intraday_low*/recovery_from_low_pct/reversal_confirmed/scans_count/last_update_at).
- **M3.4 — gradual_drop** (`gradual_scanner.py` + צעד ב-daily.yml): מקור-איסוף **נפרד** לצניחה הדרגתית — close היום ≥10% מתחת ל-close לפני 5 ימי-מסחר (מסנן Finviz `Performance: Week -10%`, אומת מול yfinance), אותה רצפת-נזילות. עמודה חדשה `drop_kind` (intraday_drop/gradual_drop, migration-safe) + שדות gradual (lookback_trading_days/drop_pct_window/ref_close_window). דדופ/cooldown חוצה-סוגים = 20 ימי-מסחר. מעקב-קדימה (intraday_timeseries/post_analysis) + שכבות point-in-time (fundamentals/news) נקלטים אוטומטית — אותה תשתית. dashboard: סינון+תצוגה לפי drop_kind. **אזהרת value-trap מתועדת — פונדמנטלי כפיצ'ר לא פילטר; אפס החלטת-כניסה; הכרעה ל-M4.**
- **M3.5 — dashboard multipage** (פיצול ויזואלי לפי drop_kind): Streamlit multipage אמיתי — entrypoint `dashboard.py` (דף-בית: פילוח+totals), `pages/1_Intraday_Drop.py` + `pages/2_Gradual_Drop.py`, כל דף = הסט המלא של 5 הטאבים מסונן מראש להשערה אחת (אין multiselect של drop_kind בדפים). כל הלוגיקה ב-`dashboard_common.py` משותף (אפס כפילות; הדפים = קריאת `render(drop_kind,…)`). דף Intraday מציג drop_pct_from_open+שדות-מסלול; דף Gradual מציג drop_pct_window+lookback+ref_close_window. coalesce ל-intraday_drop ל-legacy. תצוגה בלבד.
- **M3.6 — שני מדדי-איסוף תיאוריים** (לשתי ההשערות, **פיצ'רים בלבד — לא אותות-כניסה**; ההכרעה אם מנבאים נדחית ל-M4): (1) **recovery-from-trough** ב-`post_analysis_collector.py` — `trough_price`/`trough_day`/`recovery_from_trough_pct`/`max_recovery_from_trough_pct` (היפוך מהשפל, מחושב מאותו forward-history שכבר נמשך). (2) **prior-decline context** ב-watchlist (`scanner.py`+`gradual_scanner.py`) — `pct_from_52w_high`/`pct_from_52w_low`/`prior_decline_20d_pct`/`prior_decline_60d_pct` (מחושב מאותה yfinance-history; הורחב חלון ל-`EOD_HISTORY_DAYS=400` כדי לכסות 52ש'+60 ימי-מסחר, ללא קריאות-רשת נוספות). עמודות migration-safe (append). dashboard מציג: Post-Analysis→trough, Watchlist+Stock-Card→prior-decline. **הערה: שדות intraday-live (source=intraday) לא נושאים prior-decline — רק EOD-capture + gradual (כפי המפרט).**

## ▶ NOW (M3 — צבירה)
- לצבור דאטה (forward, בזמן-אמת).
- להציץ בדashboard מדי פעם לבריאות-הצנרת.

## ⛔ BLOCKED עד M4=go
- מנוע ניקוד/החלטה.
- סיווג-קטליסט LLM.
- אות כניסה/יציאה.

## 🚪 M4 (כששער-הדאטה מתקיים)
- להריץ פסיקת Phase-0 מול קריטריון הנטישה (MASTERPLAN §5).

## 👁 WATCH
- התקדמות לעבר: ≥200 אירועים מושלמים · ≥6 חודשים · ≥חודש SPY שלילי.

## 📦 BACKLOG
- **פיצול Google Sheets חודשי / מעבר ל-DB** — טריגר: כשטאב כלשהו (בעיקר `intraday_timeseries`, שגדל מהר) עובר ~50k שורות או צובר חודשיים נתונים. שקול רוטציה חודשית (כמו RidingHigh) או מעבר ל-DB.
