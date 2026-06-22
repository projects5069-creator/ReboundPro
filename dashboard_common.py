"""dashboard_common.py — ReboundPro shared dashboard logic (VIEW-ONLY).

Single source of truth for the Streamlit dashboard, imported by the entrypoint
(`dashboard.py`, Home) and by each hypothesis page under `pages/`. Each page
calls `render(drop_kind, ...)`, which filters the watchlist (and the forward
layers) to that one hypothesis and builds the full tab set — so everything a user
sees on a page belongs to exactly one drop_kind. NO logic is duplicated across
pages; they differ only by the drop_kind argument.

⚠️ DELIBERATELY NOT INCLUDED: scores, signals, ranking, expected-return, buy/sell
   recommendations. Those are M5 and await the M4 decision. Data-and-health viewer
   only. Collection infrastructure (Sheet + collectors) is shared and unchanged.
"""
import copy
import math

import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

import config
import sheets_manager as sm

_is_quota = sm._is_quota_error   # 429 detector (shared with the read path)

# ── unified chart theme (display-only) ───────────────────────────────────────
# One registered template + px.defaults so EVERY chart (px.* across all pages)
# inherits the same professional look: clean white, thin grey gridlines, bold
# zeroline, consistent font/margins/colorway. plot() renders with the modebar off.
GREEN, RED, GREY = "#26a69a", "#ef5350", "#cccccc"

_RBP = copy.deepcopy(pio.templates["plotly_white"])
_RBP.layout.font = dict(family="-apple-system, Segoe UI, Roboto, Arial", size=12)
_RBP.layout.margin = dict(l=10, r=10, t=40, b=10)
_RBP.layout.colorway = ["#1f77b4", GREEN, RED, "#7e57c2", "#ffa726", "#26c6da"]
_RBP.layout.xaxis = dict(gridcolor="#eeeeee", gridwidth=1, zerolinecolor="#888888",
                         zerolinewidth=1, showline=False)
_RBP.layout.yaxis = dict(gridcolor="#eeeeee", gridwidth=1, zerolinecolor="#888888",
                         zerolinewidth=1, showline=False)
pio.templates["reboundpro"] = _RBP
px.defaults.template = "reboundpro"


def sign_colors(values):
    """Per-value colour by sign for %-bars: >=0 green, <0 red, NaN/None grey."""
    out = []
    for v in values:
        try:
            f = float(v)
            out.append(GREY if math.isnan(f) else (GREEN if f >= 0 else RED))
        except (TypeError, ValueError):
            out.append(GREY)
    return out


def style_fig(fig, title=None, category=False, pct=False):
    """Per-figure tweaks on top of the template (go.* figures + axis types)."""
    if title is not None:
        fig.update_layout(title=title)
    fig.update_layout(template="reboundpro", bargap=0.55)
    if category:
        fig.update_xaxes(type="category")
    if pct:
        fig.update_yaxes(ticksuffix="%")
    return fig


def plot(target, fig):
    """Render a figure with the unified theme and NO floating modebar.
    `target` is st or a column from st.columns()."""
    target.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# ── numeric coercion sets (per tab) ──────────────────────────────────────────
NUM_WATCH = ["drop_pct_from_open", "close_pct_from_open", "pct_change_prevclose",
             "price", "open", "high", "low_so_far", "prev_close", "volume",
             "avg_volume_20d", "adv_dollar", "volume_ratio", "rsi_14",
             "spy_change_pct", "sector_etf_change_pct", "market_cap",
             # intraday-path numerics (M2 fields)
             "first_cross_price", "first_cross_drop_pct", "intraday_low",
             "recovery_from_low_pct", "scans_count",
             # gradual-drop numerics
             "drop_pct_window", "ref_close_window",
             # prior-decline context numerics (M3)
             "pct_from_52w_high", "pct_from_52w_low",
             "prior_decline_20d_pct", "prior_decline_60d_pct",
             # research-based context signals (M3)
             "vix_level", "drop_day_rel_volume",
             "sector_momentum_5d", "sector_momentum_20d",
             # descriptive ATR features (M3 — Vardan-gap)
             "atr_14", "drop_in_atr"]
NUM_POST = ["ref_close", "max_recovery_pct", "max_further_drop_pct",
            "last_close_pct", "forward_days_available", "horizon",
            "day_of_max_recovery", "day_of_max_drop",
            # recovery-from-trough numerics (M3)
            "trough_price", "trough_day",
            "recovery_from_trough_pct", "max_recovery_from_trough_pct"] \
    + [f"max_recovery_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS] \
    + [f"max_further_drop_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS] \
    + config.RECLAIM_GRID_COLUMNS   # reclaim/drop grid (day-or-blank) — Vardan-gap
NUM_SUMMARY = ["total_finviz_candidates", "passed_floor", "below_min_price",
               "below_min_cap", "below_min_adv", "drop_below_threshold", "other_rejects"]
NUM_TS = ["price", "pct_from_open", "volume"]
NUM_FDAILY = ["day_offset", "close", "cum_pct_from_ref", "daily_change_pct",
              "high_pct", "low_pct"]

# ── cross-tab display formatting ─────────────────────────────────────────────
# % sign in the cell · thousands separators · 2-decimal rounding (pandas Styler,
# so underlying values stay numeric).
PCT_COLS = {
    "drop_pct_from_open", "close_pct_from_open", "pct_change_prevclose",
    "spy_change_pct", "sector_etf_change_pct", "recovery_from_low_pct",
    "first_cross_drop_pct", "max_recovery_pct", "max_further_drop_pct",
    "last_close_pct", "pct_from_open", "pct_from_ref", "drop_pct_window",
    "pct_from_52w_high", "pct_from_52w_low", "prior_decline_20d_pct",
    "prior_decline_60d_pct", "recovery_from_trough_pct", "max_recovery_from_trough_pct",
    "sector_momentum_5d", "sector_momentum_20d",
} | {f"max_recovery_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS} \
  | {f"max_further_drop_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS}
INT_COLS = {
    "volume", "avg_volume_20d", "adv_dollar", "market_cap", "scans_count",
    "forward_days_available", "horizon", "day_of_max_recovery", "day_of_max_drop",
    "trough_day", "dn",
    "total_finviz_candidates", "passed_floor", "below_min_price", "below_min_cap",
    "below_min_adv", "drop_below_threshold", "other_rejects",
} | set(config.RECLAIM_GRID_COLUMNS)   # grid values are D+n day counts (or blank)
FLOAT_COLS = {
    "price", "open", "high", "low_so_far", "prev_close", "rsi_14",
    "volume_ratio", "ref_close", "first_cross_price", "intraday_low",
    "ref_close_window", "trough_price", "vix_level", "drop_day_rel_volume",
    "atr_14", "drop_in_atr",
}

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

# Display-only short labels for long column names (header shortening; underlying
# column names / data are UNCHANGED — applied only at render via Styler.relabel).
SHORT_LABELS = {
    # watchlist — drop / mid
    "drop_pct_from_open": "drop%open", "close_pct_from_open": "close%open",
    "pct_change_prevclose": "%prevcls", "liquidity_bucket": "liq",
    "market_regime": "regime", "adv_dollar": "adv$", "market_cap": "mcap",
    "rsi_14": "rsi", "spy_change_pct": "spy%", "sector_etf_change_pct": "sectETF%",
    "drop_pct_window": "drop%win", "lookback_trading_days": "lookback",
    "ref_close_window": "refcls_win",
    # watchlist — context signals
    "pct_from_52w_high": "%52wH", "pct_from_52w_low": "%52wL",
    "prior_decline_20d_pct": "decl20d%", "prior_decline_60d_pct": "decl60d%",
    "vix_level": "vix", "drop_day_rel_volume": "relvol",
    "sector_momentum_5d": "secmom5d", "sector_momentum_20d": "secmom20d",
    # watchlist — intraday path
    "first_cross_at": "1stX@", "first_cross_price": "1stX_px",
    "first_cross_drop_pct": "1stX_drop%", "intraday_low": "id_low",
    "intraday_low_at": "id_low@", "recovery_from_low_pct": "rec%low",
    "reversal_confirmed": "rev_ok", "scans_count": "scans",
    "last_update_at": "upd@",
    # post_analysis
    "forward_days_available": "fwd_days", "ref_close": "refcls",
    "max_recovery_pct": "maxrec%", "day_of_max_recovery": "d_maxrec",
    "max_further_drop_pct": "maxdrop%", "day_of_max_drop": "d_maxdrop",
    "trough_price": "trough_px", "trough_day": "trough_d",
    "recovery_from_trough_pct": "rec%trough",
    "max_recovery_from_trough_pct": "maxrec%trough",
    "last_close_pct": "lastcls%", "split_halt_flag": "halt?",
    "split_halt_reason": "halt_why",
    # daily_summary reject buckets
    "total_finviz_candidates": "finviz_n", "passed_floor": "passed",
    "below_min_price": "<price", "below_min_cap": "<cap",
    "below_min_adv": "<adv", "drop_below_threshold": "<drop",
    "other_rejects": "other_rej",
}

_CSS = """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0.5rem; }
    h1 { padding-top: 0.5rem; padding-bottom: 0.5rem; font-size: 1.8rem; margin-top: 0; }
    h2 { padding-top: 0.3rem; padding-bottom: 0.3rem; font-size: 1.2rem; }
    div[data-testid="metric-container"] { padding: 5px; }
    /* ── compact, width-fitting tables (show_table) ───────────────────────────
       Streamlit 1.58's st.dataframe is a canvas grid: it ignores CSS font-size,
       never wraps cells, and adds a horizontal scrollbar when columns overflow.
       We render the SAME styled tables as HTML instead, so every column stays
       visible, cells wrap in-place, and the table fits 100% of the page width
       with NO horizontal scroll. View-only — no data/logic change. */
    .rb-table { width: 100%; overflow-x: hidden; overflow-y: auto; margin-bottom: 0.6rem; }
    .rb-table table { width: 100% !important; table-layout: fixed; border-collapse: collapse;
                      font-size: 0.70rem; direction: ltr; }
    .rb-table th, .rb-table td { word-break: break-word; overflow-wrap: anywhere;
                      white-space: normal; padding: 2px 4px; line-height: 1.15;
                      border: 1px solid rgba(128,128,128,0.18); text-align: left;
                      vertical-align: top; }
    .rb-table th { font-weight: 600; background: rgba(128,128,128,0.14);
                   position: sticky; top: 0; z-index: 1; }
    .rb-table td { font-variant-numeric: tabular-nums; }
</style>
"""


# ── infra helpers ────────────────────────────────────────────────────────────
def setup_page(page_title, page_icon):
    """First Streamlit call on every page: page config + shared CSS."""
    st.set_page_config(page_title=page_title, page_icon=page_icon, layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)


def resolve_sheet_id():
    """Local/CI uses env (config.SHEET_ID); Streamlit Cloud uses st.secrets."""
    if config.SHEET_ID:
        return config.SHEET_ID
    try:
        return st.secrets.get("REBOUND_SHEET_ID", "")
    except Exception:
        return ""


# Friendly degradation text for a Sheets quota (429) spike — shown instead of a
# red traceback that would kill the whole page. Transient; recovers in ~1 min.
QUOTA_MSG = ("🕒 הנתונים זמנית לא זמינים — חריגת-מכסה ב-Google Sheets API "
             "(יותר מדי קריאות בו-זמנית). הנתונים יחזרו תוך כדקה — נסה רענון.")

# cache TTL 300s: live monitoring wants data <=5 min old. The status banner
# auto-refreshes every 300s (st.fragment), so TTL matches the refresh cadence.
# Tradeoff: more frequent Sheet reads than the old 900s — acceptable for a
# low-viewer monitoring dashboard.
CACHE_TTL = 300


def _coerce(header, rows, num_cols):
    if not header:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=header)
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL)
def load(sheet_id, tab, num_cols):
    header, rows = sm.read_rows(sheet_id, tab)
    return _coerce(header, rows, num_cols)


@st.cache_data(ttl=CACHE_TTL)
def _read_batch(sheet_id, tabs):
    """Cached raw batch read (tabs is a tuple for hashability) → {tab:(hdr,rows)}.
    One values:batchGet for all tabs instead of one read per tab — collapses a
    full page render from ~10 Sheet API calls to ~2."""
    return sm.batch_read(sheet_id, list(tabs))


def load_many(sheet_id, specs):
    """specs: {tab: num_cols}. Reads ALL tabs in one batch and returns
    {tab: DataFrame} (numeric-coerced per tab)."""
    raw = _read_batch(sheet_id, tuple(specs))
    return {tab: _coerce(*raw.get(tab, ([], [])), num_cols)
            for tab, num_cols in specs.items()}


def kpi(col, label, value):
    col.metric(label, value)


# Shared "view-only" disclaimer + page header — keeps titles/captions consistent
# across Home and the hypothesis pages (avoids per-page wording drift).
VIEW_ONLY = "תצוגה בלבד · אין ניקוד/אותות/דירוג/המלצות (M5, ממתינים ל-M4)"


def page_header(title, sub):
    """Consistent page title (H1) + sub-caption used by every page."""
    st.title(title)
    st.caption(sub)


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


def show_table(obj, height=None, rename=SHORT_LABELS):
    """View-only replacement for st.dataframe that NEVER scrolls horizontally.

    Accepts a DataFrame (auto-formatted via styled()) or a ready Styler (e.g. one
    that already has a row-highlight .apply). Renders as a compact HTML table:
    table-layout:fixed + width:100% makes every column share the page width and
    wrap in-cell, so all columns stay visible with no horizontal scroll. `rename`
    only relabels the DISPLAYED headers (data/column names unchanged); `height`
    caps the vertical box (px) and turns on vertical scroll. No logic/data change.
    """
    sty = styled(obj) if isinstance(obj, pd.DataFrame) else obj
    if rename:
        cols = list(sty.data.columns)
        sty = sty.relabel_index([rename.get(c, c) for c in cols], axis="columns")
    html = sty.hide(axis="index").to_html()
    box = f"max-height:{int(height)}px;" if height else ""
    st.markdown(f'<div class="rb-table" style="{box}">{html}</div>',
                unsafe_allow_html=True)


def _highlight_contaminated(row):
    """Row-level red highlight for split/halt-flagged post_analysis rows."""
    flagged = str(row.get("split_halt_flag", "")).strip().lower() in ("true", "1")
    return ["background-color: #5a1a1a" if flagged else "" for _ in row]


def coalesce_kind(watch):
    """Legacy rows (pre-gradual_drop) have no/blank drop_kind -> intraday_drop,
    so they never disappear from a hypothesis page."""
    watch = watch.copy()
    if "drop_kind" not in watch.columns:
        watch["drop_kind"] = "intraday_drop"
    else:
        watch["drop_kind"] = watch["drop_kind"].replace("", "intraday_drop").fillna("intraday_drop")
    return watch


def restrict(df, keys):
    """Keep only rows whose (scan_date, ticker) is in keys — so the forward layers
    on a hypothesis page show only that hypothesis's events."""
    if df.empty or "scan_date" not in df.columns or "ticker" not in df.columns:
        return df
    mask = [(str(sd), str(tk)) in keys for sd, tk in zip(df["scan_date"], df["ticker"])]
    return df[pd.Series(mask, index=df.index)]


# ── Overview (home) — DESCRIPTIVE buckets, NOT signals (M3) ───────────────────
# Status thresholds are display labels for "where is it now vs entry", never a
# buy/sell signal. last_close_pct = % from the entry/ref close to the last
# available close.
OVERVIEW_STATUS_LABELS = {
    "recovering": "🟢 מתאוששת", "stable": "⚪ יציבה", "down": "🟠 עדיין-למטה",
    "falling": "🔴 נופלת", "pending": "⏳ ממתין",
}
OUTCOME_BINS = [(-math.inf, -10, "falling"), (-10, -3, "down"),
                (-3, 3, "stable"), (3, math.inf, "recovering")]


def classify_overview_status(last_close_pct, has_forward):
    """Descriptive bucket of where an event sits now vs entry (NOT a signal):
    pending if no forward data yet; else by last_close_pct — >=+3 recovering,
    [-3,+3) stable, [-10,-3) down, <-10 falling."""
    if not has_forward or last_close_pct is None:
        return "pending"
    try:
        x = float(last_close_pct)
    except (TypeError, ValueError):
        return "pending"
    if math.isnan(x):
        return "pending"
    if x >= 3:
        return "recovering"
    if x >= -3:
        return "stable"
    if x >= -10:
        return "down"
    return "falling"


def build_overview_table(watch, post, fdaily):
    """One row per watch event (newest entry first), LEFT-joined to post_analysis
    scalars and to its forward_daily trajectory. Missing post -> pending / 0 days."""
    out_cols = ["ticker", "drop_kind", "scan_date", "days", "pct_from_entry",
                "peak", "trough", "trajectory", "status"]
    if watch is None or watch.empty:
        return pd.DataFrame(columns=out_cols)
    base = watch[["scan_date", "ticker", "drop_kind"]].drop_duplicates(
        subset=["scan_date", "ticker"]).copy()
    pcols = ["scan_date", "ticker", "last_close_pct", "max_recovery_pct",
             "max_further_drop_pct", "forward_days_available"]
    p = (post[[c for c in pcols if c in post.columns]].copy()
         if post is not None and not post.empty else pd.DataFrame(columns=pcols))
    t = base.merge(p, on=["scan_date", "ticker"], how="left")
    for c in ("last_close_pct", "max_recovery_pct", "max_further_drop_pct",
              "forward_days_available"):
        if c not in t.columns:
            t[c] = float("nan")
    # forward_daily trajectory (cum_pct_from_ref ordered by day_offset) per event
    traj = {}
    if fdaily is not None and not fdaily.empty and \
            {"scan_date", "ticker", "day_offset", "cum_pct_from_ref"} <= set(fdaily.columns):
        f = fdaily.assign(_o=pd.to_numeric(fdaily["day_offset"], errors="coerce")).sort_values("_o")
        for (sd, tk), g in f.groupby(["scan_date", "ticker"]):
            traj[(str(sd), str(tk))] = [float(v) for v in
                                        pd.to_numeric(g["cum_pct_from_ref"], errors="coerce").dropna()]
    t["trajectory"] = [traj.get((str(sd), str(tk)), [])
                       for sd, tk in zip(t["scan_date"], t["ticker"])]
    t["pct_from_entry"] = pd.to_numeric(t["last_close_pct"], errors="coerce")
    t["days"] = pd.to_numeric(t["forward_days_available"], errors="coerce").fillna(0).astype(int)
    t["peak"] = pd.to_numeric(t["max_recovery_pct"], errors="coerce")
    t["trough"] = pd.to_numeric(t["max_further_drop_pct"], errors="coerce")
    has_fwd = [(len(tr) > 0) or (d > 0) for tr, d in zip(t["trajectory"], t["days"])]
    t["status"] = [classify_overview_status(p, hf)
                   for p, hf in zip(t["pct_from_entry"], has_fwd)]
    t = t.sort_values(["scan_date", "ticker"], ascending=[False, True]).reset_index(drop=True)
    return t[out_cols]


def recovery_curve(fdaily):
    """Mean cum_pct_from_ref per (drop_kind, day_offset) — average recovery path
    per hypothesis. Empty-safe."""
    cols = ["drop_kind", "day_offset", "mean_cum_pct"]
    if fdaily is None or fdaily.empty or \
            not {"drop_kind", "day_offset", "cum_pct_from_ref"} <= set(fdaily.columns):
        return pd.DataFrame(columns=cols)
    g = (fdaily.assign(_c=pd.to_numeric(fdaily["cum_pct_from_ref"], errors="coerce"))
         .groupby(["drop_kind", "day_offset"])["_c"].mean().reset_index())
    g.columns = cols
    return g


def outcome_histogram(last_close_series):
    """Count of events per last_close_pct bucket (falling->recovering, red->green)."""
    s = pd.to_numeric(pd.Series(last_close_series), errors="coerce").dropna()
    rows = []
    for lo, hi, name in OUTCOME_BINS:
        n = int((s >= lo).sum()) if hi == math.inf else int(((s >= lo) & (s < hi)).sum())
        rows.append({"bucket": name, "count": n})
    return pd.DataFrame(rows)


def sidebar_controls(sheet_id):
    with st.sidebar:
        st.header("⚙️ Controls")
        if st.button("🔄 Refresh data", type="primary"):
            st.cache_data.clear()
            st.rerun()
        st.caption("נתונים נקראים מ-Google Sheet (cache 5 דק' · רענון אוטומטי כל 5 דק').")
        st.caption(f"Sheet: …{sheet_id[-8:]}")
        try:
            st.caption(f"SA: {sm.service_account_email()}")
        except Exception:
            pass


# ── per-tab renderers ────────────────────────────────────────────────────────
def _health(watch, post, summ, days):
    st.subheader("🩺 בריאות האיסוף")
    last_day = days[-1] if days else "—"
    last_day_n = int((watch["scan_date"] == last_day).sum())
    c = st.columns(4)
    kpi(c[0], "ריצה אחרונה (scan_date)", last_day)
    kpi(c[1], "מועמדים ביום האחרון", last_day_n)
    kpi(c[2], "סה\"כ שורות (השערה זו)", len(watch))
    kpi(c[3], "ימי מסחר ייחודיים", len(days))

    st.markdown("**מועמדים/יום שעברו את הרצפה הקשיחה**")
    per_day = watch.groupby("scan_date").size().reset_index(name="candidates")
    plot(st, px.bar(per_day, x="scan_date", y="candidates"))

    st.markdown("**טריות הדאטה (post_analysis סטטוס)**")
    if not post.empty and "status" in post.columns:
        sc = st.columns(4)
        kpi(sc[0], "ok (חלון מלא)", int(post["status"].isin(["ok"]).sum()))
        kpi(sc[1], "pending (טרם הבשיל)",
            int(post["status"].isin(["pending_forward", "forward_pending"]).sum()))
        kpi(sc[2], "partial / גאפ", int(post["status"].str.startswith("partial").sum()))
        kpi(sc[3], "halt / delisted", int((post["status"] == "delisted_or_halted").sum()))
        # contamination monitor — flagged split/halt rows (excluded from M4 aggregates)
        if "split_halt_flag" in post.columns and len(post):
            flagged = int(post["split_halt_flag"].astype(str).str.lower().isin(["true", "1"]).sum())
            pct = round(flagged / len(post) * 100, 1)
            cc = st.columns(4)
            cc[0].metric("🧪 שורות מזוהמות (split/halt)", f"{flagged} ({pct}%)")
            if flagged:
                cc[1].caption("⚠️ שורות מסומנות מוחרגות מאגרגטי M4 — ה-recovery שלהן ארטיפקט.")
    else:
        st.info("post_analysis עדיין ריק להשערה זו.")

    st.markdown("**פילוח סיבות-דחייה (EOD scanner) — `daily_summary`**")
    st.caption("הערה: daily_summary הוא בריאות סורק ה-EOD (intraday_drop) — גלובלי, "
               "לא מפוצל לפי drop_kind (לסורק gradual אין עדיין טבלת-דחיות נפרדת).")
    if summ.empty:
        st.info("daily_summary עדיין ריק — יתמלא בריצת ה-EOD הבאה.")
    else:
        summ = summ.sort_values("scan_date")
        reject_cols = ["below_min_price", "below_min_cap", "below_min_adv", "drop_below_threshold"]
        melt = summ.melt(id_vars="scan_date", value_vars=reject_cols,
                         var_name="reason", value_name="count")
        plot(st, px.bar(melt, x="scan_date", y="count", color="reason",
                        title="דחיות לפי יום (stacked)"))
        show = ["scan_date", "total_finviz_candidates", "passed_floor"] + reject_cols + ["other_rejects"]
        show = [c for c in show if c in summ.columns]
        show_table(summ[show].sort_values("scan_date", ascending=False))


def _watchlist(watch, drop_kind, days):
    st.subheader("📋 watchlist_live — נתונים גולמיים")
    # NO drop_kind filter — the page itself is the hypothesis filter.
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

    # Too many columns for one readable table → split into vertical THEME groups
    # (~10-12 cols each). `ticker` is the anchor at the head of every group, and the
    # view is sorted ONCE below so rows line up across the three tables (row N is the
    # same event everywhere). Every displayed column belongs to exactly one group;
    # drop_kind-specific columns simply filter out when absent (no column dropped).
    # drop_kind is OMITTED from the tables — it is constant within a page (the page
    # IS the hypothesis); it stays in the data and on the Home page. drop_type kept.
    GROUPS = [
        ("🪪 זיהוי + צניחה",
         ["ticker", "scan_date", "exchange",
          "drop_pct_from_open", "drop_pct_window", "price", "liquidity_bucket",
          "sector", "market_regime", "market_cap", "adv_dollar", "drop_type"]),
        ("📐 הקשר + מומנטום (תיאורי — לא אות-כניסה)",
         ["ticker", "rsi_14", "pct_from_52w_high", "pct_from_52w_low",
          "prior_decline_20d_pct", "prior_decline_60d_pct", "vix_level",
          "drop_day_rel_volume", "sector_momentum_5d", "sector_momentum_20d"]),
        ("⏱️ מסלול תוך-יומי + מקור",
         ["ticker", "source", "first_cross_at", "first_cross_price",
          "first_cross_drop_pct", "intraday_low", "intraday_low_at",
          "recovery_from_low_pct", "reversal_confirmed", "scans_count",
          "last_update_at", "lookback_trading_days", "ref_close_window"]),
    ]
    # sort controls — applied ONCE to the shared view so the 3 theme tables stay
    # row-aligned (row N is the same event in all three). Default = drop depth,
    # ascending (deepest drop first), preserving the prior order.
    depth_col = "drop_pct_window" if drop_kind == "gradual_drop" else "drop_pct_from_open"
    sort_opts = [("עומק-צניחה", depth_col), ("price", "price"), ("rsi", "rsi_14"),
                 ("market_cap", "market_cap"), ("rel-volume", "drop_day_rel_volume"),
                 ("scan_date", "scan_date"), ("ticker", "ticker")]
    sort_opts = [(lbl, c) for lbl, c in sort_opts if c in view.columns]
    sb = st.columns([2, 1])
    sel_sort = sb[0].selectbox("מיין לפי", [lbl for lbl, _ in sort_opts], index=0)
    asc = sb[1].radio("סדר", ["יורד", "עולה"], index=1, horizontal=True) == "עולה"
    sortcol = dict(sort_opts).get(sel_sort, "scan_date")
    sortcol = sortcol if sortcol in view.columns else "scan_date"
    view = view.sort_values(sortcol, ascending=asc, na_position="last")
    st.caption(f"{len(view)} שורות · מאורגן ל-טבלאות-נושא (ticker עוגן בכל אחת; "
               "אפס עמודה הושמטה)")
    for title, group_cols in GROUPS:
        present = [c for c in group_cols if c in view.columns]
        if len(present) <= 1:                   # nothing beyond the ticker anchor → skip
            continue
        st.markdown(f"**{title}**")
        show_table(view[present], height=420)


def _stock_card(watch, post, ts, fund, news, fdaily):
    st.subheader("🃏 כרטיס מניה")
    st.caption("תצוגה בלבד · מסלול תוך-יומי + תוצאות forward + תעודת-זהות פונדמנטלית + חדשות.")
    tickers = sorted(watch["ticker"].dropna().unique())
    if not tickers:
        st.info("אין מניות במעקב עדיין.")
        return
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
            try:                                  # tolerate blank/"" / non-numeric
                lb = int(float(r0.get("lookback_trading_days")))
            except (TypeError, ValueError):
                lb = config.GRADUAL_LOOKBACK_DAYS
            drop_label, drop_val = f"drop {lb}d (הדרגתי)", r0.get("drop_pct_window")
        else:
            drop_label, drop_val = "drop מהפתיחה", r0.get("drop_pct_from_open")
        m = st.columns(6)
        kpi(m[0], "drop_kind", kind)
        kpi(m[1], drop_label, f"{drop_val:.2f}%" if pd.notna(drop_val) else "—")
        kpi(m[2], "price (D0)", f"{r0.get('price'):,.2f}" if pd.notna(r0.get("price")) else "—")
        kpi(m[3], "liquidity", r0.get("liquidity_bucket", "—"))
        kpi(m[4], "sector", r0.get("sector", "—"))
        kpi(m[5], "regime", r0.get("market_regime", "—"))

        # prior-decline context (descriptive — NOT an entry signal)
        ctx = [("מהשיא 52ש'", r0.get("pct_from_52w_high")),
               ("מהשפל 52ש'", r0.get("pct_from_52w_low")),
               ("ירידה 20 ימים", r0.get("prior_decline_20d_pct")),
               ("ירידה 60 ימים", r0.get("prior_decline_60d_pct"))]
        st.caption("**הקשר ירידה קודמת (תיאורי, לא אות-כניסה):** " +
                   " · ".join(f"{lbl}: {v:.2f}%" if pd.notna(v) else f"{lbl}: —"
                              for lbl, v in ctx))
        # research-based context signals (descriptive — NOT entry signals)
        vix = r0.get("vix_level"); rv = r0.get("drop_day_rel_volume")
        sm5 = r0.get("sector_momentum_5d"); sm20 = r0.get("sector_momentum_20d")
        sig = [("VIX", vix, "{:.2f}"), ("rel-vol יום-צניחה", rv, "{:.2f}×"),
               ("תנופת-סקטור 5י'", sm5, "{:.2f}%"), ("20י'", sm20, "{:.2f}%")]
        st.caption("**סממני-הקשר (תיאורי, לא אות-כניסה):** " +
                   " · ".join(f"{lbl}: {fmt.format(v)}" if pd.notna(v) else f"{lbl}: —"
                              for lbl, v, fmt in sig))

    # 1) intraday time-series
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
            plot(gg[0], px.line(tv, x="ts", y="price", markers=True,
                                title="price לאורך הזמן"))
            plot(gg[1], px.line(tv, x="ts", y="pct_from_open", markers=True,
                                title="% מהפתיחה (אותו יום)"))
            st.caption(f"{len(tv)} נקודות מעקב")

    # 2) forward outcomes (post_analysis)
    st.markdown("**תוצאות forward (post_analysis)**")
    if post.empty:
        st.info("post_analysis עדיין ריק.")
    else:
        pvc = post[(post["ticker"] == sel_t) & (post["scan_date"] == sel_d)]
        if pvc.empty:
            st.info("אין עדיין post_analysis למניה/תאריך שנבחרו.")
        else:
            r0p = pvc.iloc[0]
            if str(r0p.get("split_halt_flag", "")).strip().lower() in ("true", "1"):
                st.warning(f"⚠️ **מזוהם (split/halt): {r0p.get('split_halt_reason', '')}** — "
                           "ה-recovery למטה הוא ארטיפקט, אל תסמוך עליו (יוחרג ב-M4).")
            pcols = ["scan_date", "ticker", "status", "split_halt_flag", "split_halt_reason",
                     "forward_days_available",
                     "ref_close", "max_recovery_pct", "day_of_max_recovery",
                     "max_further_drop_pct", "day_of_max_drop",
                     "trough_price", "trough_day", "recovery_from_trough_pct",
                     "max_recovery_from_trough_pct", "last_close_pct", "dN_date"]
            pcols = [c for c in pcols if c in pvc.columns]
            show_table(pvc[pcols])
            # (sub-window max-recovery bar chart removed — the per-day forward
            #  path below supersedes it; the D+3/5/10/20 numbers stay in the
            #  post table above.)

    # 2.5) forward_daily — per-day path D+1..D+N (cumulative + day-over-day)
    hz = config.POST_ANALYSIS_HORIZON
    st.markdown(f"**מסלול יומי D+1..D+{hz} (מצטבר מהכניסה + שינוי-יומי) — תיאורי, לא אות**")
    fdc = (fdaily[(fdaily["ticker"] == sel_t) & (fdaily["scan_date"] == sel_d)]
           if not fdaily.empty else fdaily)
    if fdc.empty:
        st.info(f"החלון טרם הבשיל — 0/{hz} ימים נאספו (יתמלא בריצות ה-EOD הבאות).")
    else:
        fdc = fdc.sort_values("day_offset")
        ndays = len(fdc)
        last_cum = fdc["cum_pct_from_ref"].iloc[-1]
        mm = st.columns(2)
        kpi(mm[0], "מצטבר נוכחי (מהכניסה)",
            f"{last_cum:.2f}%" if pd.notna(last_cum) else "—")
        kpi(mm[1], "ימים שנאספו", f"{ndays}/{hz}")

        # real short dates on the x-axis (DD.MM); D0 = the entry/scan_date
        def _short(d):
            t = pd.to_datetime(d, errors="coerce")
            return t.strftime("%d.%m") if pd.notna(t) else str(d)
        dlab = [_short(d) for d in fdc["date"]]
        d0lab = _short(sel_d)
        cum = list(fdc["cum_pct_from_ref"])
        dchg = list(fdc["daily_change_pct"])
        YELLOW, BLUE = "#fbc02d", "#1f77b4"
        gg2 = st.columns(2)

        # cumulative-from-entry line — D0 point (0%) yellow + enlarged at the left
        cx, cy = [d0lab] + dlab, [0.0] + cum
        ctext = ["0.0%"] + [f"{v:+.1f}%" if pd.notna(v) else "" for v in cum]
        figc = go.Figure(go.Scatter(
            x=cx, y=cy, mode="lines+markers+text", line=dict(color=BLUE),
            text=ctext, textposition="top center",
            marker=dict(color=[YELLOW] + [BLUE] * len(dlab), size=[13] + [7] * len(dlab))))
        figc.add_annotation(x=d0lab, y=0, text="כניסה", showarrow=False, yshift=-20,
                            font=dict(color=YELLOW, size=11))
        plot(gg2[0], style_fig(figc, "מצטבר מהכניסה (%) — נקודת-כניסה צהובה",
                               category=True, pct=True))

        # daily change — D0 = reference (NO bar); other days green/red + value labels
        bx, by = [d0lab] + dlab, [None] + dchg
        btext = [""] + [f"{v:+.1f}%" if pd.notna(v) else "" for v in dchg]
        figd = go.Figure(go.Bar(x=bx, y=by, marker_color=[YELLOW] + sign_colors(dchg),
                                text=btext, textposition="outside"))
        figd.add_annotation(x=d0lab, y=0, text="כניסה", showarrow=False,
                            font=dict(color=YELLOW, size=11))
        plot(gg2[1], style_fig(figd, "שינוי יומי (%) — D0=כניסה (ללא שינוי)",
                               category=True, pct=True))

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
                    show_table(pd.DataFrame(avail, columns=["שדה", "ערך"]))

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
                show_table(pd.DataFrame(items, columns=["datetime", "source", "headline", "url"]))
            else:
                st.caption("אין כותרות שמורות.")


def _post(post):
    st.subheader("🎯 post_analysis — תוצאות forward (ככל שמתמלאות)")
    if post.empty:
        st.info("עדיין אין post_analysis להשערה זו.")
        return
    statuses = sorted(post["status"].dropna().unique()) if "status" in post else []
    sel_st = st.multiselect("status", statuses, default=statuses)
    pv = post[post["status"].isin(sel_st)] if sel_st else post
    up_col = next((c for c in post.columns if c.startswith("touched_up_")), None)
    dn_col = next((c for c in post.columns if c.startswith("touched_down_")), None)
    cols = ["scan_date", "ticker", "status", "split_halt_flag", "split_halt_reason",
            "forward_days_available", "ref_close",
            "max_recovery_pct", "day_of_max_recovery", "max_further_drop_pct",
            "day_of_max_drop",
            # recovery-from-trough group (descriptive reversal record)
            "trough_price", "trough_day", "recovery_from_trough_pct",
            "max_recovery_from_trough_pct",
            up_col, dn_col, "last_close_pct", "dN_date"]
    cols = [c for c in cols if c and c in pv.columns]
    # contamination monitor
    if "split_halt_flag" in pv.columns and len(pv):
        nflag = int(pv["split_halt_flag"].astype(str).str.lower().isin(["true", "1"]).sum())
        if nflag:
            st.warning(f"⚠️ {nflag}/{len(pv)} שורות מסומנות split/halt — ה-recovery שלהן ארטיפקט "
                       "(מודגשות באדום). יוחרגו מאגרגטי M4; הנתון הגולמי נשמר.")
    st.caption(f"{len(pv)} שורות · halt/delist מוצג מפורשות כסטטוס (לא מושמט)")
    styler = styled(pv[cols])
    if "split_halt_flag" in cols:
        styler = styler.apply(_highlight_contaminated, axis=1)
    show_table(styler, height=460)

    # max_recovery distribution — exclude contaminated rows so the artifact spikes
    # don't distort the descriptive view (raw rows are still kept in the table above).
    matured = post[post["status"].isin(["ok"]) | post["status"].str.startswith("partial")]
    if "split_halt_flag" in matured.columns:
        clean = matured[~matured["split_halt_flag"].astype(str).str.lower().isin(["true", "1"])]
    else:
        clean = matured
    if not clean.empty and clean["max_recovery_pct"].notna().any():
        st.markdown("**התפלגות max_recovery_pct (שורות נקיות שהבשילו) — תיאורי בלבד**")
        plot(st, px.histogram(clean, x="max_recovery_pct", nbins=30))


def _stats(watch, drop_kind):
    st.subheader("📊 סטטיסטיקה תיאורית")
    st.caption("תיאור הנתונים בלבד — ללא ניקוד, דירוג או תוחלת רווח.")
    g = st.columns(2)
    if "liquidity_bucket" in watch:
        bc = watch["liquidity_bucket"].value_counts().reset_index()
        bc.columns = ["liquidity_bucket", "count"]
        plot(g[0], px.bar(bc, x="liquidity_bucket", y="count", title="לפי דלי נזילות"))
    if "market_regime" in watch:
        rc = watch["market_regime"].value_counts().reset_index()
        rc.columns = ["market_regime", "count"]
        plot(g[1], px.bar(rc, x="market_regime", y="count", title="לפי משטר שוק"))
    g2 = st.columns(2)
    if "sector" in watch:
        scn = watch["sector"].value_counts().reset_index()
        scn.columns = ["sector", "count"]
        plot(g2[0], px.bar(scn, x="count", y="sector", orientation="h", title="לפי סקטור"))
    depth_col = "drop_pct_window" if drop_kind == "gradual_drop" else "drop_pct_from_open"
    depth_title = ("עומק ירידה 5-ימים (%)" if drop_kind == "gradual_drop"
                   else "עומק צניחה מהפתיחה (%)")
    if depth_col in watch and watch[depth_col].notna().any():
        plot(g2[1], px.histogram(watch, x=depth_col, nbins=30, title=depth_title))


# ── page orchestrator ────────────────────────────────────────────────────────
def render_overview(sheet_id):
    """Home 'overview': one descriptive table of what each event did from entry to
    now (% from entry, days, trajectory sparkline, status) + two aggregate views.
    M3, VIEW-ONLY — the status buckets are descriptive, never signals."""
    try:
        data = load_many(sheet_id, {config.TAB_WATCHLIST: NUM_WATCH,
                                    config.TAB_POST: NUM_POST,
                                    config.TAB_FORWARD_DAILY: NUM_FDAILY})
    except gspread.exceptions.APIError as e:
        (st.info(QUOTA_MSG) if _is_quota(e) else st.error(f"שגיאת קריאה מה-Sheet: {e}"))
        return
    except Exception as e:
        st.error(f"שגיאת קריאה מה-Sheet: {e}")
        return
    watch = coalesce_kind(data[config.TAB_WATCHLIST])
    if watch.empty:
        st.warning("watchlist_live ריק — עדיין לא נאספו נתונים.")
        return
    tbl = build_overview_table(watch, data[config.TAB_POST], data[config.TAB_FORWARD_DAILY])

    # KPIs (descriptive)
    avg_move = tbl["pct_from_entry"].dropna().mean()
    k = st.columns(4)
    kpi(k[0], "סה\"כ במעקב", len(tbl))
    kpi(k[1], "🟢 מתאוששות", int((tbl["status"] == "recovering").sum()))
    kpi(k[2], "🔴/🟠 עדיין-למטה", int(tbl["status"].isin(["down", "falling"]).sum()))
    kpi(k[3], "תנועה ממוצעת", f"{avg_move:+.1f}%" if pd.notna(avg_move) else "—")

    # filters
    with st.expander("🔎 סינון", expanded=False):
        all_kinds = sorted(tbl["drop_kind"].dropna().unique())
        kinds = st.multiselect("סוג", all_kinds, default=all_kinds)
        statuses = st.multiselect("סטטוס", list(OVERVIEW_STATUS_LABELS),
                                  default=list(OVERVIEW_STATUS_LABELS),
                                  format_func=lambda s: OVERVIEW_STATUS_LABELS.get(s, s))
        dts = sorted(tbl["scan_date"].dropna().unique())
        dr = st.select_slider("טווח תאריך-כניסה", options=dts,
                              value=(dts[0], dts[-1])) if len(dts) > 1 else None
    view = tbl[tbl["drop_kind"].isin(kinds) & tbl["status"].isin(statuses)]
    if dr:
        view = view[(view["scan_date"] >= dr[0]) & (view["scan_date"] <= dr[1])]

    disp = pd.DataFrame({
        "טיקר": view["ticker"],
        "סוג": view["drop_kind"].map({"intraday_drop": "⚡ intraday",
                                      "gradual_drop": "🐢 gradual"}).fillna(view["drop_kind"]),
        "תאריך-כניסה": view["scan_date"],
        "ימים": view["days"],
        "% מהכניסה": view["pct_from_entry"],
        "מסלול": view["trajectory"],
        "סטטוס": view["status"].map(lambda s: OVERVIEW_STATUS_LABELS.get(s, s)),
    })
    st.dataframe(disp, width="stretch", hide_index=True, column_config={
        "ימים": st.column_config.NumberColumn(format="%d"),
        "% מהכניסה": st.column_config.NumberColumn(format="%+.2f%%"),
        "מסלול": st.column_config.LineChartColumn("מסלול (cum% מהכניסה)"),
    })
    st.caption("סטטוס תיאורי בלבד — היכן המניה כעת מול הכניסה. **אין כאן אות/המלצה.**")

    # aggregate 1 — average recovery curve (intraday vs gradual)
    st.markdown("**עקומת-התאוששות ממוצעת — cum% מהכניסה לכל יום-קדימה**")
    rc = recovery_curve(data[config.TAB_FORWARD_DAILY])
    if not rc.empty:
        plot(st, px.line(rc, x="day_offset", y="mean_cum_pct", color="drop_kind", markers=True))
    else:
        st.caption("אין עדיין נתוני forward_daily לעקומה.")

    # aggregate 2 — outcome distribution histogram (red -> green)
    st.markdown("**התפלגות-תוצאות — ספירת אירועים לפי % מהכניסה**")
    hist = outcome_histogram(tbl["pct_from_entry"])
    if int(hist["count"].sum()) > 0:
        order = ["falling", "down", "stable", "recovering"]
        cmap = {"falling": RED, "down": "#ffa726", "stable": GREY, "recovering": GREEN}
        plot(st, px.bar(hist, x="bucket", y="count", color="bucket",
                        category_orders={"bucket": order}, color_discrete_map=cmap))
    else:
        st.caption("אין עדיין תוצאות-forward להתפלגות.")


def render(drop_kind, heading, blurb):
    """Render the full tab set for ONE hypothesis (drop_kind). Called by each page.

    drop_kind: "intraday_drop" | "gradual_drop" (the page IS the filter).
    """
    page_header(heading, blurb + " · " + VIEW_ONLY)

    sheet_id = resolve_sheet_id()
    if not sheet_id:
        st.error("REBOUND_SHEET_ID לא מוגדר (.env / env / st.secrets). אין מקור נתונים.")
        st.stop()
    sidebar_controls(sheet_id)

    try:
        # one batched read for all tabs (≈2 API calls total, not ~2 per tab)
        data = load_many(sheet_id, {
            config.TAB_WATCHLIST: NUM_WATCH, config.TAB_POST: NUM_POST,
            config.TAB_TIMESERIES: NUM_TS, config.TAB_FUNDAMENTALS: [],
            config.TAB_NEWS: [], config.TAB_SUMMARY: NUM_SUMMARY,
            config.TAB_FORWARD_DAILY: NUM_FDAILY,
        })
        watch, post, ts = (data[config.TAB_WATCHLIST], data[config.TAB_POST],
                           data[config.TAB_TIMESERIES])
        fund, news, summ = (data[config.TAB_FUNDAMENTALS], data[config.TAB_NEWS],
                            data[config.TAB_SUMMARY])
        fdaily = data[config.TAB_FORWARD_DAILY]
    except gspread.exceptions.APIError as e:
        (st.info(QUOTA_MSG) if _is_quota(e) else st.error(f"שגיאת קריאה מה-Sheet: {e}"))
        st.stop()
    except Exception as e:
        st.error(f"שגיאת קריאה מה-Sheet: {e}")
        st.stop()

    if watch.empty:
        st.warning("watchlist_live ריק — עדיין לא נאספו נתונים.")
        st.stop()
    watch = coalesce_kind(watch)

    # the page IS the hypothesis filter — restrict watch + the forward layers
    watch = watch[watch["drop_kind"] == drop_kind]
    if watch.empty:
        st.info(f"אין עדיין שורות עבור {drop_kind}. (השערה זו טרם תפסה מניות.)")
        st.stop()
    keys = set(zip(watch["scan_date"].astype(str), watch["ticker"].astype(str)))
    post, ts = restrict(post, keys), restrict(ts, keys)
    fund, news = restrict(fund, keys), restrict(news, keys)
    fdaily = restrict(fdaily, keys)

    days = sorted(watch["scan_date"].dropna().unique())
    th, tw, tc, tp, tstat = st.tabs(
        ["🩺 Collection Health", "📋 Watchlist", "🃏 Stock Card",
         "🎯 Post-Analysis", "📊 Descriptive Stats"])
    with th:
        _health(watch, post, summ, days)
    with tw:
        _watchlist(watch, drop_kind, days)
    with tc:
        _stock_card(watch, post, ts, fund, news, fdaily)
    with tp:
        _post(post)
    with tstat:
        _stats(watch, drop_kind)
    st.caption("ReboundPro · monitoring only · אין כאן לוגיקת מסחר.")


# ── System Health (operational control — NOT data-quality/edge) ──────────────
_HEALTH_ICON = {"healthy": "✅", "warning": "⚠️", "error": "❌"}
_SEV_NUM = {"healthy": 0, "warning": 1, "error": 2}


def load_health(sheet_id):
    return load(sheet_id, config.TAB_HEALTH_LOG, ["exit_code"])


def _health_age(run_at):
    """(human age string, is_stale>24h). run_at = 'YYYY-MM-DD HH:MM:SS TZ' (ET)."""
    try:
        t = pd.Timestamp(str(run_at)[:19], tz="America/New_York")
        hrs = (pd.Timestamp.now(tz="America/New_York") - t).total_seconds() / 3600
        if hrs < 1:
            return f"לפני {int(hrs * 60)} דקות", False
        if hrs < 24:
            return f"לפני {hrs:.1f} שעות", False
        return f"לפני {hrs / 24:.1f} ימים", True
    except Exception:
        return str(run_at), False


@st.fragment(run_every="300s")
def render_health_banner(sheet_id=None):
    """Top-of-home status banner from the latest health_log run. Resolves the
    sheet id internally (same mechanism as render()) when not supplied.

    Wrapped in st.fragment(run_every="300s"): only this banner re-runs every
    5 min (matching CACHE_TTL=300), pulling a fresh health_log read without a
    full-page rerun — so user selections elsewhere are never reset."""
    if sheet_id is None:
        sheet_id = resolve_sheet_id()
    if not sheet_id:
        return
    try:
        df = load_health(sheet_id)
    except gspread.exceptions.APIError as e:
        # a transient quota spike must NOT take down the whole home page
        st.info(QUOTA_MSG if _is_quota(e) else f"🩺 בקרה לא נקראה מה-Sheet: {e}")
        return
    if df.empty or "run_at" not in df.columns:
        st.info("🩺 בקרה טרם רצה (אין health_log). הרץ `health_monitor.py --morning`.")
        return
    last = df.sort_values("run_at").iloc[-1]
    status = str(last.get("overall_status", "")).strip()
    icon = _HEALTH_ICON.get(status, "❔")
    age, stale = _health_age(last.get("run_at", ""))
    base = (f"{icon} בקרת-מערכת: **{status}** · בדיקה אחרונה {age} · "
            f"mode={last.get('mode', '')} · {last.get('summary_text', '')} · "
            "פרטים בדף **🩺 System Health**")
    if stale:
        st.warning(base + "  ⚠️ **הבקרה לא רצה >24ש'** — בקרה-שלא-רצה היא עצמה בעיה.")
    elif status == "error":
        st.error(base)
    elif status == "warning":
        st.warning(base)
    elif status == "healthy":
        st.success(base)
    else:
        st.info(base)


@st.fragment(run_every="300s")
def render_live_status(sheet_id=None):
    """Descriptive intraday "live status" table: the latest intraday point per
    tracked (scan_date, ticker) from intraday_timeseries — current price, % from
    that day's open, update time (ET) and days-since-entry (D+n). Sorted by
    intraday move SIZE (descriptive ordering only).

    VIEW-ONLY — NO score / signal / ranking / entry decision (M5 boundary).
    Wrapped in st.fragment(run_every="300s") like the health banner, matching
    CACHE_TTL=300: only this table re-runs every 5 min, so nothing else resets.
    intraday_timeseries only grows during market hours, so the table "breathes"
    only when the market is open; off-session it shows the last available point."""
    if sheet_id is None:
        sheet_id = resolve_sheet_id()
    if not sheet_id:
        return
    page_header("📡 מצב חי — תוך-יומי",
                VIEW_ONLY + " · תוך-יומי · נושם בשעות-מסחר בלבד · ≠ סיווג הריבאונד היומי")
    try:
        ts = load(sheet_id, config.TAB_TIMESERIES, ["price", "pct_from_open", "volume"])
    except gspread.exceptions.APIError as e:
        st.info(QUOTA_MSG if _is_quota(e) else f"מצב-חי לא נקרא מה-Sheet: {e}")
        return
    if ts.empty or "timestamp" not in ts.columns:
        st.info("intraday_timeseries עדיין ריק — יתמלא בריצת הסורק התוך-יומי הבאה (שעות-מסחר).")
        return

    ts = ts[ts["timestamp"].astype(str).str.len() >= 16].copy()
    if ts.empty:
        st.info("אין עדיין נקודות תוך-יומיות תקינות.")
        return
    ts["_date"] = ts["timestamp"].astype(str).str[:10]
    # days-since-entry (D+n) = distinct trading dates seen for the event minus 1
    # (D0). Derived from the data itself — no calendar dependency / heavy import.
    dn = (ts.groupby(["scan_date", "ticker"])["_date"].nunique() - 1).rename("dn")
    # latest intraday point per (scan_date, ticker) — string ts sorts chronologically
    latest = (ts.sort_values("timestamp")
                .groupby(["scan_date", "ticker"], as_index=False).tail(1)
                .merge(dn, on=["scan_date", "ticker"], how="left"))

    # reference price + drop_kind joined from the watchlist event (NOT recomputed):
    # intraday reference = open (drop-day open); gradual reference = ref_close_window.
    try:
        watch = load(sheet_id, config.TAB_WATCHLIST, ["open", "ref_close_window"])
    except gspread.exceptions.APIError as e:
        st.info(QUOTA_MSG if _is_quota(e) else f"מצב-חי לא נקרא מה-Sheet: {e}")
        return
    wkeep = [c for c in ("scan_date", "ticker", "open", "ref_close_window", "drop_kind")
             if c in watch.columns]
    wsub = (watch[wkeep].drop_duplicates(["scan_date", "ticker"]) if not watch.empty
            else pd.DataFrame(columns=wkeep))
    latest = latest.merge(wsub, on=["scan_date", "ticker"], how="left")
    if "drop_kind" not in latest.columns:
        latest["drop_kind"] = "intraday_drop"
    latest["drop_kind"] = latest["drop_kind"].replace("", "intraday_drop").fillna("intraday_drop")

    # reference: open for intraday_drop, ref_close_window for gradual_drop
    is_grad = latest["drop_kind"] == "gradual_drop"
    ref = latest["open"].where(~is_grad, latest.get("ref_close_window"))
    latest["reference"] = pd.to_numeric(ref, errors="coerce")
    latest["pct_from_ref"] = ((latest["price"] - latest["reference"])
                              / latest["reference"].where(latest["reference"] > 0)
                              * 100).round(2)

    today = pd.Timestamp.now(tz="America/Lima").strftime("%Y-%m-%d")
    newest = latest["timestamp"].astype(str).max()
    if newest[:10] < today:
        st.caption(f"🕒 השוק סגור — מוצג המצב האחרון מ-{newest} (ET). יתעדכן עם פתיחת-המסחר.")
    else:
        st.caption(f"🟢 חי · עדכון אחרון {newest} (ET) · {len(latest)} מניות במעקב")

    # header-style filters — same idiom as _watchlist; default = all
    KIND_LABELS = {"intraday_drop": "⚡ intraday", "gradual_drop": "🐢 gradual"}
    fc = st.columns(2)
    kinds = sorted(latest["drop_kind"].dropna().unique())
    sel_kind = fc[0].multiselect("סוג", kinds, default=kinds,
                                 format_func=lambda k: KIND_LABELS.get(k, k))
    sdays = sorted(latest["scan_date"].dropna().unique())
    sel_day = fc[1].multiselect("כניסה (scan_date)", sdays, default=sdays)
    view = latest[latest["drop_kind"].isin(sel_kind) & latest["scan_date"].isin(sel_day)]
    if view.empty:
        st.info("אין שורות לבחירה הנוכחית.")
        return

    # initial order: |daily move| descending (descriptive ordering only; the table
    # itself is click-sortable by any column header).
    view = view.assign(_abs=view["pct_from_open"].abs()).sort_values("_abs", ascending=False)
    disp = view.assign(**{"סוג": view["drop_kind"].map(KIND_LABELS).fillna(view["drop_kind"])})[
        ["ticker", "סוג", "scan_date", "dn", "reference", "price",
         "pct_from_open", "pct_from_ref", "volume", "timestamp"]]

    # reuse styled() (%, 2dp, thousands) + sign_colors() for per-sign colour on the
    # two pct columns — no duplicated formatting/colour logic.
    sty = styled(disp)
    for pcol in ("pct_from_open", "pct_from_ref"):
        sty = sty.apply(lambda s: [f"color: {c}" for c in sign_colors(s)], subset=[pcol])

    # Hebrew header labels + micro-tooltips distinguishing the two % columns.
    cfg = {
        "ticker": st.column_config.Column("טיקר"),
        "scan_date": st.column_config.Column("כניסה"),
        "dn": st.column_config.Column("D+n", help="ימי-מסחר מאז יום-הצניחה (D0)"),
        "reference": st.column_config.Column(
            "מחיר-ייחוס", help="נקודת-ההתחלה: intraday=open ביום-הצניחה · gradual=ref_close"),
        "price": st.column_config.Column("מחיר נוכחי"),
        "pct_from_open": st.column_config.Column(
            "% שינוי יומי", help="תנועת המחיר היום מהפתיחה (תוך-יומי)"),
        "pct_from_ref": st.column_config.Column(
            "% מהייחוס", help="מאז נקודת-הצניחה: (מחיר נוכחי − מחיר-ייחוס) / מחיר-ייחוס"),
        "volume": st.column_config.Column("נפח"),
        "timestamp": st.column_config.Column("עודכן (ET)"),
    }
    st.dataframe(sty, column_config=cfg, hide_index=True, width="stretch")


def render_system_health(sheet_id=None):
    """Full System Health page: latest status + trend + filterable run history.
    Resolves the sheet id internally (same mechanism as render()) when not supplied.
    Operational control only — what the monitor checked and when. NOT data-quality
    analysis of the collected data, and NOT edge."""
    if sheet_id is None:
        sheet_id = resolve_sheet_id()
    page_header("🩺 System Health — היסטוריית בקרה",
                "בקרה תפעולית בלבד — האם המערכת רצה / עובדת / מתועדת. "
                "לא ניתוח-איכות של הנתונים עצמם, ולא edge (זה M4).")
    if not sheet_id:
        st.error("REBOUND_SHEET_ID לא מוגדר.")
        return
    sidebar_controls(sheet_id)
    try:
        df = load_health(sheet_id)
    except gspread.exceptions.APIError as e:
        st.info(QUOTA_MSG if _is_quota(e) else f"שגיאת קריאה מה-Sheet: {e}")
        return
    if df.empty or "run_at" not in df.columns:
        st.info("טרם נרשמו ריצות-בקרה (health_log ריק). הרץ `health_monitor.py`.")
        return

    df = df.sort_values("run_at")
    last = df.iloc[-1]
    status = str(last.get("overall_status", "")).strip()
    age, stale = _health_age(last.get("run_at", ""))
    c = st.columns(4)
    kpi(c[0], "סטטוס אחרון", f"{_HEALTH_ICON.get(status, '❔')} {status}")
    kpi(c[1], "exit_code", last.get("exit_code", "—"))
    kpi(c[2], "בדיקה אחרונה", age)
    kpi(c[3], "סה\"כ ריצות", len(df))
    if stale:
        st.warning("⚠️ הבקרה לא רצה ביותר מ-24 שעות — בקרה-שלא-רצה היא עצמה בעיה.")

    # trend
    st.markdown("**מגמת overall_status לאורך זמן** (0=בריא · 1=אזהרה · 2=תקלה)")
    dft = df.copy()
    dft["run_at_dt"] = pd.to_datetime(dft["run_at"].astype(str).str[:19], errors="coerce")
    dft["sev"] = dft["overall_status"].map(_SEV_NUM)
    plot(st, px.line(dft, x="run_at_dt", y="sev", color="mode", markers=True))

    # filterable history (newest first)
    st.markdown("**היסטוריית-ריצות**")
    f = st.columns(2)
    modes = sorted(df["mode"].dropna().unique()) if "mode" in df else []
    sel_mode = f[0].multiselect("mode", modes, default=modes)
    stats = sorted(df["overall_status"].dropna().unique()) if "overall_status" in df else []
    sel_stat = f[1].multiselect("overall_status", stats, default=stats)
    view = df
    if sel_mode:
        view = view[view["mode"].isin(sel_mode)]
    if sel_stat:
        view = view[view["overall_status"].isin(sel_stat)]
    # details_text powers the per-run expanders below, not the wide table
    cols = [c for c in config.HEALTH_LOG_HEADER if c in view.columns and c != "details_text"]
    view = view.sort_values("run_at", ascending=False)
    st.caption(f"{len(view)} ריצות · severity לכל בדיקה: ok/warn/fail")
    show_table(view[cols], height=360)

    # full per-check explanation for each run (click to open) — newest first
    st.markdown("**פירוט מלא לכל ריצה** (לחץ לפתיחה — מה הסוכן בדק ומצא בכל בדיקה)")
    for _, r in view.head(25).iterrows():
        icon = _HEALTH_ICON.get(str(r.get("overall_status", "")).strip(), "❔")
        head = f"{icon} {r.get('run_at', '')} · {r.get('mode', '')} · {r.get('summary_text', '')}"
        with st.expander(head):
            details = str(r.get("details_text", "") or "")
            if details.strip():
                st.text(details)
            else:   # legacy rows (pre details_text) — reconstruct from severity columns
                for cid in config.HEALTH_CHECK_IDS:
                    if cid in r:
                        st.write(f"{r.get(cid, '')} — {cid}")
    if len(view) > 25:
        st.caption(f"(מוצגים 25 הראשונים מתוך {len(view)})")
