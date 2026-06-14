"""dashboard.py — ReboundPro MONITORING dashboard (VIEW-ONLY).

Reads watchlist_live + post_analysis from the Sheet (via sheets_manager) and
shows collection health, the raw watchlist, forward outcomes, and descriptive
stats. Style mirrors RidingHigh Pro's Streamlit dashboard.

⚠️ DELIBERATELY NOT INCLUDED: scores, signals, ranking, expected-return, or
   buy/sell recommendations. Those are M5 and await the M4 decision. This is a
   data-and-health viewer only.

Run locally:  streamlit run dashboard.py
"""
import pandas as pd
import plotly.express as px
import streamlit as st

import config
import sheets_manager as sm

# ── page config + style (mirrors RidingHigh) ─────────────────────────────────
st.set_page_config(page_title="ReboundPro Monitor", page_icon="📉", layout="wide")
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0.5rem; }
    h1 { padding-top: 0.5rem; padding-bottom: 0.5rem; font-size: 1.8rem; margin-top: 0; }
    h2 { padding-top: 0.3rem; padding-bottom: 0.3rem; font-size: 1.2rem; }
    div[data-testid="metric-container"] { padding: 5px; }
</style>
""", unsafe_allow_html=True)

NUM_WATCH = ["drop_pct_from_open", "close_pct_from_open", "pct_change_prevclose",
             "price", "open", "high", "low_so_far", "prev_close", "volume",
             "avg_volume_20d", "adv_dollar", "volume_ratio", "rsi_14",
             "spy_change_pct", "sector_etf_change_pct", "market_cap"]
NUM_POST = ["ref_close", "max_recovery_pct", "max_further_drop_pct",
            "last_close_pct", "forward_days_available", "horizon"]


@st.cache_data(ttl=300)
def load(tab, num_cols):
    header, rows = sm.read_rows(config.SHEET_ID, tab)
    if not header:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=header)
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def kpi(col, label, value):
    col.metric(label, value)


# ── load ─────────────────────────────────────────────────────────────────────
st.title("📉 ReboundPro — Monitoring")
st.caption("תצוגה בלבד · אין ניקוד / אותות / דירוג / המלצות (אלה M5, ממתינים להכרעת M4). "
           "View-only: raw collected data + pipeline health.")

if not config.SHEET_ID:
    st.error("REBOUND_SHEET_ID לא מוגדר (.env / env). אין מקור נתונים.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Controls")
    if st.button("🔄 Refresh data", type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.caption("נתונים נקראים מ-Google Sheet (cache 5 דק').")
    st.caption(f"Sheet: …{config.SHEET_ID[-8:]}")
    try:
        st.caption(f"SA: {sm.service_account_email()}")
    except Exception:
        pass

try:
    watch = load(config.TAB_WATCHLIST, NUM_WATCH)
    post = load(config.TAB_POST, NUM_POST)
except Exception as e:
    st.error(f"שגיאת קריאה מה-Sheet: {e}")
    st.stop()

if watch.empty:
    st.warning("watchlist_live ריק — עדיין לא נאספו נתונים.")
    st.stop()

tab_health, tab_watch, tab_post, tab_stats = st.tabs(
    ["🩺 Collection Health", "📋 Watchlist", "🎯 Post-Analysis", "📊 Descriptive Stats"])

# ── 1. COLLECTION HEALTH ─────────────────────────────────────────────────────
with tab_health:
    st.subheader("🩺 בריאות האיסוף")
    days = sorted(watch["scan_date"].dropna().unique())
    last_day = days[-1] if days else "—"
    last_day_n = int((watch["scan_date"] == last_day).sum())
    c = st.columns(4)
    kpi(c[0], "ריצה אחרונה (scan_date)", last_day)
    kpi(c[1], "מועמדים ביום האחרון", last_day_n)
    kpi(c[2], "סה\"כ שורות שנצברו", len(watch))
    kpi(c[3], "ימי מסחר ייחודיים", len(days))

    st.markdown("**מועמדים/יום שעברו את הרצפה הקשיחה**")
    per_day = watch.groupby("scan_date").size().reset_index(name="candidates")
    st.plotly_chart(px.bar(per_day, x="scan_date", y="candidates"),
                    width="stretch")

    st.markdown("**טריות הדאטה (post_analysis סטטוס)**")
    if not post.empty and "status" in post.columns:
        sc = st.columns(4)
        n_pending = int((post["status"] == "pending_forward").sum())
        n_ok = int(post["status"].isin(["ok"]).sum())
        n_partial = int(post["status"].str.startswith("partial").sum())
        n_halt = int((post["status"] == "delisted_or_halted").sum())
        kpi(sc[0], "ok (חלון מלא)", n_ok)
        kpi(sc[1], "pending (טרם הבשיל)", n_pending)
        kpi(sc[2], "partial / גאפ", n_partial)
        kpi(sc[3], "halt / delisted", n_halt)
    else:
        st.info("post_analysis עדיין ריק.")

    st.info("ℹ️ פילוח סיבות-דחייה (below_min_price/cap/adv) נרשם בלוג הסורק אך **אינו נשמר** "
            "ל-Sheet כרגע. כדי להציגו כאן צריך tab `daily_summary` (שיפור איסוף קטן, מחוץ ל-scope "
            "של dashboard-בלבד).")

# ── 2. WATCHLIST ─────────────────────────────────────────────────────────────
with tab_watch:
    st.subheader("📋 watchlist_live — נתונים גולמיים")
    f = st.columns(3)
    sel_day = f[0].multiselect("scan_date", days, default=days)
    buckets = sorted(watch["liquidity_bucket"].dropna().unique()) if "liquidity_bucket" in watch else []
    sel_bucket = f[1].multiselect("liquidity bucket", buckets, default=buckets)
    sectors = sorted(watch["sector"].dropna().unique()) if "sector" in watch else []
    sel_sector = f[2].multiselect("sector", sectors, default=sectors)

    view = watch[watch["scan_date"].isin(sel_day)]
    if sel_bucket:
        view = view[view["liquidity_bucket"].isin(sel_bucket)]
    if sel_sector:
        view = view[view["sector"].isin(sel_sector)]

    cols = ["scan_date", "ticker", "exchange", "drop_pct_from_open", "price",
            "liquidity_bucket", "sector", "market_regime", "drop_type",
            "adv_dollar", "market_cap", "rsi_14"]
    cols = [c for c in cols if c in view.columns]
    st.caption(f"{len(view)} שורות")
    st.dataframe(view[cols].sort_values("drop_pct_from_open"),
                 width="stretch", hide_index=True, height=520)

# ── 3. POST-ANALYSIS ─────────────────────────────────────────────────────────
with tab_post:
    st.subheader("🎯 post_analysis — תוצאות forward (ככל שמתמלאות)")
    if post.empty:
        st.info("עדיין אין post_analysis.")
    else:
        statuses = sorted(post["status"].dropna().unique()) if "status" in post else []
        sel_st = st.multiselect("status", statuses, default=statuses)
        pv = post[post["status"].isin(sel_st)] if sel_st else post
        up_col = next((c for c in post.columns if c.startswith("touched_up_")), None)
        dn_col = next((c for c in post.columns if c.startswith("touched_down_")), None)
        cols = ["scan_date", "ticker", "status", "forward_days_available", "ref_close",
                "max_recovery_pct", "day_of_max_recovery", "max_further_drop_pct",
                "day_of_max_drop", up_col, dn_col, "last_close_pct", "dN_date"]
        cols = [c for c in cols if c and c in pv.columns]
        st.caption(f"{len(pv)} שורות · halt/delist מוצג מפורשות כסטטוס (לא מושמט)")
        st.dataframe(pv[cols], width="stretch", hide_index=True, height=460)

        matured = post[post["status"].isin(["ok"]) | post["status"].str.startswith("partial")]
        if not matured.empty and matured["max_recovery_pct"].notna().any():
            st.markdown("**התפלגות max_recovery_pct (שורות שהבשילו) — תיאורי בלבד**")
            st.plotly_chart(px.histogram(matured, x="max_recovery_pct", nbins=30),
                            width="stretch")

# ── 4. DESCRIPTIVE STATS ─────────────────────────────────────────────────────
with tab_stats:
    st.subheader("📊 סטטיסטיקה תיאורית על כל הדאטה שנצבר")
    st.caption("תיאור הנתונים בלבד — ללא ניקוד, דירוג או תוחלת רווח.")
    g = st.columns(2)
    if "liquidity_bucket" in watch:
        bc = watch["liquidity_bucket"].value_counts().reset_index()
        bc.columns = ["liquidity_bucket", "count"]
        g[0].plotly_chart(px.bar(bc, x="liquidity_bucket", y="count", title="לפי דלי נזילות"),
                          width="stretch")
    if "market_regime" in watch:
        rc = watch["market_regime"].value_counts().reset_index()
        rc.columns = ["market_regime", "count"]
        g[1].plotly_chart(px.bar(rc, x="market_regime", y="count", title="לפי משטר שוק"),
                          width="stretch")
    g2 = st.columns(2)
    if "sector" in watch:
        scn = watch["sector"].value_counts().reset_index()
        scn.columns = ["sector", "count"]
        g2[0].plotly_chart(px.bar(scn, x="count", y="sector", orientation="h", title="לפי סקטור"),
                           width="stretch")
    if "drop_pct_from_open" in watch:
        g2[1].plotly_chart(px.histogram(watch, x="drop_pct_from_open", nbins=30,
                                        title="עומק צניחה מהפתיחה (%)"),
                           width="stretch")

st.caption("ReboundPro M3 · monitoring only · אין כאן לוגיקת מסחר.")
