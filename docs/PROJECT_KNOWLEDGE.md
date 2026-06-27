# ReboundPro — Project Knowledge (זיכרון תפעולי)

*זהו הזיכרון התפעולי — עובדות-קרקע על המערכת כפי שהיא בפועל. אסטרטגיה יציבה ב-MASTERPLAN; משימות ב-TASKS; היסטוריה ב-ACTIONS_LOG.*
*עודכן: 2026-06-26 · אבן-דרך נוכחית: **M3 (צבירה)**.*
*ספירת-אירועים חיה (אומת 2026-06-26 מה-Sheet): **527** ב-`watchlist_live` (150 `intraday_drop` + 377 `gradual_drop`); `post_analysis` = 478 partial + 49 pending_forward. בשלות-forward עדיין מוקדמת (frontier ~D+5–9; אף אירוע טרם הגיע D+10).*
*מחקר-אופק (Horizon-Sufficiency C0) — **CONCLUDED (proxy; אישור-חי ממתין לבשלות)**: על subset-שורד יחיד (n=241,962 mid+high) **SUFFICIENT — by-default** (B2 median cum_pct שטוח ~0, לא מטפס מעבר D+20; proxy גבול-עליון, לא עדות-להיפוך). **B1 (δ של atr_pct) ממשיך לטפס מעבר D+20** (→ −0.165 ב-D+90) = תצפית feature-quality תיאורית (M5-adjacent), מוחנה לשאלה-עתידית-נפרדת — לא שינוי-חלון. `POST_ANALYSIS_HORIZON` ללא-שינוי; M5 נשמר.*
*`fundamentals_snapshot` — כיסוי-forward נמוך (Finviz **burst-throttle** בריצת-ה-EOD → `'NoneType'...find_all'`; **לא** חסימת-IP — ה-intraday low-burst מקבל ~79% מאותו datacenter-IP). **B1 (retry/backoff) נכשל והחמיר:** retries=4 הגדיל burst → EOD 6/26 ירד **50%→0%** (gradual+intraday 0/65). **GATE-A (27/6):** ניסיון-יחיד (`FINVIZ_FETCH_RETRIES=1`) + pacing איטי (`FINVIZ_FETCH_SLEEP=6.0`+jitter, ~7–8min לריצה) + תקציב per-run — הכיוון הוא **פחות-burst**. **אימות ממתין ל-EOD של יום-ב'** (שבת/א' שוק סגור). **הכיסוי ההיסטורי אינו בר-שחזור** — re-fetch מחזיר ערכים-נוכחיים על D0 ישן = look-ahead (לכן ללא backfill; `main()` חוסם תאריך-עבר ללא `--force`).*
*סייג Group C: הפרדת-fundamentals ל-**gradual מורעבת ולא-אמינה** עד שכיסוי-forward יצטבר (אחרי ש-GATE-A יאומת ביום-ב'); ה-היסטורי לא בר-שחזור-PIT.*

## בשורה אחת
מערכת מחקר long (סימולציה בלבד) שתופסת point-in-time מניות NASDAQ+NYSE נזילות שצנחו ≥10% תוך-יומי, ואוספת תוצאות D1..D+20 כדי להכריע ב-M4 אם קיים יתרון נטו. אין מנוע מסחר עד M4=go.

## Repo & אחסון
- **Repo:** `projects5069-creator/ReboundPro` (פרטי).
- **Google Sheet:** `ReboundPro-Data` · ID `17HnxKlpFMrUGd1Hemg4s-_XipSRSqkIVIJdzkvjn_f4` · owner `projects5069@gmail.com`.
- **Service account:** `reboundpro-sheets@reboundpro-v1.iam.gserviceaccount.com` (Editor על ה-Sheet), בפרויקט GCP **`reboundpro-v1`** (project number 737740780440). ה-SA **לא** יכול ליצור Sheets (Drive quota) — ה-Sheet נוצר ידנית ושותף. **הפרדת-מכסה (2026-06-15):** ReboundPro קיבל project+SA משלו, מנותק מ-RidingHigh Pro (שעד אז חלקנו איתו `ridinghigh-sheets-v2@ridinghigh-pro-v2` → תחרות על דלי 60-reads/min/user משותף → 429). כעת לכל מערכת דלי-מכסה עצמאי. ה-SA הישן הושאר משותף על ה-Sheet כגיבוי בלבד.
- **6 טאבי-דאטה:** `watchlist_live` · `daily_summary` · `fundamentals_snapshot` · `news_snapshot` · `post_analysis` · `intraday_timeseries` (M3). (`Sheet1` = ברירת-מחדל ריקה.) + **טאב-בקרה** `health_log` (M3-monitor — פלט הסוכן, לא נתוני-מחקר).

## Secrets (GitHub Actions — שמות בלבד)
`GOOGLE_CREDENTIALS_JSON` · `APCA_API_KEY_ID` · `APCA_API_SECRET_KEY` · `REBOUND_SHEET_ID` · `FINNHUB_API_KEY`.
מקומית: `.env` + `google_credentials.json` (gitignored). Streamlit Cloud: `st.secrets` (`[gcp_service_account]` + `REBOUND_SHEET_ID`); קובץ עזר מקומי `streamlit_cloud_secrets.toml` (gitignored).

## אינוונטר קבצים (קוד)
| קובץ | תפקיד |
|------|-------|
| `scanner.py` | EOD: Finviz→רצפת-נזילות→snapshot+regime→`watchlist_live`; כותב `daily_summary` + `fundamentals_snapshot` inline. helpers `atr_14`/`drop_in_atr` (פיצ'רים תיאוריים) + `--backfill-atr` (חד-פעמי) |
| `intraday_scanner.py` | intraday ~10ד': מסלול תוך-יומי + dedup; `is_market_hours()` guard |
| `fundamentals.py` | Finviz quote ~89 שדות → `fundamentals_snapshot` (raw+`_num`) |
| `catalyst.py` | Finnhub news D-3..D + earnings-flag → `news_snapshot` (raw בלבד) |
| `post_analysis_collector.py` | D1..D+20 + תת-חלונות D+3/5/10/20; halt/delist/pending מפורש; **recovery-from-trough** (היפוך מהשפל); **split/halt detector** (`detect_split_halt` → `split_halt_flag`/`split_halt_reason`, flag לא-הרסני); **reclaim/drop grid** (`reclaim_grid` → `config.RECLAIM_GRID_COLUMNS`, תיאורי) |
| `intraday_timeseries.py` | M3 מעקב מדורג → `intraday_timeseries`: D0–D3 כל 10ד', D4–D20 ~3/יום (open/mid/close); key=(scan_date,ticker,timestamp); self-gating לחלונות D4–D20 (עמיד לדריפט-cron); רוכב על טריגר ה-intraday; floor יורש מ-watchlist; hours-guard מ-`intraday_scanner` |
| `health_monitor.py` | M3 סוכן-בקרת-בריאות: 10 בדיקות-צינור / 5 עמודים (Freshness/Volume/Schema/Field/Ops); `--morning`/`--evening`; exit 0/1/2; כותב טאב-בקרה `health_log` ב-Sheet (היחיד שנכתב; שאר הטאבים read-only) + `health_log.jsonl` מקומי. **בקרת-קלטים בלבד — לא מנקד/מפרש/נוגע ב-recovery (לא edge).** schema-drift שומר מבאג TAB_TIMESERIES. ראה docs/MONITORING.md |
| `pages/3_System_Health.py` | דף-תקינות (view-only): היסטוריית-ריצות מ-`health_log` + גרף-מגמה + טבלה מסוננת; באנר-סטטוס בעמוד-הבית (`dashboard.py`). בקרה תפעולית בלבד |
| `gradual_scanner.py` | M3 סורק-EOD **השערה נפרדת** (`gradual_drop`): close היום ≥10% מתחת ל-close לפני 5 ימי-מסחר (מסנן Finviz `Performance: Week -10%` + אימות yfinance); אותה רצפת-נזילות; מתייג `drop_kind="gradual_drop"`, `source="gradual_eod"`; דדופ חוצה-סוגים 20 ימי-מסחר (`recent_capture_set`); משתמש ב-helpers של `scanner.py` ללא נגיעה בו; קורא fundamentals inline. **value-trap: פונדמנטלי=פיצ'ר לא פילטר; אפס החלטת-כניסה; הכרעה ל-M4.** post_analysis/intraday_timeseries/catalyst קולטים את השורות אוטומטית |
| `sheets_manager.py` | I/O ל-Sheets; `upsert_by_key` (merge לפי שם-עמודה, migration-safe); creds: file→st.secrets→env |
| `config.py` | מקור-אמת לפרמטרים/טאבים/סכמות (כולל `TIMESERIES_HEADER`, `TS_TIER1_MAX_DAY=3`, `TS_TIER2_MAX_DAY=20`) |
| `dashboard.py` | Streamlit **multipage** entrypoint = דף-בית (פילוח+totals לפי drop_kind). תצוגה בלבד |
| `dashboard_common.py` | **כל הלוגיקה המשותפת** של ה-dashboard (load/styled/FUND_GROUPS/column-sets/coalesce_kind/restrict + 5 פונקציות-טאב + `render(drop_kind,…)`); מיובא ע"י entrypoint ושני הדפים — אפס כפילות |
| `pages/1_Intraday_Drop.py` · `pages/2_Gradual_Drop.py` | דפי-השערה דקים: כל אחד קורא `render(drop_kind)` → 5 טאבים מסונן מראש לאותה השערה (אין multiselect drop_kind). Intraday=drop_pct_from_open+מסלול; Gradual=drop_pct_window+lookback+ref_close_window |

## תזמון
- `daily.yml` — EOD `30 22 * * 1-5` UTC: scanner → **gradual_scanner** → catalyst → post_analysis. (gradual רץ אחרי scanner כדי שדדופ אותו-יום יעבוד, ולפני catalyst/post כדי שחדשות+forward יקלטו את שורות gradual.)
- `intraday.yml` — `*/10 13-21 * * 1-5` UTC (baseline) + `workflow_dispatch`. הטריגר האמין: **cron-job.org** → workflow_dispatch (America/New_York 9–16, כל 10ד'); ה-guard `is_market_hours()` הוא רשת-ביטחון. שני צעדים: `intraday_scanner.py` ואז `intraday_timeseries.py` (מעקב מדורג).

## Dashboard
Streamlit Cloud, נפרס מ-`dashboard.py` (branch `main`). Cloud מתקין מ-`uv.lock`. **URL חי:** https://reboundpro-4zkxnuulodjqdgtnffyaqz.streamlit.app (אומת נגיש 2026-06-18, HTTP 303 — redirect wakeup של Streamlit Cloud).
- **Multipage (M3.5):** entrypoint `dashboard.py` = דף-בית; שני דפי-השערה ב-`pages/` (ניווט sidebar אוטומטי) — **⚡ Intraday Drop** ו-**🐢 Gradual Drop**. כל דף מציג את הסט המלא של 5 הלשוניות **מסונן מראש ל-drop_kind אחד** (הדף עצמו הוא הפילטר; אין multiselect של drop_kind). post/ts/fund/news מוגבלים למפתחות (scan_date,ticker) של אותו דף.
- **5 לשוניות (בכל דף):** Collection Health · Watchlist · Stock Card (intraday_timeseries + post_analysis + תעודת-זהות Finviz + חדשות) · Post-Analysis · Descriptive Stats. הכל view-only.
- **תיקוני-תצוגה:** helper `styled()` (pandas Styler) — `%` בתא, פסיקי-אלפים, עיגול 2-ספרות. תשתית-איסוף משותפת (אותו Sheet, אותם collectors) — רק התצוגה מפוצלת.
- **Streamlit Cloud:** entrypoint נשאר `dashboard.py`; תיקיית `pages/` לידו מתגלה אוטומטית; creds/SHEET_ID מ-`st.secrets`. אם Cloud מגיש cache ישן — Manage app → Reboot.

## המספרים המרכזיים
- **שתי השערות נאספות בנפרד** (עמודה `drop_kind` ב-watchlist_live): `intraday_drop` (צניחה חדה תוך-יומית, scanner+intraday_scanner) ו-`gradual_drop` (ירידה הדרגתית ≥10% ב-5 ימי-מסחר, gradual_scanner). `source` נשאר provenance (eod_close/intraday/gradual_eod). דדופ חוצה-סוגים: 20 ימי-מסחר. שורות legacy ללא drop_kind נחשבות intraday_drop בדashboard.
- רצפת-נזילות: מחיר ≥ $5 · ADV$ ≥ $5M · שווי ≥ $300M (מוציא nano/micro).
- סף צניחה: ≥10% מהפתיחה (grid M4: 7/10/15) · סף gradual: ≥10% ב-5 ימי-מסחר.
- **מדדי-איסוף תיאוריים (פיצ'רים, לא אותות-כניסה; הכרעה ל-M4):**
  - (M3.6) *recovery-from-trough* ב-post_analysis (`trough_price/trough_day/recovery_from_trough_pct/max_recovery_from_trough_pct`) — היפוך מהשפל.
  - (M3.6) *prior-decline context* ב-watchlist (`pct_from_52w_high/pct_from_52w_low/prior_decline_20d_pct/prior_decline_60d_pct`) — `scanner.prior_context` מחלון `EOD_HISTORY_DAYS=400` (אותה קריאה).
  - (M3.7) *סממני-הקשר מבוססי-מחקר*: `vix_level` (^VIX close, Nagel; פעם-לריצה `sc.vix_close`), `drop_day_rel_volume` (volume/avg_20, capitulation; == volume_ratio ב-EOD), `sector_momentum_5d/20d` (תשואת sector-ETF; `sc.etf_momentum` cache פר-ריצה, פר-ETF לא פר-מניה).
  - **כיסוי:** prior-decline מתמלא גם לשורות source=intraday דרך `scanner.backfill_intraday_prior_context` (ריצת-EOD, אותו scan_date). 3 סממני-M3.7 עדיין ריקים ל-intraday-live (נאספים ב-scanner+gradual; להרחבה עתידית).
  - (M3.8.1) **backfill חד-פעמי:** `python scanner.py --backfill-context` ממלא את 8 שדות-ההקשר לשורות watchlist ישנות שחסר להן (point-in-time לפי scan_date של כל שורה; upsert חלקי merge-safe; לא ב-workflow היומי). תיקון נלווה: cache של `vix_close`/`etf_momentum` לפי (symbol,scan_date) — נכון לבקפיל רב-תאריכי.
  - (M3.8) **split/halt detector** (הגנת-תקפות M4): `split_halt_flag`/`split_halt_reason` ב-post_analysis — מסמן reverse-split/halt artifacts (קפיצת-split = "recovery" מזויף של מאות %). מקור-אמת = yf split-feed (עמודת `Stock Splits` ב-history, אפס קריאה) + גיבוי jump>`SPLIT_HALT_JUMP_PCT=100` + halt_gap. **flag לא-הרסני — הנתון הגולמי נשמר; M4 מחריג שורות מסומנות ומדווח contamination%** (MASTERPLAN §5).
  - (M3.9) **Vardan-gap — ATR + reclaim/drop grid** (תיאורי, **פיצ'רים לא אותות**; M5-safe): ב-watchlist `atr_14` (Wilder ATR(14)$ נכון ל-scan_date — **מקור-ATR יחיד**, גם נקרא ע"י הקולקטור) + `drop_in_atr` (גודל-הצניחה ב-ATR; intraday=open−low_so_far, gradual=ref_close_window−price). ב-post_analysis **גריד**: `up_reach_day_{1,2,3,5,8}pct`, `down_reach_day_{1,2,3,5,8}pct` (יום-או-ריק; **superset** של `touched_up_5pct`/`touched_down_8pct` הקיימים), ו-`reclaim_atr_day_{0_5,1,1_5}x` (reclaim מעל השפל ב-יחידות-ATR, נמדד מ-**היום שאחרי השפל** = תזמון-אישור; **שונה במכוון** מ-`max_recovery_from_trough_pct` שכולל את יום-השפל = מדד-עוצמה). מקור-שמות יחיד `config.RECLAIM_GRID_COLUMNS`. **כיסוי:** הגריד מתמלא לכל אירוע בריצת-הקולקטור היומית (re-process מלא של ה-watchlist — מאומת בקוד); backfill נדרש ל-watchlist בלבד: `scanner.py --backfill-atr` (point-in-time, חד-פעמי, לא ב-cron).
- חלון תוצאות: D1..D+20 (+ תת-חלונות 3/5/10/20).
- עלות-סטרס M4: 0.50% round-trip.

## קונבנציות עבודה
- **סודות לעולם לא מודפסים** (חילוץ דרך קובץ/stdin בלבד).
- **time-check** לפני כל פעולה רגישת-זמן (יום-מסחר/שעות/D+N/cron); cron ב-UTC, שעות-שוק ב-ET.
- **מנדט-סקילים:** סריקת כל הסקילים + שימוש בכמה שרלוונטיים; פתיחה בסריקה, סגירה ברשימת-שימוש.
- **Handoff:** פרומפט בבלוק-העתקה אחד; recap בסוף; `upsert` בטוח לריצה-חוזרת.
- **גבול M5:** אין ניקוד/אותות/דירוג/המלצות עד M4=go.
