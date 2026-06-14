# ReboundPro — Actions Log

יומן-פעולות **append-only**: כל סשן עבודה מוסיף ערך מתוארך (תאריך · commit hash · תקציר) בסוף, לפני `## Next`. לא עורכים/מוחקים ערכים קיימים — רק מוסיפים. זהו התיעוד הכרונולוגי של מה נעשה ומתי (נגזר מ-git history).

| תאריך | commit | פעולה |
|-------|--------|-------|
| 2026-06-13 | `1196418` | M1: live collector (scanner + post-analysis) + daily workflow |
| 2026-06-14 | `6f58292` | M4-collect: snapshot פונדמנטלי point-in-time (Finviz) + monitoring dashboard |
| 2026-06-14 | `e64f05f` | M2: intraday scanner + חלון post-analysis 20 יום |
| 2026-06-14 | `8949557` | docs: חוקי-עבודה ל-CLAUDE.md (מיזוג, ללא מחיקה) |
| 2026-06-14 | `e82430a` | intraday_scanner: הגנת-שעות עצמית (לוח NYSE + 09:30–16:00 ET) |
| 2026-06-14 | `0fa8e72` | M4-collect: לכידת חדשות point-in-time (catalyst.py, Finnhub) |
| 2026-06-14 | `22c218c` | daily_summary (בריאות-איסוף) + תמיכת Streamlit Cloud creds + רענון state |
| 2026-06-14 | `5acf733` | deps: הוספת plotly ל-requirements.txt |
| 2026-06-14 | `acc4c23` | gitignore: streamlit_cloud_secrets.toml |
| 2026-06-14 | `882a9b2` | chore: force rebuild ל-Streamlit Cloud |
| 2026-06-14 | `40ad829` | deps: הצהרת תלויות dashboard ב-pyproject + uv.lock (Cloud צורך uv.lock) |
| 2026-06-14 | _(this commit)_ | docs: מערך-תיעוד מלא (MASTERPLAN/ACTIONS_LOG/TASKS/PROJECT_KNOWLEDGE) + חיווט-זיכרון ב-CLAUDE.md |
| 2026-06-14 | _(this commit)_ | M3: מעקב מדורג (`intraday_timeseries.py` + טאב + צעד workflow, D0–D3 10ד'/D4–D20 ~3/יום) · כרטיס-מניה בדashboard (intraday/post/fundamentals-Finviz/news, view-only) · תיקוני-תצוגה רוחביים (`%` בתא/פסיקים/2-ספרות + חשיפת שדות-מסלול ב-watchlist) |
| 2026-06-14 | _(this commit)_ | M3.4: מקור-איסוף `gradual_drop` (`gradual_scanner.py` + צעד ב-daily.yml בין scanner ל-catalyst) — close היום ≥10% מתחת ל-5 ימי-מסחר אחורה (Finviz `Performance: Week -10%`, אומת חי 422 מועמדים + ADBE -18.86%) · עמודה `drop_kind` migration-safe + תיוג intraday_drop ב-scanner/intraday_scanner · דדופ חוצה-סוגים 20 ימי-מסחר · dashboard סינון/תצוגה לפי drop_kind · אזהרת value-trap מתועדת |
| 2026-06-14 | _(this commit)_ | M3.5: dashboard → Streamlit multipage (דף לכל drop_kind). חילוץ כל הלוגיקה ל-`dashboard_common.py` (אפס כפילות); `dashboard.py`=דף-בית; `pages/1_Intraday_Drop.py`+`pages/2_Gradual_Drop.py` כל אחד `render(drop_kind)` עם 5 הטאבים מסונן מראש (בלי multiselect drop_kind). אומת headless ב-AppTest: בית+2 דפים, 0 חריגות, 5 טאבים/דף; audit config.* נקי |
| 2026-06-14 | _(this commit)_ | M3-monitor: `health_monitor.py` — סוכן-בקרת-בריאות (10 בדיקות / 5 עמודים: Freshness/Volume/Schema/Field/Ops), READ-ONLY מול Sheet (רק read_rows), `--morning`/`--evening`, exit 0/1/2, `health_log.jsonl` מקומי (.gitignore). **בקרת-צינור בלבד, לא edge.** + `docs/MONITORING.md` (runbook). הרצה חיה אומתה: morning+evening exit=2 (schema-drift אמיתי: post_analysis header חסר 14 עמודות חדשות — ייפתר בריצת post הבאה). READ-ONLY מאומת (אפס upsert/update). עדכון הפניה ב-MASTERPLAN §8 |
| 2026-06-14 | _(this commit)_ | docs: הוספת §8 "מפת-דרכים M0→M6" ל-MASTERPLAN (סיכום אבני-דרך לחזרה עתידית; M0–M2 ✅, M3 נוכחי + יעד-יציאה, M4 גייט/edge, M5 מנוע, M6 paper; "הנדסה ≠ הוכחת-edge, NO-GO=ניצחון מתודולוגי") |
| 2026-06-14 | `8c50749` | M3.8.1-fix+run: תיקון targeting (עמודות נעדרות מה-header החי = חסר) + **הרצה חיה**: 23/23 שורות 6/12 מולאו ב-8 שדות-הקשר; readback אישר (עמודות נוספו, ערכים שפויים, שדות קיימים נשמרו). PWRL בלבד עם d20/d60 ריקים (היסטוריה קצרה — תקין). תצפית: ל-23 הישנות `drop_kind`/`source` ריקים (legacy טרום-M3.4; dashboard עושה coalesce→intraday_drop) — מחוץ לסקופ. |
| 2026-06-14 | _(this commit)_ | M3.8.1: backfill הקשר חד-פעמי (`scanner.py --backfill-context`) — ממלא 8 שדות-הקשר (M3.6+M3.7) לכל שורת watchlist חסרה, **point-in-time** לפי scan_date של השורה (`_context_for_row`/`backfill_missing_context`), upsert חלקי merge-safe (לא דורס מלאות), לא ב-workflow. **תיקון באג:** cache של `vix_close`/`etf_momentum` עכשיו לפי (symbol,scan_date) — נכון רב-תאריכי. אומת: ASTS/RKLB @6/12 שפויים, cache-fix (6/12≠5/1), dry-run לא כותב, רק חסרים. (הרצה חיה על ה-23 ע"י עמיחי — דורש creds) |
| 2026-06-14 | _(this commit)_ | M3.8: split/halt detector ב-post_analysis (הגנת-תקפות M4) — flag לא-הרסני `split_halt_flag`+`split_halt_reason`; yf split-feed ראשי (עמודת Stock Splits, אפס קריאה) + גיבוי jump>`SPLIT_HALT_JUMP_PCT=100` + halt_gap. dashboard: הדגשה+מונה contamination ב-Post/Card/Health. MASTERPLAN §5: החרגה מאגרגטים. אומת: CENN 1:60 reverse-split(2026-04-13)→מסומן, AAPL נקי, 4 מסלולי-detector, HEADER 31 מיושר, AppTest 0-חריגות |
| 2026-06-14 | _(this commit)_ | M3.7: 3 סממני-הקשר מבוססי-מחקר (vix_level→Nagel, drop_day_rel_volume→capitulation, sector_momentum_5d/20d→enhanced-reversal) ב-scanner+gradual — VIX+sector פעם-לריצה (`vix_close`/`etf_momentum` cache), rel_vol מ-history קיים. + תיקון פער M3.6: `backfill_intraday_prior_context` ממלא prior-decline לשורות source=intraday בריצת-EOD. עמודות migration-safe; dashboard מציג קבוצת "סממני-הקשר". אומת: compile(9)+audit+יח'(VIX 17.68/XLK mom/ASTS rel-vol 2.11×/backfill AAPL merge-safe)+gradual regression+AppTest 0-חריגות. **פיצ'רים לא אותות; הכרעה M4** |
| 2026-06-14 | _(this commit)_ | M3.6: שני מדדי-איסוף תיאוריים (פיצ'רים, **לא אותות**). recovery-from-trough ב-post_analysis (trough_price/day/recovery/max_recovery — אומת AAPL 2026-04-08); prior-decline ב-watchlist (scanner+gradual): pct_from_52w_high/low + prior_decline_20d/60d, helper משותף `scanner.prior_context`, חלון EOD הורחב ל-`EOD_HISTORY_DAYS=400` (אותה קריאה, אומת ADBE: -51% מהשיא/+3.62% מהשפל). עמודות migration-safe; dashboard מציג. אומת: compile(9)+audit+regression+AppTest enriched (0 חריגות) |

## Next
<!-- הוסף כאן ערכים חדשים מתוארכים בכל סוף-סשן -->
