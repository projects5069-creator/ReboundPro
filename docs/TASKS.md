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
