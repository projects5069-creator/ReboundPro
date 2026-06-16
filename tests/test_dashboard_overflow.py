"""Verify the no-horizontal-scroll dashboard render path (display-only fix).

The default AppTest has no Sheet creds, so render() st.stop()s before any table
is built. Here we patch resolve_sheet_id + load with synthetic frames so AppTest
actually exercises show_table on every tab of all 4 pages, then assert:
  • zero exceptions on each page,
  • the compact HTML table ('rb-table' + table-layout:fixed CSS) is rendered,
  • a long column name is shortened in the header (SHORT_LABELS applied),
  • all original columns survive (no column dropped by the display change).
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import config
import dashboard_common as common

PAGES = ["dashboard.py", "pages/1_Intraday_Drop.py",
         "pages/2_Gradual_Drop.py", "pages/3_System_Health.py"]


def _watch():
    rows = []
    for kind, dropcol in (("intraday_drop", "drop_pct_from_open"),
                          ("gradual_drop", "drop_pct_window")):
        rows.append({
            "scan_date": "2026-06-13", "ticker": "AAPL", "drop_kind": kind,
            "exchange": "NASDAQ", "price": 123.45, dropcol: -12.34,
            "liquidity_bucket": "large", "sector": "Technology",
            "market_regime": "neutral", "drop_type": "gap", "adv_dollar": 1.2e9,
            "market_cap": 2.5e12, "rsi_14": 28.7, "spy_change_pct": -0.5,
            "sector_etf_change_pct": -0.8, "pct_from_52w_high": -22.2,
            "pct_from_52w_low": 5.1, "prior_decline_20d_pct": -15.0,
            "prior_decline_60d_pct": -30.0, "vix_level": 17.68,
            "drop_day_rel_volume": 2.11, "sector_momentum_5d": -1.2,
            "sector_momentum_20d": -3.4, "source": "eod_close",
            "lookback_trading_days": 5, "ref_close_window": 140.0,
            "first_cross_at": "10:01", "first_cross_price": 130.0,
            "first_cross_drop_pct": -8.0, "intraday_low": 120.0,
            "intraday_low_at": "11:30", "recovery_from_low_pct": 2.9,
            "reversal_confirmed": "true", "scans_count": 14,
            "last_update_at": "15:59",
        })
    return pd.DataFrame(rows)


def _post():
    return pd.DataFrame([{
        "scan_date": "2026-06-13", "ticker": "AAPL", "status": "ok",
        "split_halt_flag": "false", "split_halt_reason": "",
        "forward_days_available": 20, "ref_close": 123.45,
        "max_recovery_pct": 8.1, "day_of_max_recovery": 4,
        "max_further_drop_pct": -3.2, "day_of_max_drop": 2,
        "trough_price": 119.0, "trough_day": 2, "recovery_from_trough_pct": 3.7,
        "max_recovery_from_trough_pct": 9.0, "last_close_pct": 4.4,
        "dN_date": "2026-07-11", "horizon": 20,
        **{f"max_recovery_{w}d": 1.0 * w for w in config.POST_ANALYSIS_SUBWINDOWS},
        **{f"max_further_drop_{w}d": -0.5 * w for w in config.POST_ANALYSIS_SUBWINDOWS},
        "touched_up_5pct": "true", "touched_down_5pct": "false",
    }])


def _summary():
    return pd.DataFrame([{
        "scan_date": "2026-06-13", "total_finviz_candidates": 422,
        "passed_floor": 30, "below_min_price": 100, "below_min_cap": 150,
        "below_min_adv": 90, "drop_below_threshold": 40, "other_rejects": 12,
    }])


def _ts():
    return pd.DataFrame([{"scan_date": "2026-06-13", "ticker": "AAPL",
                          "timestamp": "2026-06-13 10:00:00", "price": 122.0,
                          "pct_from_open": -10.0, "volume": 1000}])


def _fund():
    return pd.DataFrame([{"scan_date": "2026-06-13", "ticker": "AAPL",
                          "Market Cap": "2.5T", "P/E": "28.1", "Short Float": "1.2%"}])


def _news():
    return pd.DataFrame([{"scan_date": "2026-06-13", "ticker": "AAPL",
                          "news_count": 3, "earnings_within_7d": "no",
                          "headline_1": "Apple drops on guidance worries " * 4,
                          "datetime_1": "2026-06-13 09:00", "source_1": "Reuters",
                          "url_1": "https://example.com/a-very-long-url/" + "x" * 80}])


def _health():
    base = {"run_at": "2026-06-14 13:00:00 ET", "mode": "morning",
            "overall_status": "warning", "exit_code": 1,
            "summary_text": "1 warning", "details_text": "field-completeness: warn"}
    base.update({cid: "ok" for cid in config.HEALTH_CHECK_IDS})
    return pd.DataFrame([base])


_FRAMES = {
    config.TAB_WATCHLIST: _watch(), config.TAB_POST: _post(),
    config.TAB_SUMMARY: _summary(), config.TAB_TIMESERIES: _ts(),
    config.TAB_FUNDAMENTALS: _fund(), config.TAB_NEWS: _news(),
    config.TAB_HEALTH_LOG: _health(),
}


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(common, "resolve_sheet_id", lambda: "TEST_SHEET")

    def fake_load(sheet_id, tab, num_cols):
        df = _FRAMES.get(tab, pd.DataFrame()).copy()
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    # Home + System Health still use load()/load_health(); the hypothesis pages
    # now read all tabs via the batched load_many() — patch both paths.
    monkeypatch.setattr(common, "load", fake_load)
    monkeypatch.setattr(common, "load_many",
                        lambda sheet_id, specs: {t: fake_load(sheet_id, t, n)
                                                 for t, n in specs.items()})


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page):
    at = AppTest.from_file(page).run(timeout=30)
    assert not at.exception, f"{page} raised: {at.exception}"


def _all_markdown(at):
    return "\n".join(getattr(m, "value", "") or "" for m in at.markdown)


@pytest.mark.parametrize("page", ["pages/1_Intraday_Drop.py", "pages/3_System_Health.py"])
def test_compact_html_table_rendered(page):
    at = AppTest.from_file(page).run(timeout=30)
    md = _all_markdown(at)
    assert "rb-table" in md, f"{page}: compact HTML table wrapper not rendered"


def test_long_header_shortened_and_columns_preserved():
    at = AppTest.from_file("pages/1_Intraday_Drop.py").run(timeout=30)
    md = _all_markdown(at)
    # SHORT_LABELS applied to a displayed header (drop_pct_from_open -> drop%open)
    assert "drop%open" in md, "header shortening (SHORT_LABELS) not applied"
    # no column removed: the watchlist still surfaces e.g. liquidity short label
    assert "liq" in md


# Every column that was displayed in the single wide watchlist table must still
# appear after the theme-group split — split must reorganize, never drop.
_INTRADAY_COLS = [
    "scan_date", "ticker", "exchange", "drop_pct_from_open", "price",
    "liquidity_bucket", "sector", "market_regime", "drop_type", "adv_dollar",
    "market_cap", "rsi_14", "pct_from_52w_high", "pct_from_52w_low",
    "prior_decline_20d_pct", "prior_decline_60d_pct", "vix_level",
    "drop_day_rel_volume", "sector_momentum_5d", "sector_momentum_20d", "source",
    "first_cross_at", "first_cross_price", "first_cross_drop_pct", "intraday_low",
    "intraday_low_at", "recovery_from_low_pct", "reversal_confirmed", "scans_count",
    "last_update_at",
]
_GRADUAL_COLS = [
    "scan_date", "ticker", "exchange", "drop_pct_window", "price",
    "liquidity_bucket", "sector", "market_regime", "drop_type", "adv_dollar",
    "market_cap", "rsi_14", "pct_from_52w_high", "pct_from_52w_low",
    "prior_decline_20d_pct", "prior_decline_60d_pct", "vix_level",
    "drop_day_rel_volume", "sector_momentum_5d", "sector_momentum_20d",
    "source", "lookback_trading_days", "ref_close_window",
]


@pytest.mark.parametrize("page,cols", [
    ("pages/1_Intraday_Drop.py", _INTRADAY_COLS),
    ("pages/2_Gradual_Drop.py", _GRADUAL_COLS),
])
def test_watchlist_split_drops_no_column(page, cols):
    at = AppTest.from_file(page).run(timeout=30)
    md = _all_markdown(at)
    # all three theme-group headers rendered
    assert "זיהוי" in md and "מומנטום" in md and "מסלול" in md, f"{page}: a theme group is missing"
    # every displayed column present (by its short label or raw header)
    missing = [c for c in cols if common.SHORT_LABELS.get(c, c) not in md]
    assert not missing, f"{page}: columns dropped by the split: {missing}"


def test_watchlist_sort_selectbox_works():
    at = AppTest.from_file("pages/1_Intraday_Drop.py").run(timeout=30)
    sb = [s for s in at.selectbox if "מיין" in (s.label or "")]
    assert sb, "'מיין לפי' sort selectbox missing"
    sb[0].set_value("price")
    at.run(timeout=30)
    assert not at.exception, f"sort re-run raised: {at.exception}"
    assert "rb-table" in _all_markdown(at), "theme tables vanished after sort change"


# The Collection-Health "pending" KPI must count BOTH window-not-started
# (pending_forward) AND recent-lag (forward_pending), else forward_pending rows
# show in the table but vanish from the KPI tally.
def test_health_pending_kpi_includes_forward_pending(monkeypatch):
    base = _post()                          # full-schema ok row (AAPL@2026-06-13)
    extra = base.iloc[[0, 0]].copy()
    extra["status"] = ["pending_forward", "forward_pending"]
    post = pd.concat([base, extra], ignore_index=True)   # 3 rows, all keyed to watch
    frames = dict(_FRAMES)
    frames[config.TAB_POST] = post

    def fake_many(sid, specs):
        out = {}
        for t, num in specs.items():
            df = frames.get(t, pd.DataFrame()).copy()
            for c in num:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            out[t] = df
        return out

    monkeypatch.setattr(common, "load_many", fake_many)
    at = AppTest.from_file("pages/1_Intraday_Drop.py").run(timeout=30)
    assert not at.exception, f"render raised: {at.exception}"
    pend = [m for m in at.metric if "pending" in (m.label or "")]
    assert pend, "pending KPI metric not found"
    assert str(pend[0].value) == "2", \
        f"pending KPI = {pend[0].value}, expected 2 (pending_forward + forward_pending)"
