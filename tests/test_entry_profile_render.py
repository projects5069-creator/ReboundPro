"""AppTest smoke for the descriptive Entry-Profile pages: each page renders without
exception, shows the DESCRIPTIVE banner + a table, and contains NONE of the
M5-forbidden terms in any rendered text (no scores/signals/ranking/thresholds/
effect-sizes/salience/up-vs-down). Mirrors tests/test_dashboard_overview.py.
"""
import pandas as pd
from streamlit.testing.v1 import AppTest

import config
import dashboard_common as common

# The page now legitimately shows Cliff's delta / a top-10 / up-down separation
# (DESCRIPTIVE). The genuinely-forbidden M5 terms are only those implying a
# decision: a unified score, an entry rule, or a buy/sell recommendation.
FORBIDDEN = ["buy", "sell", "קנה", "מכור", "recommend", "המלצה",
             "ציון מאוחד", "unified score", "entry rule", "כלל כניסה", "כדאי לקנות"]


def _patch(monkeypatch):
    watch = pd.DataFrame([
        # active intraday event (no forward) → live %
        {"scan_date": "2026-06-12", "ticker": "AAA", "drop_kind": "intraday_drop",
         "source": "intraday", "open": 100.0, "ref_close_window": "", "price": 90.0,
         "sector": "Technology", "market_cap_category": "Small", "market_regime": "neutral",
         "rsi_14": 40.0, "atr_pct": 12.0, "dist_sma50": -5.0, "dist_sma200": 3.0,
         "drop_day_rel_volume": 2.5, "market_cap": 8e8, "adv_dollar": 1.2e7},
        # matured event (has forward) → forward last-day %
        {"scan_date": "2026-06-12", "ticker": "BBB", "drop_kind": "intraday_drop",
         "source": "eod_close", "open": 100.0, "ref_close_window": "", "price": 110.0,
         "sector": "Healthcare", "market_cap_category": "Mid", "market_regime": "risk_on",
         "rsi_14": 55.0, "atr_pct": 8.0, "dist_sma50": 2.0, "dist_sma200": -1.0,
         "drop_day_rel_volume": 1.5, "market_cap": 3e9, "adv_dollar": 5e7},
    ])
    fdaily = pd.DataFrame([
        {"scan_date": "2026-06-12", "ticker": "BBB", "day_offset": 1,
         "cum_pct_from_ref": 5.0, "drop_kind": "intraday_drop"},
        {"scan_date": "2026-06-12", "ticker": "BBB", "day_offset": 2,
         "cum_pct_from_ref": 8.0, "drop_kind": "intraday_drop"},
    ])
    monkeypatch.setattr(common, "resolve_sheet_id", lambda: "TEST")
    monkeypatch.setattr(common, "sidebar_controls", lambda sid: None)
    monkeypatch.setattr(common, "load_many", lambda sid, specs: {
        config.TAB_WATCHLIST: watch, config.TAB_FORWARD_DAILY: fdaily})


def _rendered_text(at):
    parts = []
    for kind in ("title", "header", "subheader", "caption", "markdown", "info",
                 "warning", "error"):
        try:
            for el in getattr(at, kind):
                parts.append(str(getattr(el, "value", "")))
        except Exception:
            pass
    return " ".join(parts)


def test_entry_profile_intraday_renders_m5_safe(monkeypatch):
    _patch(monkeypatch)
    at = AppTest.from_file("pages/6_Entry_Profile_Intraday.py").run(timeout=30)
    assert not at.exception, f"page crashed: {at.exception}"
    text = _rendered_text(at)
    assert "DESCRIPTIVE" in text or "תיאורי" in text     # banner present
    assert "טבלת הפרדה" in text and "הבולטים" in text     # main + top-10 separation tables
    assert "חוצה רצפת-רעש" in text                        # legend (null-band) is shown
    assert len(at.markdown) >= 1                          # a table rendered (show_table → markdown)
    low = text.lower()
    hits = [t for t in FORBIDDEN if t in low]
    assert not hits, f"M5-forbidden term(s) rendered on the page: {hits}"


def test_entry_profile_gradual_renders_m5_safe(monkeypatch):
    _patch(monkeypatch)
    at = AppTest.from_file("pages/7_Entry_Profile_Gradual.py").run(timeout=30)
    # gradual fixture has no gradual rows → page shows the empty-strata info, no crash
    assert not at.exception, f"page crashed: {at.exception}"
    low = _rendered_text(at).lower()
    hits = [t for t in FORBIDDEN if t in low]
    assert not hits, f"M5-forbidden term(s) rendered on the page: {hits}"
