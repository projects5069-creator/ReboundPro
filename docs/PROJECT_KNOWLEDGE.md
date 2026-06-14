# ReboundPro — Project Knowledge (זיכרון תפעולי)

*זהו הזיכרון התפעולי — עובדות-קרקע על המערכת כפי שהיא בפועל. אסטרטגיה יציבה ב-MASTERPLAN; משימות ב-TASKS; היסטוריה ב-ACTIONS_LOG.*
*עודכן: 2026-06-14 · אבן-דרך נוכחית: **M3 (צבירה)**.*

## בשורה אחת
מערכת מחקר long (סימולציה בלבד) שתופסת point-in-time מניות NASDAQ+NYSE נזילות שצנחו ≥10% תוך-יומי, ואוספת תוצאות D1..D+20 כדי להכריע ב-M4 אם קיים יתרון נטו. אין מנוע מסחר עד M4=go.

## Repo & אחסון
- **Repo:** `projects5069-creator/ReboundPro` (פרטי).
- **Google Sheet:** `ReboundPro-Data` · ID `17HnxKlpFMrUGd1Hemg4s-_XipSRSqkIVIJdzkvjn_f4` · owner `projects5069@gmail.com`.
- **Service account:** `ridinghigh-sheets-v2@ridinghigh-pro-v2.iam.gserviceaccount.com` (Editor על ה-Sheet). ה-SA **לא** יכול ליצור Sheets (Drive quota) — ה-Sheet נוצר ידנית ושותף.
- **5 טאבי-דאטה:** `watchlist_live` · `daily_summary` · `fundamentals_snapshot` · `news_snapshot` · `post_analysis`. (`Sheet1` = ברירת-מחדל ריקה.)

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
| `sheets_manager.py` | I/O ל-Sheets; `upsert_by_key` (merge לפי שם-עמודה, migration-safe); creds: file→st.secrets→env |
| `config.py` | מקור-אמת לפרמטרים/טאבים/סכמות |
| `dashboard.py` | Streamlit, תצוגה בלבד (Health/Watchlist/Post/Stats) |

## תזמון
- `daily.yml` — EOD `30 22 * * 1-5` UTC: scanner → catalyst → post_analysis.
- `intraday.yml` — `*/10 13-21 * * 1-5` UTC (baseline) + `workflow_dispatch`. הטריגר האמין: **cron-job.org** → workflow_dispatch (America/New_York 9–16, כל 10ד'); ה-guard `is_market_hours()` הוא רשת-ביטחון.

## Dashboard
Streamlit Cloud, נפרס מ-`dashboard.py` (branch `main`). Cloud מתקין מ-`uv.lock`. *(URL: למלא לאחר אישור הפריסה ב-share.streamlit.io עבור `projects5069-creator/ReboundPro`.)*

## המספרים המרכזיים
- רצפת-נזילות: מחיר ≥ $5 · ADV$ ≥ $5M · שווי ≥ $300M (מוציא nano/micro).
- סף צניחה: ≥10% מהפתיחה (grid M4: 7/10/15).
- חלון תוצאות: D1..D+20 (+ תת-חלונות 3/5/10/20).
- עלות-סטרס M4: 0.50% round-trip.

## קונבנציות עבודה
- **סודות לעולם לא מודפסים** (חילוץ דרך קובץ/stdin בלבד).
- **time-check** לפני כל פעולה רגישת-זמן (יום-מסחר/שעות/D+N/cron); cron ב-UTC, שעות-שוק ב-ET.
- **מנדט-סקילים:** סריקת כל הסקילים + שימוש בכמה שרלוונטיים; פתיחה בסריקה, סגירה ברשימת-שימוש.
- **Handoff:** פרומפט בבלוק-העתקה אחד; recap בסוף; `upsert` בטוח לריצה-חוזרת.
- **גבול M5:** אין ניקוד/אותות/דירוג/המלצות עד M4=go.
