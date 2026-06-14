# ReboundPro — Project Knowledge (זיכרון תפעולי)

*זהו הזיכרון התפעולי — עובדות-קרקע על המערכת כפי שהיא בפועל. אסטרטגיה יציבה ב-MASTERPLAN; משימות ב-TASKS; היסטוריה ב-ACTIONS_LOG.*
*עודכן: 2026-06-14 · אבן-דרך נוכחית: **M3 (צבירה)**.*

## בשורה אחת
מערכת מחקר long (סימולציה בלבד) שתופסת point-in-time מניות NASDAQ+NYSE נזילות שצנחו ≥10% תוך-יומי, ואוספת תוצאות D1..D+20 כדי להכריע ב-M4 אם קיים יתרון נטו. אין מנוע מסחר עד M4=go.

## Repo & אחסון
- **Repo:** `projects5069-creator/ReboundPro` (פרטי).
- **Google Sheet:** `ReboundPro-Data` · ID `17HnxKlpFMrUGd1Hemg4s-_XipSRSqkIVIJdzkvjn_f4` · owner `projects5069@gmail.com`.
- **Service account:** `ridinghigh-sheets-v2@ridinghigh-pro-v2.iam.gserviceaccount.com` (Editor על ה-Sheet). ה-SA **לא** יכול ליצור Sheets (Drive quota) — ה-Sheet נוצר ידנית ושותף.
- **6 טאבי-דאטה:** `watchlist_live` · `daily_summary` · `fundamentals_snapshot` · `news_snapshot` · `post_analysis` · `intraday_timeseries` (M3). (`Sheet1` = ברירת-מחדל ריקה.)

## Secrets (GitHub Actions — שמות בלבד)
`GOOGLE_CREDENTIALS_JSON` · `APCA_API_KEY_ID` · `APCA_API_SECRET_KEY` · `REBOUND_SHEET_ID` · `FINNHUB_API_KEY`.
מקומית: `.env` + `google_credentials.json` (gitignored). Streamlit Cloud: `st.secrets` (`[gcp_service_account]` + `REBOUND_SHEET_ID`); קובץ עזר מקומי `streamlit_cloud_secrets.toml` (gitignored).

## אינוונטר קבצים (קוד)
| קובץ | תפקיד |
|------|-------|
| `scanner.py` | EOD: Finviz→רצפת-נזילות→snapshot+regime→`watchlist_live`; כותב `daily_summary` + `fundamentals_snapshot` inline |
| `intraday_scanner.py` | intraday ~10ד': מסלול תוך-יומי + dedup; `is_market_hours()` guard |
| `fundamentals.py` | Finviz quote ~89 שדות → `fundamentals_snapshot` (raw+`_num`) |
| `catalyst.py` | Finnhub news D-3..D + earnings-flag → `news_snapshot` (raw בלבד) |
| `post_analysis_collector.py` | D1..D+20 + תת-חלונות D+3/5/10/20; halt/delist/pending מפורש |
| `intraday_timeseries.py` | M3 מעקב מדורג → `intraday_timeseries`: D0–D3 כל 10ד', D4–D20 ~3/יום (open/mid/close); key=(scan_date,ticker,timestamp); self-gating לחלונות D4–D20 (עמיד לדריפט-cron); רוכב על טריגר ה-intraday; floor יורש מ-watchlist; hours-guard מ-`intraday_scanner` |
| `gradual_scanner.py` | M3 סורק-EOD **השערה נפרדת** (`gradual_drop`): close היום ≥10% מתחת ל-close לפני 5 ימי-מסחר (מסנן Finviz `Performance: Week -10%` + אימות yfinance); אותה רצפת-נזילות; מתייג `drop_kind="gradual_drop"`, `source="gradual_eod"`; דדופ חוצה-סוגים 20 ימי-מסחר (`recent_capture_set`); משתמש ב-helpers של `scanner.py` ללא נגיעה בו; קורא fundamentals inline. **value-trap: פונדמנטלי=פיצ'ר לא פילטר; אפס החלטת-כניסה; הכרעה ל-M4.** post_analysis/intraday_timeseries/catalyst קולטים את השורות אוטומטית |
| `sheets_manager.py` | I/O ל-Sheets; `upsert_by_key` (merge לפי שם-עמודה, migration-safe); creds: file→st.secrets→env |
| `config.py` | מקור-אמת לפרמטרים/טאבים/סכמות (כולל `TIMESERIES_HEADER`, `TS_TIER1_MAX_DAY=3`, `TS_TIER2_MAX_DAY=20`) |
| `dashboard.py` | Streamlit, תצוגה בלבד (Health/Watchlist/**Stock Card**/Post/Stats); helper `styled()` לעיצוב (`%` בתא/פסיקים/2-ספרות) |

## תזמון
- `daily.yml` — EOD `30 22 * * 1-5` UTC: scanner → **gradual_scanner** → catalyst → post_analysis. (gradual רץ אחרי scanner כדי שדדופ אותו-יום יעבוד, ולפני catalyst/post כדי שחדשות+forward יקלטו את שורות gradual.)
- `intraday.yml` — `*/10 13-21 * * 1-5` UTC (baseline) + `workflow_dispatch`. הטריגר האמין: **cron-job.org** → workflow_dispatch (America/New_York 9–16, כל 10ד'); ה-guard `is_market_hours()` הוא רשת-ביטחון. שני צעדים: `intraday_scanner.py` ואז `intraday_timeseries.py` (מעקב מדורג).

## Dashboard
Streamlit Cloud, נפרס מ-`dashboard.py` (branch `main`). Cloud מתקין מ-`uv.lock`. *(URL: למלא לאחר אישור הפריסה ב-share.streamlit.io עבור `projects5069-creator/ReboundPro`.)*
- **5 לשוניות:** Collection Health · Watchlist · **Stock Card** (כרטיס-מניה: גרף intraday_timeseries + post_analysis + תעודת-זהות פונדמנטלית בסגנון Finviz + חדשות) · Post-Analysis · Descriptive Stats. הכל view-only.
- **תיקוני-תצוגה (M3):** helper `styled()` (pandas Styler) — `%` בתא, פסיקי-אלפים, עיגול 2-ספרות; שדות-המסלול התוך-יומי חשופים בטבלת ה-watchlist.

## המספרים המרכזיים
- **שתי השערות נאספות בנפרד** (עמודה `drop_kind` ב-watchlist_live): `intraday_drop` (צניחה חדה תוך-יומית, scanner+intraday_scanner) ו-`gradual_drop` (ירידה הדרגתית ≥10% ב-5 ימי-מסחר, gradual_scanner). `source` נשאר provenance (eod_close/intraday/gradual_eod). דדופ חוצה-סוגים: 20 ימי-מסחר. שורות legacy ללא drop_kind נחשבות intraday_drop בדashboard.
- רצפת-נזילות: מחיר ≥ $5 · ADV$ ≥ $5M · שווי ≥ $300M (מוציא nano/micro).
- סף צניחה: ≥10% מהפתיחה (grid M4: 7/10/15) · סף gradual: ≥10% ב-5 ימי-מסחר.
- חלון תוצאות: D1..D+20 (+ תת-חלונות 3/5/10/20).
- עלות-סטרס M4: 0.50% round-trip.

## קונבנציות עבודה
- **סודות לעולם לא מודפסים** (חילוץ דרך קובץ/stdin בלבד).
- **time-check** לפני כל פעולה רגישת-זמן (יום-מסחר/שעות/D+N/cron); cron ב-UTC, שעות-שוק ב-ET.
- **מנדט-סקילים:** סריקת כל הסקילים + שימוש בכמה שרלוונטיים; פתיחה בסריקה, סגירה ברשימת-שימוש.
- **Handoff:** פרומפט בבלוק-העתקה אחד; recap בסוף; `upsert` בטוח לריצה-חוזרת.
- **גבול M5:** אין ניקוד/אותות/דירוג/המלצות עד M4=go.
