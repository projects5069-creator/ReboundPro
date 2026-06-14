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
             "spy_change_pct", "sector_etf_change_pct", "market_cap",
             # intraday-path numerics (M2 fields, exposed in M3)
             "first_cross_price", "first_cross_drop_pct", "intraday_low",
             "recovery_from_low_pct", "scans_count",
             # gradual-drop numerics
             "drop_pct_window", "ref_close_window"]
NUM_POST = ["ref_close", "max_recovery_pct", "max_further_drop_pct",
            "last_close_pct", "forward_days_available", "horizon",
            "day_of_max_recovery", "day_of_max_drop"] \
    + [f"max_recovery_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS] \
    + [f"max_further_drop_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS]
NUM_SUMMARY = ["total_finviz_candidates", "passed_floor", "below_min_price",
               "below_min_cap", "below_min_adv", "drop_below_threshold", "other_rejects"]
NUM_TS = ["price", "pct_from_open", "volume"]

# ── cross-tab display formatting (M3) ────────────────────────────────────────
# % sign in the cell · thousands separators · 2-decimal rounding. Applied via a
# pandas Styler so the underlying values stay numeric.
PCT_COLS = {
    "drop_pct_from_open", "close_pct_from_open", "pct_change_prevclose",
    "spy_change_pct", "sector_etf_change_pct", "recovery_from_low_pct",
    "first_cross_drop_pct", "max_recovery_pct", "max_further_drop_pct",
    "last_close_pct", "pct_from_open", "drop_pct_window",
} | {f"max_recovery_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS} \
  | {f"max_further_drop_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS}
INT_COLS = {
    "volume", "avg_volume_20d", "adv_dollar", "market_cap", "scans_count",
    "forward_days_available", "horizon", "day_of_max_recovery", "day_of_max_drop",
    "total_finviz_candidates", "passed_floor", "below_min_price", "below_min_cap",
    "below_min_adv", "drop_below_threshold", "other_rejects",
}
FLOAT_COLS = {
    "price", "open", "high", "low_so_far", "prev_close", "rsi_14",
    "volume_ratio", "ref_close", "first_cross_price", "intraday_low",
    "ref_close_window",
}


def styled(df):
    """Format numeric columns for display (Styler keeps values numeric)."""
    fmt = {}
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        if c in PCT_COLS:
            fmt[c] = "{:,.2f}%"
        elif c in INT_COLS:
            fmt[c] = "{:,.0f}"
        else:                       # known floats + any other numeric -> 2dp + commas
            fmt[c] = "{:,.2f}"
    return df.style.format(fmt, na_rep="")


# Finviz-style fundamental categories for the stock card (display grouping only).
FUND_GROUPS = {
    "Valuation": ["Market Cap", "Enterprise Value", "P/E", "Forward P/E", "PEG",
                  "P/S", "P/B", "P/FCF", "P/C", "EV/EBITDA", "EV/Sales", "Target Price"],
    "Margins / Profitability": ["Gross Margin", "Oper. Margin", "Profit Margin",
                                "ROA", "ROE", "ROIC", "EPS (ttm)", "EPS this Y",
                                "EPS next Y", "EPS Q/Q", "Income", "Sales"],
    "Debt / Liquidity": ["Debt/Eq", "LT Debt/Eq", "Quick Ratio", "Current Ratio",
                         "Cash/sh", "Book/sh"],
    "Short interest": ["Short Float", "Short Ratio", "Short Interest"],
    "52W range / Technicals": ["52W High", "52W Low", "SMA20", "SMA50", "SMA200",
                               "RSI (14)", "ATR (14)", "Beta", "Volatility W", "Volatility M"],
    "Ownership": ["Insider Own", "Insider Trans", "Inst Own", "Inst Trans",
                  "Shs Outstand", "Shs Float", "Employees"],
}


def _resolve_sheet_id():
    """Local/CI uses env (config.SHEET_ID); Streamlit Cloud uses st.secrets."""
    if config.SHEET_ID:
        return config.SHEET_ID
    try:
        return st.secrets.get("REBOUND_SHEET_ID", "")
    except Exception:
        return ""


SHEET_ID = _resolve_sheet_id()


@st.cache_data(ttl=300)
def load(tab, num_cols):
    header, rows = sm.read_rows(SHEET_ID, tab)
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

if not SHEET_ID:
    st.error("REBOUND_SHEET_ID לא מוגדר (.env / env / st.secrets). אין מקור נתונים.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Controls")
    if st.button("🔄 Refresh data", type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.caption("נתונים נקראים מ-Google Sheet (cache 5 דק').")
    st.caption(f"Sheet: …{SHEET_ID[-8:]}")
    try:
        st.caption(f"SA: {sm.service_account_email()}")
    except Exception:
        pass

try:
    watch = load(config.TAB_WATCHLIST, NUM_WATCH)
    post = load(config.TAB_POST, NUM_POST)
    ts = load(config.TAB_TIMESERIES, NUM_TS)
    fund = load(config.TAB_FUNDAMENTALS, [])
    news = load(config.TAB_NEWS, [])
except Exception as e:
    st.error(f"שגיאת קריאה מה-Sheet: {e}")
    st.stop()

if watch.empty:
    st.warning("watchlist_live ריק — עדיין לא נאספו נתונים.")
    st.stop()

# hypothesis tag — legacy rows (pre-M3 gradual_drop) have no/blank drop_kind;
# treat them as intraday_drop so the filter/breakdown stay coherent.
if "drop_kind" not in watch.columns:
    watch["drop_kind"] = "intraday_drop"
else:
    watch["drop_kind"] = watch["drop_kind"].replace("", "intraday_drop").fillna("intraday_drop")

tab_health, tab_watch, tab_card, tab_post, tab_stats = st.tabs(
    ["🩺 Collection Health", "📋 Watchlist", "🃏 Stock Card",
     "🎯 Post-Analysis", "📊 Descriptive Stats"])

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

    st.markdown("**פילוח סיבות-דחייה (EOD scanner) — `daily_summary`**")
    summ = load(config.TAB_SUMMARY, NUM_SUMMARY)
    if summ.empty:
        st.info("daily_summary עדיין ריק — יתמלא בריצת ה-EOD הבאה.")
    else:
        summ = summ.sort_values("scan_date")
        reject_cols = ["below_min_price", "below_min_cap", "below_min_adv", "drop_below_threshold"]
        melt = summ.melt(id_vars="scan_date", value_vars=reject_cols,
                         var_name="reason", value_name="count")
        st.plotly_chart(px.bar(melt, x="scan_date", y="count", color="reason",
                               title="דחיות לפי יום (stacked)"), width="stretch")
        show = ["scan_date", "total_finviz_candidates", "passed_floor"] + reject_cols + ["other_rejects"]
        show = [c for c in show if c in summ.columns]
        st.dataframe(styled(summ[show].sort_values("scan_date", ascending=False)),
                     width="stretch", hide_index=True)

# ── 2. WATCHLIST ─────────────────────────────────────────────────────────────
with tab_watch:
    st.subheader("📋 watchlist_live — נתונים גולמיים")
    f = st.columns(4)
    sel_day = f[0].multiselect("scan_date", days, default=days)
    kinds = sorted(watch["drop_kind"].dropna().unique()) if "drop_kind" in watch else []
    sel_kind = f[1].multiselect("drop_kind", kinds, default=kinds)
    buckets = sorted(watch["liquidity_bucket"].dropna().unique()) if "liquidity_bucket" in watch else []
    sel_bucket = f[2].multiselect("liquidity bucket", buckets, default=buckets)
    sectors = sorted(watch["sector"].dropna().unique()) if "sector" in watch else []
    sel_sector = f[3].multiselect("sector", sectors, default=sectors)

    view = watch[watch["scan_date"].isin(sel_day)]
    if sel_kind:
        view = view[view["drop_kind"].isin(sel_kind)]
    if sel_bucket:
        view = view[view["liquidity_bucket"].isin(sel_bucket)]
    if sel_sector:
        view = view[view["sector"].isin(sel_sector)]

    cols = ["scan_date", "ticker", "drop_kind", "exchange", "drop_pct_from_open",
            "drop_pct_window", "price", "liquidity_bucket", "sector", "market_regime",
            "drop_type", "adv_dollar", "market_cap", "rsi_14",
            # intraday-path fields (source: intraday scanner) — exposed in M3
            "source", "first_cross_at", "first_cross_price", "first_cross_drop_pct",
            "intraday_low", "intraday_low_at", "recovery_from_low_pct",
            "reversal_confirmed", "scans_count", "last_update_at",
            # gradual-drop fields
            "lookback_trading_days", "ref_close_window"]
    cols = [c for c in cols if c in view.columns]
    st.caption(f"{len(view)} שורות · כולל שדות-המסלול התוך-יומי (ריקים לשורות EOD)")
    st.dataframe(styled(view[cols].sort_values("drop_pct_from_open")),
                 width="stretch", hide_index=True, height=520)

# ── STOCK CARD (view-only) ───────────────────────────────────────────────────
with tab_card:
    st.subheader("🃏 כרטיס מניה")
    st.caption("תצוגה בלבד · מסלול תוך-יומי + תוצאות forward + תעודת-זהות פונדמנטלית + חדשות.")
    tickers = sorted(watch["ticker"].dropna().unique())
    if not tickers:
        st.info("אין מניות במעקב עדיין.")
    else:
        cc = st.columns([2, 2, 3])
        sel_t = cc[0].selectbox("ticker", tickers)
        t_dates = sorted(watch[watch["ticker"] == sel_t]["scan_date"].dropna().unique())
        sel_d = cc[1].selectbox("scan_date (D0)", t_dates,
                                index=len(t_dates) - 1) if t_dates else None

        wr = watch[(watch["ticker"] == sel_t) & (watch["scan_date"] == sel_d)]
        if not wr.empty:
            r0 = wr.iloc[0]
            kind = r0.get("drop_kind") or "intraday_drop"
            if kind == "gradual_drop":
                lb = r0.get("lookback_trading_days")
                lb = int(lb) if pd.notna(lb) else config.GRADUAL_LOOKBACK_DAYS
                drop_label, drop_val = f"drop {lb}d (הדרגתי)", r0.get("drop_pct_window")
            else:
                drop_label, drop_val = "drop מהפתיחה", r0.get("drop_pct_from_open")
            m = st.columns(6)
            kpi(m[0], "drop_kind", kind)
            kpi(m[1], drop_label, f"{drop_val:.2f}%" if pd.notna(drop_val) else "—")
            kpi(m[2], "price (D0)", f"{r0.get('price'):,.2f}"
                if pd.notna(r0.get("price")) else "—")
            kpi(m[3], "liquidity", r0.get("liquidity_bucket", "—"))
            kpi(m[4], "sector", r0.get("sector", "—"))
            kpi(m[5], "regime", r0.get("market_regime", "—"))

        # 1) intraday time-series (price + pct path across D0–D20)
        st.markdown("**מסלול תוך-יומי מדורג (intraday_timeseries · D0–D3 כל 10ד' · D4–D20 ~3/יום)**")
        if ts.empty:
            st.info("טאב intraday_timeseries עדיין ריק — יתמלא בריצות התוך-יומיות.")
        else:
            tv = ts[(ts["ticker"] == sel_t) & (ts["scan_date"] == sel_d)].copy()
            if tv.empty:
                st.info("אין עדיין נקודות מעקב למניה/תאריך שנבחרו.")
            else:
                tv["ts"] = pd.to_datetime(tv["timestamp"], errors="coerce")
                tv = tv.sort_values("ts")
                gg = st.columns(2)
                gg[0].plotly_chart(px.line(tv, x="ts", y="price", markers=True,
                                           title="price לאורך הזמן"), width="stretch")
                gg[1].plotly_chart(px.line(tv, x="ts", y="pct_from_open", markers=True,
                                           title="% מהפתיחה (אותו יום)"), width="stretch")
                st.caption(f"{len(tv)} נקודות מעקב")

        # 2) forward outcomes (post_analysis) for this stock
        st.markdown("**תוצאות forward (post_analysis)**")
        if post.empty:
            st.info("post_analysis עדיין ריק.")
        else:
            pvc = post[(post["ticker"] == sel_t) & (post["scan_date"] == sel_d)]
            if pvc.empty:
                st.info("אין עדיין post_analysis למניה/תאריך שנבחרו.")
            else:
                pcols = ["scan_date", "ticker", "status", "forward_days_available",
                         "ref_close", "max_recovery_pct", "day_of_max_recovery",
                         "max_further_drop_pct", "day_of_max_drop", "last_close_pct", "dN_date"]
                pcols = [c for c in pcols if c in pvc.columns]
                st.dataframe(styled(pvc[pcols]), width="stretch", hide_index=True)
                sub = [(w, f"max_recovery_{w}d") for w in config.POST_ANALYSIS_SUBWINDOWS
                       if f"max_recovery_{w}d" in pvc.columns]
                row0 = pvc.iloc[0]
                if sub and any(pd.notna(row0[c]) for _, c in sub):
                    barf = pd.DataFrame({"window": [f"D+{w}" for w, _ in sub],
                                         "max_recovery_pct": [row0[c] for _, c in sub]})
                    st.plotly_chart(px.bar(barf, x="window", y="max_recovery_pct",
                                           title="max recovery לפי תת-חלון (%)"), width="stretch")

        # 3) fundamental ID card (Finviz-style, point-in-time) — raw values
        st.markdown("**תעודת זהות פונדמנטלית (Finviz, point-in-time)**")
        if fund.empty:
            st.info("fundamentals_snapshot עדיין ריק.")
        else:
            fr = fund[(fund["ticker"] == sel_t) & (fund["scan_date"] == sel_d)]
            if fr.empty:
                st.info("אין fundamentals למניה/תאריך שנבחרו.")
            else:
                frow = fr.iloc[0]
                gcols = st.columns(2)
                for i, (grp, fields) in enumerate(FUND_GROUPS.items()):
                    avail = [(f, str(frow.get(f, ""))) for f in fields if f in fr.columns]
                    if not avail:
                        continue
                    with gcols[i % 2]:
                        st.markdown(f"**{grp}**")
                        st.dataframe(pd.DataFrame(avail, columns=["שדה", "ערך"]),
                                     width="stretch", hide_index=True)

        # 4) news (news_snapshot) — raw headlines
        st.markdown("**חדשות (news_snapshot, point-in-time)**")
        if news.empty:
            st.info("news_snapshot עדיין ריק.")
        else:
            nr = news[(news["ticker"] == sel_t) & (news["scan_date"] == sel_d)]
            if nr.empty:
                st.info("אין חדשות שמורות למניה/תאריך שנבחרו.")
            else:
                nrow = nr.iloc[0]
                st.caption(f"news_count: {nrow.get('news_count', '')} · "
                           f"earnings±7d: {nrow.get('earnings_within_7d', '')}")
                items = []
                for i in range(1, config.NEWS_MAX_HEADLINES + 1):
                    h = nrow.get(f"headline_{i}", "")
                    if h:
                        items.append((nrow.get(f"datetime_{i}", ""), nrow.get(f"source_{i}", ""),
                                      h, nrow.get(f"url_{i}", "")))
                if items:
                    st.dataframe(pd.DataFrame(items, columns=["datetime", "source", "headline", "url"]),
                                 width="stretch", hide_index=True)
                else:
                    st.caption("אין כותרות שמורות.")


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
        st.dataframe(styled(pv[cols]), width="stretch", hide_index=True, height=460)

        matured = post[post["status"].isin(["ok"]) | post["status"].str.startswith("partial")]
        if not matured.empty and matured["max_recovery_pct"].notna().any():
            st.markdown("**התפלגות max_recovery_pct (שורות שהבשילו) — תיאורי בלבד**")
            st.plotly_chart(px.histogram(matured, x="max_recovery_pct", nbins=30),
                            width="stretch")

# ── 4. DESCRIPTIVE STATS ─────────────────────────────────────────────────────
with tab_stats:
    st.subheader("📊 סטטיסטיקה תיאורית על כל הדאטה שנצבר")
    st.caption("תיאור הנתונים בלבד — ללא ניקוד, דירוג או תוחלת רווח.")
    if "drop_kind" in watch:
        kc = watch["drop_kind"].value_counts().reset_index()
        kc.columns = ["drop_kind", "count"]
        st.plotly_chart(px.bar(kc, x="drop_kind", y="count",
                               title="פילוח לפי השערה (intraday_drop מול gradual_drop)"),
                        width="stretch")
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
