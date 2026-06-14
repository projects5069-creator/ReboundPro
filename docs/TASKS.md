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
- **M3.8.1 — backfill הקשר חד-פעמי** (`scanner.py --backfill-context`): ממלא את 8 שדות-ההקשר התיאוריים (prior-decline M3.6 + context-signals M3.7) לכל שורת watchlist_live שחסר לה ≥1 שדה — כל source/scan_date. **point-in-time** לפי ה-scan_date של כל שורה (history ≤scan_date, VIX/sector של אותו יום) דרך `_context_for_row`+`backfill_missing_context`. upsert חלקי merge-safe (לא דורס שורות מלאות). **תיקון באג cache:** `vix_close`/`etf_momentum` מפתחים לפי (symbol,scan_date) — נכון רב-תאריכי. **לא ב-workflow היומי** (תיקון-פעם; הרצה ידנית). אומת point-in-time: ASTS/RKLB @6/12 שפויים, dry-run לא כותב, רק חסרים נתפסים.
- **M3.8 — split/halt detector** (הגנת-תקפות M4 הקריטית; flag **לא-הרסני**, לא מוחק/משנה): מזהה ארטיפקטים של reverse-split/halt ב-post_analysis שאחרת נרשמים כ"recovery" מזויף של מאות %. שדות חדשים `split_halt_flag` (bool) + `split_halt_reason` (reverse_split_ratio / inter_day_jump / halt_gap / clean). מקור-אמת ראשי = yf split feed (עמודת `Stock Splits` שכבר ב-history, אפס קריאה נוספת); גיבוי = קפיצה בין-יומית > `config.SPLIT_HALT_JUMP_PCT=100.0` (מתואם עם RidingHigh TASK-180); halt = gap/delisted. dashboard: Post-Analysis (עמודות + הדגשת-שורה אדומה + מונה contamination%), Stock-Card (אזהרה), Collection-Health (מונה מזוהמות). MASTERPLAN §5: שורות מסומנות מוחרגות מאגרגטי M4 + contamination% מדווח. אומת: CENN 1:60 reverse-split (2026-04-13) → מסומן; AAPL נקי. **detector תיאורי-הגנתי, לא לוגיקת-מסחר.**
- **M3.7 — שלושה סממני-הקשר מבוססי-מחקר + תיקון פער-כיסוי** (תיאורי, **פיצ'רים לא אותות**; הכרעה ל-M4): (1) `vix_level` — ^VIX close ב-scan_date (Nagel: פרמיית-היפוך↑ כש-VIX↑), משיכה פעם-אחת-לריצה. (2) `drop_day_rel_volume` — volume/avg_volume_20d (capitulation), מ-history קיים. (3) `sector_momentum_5d`/`sector_momentum_20d` — תשואת sector-ETF ל-5/20 ימי-מסחר (enhanced-reversal), `sc.etf_momentum` עם cache פר-ריצה (משיכה פר-ETF, לא פר-מניה). נאספים ב-scanner+gradual. **תיקון פער M3.6:** `scanner.backfill_intraday_prior_context` ממלא prior-decline לשורות source=intraday של אותו scan_date בריצת-ה-EOD (intraday_scanner נשאר קל). עמודות migration-safe. dashboard: קבוצת "סממני-הקשר" ב-Watchlist+Stock-Card. **הערה: 3 הסממנים החדשים עדיין ריקים בשורות intraday-live (נאספים ב-scanner+gradual בלבד) — להרחבה עתידית אם נרצה.**
- **M3.6 — שני מדדי-איסוף תיאוריים** (לשתי ההשערות, **פיצ'רים בלבד — לא אותות-כניסה**; ההכרעה אם מנבאים נדחית ל-M4): (1) **recovery-from-trough** ב-`post_analysis_collector.py` — `trough_price`/`trough_day`/`recovery_from_trough_pct`/`max_recovery_from_trough_pct` (היפוך מהשפל, מחושב מאותו forward-history שכבר נמשך). (2) **prior-decline context** ב-watchlist (`scanner.py`+`gradual_scanner.py`) — `pct_from_52w_high`/`pct_from_52w_low`/`prior_decline_20d_pct`/`prior_decline_60d_pct` (מחושב מאותה yfinance-history; הורחב חלון ל-`EOD_HISTORY_DAYS=400` כדי לכסות 52ש'+60 ימי-מסחר, ללא קריאות-רשת נוספות). עמודות migration-safe (append). dashboard מציג: Post-Analysis→trough, Watchlist+Stock-Card→prior-decline. **הערה: שדות intraday-live (source=intraday) לא נושאים prior-decline — רק EOD-capture + gradual (כפי המפרט).**

## ▶ NOW (M3 — צבירה)
- לצבור דאטה (forward, בזמן-אמת).
- להציץ בדashboard מדי פעם לבריאות-הצנרת.
- **סוכן-בריאות `health_monitor.py`** (M3-monitor): 10 בדיקות-צינור ב-5 עמודים (Freshness/Volume/Schema/Field/Ops), READ-ONLY מול Sheet, `--morning`/`--evening`, exit 0/1/2, `health_log.jsonl` מקומי. **בקרה בלבד — לא edge** (ראה docs/MONITORING.md). להריץ בוקר/ערב.

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
