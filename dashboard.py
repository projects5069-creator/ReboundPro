"""dashboard.py — ReboundPro MONITORING dashboard — HOME (VIEW-ONLY).

Streamlit multipage entrypoint. The full monitoring tab set now lives on two
hypothesis pages (sidebar nav), one per drop_kind, so each view contains a single
hypothesis only:
  • pages/1_Intraday_Drop.py — sharp same-day drops (drop_kind == "intraday_drop")
  • pages/2_Gradual_Drop.py  — slow 5-day declines (drop_kind == "gradual_drop")

All shared logic lives in dashboard_common.py (imported here and by both pages —
no duplication). This Home page is a lightweight landing: hypothesis split +
totals, then "pick a page in the sidebar".

⚠️ NOT INCLUDED anywhere: scores, signals, ranking, recommendations (M5, await M4).

Run locally:  streamlit run dashboard.py
Streamlit Cloud entrypoint stays dashboard.py; pages/ is auto-discovered.
"""
# Streamlit Cloud redeploy marker — 2026-06-25b (Group-C fundamentals fed into the
# Entry-Profile separation table D+3 + horizon strip: the 6 pre-registered Finviz _num
# fields — ROA, Debt/Eq, Current Ratio, Short Float, Gross Margin, P/B — plus derived
# E/P, joined from fundamentals_snapshot point-in-time, each read PER-METRIC with no
# composite/score. Pre-registration sha256 032f10eb. DESCRIPTIVE / M5-safe).
# Bump to force a clean reboot.
import gspread
import streamlit as st

import config
import dashboard_common as common

common.setup_page("ReboundPro Monitor", "📉")

common.page_header("📉 ReboundPro — ניטור",
                   common.VIEW_ONLY + " · שתי השערות מופרדות לדפים בסרגל הצד.")

sheet_id = common.resolve_sheet_id()
if not sheet_id:
    st.error("REBOUND_SHEET_ID לא מוגדר (.env / env / st.secrets). אין מקור נתונים.")
    st.stop()
common.sidebar_controls(sheet_id)

# operational status banner (latest health_monitor run) — control, not edge
common.render_health_banner()

try:
    watch = common.load(sheet_id, config.TAB_WATCHLIST, common.NUM_WATCH)
except gspread.exceptions.APIError as e:
    (st.info(common.QUOTA_MSG) if common._is_quota(e)
     else st.error(f"שגיאת קריאה מה-Sheet: {e}"))
    st.stop()
except Exception as e:
    st.error(f"שגיאת קריאה מה-Sheet: {e}")
    st.stop()

if watch.empty:
    st.warning("watchlist_live ריק — עדיין לא נאספו נתונים.")
    st.stop()
watch = common.coalesce_kind(watch)

n_intraday = int((watch["drop_kind"] == "intraday_drop").sum())
n_gradual = int((watch["drop_kind"] == "gradual_drop").sum())
days = sorted(watch["scan_date"].dropna().unique())
c = st.columns(4)
common.kpi(c[0], "סה\"כ שורות", len(watch))
common.kpi(c[1], "⚡ Intraday Drop", n_intraday)
common.kpi(c[2], "🐢 Gradual Drop", n_gradual)
common.kpi(c[3], "ימי מסחר ייחודיים", len(days))

st.info("בחר דף בסרגל הצד: **⚡ Intraday Drop** (צניחה חדה תוך-יומית) או "
        "**🐢 Gradual Drop** (ירידה הדרגתית ל-5 ימים). כל דף מסונן מראש להשערה שלו.")

# 📊 מבט-על: טבלה אחת — מה כל מניה עשתה מהכניסה עד עכשיו — + שתי תצוגות-מצרף.
st.subheader("📊 מבט-על — מהכניסה עד עכשיו")
common.render_overview(sheet_id)

st.caption("ReboundPro · monitoring only · אין כאן לוגיקת מסחר.")
