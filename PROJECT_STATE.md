# ReboundPro — PROJECT STATE

**עודכן:** 2026-06-16 · **שלב:** **M3 צבירה** (~77+ אירועים מתוך יעד 200 · scan_dates 6/12,6/15,6/16) · אגף איסוף/תצוגה **חי** (M1–M4 collect); מנוע ההחלטה (M5) ממתין להכרעת M4

## מה חי עכשיו
- ✅ **Repo:** `projects5069-creator/ReboundPro` (פרטי). Sheet: `ReboundPro-Data` (משותף עם ה-SA `reboundpro-sheets@reboundpro-v1` — project GCP עצמאי `reboundpro-v1`, הופרד מ-RidingHigh ב-2026-06-15 לפתרון 429).
- ✅ **EOD scanner** (`scanner.py`) — Finviz→רצפת-נזילות קשיחה→snapshot point-in-time + regime → `watchlist_live`; כותב גם `daily_summary` (בריאות-איסוף) + `fundamentals_snapshot` inline.
- ✅ **Intraday scanner** (`intraday_scanner.py`) — כל ~10 דק' בשעות-שוק (guard `is_market_hours`), מסלול תוך-יומי (first-cross/intraday-low/recovery/reversal) עם dedup merge-by-key.
- ✅ **Gradual scanner** (`gradual_scanner.py`) — **השערה נפרדת** מ-intraday_drop: close היום ≤ -10% מול הסגירה לפני **5 ימי-מסחר** (`GRADUAL_LOOKBACK_DAYS`), אותה רצפת-נזילות קשיחה, point-in-time → `watchlist_live` עם `drop_kind="gradual_drop"` (`source="gradual_eod"`) + `fundamentals_snapshot` inline. דה-דופ: דילוג אם הטיקר נתפס (כל `drop_kind`) ב-20 ימי-מסחר אחרונים (`GRADUAL_DEDUP_WINDOW`) — cross-strategy dedup (intraday_drop זוכה, רץ קודם) + gradual self-cooldown. נאסף ונבדק **בנפרד** מ-intraday_drop ב-M4 (MASTERPLAN §5). ✅ `drop_kind`+`source` נישאים כעת גם ל-`post_analysis` ול-`forward_daily` (P1, commit a8ab776 — going-forward + backfill חי שאומת: post 46/49, forward 57/38, 0 ריקים), כך שהפרדת ההשערות לא תלויה עוד ב-join.
- ✅ **Fundamentals** (`fundamentals.py`) — Finviz quote (~89 שדות) → `fundamentals_snapshot`, raw+`_num`, רמות primary/peripheral (config).
- ✅ **News/catalyst** (`catalyst.py`) — Finnhub company-news (D-3..D) + earnings-flag → `news_snapshot`; EOD, raw בלבד.
- ✅ **post_analysis** (`post_analysis_collector.py`) — D1..D+20 + תת-חלונות D+3/5/10/20; halt/delist/**forward_pending** מפורש (סיווג מתוקן 6/16). כותב גם **`forward_daily`** (סדרה יומית D+1..D+N) — חיווט-auto בריצה הרגילה (post קודם → forward_daily מבודד ב-try/except).
- ✅ **Dashboard** (`dashboard.py`, Streamlit) — תצוגה בלבד: Collection Health (כולל `daily_summary`), Watchlist, Post-Analysis, Descriptive Stats. תומך local + Streamlit Cloud (`st.secrets`).
- ✅ **תזמון:** `daily.yml` (EOD 22:30 UTC: scanner→**gradual_scanner**→catalyst→post_analysis; gradual אחרי scanner ל-dedup same-day ולפני catalyst+post כדי ש-news+forward מרימים אותו) · `intraday.yml` (cron */10 + workflow_dispatch ל-cron-job.org). הערה: יעד ~200 האירועים מתפצל כעת לשתי השערות (intraday_drop + gradual_drop), כל אחת נצברת ונבדקת בנפרד.
- ✅ **Secrets (GitHub Actions):** GOOGLE_CREDENTIALS_JSON · APCA_API_KEY_ID · APCA_API_SECRET_KEY · REBOUND_SHEET_ID · FINNHUB_API_KEY.

## טאבים ב-Sheet
`watchlist_live` · `daily_summary` · `fundamentals_snapshot` · `news_snapshot` · `post_analysis` · **`forward_daily`** (D+1..D+20) · `health_log` (בקרה).

## 2026-06-16 — סשן אחרון (M3 + infra + UX)
- **forward_daily חי:** טאב חדש (long; D+1..D+20 לכל אירוע: `cum_pct_from_ref`/`daily_change_pct`/high/low). נכתב **אוטומטית** בריצת-post היומית (חיווט-auto: post-first → forward_daily מבודד ב-try/except). backfill ידני בוצע (**81 שורות / 72 אירועים**).
- **תיקון wipe-bug** (`sheets_manager`): `upsert_*` עברו ל-`_write_matrix` — **update-first בלי clear מקדים** + **sanitize floats** (inf/NaN→""). מנע הישנות מחיקת-watchlist (TDD + אומת-חי: $LILKV נכתב נקי). watchlist שוחזר מ-version-history (72 שורות).
- **תיקון over-flagging** (post): `completed_forward_sessions` (סופר רק סשנים שנסגרו) + `classify_status` (forward_pending מול delisted אמיתי). false-positive **49→0** (אומת-חי).
- **דשבורד — תבנית `reboundpro` אחידה:** 15 גרפים דרך `plot()` wrapper (modebar off), קווי-רשת דקים, ברים ירוק/אדום (sign), הגרף הכחול (תת-חלון) הוסר. כרטיס-המניה: מסלול forward_daily עם תאריכים-אמיתיים + תוויות-% + נקודת-D0 צהובה.
- **טסטים:** 46/46 · **commit אחרון:** `c1b0fc7` · **redeploy-marker:** 2026-06-16f.
- **🟡 פתוח/דחוי:** **dead-man חיצוני** (healthchecks.io ל-daily+health) — קוד ה-heartbeat ב-workflows **בוצע** (מוגן ב-secret; ראה MONITORING.md §Dead-man), **נותרה הקמת-UI חיצונית**: 2 checks + secrets `HC_PING_DAILY`/`HC_PING_HEALTH` (צ'קליסט ב-MONITORING.md). עתידי: **H3** intraday-WARN-ללא-מייל (escalation סטייטפולי), dead-man ל-intraday. שאר פתוחים: תזמון post (לא פרה-מרקט); הסרת ה-SA הישן של RidingHigh מה-Sheet (אחרי תקופת-יציבות).
- **⏳ ממתין-אימות-פסיבי:** ריצת EOD הערב (~21:30 UTC) צריכה לכתוב `forward_daily` אוטומטית — זה האימות-החי של החיווט-auto (forward_daily יגדל מ-81; offsets חדשים שהבשילו).

## ממתין (M5 — לא לבנות עד הכרעת M4)
- ⬜ Phase 0 / harness לבדיקת יתרון נטו (ראה ביקורת ב-`docs/`); הכרעת go/no-go.
- ⬜ סיווג קטליסט (LLM) מהכותרות השמורות ב-`news_snapshot`.
- ⬜ מנוע ניקוד/החלטה/אותות — **חסום** עד M5.
- ✅ pinger ל-`intraday.yml` פעיל ב-cron-job.org (כל 10 דק'; ה-cron הנייטיב לא אמין). 🟡 pinger ל-`health.yml`/`daily.yml` טרם הוקם.

## החלטות שאושרו
- שם ReboundPro · יקום NASDAQ+NYSE · סף 10% מהפתיחה · ספק חינמי (Finviz+yfinance+Finnhub); Polygon minute-bars = שדרוג דיוק עתידי.
- timezone: שעון-שוק לפי ET (DST) דרך לוח NYSE; cron ב-UTC.

## לקחים מיובאים
- מדד חסר קורלציה לא נכנס לניקוד (RidingHigh: Score r≈-0.07).
- יישור עמודות ב-Sheets — מקור באגים; משתמשים ב-`upsert_by_key` (merge לפי שם-עמודה, migration-safe).
- survivorship: לספור halts/delistings כתוצאה, לא להשמיט.
- סודות לעולם לא מודפסים; `.env`+`google_credentials.json` gitignored.
