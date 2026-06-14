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

## Next
<!-- הוסף כאן ערכים חדשים מתוארכים בכל סוף-סשן -->
