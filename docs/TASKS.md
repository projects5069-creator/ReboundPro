# ReboundPro — Tasks

## ▶ NEXT — HYP-002 integration (2026-06-19)
- **TASK-A** — Document HYP-002 long-rebound thesis (composite distress+rsi + VIX regime-gate) + register in HYPOTHESES.md (DONE — `docs/HYP-002_long_rebound_thesis.md` + `docs/HYPOTHESES.md`).
- **TASK-B** — Fix BuildSpec DropsLab drift: Ambroseius→projects5069-creator, sheet→1XM-qId7, tab→drops_raw/post (DONE).
- **TASK-C** — Resolve Phase-0 data source: DropsLab vs ReboundPro parity. **(parity ANALYZED — `research/phase0/TASK-C_parity_memo.md`):** HYP-002 z-constants + threshold −1.7733 do **NOT** transfer to ReboundPro — dual gap: definition (~28% of close-to-close drops miss the intraday open→low rule) + universe (only 12.7% of DropsLab survive RB's mid+large floor; HYP-002's edge sits in the nano/micro RB excludes). Distress center shifts −59→−37 ⇒ discovery threshold fires 1.7% on intraday / 30.4% on gradual (vs ~10%). Live count corrected: RB = **200** events (not ~77) but only ~1 week (6/12–18) — §5 span gate far from met.
  - **TASK-C.1 (DONE — `research/phase0/TASK-C1_liquid_edge_memo.md`):** Phase-0 edge-harness on DropsLab∩RB-floor (n=591; 541 with final D5, 91.5% cov) + `drops_post`. **Verdict: NO robust net edge in the liquid subset.** long→D5 net **+0.27%**, day-clustered CI95 [−2.94,+2.22] **includes 0**; does **not** beat SPY net (alpha −0.12%). VIX regime DIRECTION replicates (calm VIX<18 net −4.50% sig-negative; elevated positive) → supports HYP-002 mechanism as a **prior** — but the actual gate VIX≥20 is **not** net-significant (CI [−10.99,+5.24], few-cluster fragile); only the narrow 18–20 band is sig-positive (data-mining risk). Matches the literature prior (edge sits in illiquid names RB excludes). **PROXY/PRIOR only — not M4=GO, not M5 release; §5 unchanged.**

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
- **סוכן-בריאות `health_monitor.py`** (M3-monitor): 10 בדיקות-צינור ב-5 עמודים (Freshness/Volume/Schema/Field/Ops), `--morning`/`--evening`, exit 0/1/2. כותב טאב-בקרה `health_log` ב-Sheet (היחיד שנכתב) + `health_log.jsonl` מקומי. **בקרה בלבד — לא edge** (ראה docs/MONITORING.md). להריץ בוקר/ערב.
- **דף System Health בדashboard** (`pages/3_System_Health.py` + באנר-סטטוס בעמוד-הבית): היסטוריית-ריצות + גרף-מגמה + טבלה מסוננת; באנר עם הריצה האחרונה + דגל ">24ש' לא רצה". view-only.

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

## 🧩 מועמדי-איסוף תיאוריים — Vardan gap (M3-חוקי, ללא קוד עדיין)
*מקור: `docs/VARDAN_GAP_ANALYSIS.md`. שניהם פיצ'רים תיאוריים בלבד (כמו `touched_up_5pct`/`recovery-from-trough` הקיימים) — **אפס ניקוד/אות/החלטת-כניסה; גבול M5 נשמר**. אומתו בקוד 2026-06-22. ממתינים לאישור-בנייה (סקיל-תכנון לפני קוד).*
- **TASK-V1 — Reclaim grid רב-ספי** (הכללת `touched_up_5pct`): סדרת ספים `[1,2,3,5,8]%` מעל `ref_close` + יום-חציה ראשון לכל סף, ב-`post_analysis`. אומת: `touched_up` הוא `highs[highs>=TOUCH_UP_PCT]`+יום — חישוב תיאורי טהור מאותה סדרת `highs`; הגריד זהה-באופי → M3-חוקי. מתאר את פרופיל-ההתאוששות הרב-יומי בגרעיניות עדינה. *(אופציונלי סימטרי: down-grid להרחבת `touched_down_8pct`.)*
- **TASK-V2 — חשיפת SMA%/52W-dist ל-`watchlist_live`** (לא חישוב חדש): אומת ש-Finviz מדווח SMA20/50/200 כ-**% מרחק מהמחיר** ו-`parse_num` מסיר `%` → `SMA20_num`/`SMA50_num` + `52W High/Low_dist_num` כבר אחוזי-מרחק, קיימים ב-`fundamentals_snapshot`. הפער: לא חשופים ב-`watchlist_live`, ו-`SMA200` הוא raw-only (לא ב-`FUND_NUMERIC`). → חשיפה/parse בלבד, אפס מתמטיקה חדשה. *(dist_to_SMA המקורי — מיותר, נדחה.)*
- *(שלישי, לא-מאושר: `drop_in_ATR` — צניחה מנורמלת ב-ATR14; פיצ'ר תיאורי, ממתין לאישור מפורש.)*
