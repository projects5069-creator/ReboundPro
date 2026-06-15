# ReboundPro — PROJECT STATE

**עודכן:** 2026-06-14 · **שלב:** אגף איסוף/תצוגה **חי** (M1–M4 collect); מנוע ההחלטה ממתין

## מה חי עכשיו
- ✅ **Repo:** `projects5069-creator/ReboundPro` (פרטי). Sheet: `ReboundPro-Data` (משותף עם ה-SA `reboundpro-sheets@reboundpro-v1` — project GCP עצמאי `reboundpro-v1`, הופרד מ-RidingHigh ב-2026-06-15 לפתרון 429).
- ✅ **EOD scanner** (`scanner.py`) — Finviz→רצפת-נזילות קשיחה→snapshot point-in-time + regime → `watchlist_live`; כותב גם `daily_summary` (בריאות-איסוף) + `fundamentals_snapshot` inline.
- ✅ **Intraday scanner** (`intraday_scanner.py`) — כל ~10 דק' בשעות-שוק (guard `is_market_hours`), מסלול תוך-יומי (first-cross/intraday-low/recovery/reversal) עם dedup merge-by-key.
- ✅ **Fundamentals** (`fundamentals.py`) — Finviz quote (~89 שדות) → `fundamentals_snapshot`, raw+`_num`, רמות primary/peripheral (config).
- ✅ **News/catalyst** (`catalyst.py`) — Finnhub company-news (D-3..D) + earnings-flag → `news_snapshot`; EOD, raw בלבד.
- ✅ **post_analysis** (`post_analysis_collector.py`) — D1..D+20 + תת-חלונות D+3/5/10/20; halt/delist/pending מפורש.
- ✅ **Dashboard** (`dashboard.py`, Streamlit) — תצוגה בלבד: Collection Health (כולל `daily_summary`), Watchlist, Post-Analysis, Descriptive Stats. תומך local + Streamlit Cloud (`st.secrets`).
- ✅ **תזמון:** `daily.yml` (EOD 22:30 UTC: scanner→catalyst→post_analysis) · `intraday.yml` (cron */10 + workflow_dispatch ל-cron-job.org).
- ✅ **Secrets (GitHub Actions):** GOOGLE_CREDENTIALS_JSON · APCA_API_KEY_ID · APCA_API_SECRET_KEY · REBOUND_SHEET_ID · FINNHUB_API_KEY.

## טאבים ב-Sheet
`watchlist_live` · `daily_summary` · `fundamentals_snapshot` · `news_snapshot` · `post_analysis`.

## ממתין (M5 — לא לבנות עד הכרעת M4)
- ⬜ Phase 0 / harness לבדיקת יתרון נטו (ראה ביקורת ב-`docs/`); הכרעת go/no-go.
- ⬜ סיווג קטליסט (LLM) מהכותרות השמורות ב-`news_snapshot`.
- ⬜ מנוע ניקוד/החלטה/אותות — **חסום** עד M5.
- ⬜ פעלת cron-job.org בפועל (pinger ל-`intraday.yml`).

## החלטות שאושרו
- שם ReboundPro · יקום NASDAQ+NYSE · סף 10% מהפתיחה · ספק חינמי (Finviz+yfinance+Finnhub); Polygon minute-bars = שדרוג דיוק עתידי.
- timezone: שעון-שוק לפי ET (DST) דרך לוח NYSE; cron ב-UTC.

## לקחים מיובאים
- מדד חסר קורלציה לא נכנס לניקוד (RidingHigh: Score r≈-0.07).
- יישור עמודות ב-Sheets — מקור באגים; משתמשים ב-`upsert_by_key` (merge לפי שם-עמודה, migration-safe).
- survivorship: לספור halts/delistings כתוצאה, לא להשמיט.
- סודות לעולם לא מודפסים; `.env`+`google_credentials.json` gitignored.
