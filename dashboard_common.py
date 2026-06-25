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
import numpy as np
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
             "atr_14", "drop_in_atr",
             # descriptive SMA / vol-normalized features
             "atr_pct", "dist_sma50", "dist_sma200"]
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
# Group-C fundamentals — the locked pre-reg _num fields (+ P/E for derived E/P) read
# from fundamentals_snapshot (sha256 032f10eb...). Display/data only — no scoring (M5).
NUM_FUND = ["ROA_num", "Debt/Eq_num", "Current Ratio_num", "Short Float_num",
            "Gross Margin_num", "P/B_num", "P/E_num"]

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
    "atr_pct", "dist_sma50", "dist_sma200",
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


def _num1(v):
    """Single value → float or nan (sheet cells arrive as strings/blanks)."""
    return pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]


def current_pct_from_entry(watch, fdaily):
    """Per event, the CURRENT % from entry + its single source (one-source-per-datum):
      • 'forward_daily' — cum_pct_from_ref of the LAST available forward day
        (the window, still maturing).
      • 'live' — (price - reference)/reference*100 for an active event with no
        forward rows yet; reference = open (intraday_drop) / ref_close_window
        (gradual_drop).
    DESCRIPTIVE current status (the window is still maturing → the sign can flip),
    NOT an outcome. Returns df[scan_date, ticker, pct_from_entry, pct_source]."""
    cols = ["scan_date", "ticker", "pct_from_entry", "pct_source"]
    if watch is None or watch.empty:
        return pd.DataFrame(columns=cols)
    base = watch.drop_duplicates(["scan_date", "ticker"]).copy()
    last_fwd = {}
    if fdaily is not None and not fdaily.empty and \
            {"scan_date", "ticker", "day_offset", "cum_pct_from_ref"} <= set(fdaily.columns):
        f = fdaily.assign(_o=pd.to_numeric(fdaily["day_offset"], errors="coerce")).sort_values("_o")
        for (sd, tk), g in f.groupby(["scan_date", "ticker"]):
            vals = pd.to_numeric(g["cum_pct_from_ref"], errors="coerce").dropna()
            if len(vals):
                last_fwd[(str(sd), str(tk))] = float(vals.iloc[-1])
    out = []
    for _, r in base.iterrows():
        sd, tk = str(r["scan_date"]), str(r["ticker"])
        if (sd, tk) in last_fwd:
            out.append({"scan_date": sd, "ticker": tk,
                        "pct_from_entry": last_fwd[(sd, tk)], "pct_source": "forward_daily"})
            continue
        kind = r.get("drop_kind") or "intraday_drop"
        ref = _num1(r.get("ref_close_window") if kind == "gradual_drop" else r.get("open"))
        price = _num1(r.get("price"))
        pct = round((price - ref) / ref * 100, 2) if (ref == ref and ref > 0 and price == price) else float("nan")
        out.append({"scan_date": sd, "ticker": tk, "pct_from_entry": pct, "pct_source": "live"})
    return pd.DataFrame(out, columns=cols)


def metric_distributions(df, numeric_cols):
    """Pooled descriptive distribution per numeric metric — median, IQR (Q1–Q3),
    min–max, %filled — over ALL strata events (NOT split up/down; no ranking).
    DESCRIPTIVE only (M5-safe). Returns one row per metric."""
    cols = ["metric", "n_filled", "pct_filled", "median", "q1", "q3", "iqr", "vmin", "vmax"]
    n = 0 if df is None else len(df)
    rows = []
    for c in numeric_cols:
        s = (pd.to_numeric(df[c], errors="coerce").dropna()
             if (df is not None and c in df.columns) else pd.Series(dtype=float))
        nf = int(s.size)
        if nf == 0:
            rows.append({"metric": c, "n_filled": 0, "pct_filled": 0.0, "median": float("nan"),
                         "q1": float("nan"), "q3": float("nan"), "iqr": float("nan"),
                         "vmin": float("nan"), "vmax": float("nan")})
            continue
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        rows.append({"metric": c, "n_filled": nf,
                     "pct_filled": round(100.0 * nf / n, 1) if n else 0.0,
                     "median": round(float(s.median()), 3), "q1": round(q1, 3), "q3": round(q3, 3),
                     "iqr": round(q3 - q1, 3), "vmin": round(float(s.min()), 3),
                     "vmax": round(float(s.max()), 3)})
    return pd.DataFrame(rows, columns=cols)


def collection_progress(watch):
    """Collection status: cumulative unique-event count over scan_date + total +
    counts by source. Returns (cum_df[scan_date,n,cum_n], total, by_source dict)."""
    if watch is None or watch.empty:
        return pd.DataFrame(columns=["scan_date", "n", "cum_n"]), 0, {}
    ev = watch.drop_duplicates(["scan_date", "ticker"]).copy()
    total = len(ev)
    by_source = (ev["source"].fillna("?").replace("", "?").value_counts().to_dict()
                 if "source" in ev.columns else {})
    g = ev.groupby("scan_date").size().reset_index(name="n").sort_values("scan_date")
    g["cum_n"] = g["n"].cumsum()
    return g.reset_index(drop=True), total, by_source


def count_completed(fdaily, horizon=None):
    """Number of events whose forward window has MATURED — max day_offset >= horizon
    (config.POST_ANALYSIS_HORIZON). The M3 ~200 target counts COMPLETED events, not
    merely collected ones, so the page never implies a maturity that isn't there."""
    h = config.POST_ANALYSIS_HORIZON if horizon is None else horizon
    if fdaily is None or fdaily.empty or \
            not {"scan_date", "ticker", "day_offset"} <= set(fdaily.columns):
        return 0
    mx = (fdaily.assign(_o=pd.to_numeric(fdaily["day_offset"], errors="coerce"))
          .groupby(["scan_date", "ticker"])["_o"].max())
    return int((mx >= h).sum())


# ── ported pure separation stats (M5-safe DESCRIPTIVE in-sample separation) ────
# Cliff's delta + permutation null band, pure numpy (scipy is not a dep). Ports the
# TDD'd research/entry_profile/descriptive_stats.py. Feeds the Entry-Profile
# separation tables. NOTHING here is a score / entry-rule / recommendation — it
# measures observed separation between the (still-maturing) up/down groups only.
SEP_SEED = 42
_BAND_NEGLIGIBLE, _BAND_SMALL, _BAND_MEDIUM = 0.147, 0.33, 0.474


def _clean_arr(a):
    a = np.asarray(a, dtype=float)
    return a[~np.isnan(a)]


def split_groups(outcome):
    """up = outcome > 0 ; down = outcome <= 0 (0 → down); NaN → neither."""
    arr = np.asarray(outcome, dtype=float)
    nan = np.isnan(arr)
    return (arr > 0) & ~nan, (arr <= 0) & ~nan


def magnitude_label(delta):
    """|delta| → negligible/small/medium/large; nan → '—'."""
    if delta is None or (isinstance(delta, float) and np.isnan(delta)):
        return "—"
    a = abs(float(delta))
    if a < _BAND_NEGLIGIBLE:
        return "negligible"
    if a < _BAND_SMALL:
        return "small"
    if a < _BAND_MEDIUM:
        return "medium"
    return "large"


def cliffs_delta(x, y):
    """δ = [#(x>y) − #(x<y)] / (n_x·n_y) via two searchsorted calls. NaN dropped;
    ties excluded from the numerator; empty group → nan. Returns dict."""
    x, y = _clean_arr(x), _clean_arr(y)
    n_x, n_y = int(x.size), int(y.size)
    if n_x == 0 or n_y == 0:
        return {"delta": float("nan"), "n_x": n_x, "n_y": n_y, "magnitude": "—"}
    ys = np.sort(y)
    num_gt = int(np.searchsorted(ys, x, side="left").sum())
    num_le = int(np.searchsorted(ys, x, side="right").sum())
    num_lt = n_x * n_y - num_le
    delta = float(max(-1.0, min(1.0, (num_gt - num_lt) / (n_x * n_y))))
    return {"delta": delta, "n_x": n_x, "n_y": n_y, "magnitude": magnitude_label(delta)}


def side_fractions(x, y, threshold):
    """(pct_up_above, pct_down_above) — % of each group with value > threshold."""
    x, y = _clean_arr(x), _clean_arr(y)
    up_a = float((x > threshold).mean() * 100) if x.size else float("nan")
    down_a = float((y > threshold).mean() * 100) if y.size else float("nan")
    return up_a, down_a


def midpoint_threshold(x, y):
    """threshold = mean(median(x), median(y)) + the side fractions at it."""
    x, y = _clean_arr(x), _clean_arr(y)
    if x.size == 0 or y.size == 0:
        return {"threshold": float("nan"), "pct_up_above": float("nan"),
                "pct_down_above": float("nan")}
    thr = float((np.median(x) + np.median(y)) / 2.0)
    up_a, down_a = side_fractions(x, y, thr)
    return {"threshold": thr, "pct_up_above": up_a, "pct_down_above": down_a}


def permute_labels(up_mask, k, rng):
    """(k, n) boolean matrix; each row a permutation of up_mask (sizes preserved)."""
    up_mask = np.asarray(up_mask, dtype=bool)
    out = np.empty((k, up_mask.size), dtype=bool)
    for i in range(k):
        out[i] = rng.permutation(up_mask)
    return out


def _abs_delta(values, lbl):
    d = cliffs_delta(values[lbl], values[~lbl])["delta"]
    return 0.0 if np.isnan(d) else abs(d)


def permutation_band(values, up_mask, k=1000, seed=SEP_SEED):
    """Null distribution of |Cliff's delta| under K label shuffles (group sizes
    fixed). Returns dict{null, observed_abs_delta, p_value, exceeds_95, exceeds_99}."""
    values = np.asarray(values, dtype=float)
    up_mask = np.asarray(up_mask, dtype=bool)
    obs = cliffs_delta(values[up_mask], values[~up_mask])["delta"]
    obs_abs = float("nan") if np.isnan(obs) else abs(obs)
    rng = np.random.default_rng(seed)
    mats = permute_labels(up_mask, k, rng)
    null = np.array([_abs_delta(values, mats[i]) for i in range(k)])
    if np.isnan(obs_abs):
        return {"null": null, "observed_abs_delta": obs_abs, "p_value": float("nan"),
                "exceeds_95": False, "exceeds_99": False}
    p = (1 + int(np.sum(null >= obs_abs))) / (k + 1)
    return {"null": null, "observed_abs_delta": obs_abs, "p_value": float(p),
            "exceeds_95": bool(obs_abs > np.percentile(null, 95)),
            "exceeds_99": bool(obs_abs > np.percentile(null, 99))}


def family_wise_max_null(value_cols, up_mask, k=1000, seed=SEP_SEED):
    """ONE shared shuffle per iteration across ALL metrics → (k,) array of
    max_metric |delta| (multiplicity-corrected null). Pass only non-empty metrics."""
    up_mask = np.asarray(up_mask, dtype=bool)
    cols = [np.asarray(v, dtype=float) for v in value_cols]
    rng = np.random.default_rng(seed)
    mats = permute_labels(up_mask, k, rng)
    maxnull = np.zeros(k)
    for i in range(k):
        lbl = mats[i]
        maxnull[i] = max((_abs_delta(v, lbl) for v in cols), default=0.0)
    return maxnull


def build_separation_table(events, metrics, pct_col="pct_from_entry", k=1000, seed=SEP_SEED):
    """DESCRIPTIVE per-metric separation between the up (pct_col > 0) and down (<= 0)
    groups of the CURRENT change-from-entry. Per metric: n_up/n_down, median_up,
    median_down, Cliff's delta, magnitude, direction (🟢 delta>0 / 🔴 <0 / ▬ ≈0|nan),
    side-fractions at the midpoint threshold, and `crosses` = |delta| exceeds the
    95th pct of the FAMILY-WISE (multiplicity-corrected) permutation null over the
    non-empty metrics. NOT a score/entry-rule — observed in-sample separation only,
    on a still-maturing outcome (the sign can flip). One row per metric."""
    cols = ["metric", "n_up", "n_down", "median_up", "median_down", "delta",
            "magnitude", "direction", "pct_upside_up", "pct_upside_down", "crosses"]
    if events is None or events.empty or pct_col not in events.columns:
        return pd.DataFrame(columns=cols)
    pct = pd.to_numeric(events[pct_col], errors="coerce").to_numpy()
    up_all, down_all = split_groups(pct)
    labeled = up_all | down_all
    sub = events[labeled]
    upm = up_all[labeled]
    arrs = {m: (pd.to_numeric(sub[m], errors="coerce").to_numpy()
                if m in sub.columns else np.full(len(sub), np.nan)) for m in metrics}
    valid = len(sub) > 0 and upm.sum() > 0 and (~upm).sum() > 0
    nonempty = [m for m in metrics if np.isfinite(arrs[m]).any()]
    fw95 = float("nan")
    if valid and nonempty:
        maxnull = family_wise_max_null([arrs[m] for m in nonempty], upm, k=k, seed=seed)
        fw95 = float(np.percentile(maxnull, 95))

    rows = []
    for m in metrics:
        a = arrs[m]
        x, y = a[upm], a[~upm]
        cd = cliffs_delta(x, y)
        delta = cd["delta"]
        mid = midpoint_threshold(x, y)
        uu, dd = ((float("nan"), float("nan")) if np.isnan(mid["threshold"])
                  else side_fractions(x, y, mid["threshold"]))
        xc, yc = _clean_arr(x), _clean_arr(y)
        direction = "▬" if (np.isnan(delta) or delta == 0) else ("🟢" if delta > 0 else "🔴")
        obs_abs = float("nan") if np.isnan(delta) else abs(delta)
        crosses = bool(valid and not np.isnan(obs_abs) and not np.isnan(fw95) and obs_abs > fw95)
        rows.append({
            "metric": m, "n_up": cd["n_x"], "n_down": cd["n_y"],
            "median_up": round(float(np.median(xc)), 3) if xc.size else float("nan"),
            "median_down": round(float(np.median(yc)), 3) if yc.size else float("nan"),
            "delta": round(delta, 3) if not np.isnan(delta) else float("nan"),
            "magnitude": cd["magnitude"], "direction": direction,
            "pct_upside_up": round(uu, 1) if not np.isnan(uu) else float("nan"),
            "pct_upside_down": round(dd, 1) if not np.isnan(dd) else float("nan"),
            "crosses": crosses})
    return pd.DataFrame(rows, columns=cols)


def top_separation(table, n=10):
    """Top-n metrics by |Cliff's delta| (desc; NaN delta sorted last)."""
    if table is None or table.empty:
        return table
    t = table.assign(_abs=table["delta"].abs())
    return (t.sort_values("_abs", ascending=False, na_position="last")
            .drop(columns="_abs").head(n).reset_index(drop=True))


# ── fixed-horizon split engine (removes the age confound; B-ready via day_offset) ─
# All three feed the EXISTING build_separation_table via its pct_col argument — no
# new stats math. Splitting at a FIXED forward day (same age for every event) instead
# of the current change-from-entry is what removes the immortal-time confound.
def fixed_horizon_outcome(fdaily, day_offset):
    """cum_pct_from_ref at EXACTLY day_offset==k per event (point-in-time). Events
    that did not reach D+k are ABSENT (never imputed / last-available). Series indexed
    by (scan_date, ticker)."""
    need = {"scan_date", "ticker", "day_offset", "cum_pct_from_ref"}
    if fdaily is None or fdaily.empty or not need <= set(fdaily.columns):
        return pd.Series(dtype=float)
    f = fdaily.assign(_o=pd.to_numeric(fdaily["day_offset"], errors="coerce"))
    sel = f[f["_o"] == day_offset].drop_duplicates(["scan_date", "ticker"])
    s = pd.to_numeric(sel["cum_pct_from_ref"], errors="coerce")
    s.index = pd.MultiIndex.from_arrays(
        [sel["scan_date"].astype(str), sel["ticker"].astype(str)], names=["scan_date", "ticker"])
    return s.dropna()


def spy_excess_outcome(fdaily, day_offset, spy_closes):
    """Fixed-horizon raw cum MINUS SPY's return over scan_date → the D+k date (nets out
    market beta). `spy_closes`: {YYYY-MM-DD: close}. NaN where SPY is unavailable for
    either date. Series indexed by (scan_date, ticker) over events that reached D+k."""
    need = {"scan_date", "ticker", "day_offset", "cum_pct_from_ref", "date"}
    if fdaily is None or fdaily.empty or not need <= set(fdaily.columns):
        return pd.Series(dtype=float)
    f = fdaily.assign(_o=pd.to_numeric(fdaily["day_offset"], errors="coerce"))
    sel = f[f["_o"] == day_offset].drop_duplicates(["scan_date", "ticker"]).copy()
    sd = sel["scan_date"].astype(str)
    dk = sel["date"].astype(str).str.slice(0, 10)
    spy_cum = (pd.to_numeric(dk.map(spy_closes), errors="coerce")
               / pd.to_numeric(sd.map(spy_closes), errors="coerce") - 1.0) * 100.0
    excess = pd.to_numeric(sel["cum_pct_from_ref"], errors="coerce").to_numpy() - spy_cum.to_numpy()
    return pd.Series(excess, index=pd.MultiIndex.from_arrays(
        [sd, sel["ticker"].astype(str)], names=["scan_date", "ticker"]))


def horizon_split_counts(outcome):
    """Honest per-horizon counts: {n_reached (non-NaN), n_up (>0), n_down (<=0)}."""
    s = pd.Series(outcome, dtype=float)
    up, down = split_groups(s.to_numpy())
    return {"n_reached": int(s.notna().sum()), "n_up": int(up.sum()), "n_down": int(down.sum())}


def horizon_strip(events, fdaily, metrics, horizons, k=1000, min_n=None):
    """Multi-horizon delta strip (B). Per (metric, horizon): Cliff's delta +
    direction + crosses (family-wise WITHIN that horizon) + ok (the horizon is
    well-powered — n>=min_n each side — AND the metric is non-empty there). Reuses
    fixed_horizon_outcome + build_separation_table — NO new stats math. No
    cross-horizon multiplicity correction (horizons are autocorrelated → consistency
    is read descriptively, not inferentially). Returns (long_df[metric,horizon,delta,
    direction,crosses,ok], meta[h]->{n_reached,n_up,n_down,enough})."""
    mn = ENTRY_PROFILE_MIN_N if min_n is None else min_n
    rows, meta = [], {}
    for h in horizons:
        out = fixed_horizon_outcome(fdaily, h)
        cnt = horizon_split_counts(out)
        enough = cnt["n_reached"] > 0 and cnt["n_up"] >= mn and cnt["n_down"] >= mn
        meta[h] = {**cnt, "enough": enough}
        ev_h = events.merge(out.rename("pct_k").reset_index(), on=["scan_date", "ticker"], how="left")
        by = build_separation_table(ev_h, metrics, pct_col="pct_k", k=k).set_index("metric")
        for m in metrics:
            delta = float(by.loc[m, "delta"]) if m in by.index else float("nan")
            direction = by.loc[m, "direction"] if m in by.index else "▬"
            crosses = bool(by.loc[m, "crosses"]) if m in by.index else False
            ok = bool(enough and np.isfinite(delta))
            rows.append({"metric": m, "horizon": h, "delta": delta,
                         "direction": direction if ok else "▬",
                         "crosses": bool(crosses and ok), "ok": ok})
    return pd.DataFrame(rows), meta


@st.cache_data(ttl=3600, show_spinner=False)
def _spy_closes_cached(date_min, date_max):
    """READ-ONLY SPY daily closes {YYYY-MM-DD: close} for the SPY-excess split. Cached
    1h; returns {} on any failure (the page then falls back to the raw split)."""
    try:
        import yfinance as yf
        hi = (pd.Timestamp(date_max) + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
        h = yf.Ticker("SPY").history(start=date_min, end=hi, auto_adjust=False)
        return {ts.strftime("%Y-%m-%d"): float(c) for ts, c in h["Close"].items()}
    except Exception:
        return {}


def _spy_closes_for(fdaily, events):
    ds = pd.concat([events.get("scan_date", pd.Series(dtype=str)).astype(str),
                    fdaily.get("date", pd.Series(dtype=str)).astype(str).str.slice(0, 10)])
    ds = sorted({d for d in ds if d and d != "nan"})
    return _spy_closes_cached(ds[0], ds[-1]) if ds else {}


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


_LIVE_TITLES = {"intraday_drop": "📡 מצב חי — ⚡ Intraday",
                "gradual_drop": "📡 מצב חי — 🐢 Gradual"}
_KIND_LABELS = {"intraday_drop": "⚡ intraday", "gradual_drop": "🐢 gradual"}


def _live_build(sheet_id, kind=None):
    """Shared compute for the live-status pages: latest intraday point per event
    (+ D+n via the GLOBAL trading calendar, reference price, % from reference, and
    an in-row price sparkline), optionally filtered to ONE drop_kind. Returns
    (latest, ts, watch, tbl, today); latest/ts are None on no-data / quota. Pure
    read — the underlying loads are st.cache_data(ttl=300), so calling this from
    both the fragment and the table section costs one Sheet read, not two."""
    try:
        ts = load(sheet_id, config.TAB_TIMESERIES, ["price", "pct_from_open", "volume"])
        data = load_many(sheet_id, {config.TAB_WATCHLIST: NUM_WATCH,
                                    config.TAB_POST: NUM_POST,
                                    config.TAB_FORWARD_DAILY: NUM_FDAILY})
    except gspread.exceptions.APIError as e:
        st.info(QUOTA_MSG if _is_quota(e) else f"מצב-חי לא נקרא מה-Sheet: {e}")
        return None, None, None, None, None, None
    if ts.empty or "timestamp" not in ts.columns:
        st.info("intraday_timeseries עדיין ריק — יתמלא בריצת הסורק התוך-יומי הבאה (שעות-מסחר).")
        return None, None, None, None, None, None
    ts = ts[ts["timestamp"].astype(str).str.len() >= 16].copy()
    if ts.empty:
        st.info("אין עדיין נקודות תוך-יומיות תקינות.")
        return None, None, None, None, None, None
    ts["_date"] = ts["timestamp"].astype(str).str[:10]
    watch = coalesce_kind(data[config.TAB_WATCHLIST])
    fdaily = data[config.TAB_FORWARD_DAILY]

    # D+n from the GLOBAL trading calendar = union of all dates seen in
    # intraday_timeseries + forward_daily, so every event sharing a scan_date gets
    # the SAME D+n; the union naturally skips non-trading days (weekends, Juneteenth).
    fd_dates = (set(fdaily["date"].astype(str).str[:10]) if "date" in fdaily.columns
                else set())
    cal = sorted((set(ts["_date"]) | fd_dates) - {""})
    gmax = cal[-1] if cal else ""
    dn_by_sd = {sd: sum(1 for c in cal if sd < c <= gmax)
                for sd in ts["scan_date"].dropna().unique()}

    latest = (ts.sort_values("timestamp")
                .groupby(["scan_date", "ticker"], as_index=False).tail(1).copy())
    latest["dn"] = latest["scan_date"].map(dn_by_sd).astype("Int64")
    # in-row sparkline = the DAILY path (one cum%-from-ref point per trading day from
    # forward_daily) — same story as the click-to-detail chart, NOT the intraday minutes.
    # Empty list for D0 events with no forward data yet (a blank sparkline is fine).
    if not fdaily.empty and {"day_offset", "cum_pct_from_ref"} <= set(fdaily.columns):
        fds = fdaily.assign(_o=pd.to_numeric(fdaily["day_offset"], errors="coerce"),
                            _c=pd.to_numeric(fdaily["cum_pct_from_ref"], errors="coerce"))
        spark = (fds.dropna(subset=["_o"]).sort_values("_o")
                    .groupby(["scan_date", "ticker"])["_c"].apply(list).rename("spark"))
        latest = latest.merge(spark, on=["scan_date", "ticker"], how="left")
    else:
        latest["spark"] = pd.NA
    latest["spark"] = latest["spark"].apply(lambda v: v if isinstance(v, list) else [])

    wkeep = [c for c in ("scan_date", "ticker", "open", "ref_close_window", "drop_kind")
             if c in watch.columns]
    wsub = (watch[wkeep].drop_duplicates(["scan_date", "ticker"]) if not watch.empty
            else pd.DataFrame(columns=wkeep))
    latest = latest.merge(wsub, on=["scan_date", "ticker"], how="left")
    if "drop_kind" not in latest.columns:
        latest["drop_kind"] = "intraday_drop"
    latest["drop_kind"] = latest["drop_kind"].replace("", "intraday_drop").fillna("intraday_drop")
    is_grad = latest["drop_kind"] == "gradual_drop"
    ref = latest["open"].where(~is_grad, latest.get("ref_close_window"))
    latest["reference"] = pd.to_numeric(ref, errors="coerce")
    latest["pct_from_ref"] = ((latest["price"] - latest["reference"])
                              / latest["reference"].where(latest["reference"] > 0)
                              * 100).round(2)

    tbl = build_overview_table(watch, data[config.TAB_POST], fdaily)
    if kind:                                   # per-page: ONE drop_kind only, no averaging across kinds
        latest = latest[latest["drop_kind"] == kind].copy()
        tbl = tbl[tbl["drop_kind"] == kind].copy()
    today = pd.Timestamp.now(tz="America/Lima").strftime("%Y-%m-%d")
    return latest, ts, watch, tbl, fdaily, today


@st.fragment(run_every="300s")
def _live_overview(sheet_id, kind):
    """Breathing overview — freshness + intraday KPIs + daily-classification KPIs +
    two small pies. Auto-refreshes every 300s. Kept SEPARATE from the selectable
    table so a row selection is never reset by the timer. VIEW-ONLY (M5)."""
    latest, ts, watch, tbl, _fdaily, today = _live_build(sheet_id, kind)
    if latest is None:
        return
    if latest.empty:
        st.info("אין עדיין אירועים מסוג זה במעקב.")
        return
    pf = pd.to_numeric(latest["pct_from_open"], errors="coerce")
    is_today = latest["_date"] == today
    newest = latest["timestamp"].astype(str).max()
    if newest[:10] < today:
        st.caption(f"🕒 השוק סגור — מוצג המצב האחרון מ-{newest} (ET). יתעדכן עם פתיחת-המסחר.")
    else:
        st.caption(f"🟢 חי · עדכון אחרון {newest} (ET) · {len(latest)} מניות במעקב")

    # layer 1 — intraday KPIs: today's count + cumulative-total beside it (delta)
    st.markdown("##### 📈 תוך-יומי · נושם בשעות-מסחר")
    mover = latest.loc[pf.abs().idxmax()] if pf.notna().any() else None
    ic = st.columns(4)
    ic[0].metric("עולות היום 🟢", int((is_today & (pf > 0)).sum()),
                 delta=f"{int((pf > 0).sum())} מצטבר", delta_color="off", border=True)
    ic[1].metric("יורדות היום 🔴", int((is_today & (pf < 0)).sum()),
                 delta=f"{int((pf < 0).sum())} מצטבר", delta_color="off", border=True)
    ic[2].metric("תנועה יומית ממוצעת",
                 f"{pf[is_today].mean():+.2f}%" if is_today.any() else "—", border=True)
    ic[3].metric("המזיזה ביותר",
                 f"{mover['ticker']} {float(mover['pct_from_open']):+.1f}%"
                 if mover is not None else "—", border=True)

    # layer 2 — daily classification (reuse build_overview_table buckets)
    st.markdown("##### 🗓️ סיווג יומי · מתעדכן 22:30 (סיווג ריבאונד — לא נתון תוך-יומי)")
    avg_day = tbl["pct_from_entry"].dropna().mean() if not tbl.empty else float("nan")
    # all 5 status buckets shown → 🟢 + 🔴🟠 + ⚪ + ⏳ sums to "סה\"כ במעקב" exactly
    dc = st.columns(6)
    dc[0].metric("סה\"כ במעקב", len(tbl), border=True,
                 help="סך אירועי-המעקב מסוג זה (כל שורות ה-watchlist של ההשערה).")
    dc[1].metric("🟢 מתאוששות", int((tbl["status"] == "recovering").sum()), border=True,
                 help="מתאוששת: +3% ומעלה מהכניסה.")
    dc[2].metric("🔴🟠 עדיין-למטה",
                 int(tbl["status"].isin(["down", "falling"]).sum()), border=True,
                 help="עדיין-למטה: בין −3% ל−10% מהכניסה (כולל 'נופלת' — מתחת −10%).")
    dc[3].metric("⚪ יציבה", int((tbl["status"] == "stable").sum()), border=True,
                 help="יציבה: בין −3% ל-+3% מהכניסה.")
    dc[4].metric("⏳ ממתין", int((tbl["status"] == "pending").sum()), border=True,
                 help="ממתין: עוד אין מספיק נתוני-קדימה לסיווג (יתמלא בריצת 22:30).")
    dc[5].metric("תנועה ממוצעת (יומי)",
                 f"{avg_day:+.1f}%" if pd.notna(avg_day) else "—", border=True,
                 help="ממוצע % מהכניסה על-פני כל אירועי המעקב מסוג זה.")

    # smaller pies — direction + D-bucket (kind is fixed per page → no "by kind" pie)
    pie = latest.assign(
        כיוון=pf.map(lambda v: "עולה 🟢" if pd.notna(v) and v >= 0 else "יורד 🔴"),
        Dbucket=latest["dn"].map(lambda d: "D0" if pd.notna(d) and d == 0
                                 else ("D1-3" if pd.notna(d) and d <= 3 else "D4+")),
    )
    pc = st.columns(2)
    for col, names, title in ((pc[0], "כיוון", "לפי כיוון-היום"),
                              (pc[1], "Dbucket", "לפי D-bucket")):
        fig = px.pie(pie, names=names, title=title, hole=0.4)
        fig.update_layout(height=240, margin=dict(t=40, b=0, l=0, r=0))
        plot(col, fig)


def _dd_mm(d):
    """'YYYY-MM-DD' -> 'DD.MM' (else the raw string)."""
    d = str(d)
    return f"{d[8:10]}.{d[5:7]}" if len(d) >= 10 else d


def _live_event_detail(ts, watch, fdaily, scan_date, ticker, live_pct=None):
    """Descriptive detail panel for one selected event. TWO clearly-labelled sources:
      • 📅 forward_daily (daily closes): the daily path chart + peak/trough/trend/
        range/days-up-down — the window's outcome.
      • 🟢 live (intraday): `live_pct` (= the table's % מהכניסה, computed ONCE in
        _live_build and passed in — NOT recomputed here) — where the price is NOW,
        positioned against the historical forward_daily extremes.
    VIEW-ONLY (M5), no signal/recommendation. `live_pct` is the live cum% from entry."""
    st.markdown(f"#### 🔎 {ticker} · כניסה {scan_date}")
    mfe = mae = trend = None              # window outcome (descriptive); filled when mature
    days_up = days_down = None
    fd = fdaily[(fdaily["scan_date"] == scan_date) & (fdaily["ticker"] == ticker)].copy() \
        if fdaily is not None and not fdaily.empty else fdaily
    if fd is None or fd.empty or "day_offset" not in fd.columns:
        st.info("אין עדיין נתוני forward_daily לאירוע זה — חלון-הקדימה טרם הבשיל "
                "(יתמלא בריצת 22:30).")
        n_days = 0
    else:
        fd["_off"] = pd.to_numeric(fd["day_offset"], errors="coerce")
        fd = fd.dropna(subset=["_off"]).sort_values("_off")
        ycol = "cum_pct_from_ref" if "cum_pct_from_ref" in fd.columns else "close"
        fd[ycol] = pd.to_numeric(fd[ycol], errors="coerce")
        # per-day move: prefer forward_daily.daily_change_pct, fall back to the diff of
        # consecutive cum_pct_from_ref (first forward day = change from the reference).
        chg = (pd.to_numeric(fd["daily_change_pct"], errors="coerce")
               if "daily_change_pct" in fd.columns
               else pd.Series(index=fd.index, dtype="float64"))
        fd["_chg"] = chg.fillna(fd[ycol].diff().fillna(fd[ycol]))
        fd["יום"] = [f"D+{int(o)} ({_dd_mm(d)})"
                     for o, d in zip(fd["_off"], fd.get("date", ""))]
        # anchor the path at D+0 = 0% (the reference itself); no daily-move label on it
        anchor = pd.DataFrame({"_off": [0.0], "יום": [f"D+0 ({_dd_mm(scan_date)})"],
                               ycol: [0.0], "_chg": [float("nan")]})
        plot_df = pd.concat([anchor, fd[["_off", "יום", ycol, "_chg"]]], ignore_index=True)
        fig = px.line(plot_df, x="יום", y=ycol, markers=True,
                      title=f"{ticker} — מעקב סגירות יומיות (forward_daily) · cum% מהכניסה · תווית = שינוי יומי")
        fig.update_traces(mode="lines+markers")
        # per-point daily-move label, green up / red down (descriptive colour cue only)
        for _, pt in plot_df.iterrows():
            d = pt["_chg"]
            if pd.notna(d):
                fig.add_annotation(x=pt["יום"], y=pt[ycol], text=f"{d:+.1f}%",
                                   showarrow=False, yshift=14,
                                   font=dict(size=12, color=GREEN if d >= 0 else RED))
        fig.update_xaxes(tickfont=dict(size=16))
        fig.update_layout(height=360, margin=dict(t=50, b=10, l=0, r=0))
        plot(st, fig)
        n_days = int(fd["_off"].max())
        # peak/trough INCLUDE the D+0=0% anchor (the entry is itself a point on the
        # path): a name that only ever fell still has peak ≥ 0% (the entry is the
        # highest point), and one that only ever rose has trough ≤ 0% — never a
        # sign-flipped surprise like a negative "peak".
        path = plot_df[ycol].dropna()
        if not path.empty:
            mfe, mae = float(path.max()), float(path.min())
        # trend of the last 3 daily closes (forward_daily day-over-day moves)
        chgs = fd["_chg"].dropna().tolist()
        if len(chgs) >= 3:
            last3 = chgs[-3:]
            trend = (("▲", "עולה") if all(c > 0 for c in last3)
                     else ("▼", "יורד") if all(c < 0 for c in last3)
                     else ("▬", "מעורבת"))
        # days that ROSE vs FELL on their own day — counted from the per-day move
        # fd["_chg"] (daily_change_pct), NOT cum-from-entry, so the card matches the
        # green/red daily-move labels on the chart exactly. Same threshold as the
        # chart colour (line ~1229: d >= 0 → GREEN else RED): up = _chg >= 0,
        # down = _chg < 0 → ↑ == #green labels, ↓ == #red labels, ↑+↓ == #labels.
        fchg = fd["_chg"].dropna()
        if not fchg.empty:
            days_up, days_down = int((fchg >= 0).sum()), int((fchg < 0).sum())

    def _pct(v):
        return f"{v:+.1f}%" if v is not None and pd.notna(v) else "—"

    # ══ 📅 DAILY-CLOSES group — every datum here is forward_daily (descriptive) ════
    st.markdown("##### 📅 סגירות יומיות · `forward_daily`")
    a = st.columns(2)
    a[0].metric("מגמה (3 ימים)", f"{trend[0]} {trend[1]}" if trend else "—", border=True,
                help="כיוון 3 הסגירות היומיות האחרונות — ▲ עולה / ▼ יורד / ▬ מעורבת. "
                     "תיאורי, לא המלצה. (מקור: forward_daily)")
    a[1].metric("ימי עלייה / ירידה", f"{days_up} ↑ / {days_down} ↓" if days_up is not None else "—",
                border=True, help="כמה ימים עלו וכמה ירדו לפי השינוי היומי — בדיוק התוויות "
                                  "הצבעוניות בגרף (ירוק עלייה / אדום ירידה), לא מול מחיר-הכניסה. "
                                  "(מקור: forward_daily)")
    st.caption("כל הנתונים בקבוצה זו מסגירות יומיות (`forward_daily`) עד היום האחרון שנרשם — "
               "עשויים לפגר אחרי המחיר החי שבטבלה עד ריצת-הסגירה (22:30).")

    # ══ 🟢 LIVE group — high/low SINCE ENTRY (incl. the live price) + where now sits ════
    st.markdown("##### 🟢 מצב חי · `intraday`")
    # peak/trough SINCE ENTRY fold the live price into the historical path extremes
    # (single source: the live_pct passed in) so the cards are always current to the
    # tick; historical-only when live is missing; the entry (0%) is always a point.
    peak, trough = mfe, mae
    if live_pct is not None and pd.notna(live_pct):
        live_pct = float(live_pct)
        peak = max(live_pct, 0.0) if peak is None else max(peak, live_pct)
        trough = min(live_pct, 0.0) if trough is None else min(trough, live_pct)
    _hlp = "מאז הכניסה — כולל המחיר החי, מתעדכן מיד."
    a = st.columns(3)
    a[0].metric("נקודת שיא מאז הכניסה", _pct(peak), border=True,
                help="הגבוה ביותר שהמניה הגיעה אליו " + _hlp)
    a[1].metric("נקודת שפל מאז הכניסה", _pct(trough), border=True,
                help="הנמוך ביותר שהמניה הגיעה אליו " + _hlp)
    if live_pct is not None and pd.notna(live_pct):
        a[2].metric("מיקום נוכחי · חי", _pct(live_pct), border=True,
                    help="מיקום המחיר החי (intraday) מול מחיר-הכניסה. השיא/שפל למעלה כבר "
                         "מקפלים את החי — לכן כשהחי הוא הקצה, הוא יישב על השיא או השפל.")
        if mfe is not None and mae is not None:
            pos = ("מתחת לשפל ההיסטורי" if live_pct < mae
                   else "מעל השיא ההיסטורי" if live_pct > mfe
                   else "בין השיא והשפל ההיסטוריים")
            # when the live price is itself the overall extreme since entry, say so —
            # keeps the sentence coherent with the (now live-inclusive) שיא/שפל cards.
            extreme = (" — זהו גם השפל מאז הכניסה" if live_pct <= trough
                       else " — זהו גם השיא מאז הכניסה" if live_pct >= peak
                       else "")
            sentence = (f"החי {live_pct:+.1f}% — {pos} "
                        f"(שפל {mae:+.1f}% · שיא {mfe:+.1f}%, מ-`forward_daily`){extreme}.")
        else:
            sentence = f"החי {live_pct:+.1f}% — אין עדיין קצוות היסטוריים (החלון טרם הבשיל)."
        st.caption(sentence)
    else:
        st.caption("מיקום חי לא זמין לאירוע זה — שיא/שפל מחושבים מהסגירות היומיות בלבד.")

    # ══ 📌 entry facts (watchlist) ════════════════════════════════════════════════
    st.markdown("##### 📌 עובדות הכניסה")
    w = watch[(watch["scan_date"] == scan_date) & (watch["ticker"] == ticker)]
    if not w.empty:
        r = w.iloc[0]
        kind = (r.get("drop_kind") or "intraday_drop")
        reference = pd.to_numeric(r.get("open") if kind != "gradual_drop"
                                  else r.get("ref_close_window"), errors="coerce")
        vol = pd.to_numeric(r.get("volume"), errors="coerce")
        b = st.columns(3)
        b[0].metric("מחיר-כניסה", f"{reference:.2f}" if pd.notna(reference) else "—")
        b[1].metric("נפח (כניסה)", f"{vol:,.0f}" if pd.notna(vol) else "—")
        b[2].metric("ימי-מסחר בחלון", n_days)
    st.caption("פירוט תיאורי בלבד — אין כאן אות/המלצה.")


def render_live_status(kind=None):
    """Per-kind live-status page (kind ∈ intraday_drop / gradual_drop). The breathing
    overview (KPIs + pies) auto-refreshes every 300s inside _live_overview; the
    selectable table + detail panel live OUTSIDE the fragment, so a row selection
    survives the timer. VIEW-ONLY — no score / signal / ranking / entry (M5)."""
    sheet_id = resolve_sheet_id()
    if not sheet_id:
        st.error("REBOUND_SHEET_ID לא מוגדר (.env / env / st.secrets).")
        return
    page_header(_LIVE_TITLES.get(kind, "📡 מצב חי"),
                VIEW_ONLY + " · תוך-יומי · נושם בשעות-מסחר בלבד · ≠ סיווג הריבאונד היומי")

    _live_overview(sheet_id, kind)             # breathing part (auto-refresh 300s)

    # ── selectable table + detail — OUTSIDE the fragment (selection is stable) ────
    latest, ts, watch, _tbl, fdaily, _today = _live_build(sheet_id, kind)
    if latest is None or latest.empty:
        return
    st.markdown("##### 📋 אירועים — בחר שורה לפירוט יומי על-פני החלון")
    sdays = sorted(latest["scan_date"].dropna().unique())
    sel_day = st.multiselect("כניסה (scan_date)", sdays, default=sdays)
    view = latest[latest["scan_date"].isin(sel_day)]
    if view.empty:
        st.info("אין שורות לבחירה הנוכחית.")
        return
    view = (view.assign(_abs=pd.to_numeric(view["pct_from_open"], errors="coerce").abs())
                .sort_values("_abs", ascending=False).reset_index(drop=True))
    # SINGLE-SOURCE: this table is LIVE-ONLY (intraday_timeseries vs the entry
    # reference). The daily-closes view (forward_daily) lives ONLY in the detail
    # panel — so NO `spark` column here (that was forward_daily leaking into the
    # live table), and NO standalone direction column (folded into the coloured %).
    disp = view[["ticker", "scan_date", "dn", "reference", "price",
                 "pct_from_open", "pct_from_ref", "volume"]].copy()

    # Colour per-cell WITHOUT a Styler (a Styler input silently breaks st.dataframe
    # row-selection — the d28c6cc saga): a green/red emoji PREFIX on each % cell.
    # This is the only no-Styler way to colour a cell and keep on_select working.
    def _sign_pct(s):
        s = pd.to_numeric(s, errors="coerce")
        return s.map(lambda v: f"🟢 {v:+.2f}%" if pd.notna(v) and v >= 0
                     else (f"🔴 {v:+.2f}%" if pd.notna(v) else "—"))
    disp["pct_from_open"] = _sign_pct(disp["pct_from_open"])
    disp["pct_from_ref"] = _sign_pct(disp["pct_from_ref"])

    # PLAIN DataFrame (NOT a Styler) so on_select row-selection works. The two %
    # columns are TextColumns (they now carry the 🟢/🔴 colour prefix).
    cfg = {
        "ticker": st.column_config.TextColumn("טיקר"),
        "scan_date": st.column_config.TextColumn("כניסה"),
        "dn": st.column_config.NumberColumn(
            "D+n", format="%d", help="ימי-מסחר מ-scan_date (לוח גלובלי; מדלג ימי-שבתון/חג)"),
        "reference": st.column_config.NumberColumn(
            "מחיר-כניסה", format="%.2f",
            help="נקודת-הכניסה (הייחוס): intraday=open ביום-הצניחה · gradual=ref_close_window"),
        "price": st.column_config.NumberColumn(
            "מחיר חי", format="%.2f",
            help="המחיר העדכני מ-intraday_timeseries (חי, בשעות-מסחר)"),
        "pct_from_open": st.column_config.TextColumn(
            "שינוי-יום %",
            help="תנועת המחיר היום מהפתיחה (תוך-יומי) — 🟢 עלה היום / 🔴 ירד היום"),
        "pct_from_ref": st.column_config.TextColumn(
            "% מהכניסה",
            help="סך מצטבר חי מאז הכניסה: (מחיר חי − מחיר-כניסה) / מחיר-כניסה — "
                 "🟢 מעל הכניסה / 🔴 מתחת לכניסה"),
        "volume": st.column_config.NumberColumn(
            "נפח", format="%,d", help="נפח חי מ-intraday_timeseries"),
    }
    event = st.dataframe(disp, column_config=cfg, hide_index=True, width="stretch",
                         height=720, key=f"live_tbl_{kind}",
                         on_select="rerun", selection_mode="single-row")
    try:
        rows = list(event.selection.rows)
    except Exception:
        rows = []
    if rows:
        r = disp.iloc[rows[0]]
        # live cum%-from-entry: reuse the value _live_build already computed (in `view`),
        # do NOT recompute here — single source for the live "% מהכניסה".
        live_pct = pd.to_numeric(view.iloc[rows[0]].get("pct_from_ref"), errors="coerce")
        _live_event_detail(ts, watch, fdaily, r["scan_date"], r["ticker"], live_pct=live_pct)
    else:
        st.caption("↑ בחר שורה בטבלה כדי לראות גרף יומי על-פני החלון + נתוני-האירוע.")


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


# ── Entry-Profile pages (DESCRIPTIVE / M5-safe) ──────────────────────────────
# Per-strata DESCRIPTIVE separation tables: up/down split at a FIXED forward horizon
# (D+headline) — same age for every event, which removes the immortal-time confound
# of splitting on the *current* change-from-entry. View-only. DELIBERATELY NOT HERE
# (M5): a unified score, an entry rule, buy/sell, or a recommendation.
ENTRY_PROFILE_TARGET = 200
ENTRY_PROFILE_HEADLINE_DAY = 3      # pre-registered headline horizon (ENTRY_PROFILE_memo)
ENTRY_PROFILE_MIN_N = 5             # min per-side n to colour/bold a horizon's split
ENTRY_PROFILE_HORIZONS = [3, 5, 7, 10, 15, 20]   # the multi-horizon delta strip (B)
_ENTRY_PROFILE_TITLES = {"intraday_drop": "🔬 פרופיל כניסה — ⚡ Intraday",
                         "gradual_drop": "🔬 פרופיל כניסה — 🐢 Gradual"}
# numeric entry metrics profiled (header order; no ordering implies importance)
ENTRY_PROFILE_METRICS = [
    "drop_pct_from_open", "close_pct_from_open", "pct_change_prevclose",
    "drop_pct_window", "volume_ratio", "drop_day_rel_volume", "rsi_14",
    "atr_14", "atr_pct", "drop_in_atr", "dist_sma50", "dist_sma200",
    "pct_from_52w_high", "pct_from_52w_low", "prior_decline_20d_pct",
    "prior_decline_60d_pct", "vix_level", "sector_momentum_5d", "sector_momentum_20d",
    "spy_change_pct", "sector_etf_change_pct", "market_cap", "adv_dollar",
    # Group-C fundamentals (locked pre-reg 032f10eb; each read per-metric — NO composite).
    "ROA_num", "Debt/Eq_num", "Current Ratio_num", "Short Float_num",
    "Gross Margin_num", "P/B_num", "E/P_num",
]

# The 6 locked Finviz _num fields fed directly (+ derived E/P_num). Pre-registered set.
GROUP_C_FIELDS = ["ROA_num", "Debt/Eq_num", "Current Ratio_num", "Short Float_num",
                  "Gross Margin_num", "P/B_num"]


def join_fundamentals(events, fund):
    """LEFT-join the locked Group-C fundamental _num fields (+ derived E/P_num) from
    fundamentals_snapshot onto `events` by (scan_date,ticker). Pre-registered set ONLY
    (sha256 032f10eb...). Safe join: deduped 1:1 (no row duplication), never overwrites
    an existing events column, missing snapshot → NaN (treated like any blank in the
    table). DISPLAY/DATA only — no scoring / no composite (M5)."""
    out = events.copy()
    need = GROUP_C_FIELDS + ["P/E_num"]
    if fund is None or fund.empty or not {"scan_date", "ticker"} <= set(fund.columns):
        f = pd.DataFrame({"scan_date": pd.Series(dtype=str), "ticker": pd.Series(dtype=str)})
        for c in need:
            f[c] = pd.Series(dtype=float)
    else:
        f = (fund.drop_duplicates(["scan_date", "ticker"])
             [["scan_date", "ticker"] + [c for c in need if c in fund.columns]].copy())
        for c in need:
            f[c] = pd.to_numeric(f[c], errors="coerce") if c in f.columns else np.nan
    # derived E/P (earnings yield %); guard negative/zero P/E → NaN (not infinity)
    pe_pos = pd.to_numeric(f["P/E_num"], errors="coerce").where(lambda s: s > 0)
    f["E/P_num"] = 100.0 / pe_pos
    f = f.drop(columns=["P/E_num"])
    add = [c for c in (GROUP_C_FIELDS + ["E/P_num"]) if c not in out.columns]  # never overwrite
    return out.merge(f[["scan_date", "ticker"] + add], on=["scan_date", "ticker"], how="left")


def _signed_pct_str(series):
    s = pd.to_numeric(series, errors="coerce")
    return s.map(lambda v: f"🟢 {v:+.2f}%" if pd.notna(v) and v >= 0
                 else (f"🔴 {v:+.2f}%" if pd.notna(v) else "—"))


# ── unit-aware per-metric display formatting (display-only; M5-safe) ──────────
# One unit per metric so every Entry-Profile table renders values consistently:
# percent (%), dollar (abbreviated B/M/K with $), or plain (no suffix).
METRIC_UNITS = {
    **{m: "pct" for m in (
        "drop_pct_from_open", "close_pct_from_open", "pct_change_prevclose",
        "drop_pct_window", "atr_pct", "dist_sma50", "dist_sma200",
        "pct_from_52w_high", "pct_from_52w_low", "prior_decline_20d_pct",
        "prior_decline_60d_pct", "sector_momentum_5d", "sector_momentum_20d",
        "spy_change_pct", "sector_etf_change_pct",
        # Group-C %-valued fundamentals (Finviz parse strips %, keeps magnitude)
        "ROA_num", "Short Float_num", "Gross Margin_num", "E/P_num")},
    **{m: "dollar" for m in ("market_cap", "adv_dollar")},
    **{m: "plain" for m in (
        "rsi_14", "vix_level", "atr_14", "volume_ratio", "drop_day_rel_volume",
        "drop_in_atr",
        # Group-C ratio fundamentals (plain)
        "Debt/Eq_num", "Current Ratio_num", "P/B_num")},
}


def _fmt_dollar(x):
    a = abs(x)
    if a >= 1e9:
        return f"${x / 1e9:.2f}B"
    if a >= 1e6:
        return f"${x / 1e6:.1f}M"
    if a >= 1e3:
        return f"${x / 1e3:.1f}K"
    return f"${x:.0f}"


def fmt_metric_value(metric, v):
    """One value → display string by the metric's unit (pct / dollar / plain).
    NaN/blank/non-numeric → '—'. Unknown metric → plain."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if x != x:                                  # NaN
        return "—"
    unit = METRIC_UNITS.get(metric, "plain")
    if unit == "pct":
        return f"{x:,.2f}%"
    if unit == "dollar":
        return _fmt_dollar(x)
    return f"{x:,.2f}"


def fmt_metric_table(df, value_cols, metric_col="metric"):
    """Copy of df with `value_cols` rendered as strings per EACH ROW's metric unit
    (rows are metrics; same column can hold %, $, and plain across rows)."""
    out = df.copy()
    for c in value_cols:
        out[c] = [fmt_metric_value(m, v) for m, v in zip(out[metric_col], out[c])]
    return out


def _sep_row_style(row):
    """Row styling for the separation table. Direction = a SOFT/light Finviz-style
    tint (gentle hint only). The strong signal (fuller fill + bold + a leading-edge
    accent border) is reserved for metrics that CROSS the family-wise noise band —
    so crossers pop and the rest stay calm. Expects hidden cols `_dir`, `_cross`."""
    d, cr = row["_dir"], row["_cross"]
    if d not in ("🟢", "🔴"):
        return [""] * len(row)            # ▬ neutral — no colour
    if d == "🟢":
        bg, accent = ("#b7e4c7" if cr else "#e9f7ef"), "#1e8449"
    else:
        bg, accent = ("#f5b7b1" if cr else "#fdecea"), "#c0392b"
    cell = f"background-color:{bg};color:#111;" + ("font-weight:700;" if cr else "")
    styles = [cell] * len(row)
    if cr:                                # accent only on the leading (RTL-right) cell
        styles[0] = cell + f"border-right:4px solid {accent};"
    return styles


def _strip_cell(direction, crosses, ok, delta):
    """One multi-horizon strip cell → (text, css). Shows the arrow AND the numeric
    Cliff's delta (+.2f, −1..+1, NO %) in the same cell. Soft tint by direction;
    bold fill + border only for crossers; thin/unreached (not ok) → '—' only (no
    arrow/number). Slightly smaller font so arrow+number fit cleanly."""
    if not ok:
        return "—", "background-color:#f3f3f3;color:#aaaaaa;text-align:center;font-size:12px;"
    num = f"{delta:+.2f}".replace("-", "−")
    if direction == "🟢":
        bg, accent, gl = ("#b7e4c7" if crosses else "#e9f7ef"), "#1e8449", "▲"
    elif direction == "🔴":
        bg, accent, gl = ("#f5b7b1" if crosses else "#fdecea"), "#c0392b", "▼"
    else:
        return f"· {num}", "background-color:#fafafa;color:#666666;text-align:center;font-size:12px;"
    css = f"background-color:{bg};color:#111;text-align:center;font-size:12px;"
    if crosses:
        css += f"font-weight:700;border:2px solid {accent};"
    return f"{gl} {num}", css


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _horizon_strip_cached(events, fdaily, metrics, horizons, k):
    """Cached wrapper (the K-shuffle permutation per horizon is the cost)."""
    return horizon_strip(events, fdaily, list(metrics), list(horizons), k=k)


def render_entry_profile(kind):
    """DESCRIPTIVE entry-condition SEPARATION profile for ONE strata (kind ∈
    intraday_drop / gradual_drop), never mixing strata. View-only, M5-safe: it
    reports observed in-sample SEPARATION (Cliff's delta + family-wise permutation
    null band) between the up/down groups of the CURRENT change-from-entry — it is
    NOT a unified score, an entry rule, or a buy/sell recommendation, and the window
    is still maturing (the sign can flip). Finviz-style metric tables, no charts:
    (1) all-metrics separation table (colored), (2) top-10 by |delta|, (3) collection
    KPIs, (4) coverage, (5) reference per-event table (expander)."""
    page_header(_ENTRY_PROFILE_TITLES.get(kind, "🔬 פרופיל כניסה"),
                "DESCRIPTIVE · תיאורי בלבד · " + VIEW_ONLY)
    sheet_id = resolve_sheet_id()
    if not sheet_id:
        st.error("REBOUND_SHEET_ID לא מוגדר (.env / env / st.secrets). אין מקור נתונים.")
        st.stop()
    sidebar_controls(sheet_id)
    try:
        data = load_many(sheet_id, {config.TAB_WATCHLIST: NUM_WATCH,
                                    config.TAB_FORWARD_DAILY: NUM_FDAILY,
                                    config.TAB_FUNDAMENTALS: NUM_FUND})
        watch, fdaily = data[config.TAB_WATCHLIST], data[config.TAB_FORWARD_DAILY]
        fund = data[config.TAB_FUNDAMENTALS]
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
    watch = watch[watch["drop_kind"] == kind].copy()        # the page IS the strata filter
    if "drop_kind" in fdaily.columns:
        fdaily = fdaily[fdaily["drop_kind"] == kind].copy()
    if watch.empty:
        st.info("אין אירועים בסטרטה זו עדיין.")
        st.stop()

    events = watch.drop_duplicates(["scan_date", "ticker"]).copy()
    events = join_fundamentals(events, fund)                 # Group-C: locked _num fields → events (point-in-time D0)
    cur = current_pct_from_entry(events, fdaily)
    disp = events.merge(cur, on=["scan_date", "ticker"], how="left")  # current-status (reference table only)

    # ── 1) MAIN — fixed-horizon separation table (removes the age confound) ───
    K = ENTRY_PROFILE_HEADLINE_DAY
    st.subheader(f"🧭 טבלת הפרדה — כל המדדים · אופק קבוע D+{K}")
    mode = st.radio(f"פיצול עולה/יורד לפי (D+{K}):", ["שינוי גולמי", "תשואה-עודפת מול SPY"],
                    horizontal=True, key=f"ep_mode_{kind}")
    if mode.startswith("תשואה"):
        spy = _spy_closes_for(fdaily, events)
        outcome = spy_excess_outcome(fdaily, K, spy)
        if not spy:
            st.caption("⚠️ SPY לא זמין כעת — נפילה חזרה לשינוי גולמי.")
            outcome, mode = fixed_horizon_outcome(fdaily, K), "שינוי גולמי"
    else:
        outcome = fixed_horizon_outcome(fdaily, K)
    cnt = horizon_split_counts(outcome)
    ev_k = events.merge(outcome.rename("pct_k").reset_index(), on=["scan_date", "ticker"], how="left")
    sep = build_separation_table(ev_k, ENTRY_PROFILE_METRICS, pct_col="pct_k")

    st.caption(f"פיצול לפי **{mode}** ב-D+{K} (עולה>0 / יורד≤0) · אותו גיל לכל אירוע — "
               f"הוסר ה-confound של 'שינוי נוכחי'. n: עולים={cnt['n_up']} · יורדים={cnt['n_down']} · "
               f"הגיעו ל-D+{K}: {cnt['n_reached']} מתוך {len(events)}.")
    st.info("**מקרא:** צבע רקע = כיוון ההפרדה (🟢 נוטה לעולים · 🔴 נוטה ליורדים, גוון רך) · "
            "**מודגש + מסגרת = חוצה רצפת-רעש** (permutation family-wise, K=1000) · "
            "כרגע ייתכן שאף מדד לא מודגש = עוד אין מבדיל אמיתי.")

    enough = (cnt["n_reached"] > 0 and cnt["n_up"] >= ENTRY_PROFILE_MIN_N
              and cnt["n_down"] >= ENTRY_PROFILE_MIN_N)
    if not enough:
        if cnt["n_reached"] == 0:
            st.warning(f"אין אירועים שהגיעו ל-D+{K} עדיין — הטבלה תתמלא עם ההבשלה.")
        else:
            st.warning(f"⚠️ מדגם דק ב-D+{K} (עולים={cnt['n_up']}, יורדים={cnt['n_down']}; צריך "
                       f"≥{ENTRY_PROFILE_MIN_N} בכל צד) — צבע/הדגשה מושבתים עד שיבשילו אירועים.")
        plain = fmt_metric_table(sep, ["median_up", "median_down"])[
            ["metric", "median_up", "median_down", "delta"]].rename(
            columns={"metric": "מדד", "median_up": "חציון-עולים",
                     "median_down": "חציון-יורדים", "delta": "Cliff's delta"})
        # thin sample → DIM the delta too (grey italic), so ±1.000 isn't read as a real separator
        plain_sty = (plain.style.format({"Cliff's delta": "{:+.3f}"}, na_rep="—")
                     .set_properties(subset=["Cliff's delta"],
                                     color="#999999", **{"font-style": "italic"})
                     .hide(axis="index"))
        show_table(plain_sty, rename=None)
    else:
        fmain = fmt_metric_table(sep, ["median_up", "median_down"])
        main = fmain.assign(_dir=fmain["direction"], _cross=fmain["crosses"])[
            ["metric", "median_up", "median_down", "delta", "_dir", "_cross"]].rename(
            columns={"metric": "מדד", "median_up": "חציון-עולים",
                     "median_down": "חציון-יורדים", "delta": "Cliff's delta"})
        main_sty = (main.style.apply(_sep_row_style, axis=1)
                    .format({"Cliff's delta": "{:+.3f}"}, na_rep="—")  # medians already unit-formatted
                    .hide(["_dir", "_cross"], axis="columns").hide(axis="index"))
        show_table(main_sty, rename=None)

    # ── 2) Top-10 by |delta| (only when the split is well-powered) ───────────
    st.subheader(f"🏅 10 הבולטים (|Cliff's delta| הגדול ביותר) · D+{K}")
    if not enough:
        st.caption(f"מדגם דק ב-D+{K} — 'הבולטים' יוצג כשיבשילו אירועים (≥{ENTRY_PROFILE_MIN_N} בכל צד).")
    else:
        topd = top_separation(sep, 10)[["metric", "median_up", "median_down",
                                        "pct_upside_up", "pct_upside_down", "direction", "crosses"]].copy()
        topd = fmt_metric_table(topd, ["median_up", "median_down"])      # medians per metric unit
        for c in ("pct_upside_up", "pct_upside_down"):                    # always %
            topd[c] = topd[c].map(lambda v: f"{v:.0f}%" if pd.notna(v) else "—")
        topd["crosses"] = topd["crosses"].map(lambda b: "✔ חוצה" if b else "—")
        topd = topd.rename(columns={
            "metric": "מדד", "median_up": "חציון-עולים", "median_down": "חציון-יורדים",
            "pct_upside_up": "%בצד-עולים (עולים)", "pct_upside_down": "%בצד-עולים (יורדים)",
            "direction": "כיוון", "crosses": "חוצה-רעש?"})
        show_table(topd, rename=None)

    # ── 2.5) multi-horizon delta strip (B) ───────────────────────────────────
    st.subheader("🎞️ רצועת-אופקים — Cliff's delta לאורך D+3/5/7/10/15/20")
    st.caption("תא = חץ-כיוון + ערך Cliff's delta באותו אופק (▲ +0.42 / ▼ −0.55; −1..+1, לא %) · "
               "**מסגרת+מודגש = חוצה רצפת-רעש** (family-wise *בתוך* האופק) · — = לא הבשיל / מדגם דק. "
               "מדד עקבי לאורך האופקים = אמיתי; מרצד = רעש. ללא תיקון-ריבוי בין אופקים (תיאורי). מתמלא עם ההבשלה.")
    strip_long, smeta = _horizon_strip_cached(
        events, fdaily, tuple(ENTRY_PROFILE_METRICS), tuple(ENTRY_PROFILE_HORIZONS), 1000)
    st.caption("הגיעו לאופק (n): " +
               " · ".join(f"D+{h}={smeta[h]['n_reached']}" for h in ENTRY_PROFILE_HORIZONS))
    lookup = {(r["metric"], r["horizon"]): r for _, r in strip_long.iterrows()}
    gdata, cdata = [], []
    for m in ENTRY_PROFILE_METRICS:
        grow, crow = {"מדד": m}, {"מדד": ""}
        for h in ENTRY_PROFILE_HORIZONS:
            r = lookup[(m, h)]
            txt, css = _strip_cell(r["direction"], r["crosses"], r["ok"], r["delta"])
            grow[f"D+{h}"], crow[f"D+{h}"] = txt, css
        gdata.append(grow)
        cdata.append(crow)
    gdf, cdf = pd.DataFrame(gdata), pd.DataFrame(cdata)
    show_table(gdf.style.apply(lambda _: cdf, axis=None).hide(axis="index"), rename=None)

    # ── 3) collection status (numbers only — no charts) ──────────────────────
    st.subheader("📈 סטטוס איסוף")
    _, total, by_source = collection_progress(events)
    completed = count_completed(fdaily)
    pct_done = round(100 * completed / ENTRY_PROFILE_TARGET) if ENTRY_PROFILE_TARGET else 0
    c = st.columns(3)
    kpi(c[0], "נאספו (אירועים)", total)
    kpi(c[1], f"הושלמו (חלון בשל ≥D+{config.POST_ANALYSIS_HORIZON})", completed)
    kpi(c[2], f"התקדמות ליעד ~{ENTRY_PROFILE_TARGET} (הושלמו)", f"{pct_done}%")
    bys = " · ".join(f"{k}: {v}" for k, v in sorted(by_source.items())) if by_source else "—"
    st.caption(f"פילוח לפי מקור — {bys}. היעד (~200, M3) נמדד באירועים שהושלמו; 'נאספו' אינו 'הושלם'.")

    # ── 4) coverage (%-filled) ───────────────────────────────────────────────
    st.subheader("🧮 כיסוי — %מולא לכל מדד")
    st.caption("ריק ב-dist_sma200 / dist_sma50 = young listing לגיטימי "
               "(פחות מ-200 / 50 ברי-מסחר). שקיפות, לא שער חוסם.")
    cov = metric_distributions(disp, ENTRY_PROFILE_METRICS)[["metric", "n_filled", "pct_filled"]].copy()
    cov["n_filled"] = cov["n_filled"].map(lambda v: f"{int(v)}" if pd.notna(v) else "—")
    cov["pct_filled"] = cov["pct_filled"].map(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
    cov = cov.rename(columns={"metric": "מדד", "n_filled": "מולא (n)", "pct_filled": "%מולא"})
    show_table(cov, rename=None)

    # ── 5) reference per-event table (compact, in an expander) ───────────────
    with st.expander("📋 טבלת אירועים (רשימת-ייחוס · סטטוס נוכחי, לא תוצאה)", expanded=False):
        st.caption("⚠️ סטטוס נוכחי — החלון מבשיל, הסימן יכול להתהפך. מקור ה-% מתויג לכל "
                   "שורה: 📅 forward_daily (יום אחרון) או 🟢 live — one-source-per-datum.")
        cols = ["scan_date", "ticker", "source", "sector", "market_cap_category",
                "market_regime", "rsi_14", "atr_pct", "dist_sma50", "dist_sma200",
                "drop_day_rel_volume", "pct_from_entry", "pct_source"]
        d = disp[[c for c in cols if c in disp.columns]].copy()
        for mc in ("rsi_14", "atr_pct", "dist_sma50", "dist_sma200", "drop_day_rel_volume"):
            if mc in d.columns:                              # each column is one metric → its unit
                d[mc] = [fmt_metric_value(mc, v) for v in d[mc]]
        if "pct_from_entry" in d.columns:
            d["שינוי נוכחי %"] = _signed_pct_str(d["pct_from_entry"])
            d = d.drop(columns=["pct_from_entry"])
        d = d.rename(columns={"pct_source": "מקור-%"})
        show_table(d.sort_values("scan_date", ascending=False), height=420)
