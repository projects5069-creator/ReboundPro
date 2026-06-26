"""AppTest smoke for the descriptive Entry-Profile pages (Finviz separation tables,
now split at a FIXED horizon D+3). Each page renders without exception, shows the
separation + top-10 tables and the legend, splits at D+3 (not current-status), and
contains NONE of the genuinely-forbidden M5 terms (a unified score / entry rule /
buy-sell / recommendation). Mirrors tests/test_dashboard_overview.py.
"""
import pandas as pd
from streamlit.testing.v1 import AppTest

import config
import dashboard_common as common

# Cliff's delta / top-10 / up-down separation are ALLOWED (descriptive). Forbidden =
# only terms implying a decision.
FORBIDDEN = ["buy", "sell", "קנה", "מכור", "recommend", "המלצה",
             "ציון מאוחד", "unified score", "entry rule", "כלל כניסה", "כדאי לקנות",
             "ציון איכות", "quality score", "composite score", "fundamental score"]


def _patch(monkeypatch):
    # 12 intraday_drop events, all reaching D+3; first 6 up (+5), last 6 down (−5)
    watch = pd.DataFrame([{
        "scan_date": "2026-06-12", "ticker": f"T{i}", "drop_kind": "intraday_drop",
        "source": "eod_close", "open": 100.0, "ref_close_window": "", "price": 100.0,
        "sector": "Technology", "market_cap_category": "Small", "market_regime": "neutral",
        "rsi_14": (55.0 if i < 6 else 42.0) + i * 0.1, "atr_pct": 10.0 + i * 0.2,
        "dist_sma50": (3.0 if i < 6 else -3.0), "dist_sma200": 1.0,
        "drop_day_rel_volume": 2.0, "market_cap": 8e8, "adv_dollar": 1e7,
    } for i in range(12)])
    rows = []
    for i in range(12):
        c3 = 5.0 if i < 6 else -5.0
        for k, (cum, dt) in enumerate([(1.0, "2026-06-13"), (2.0, "2026-06-16"), (c3, "2026-06-17")], 1):
            rows.append({"scan_date": "2026-06-12", "ticker": f"T{i}", "day_offset": k,
                         "cum_pct_from_ref": cum, "date": dt, "drop_kind": "intraday_drop"})
    fdaily = pd.DataFrame(rows)
    # Group-C fundamentals snapshot for the events (point-in-time D0): up-group higher ROA
    fund = pd.DataFrame([{
        "scan_date": "2026-06-12", "ticker": f"T{i}",
        "ROA_num": (8.0 if i < 6 else 2.0), "Debt/Eq_num": (0.5 if i < 6 else 2.5),
        "Current Ratio_num": (2.5 if i < 6 else 1.0), "Short Float_num": (3.0 if i < 6 else 12.0),
        "Gross Margin_num": (45.0 if i < 6 else 20.0), "P/B_num": (2.0 if i < 6 else 1.0),
        "P/E_num": (18.0 if i < 6 else -5.0),
    } for i in range(12)])
    monkeypatch.setattr(common, "resolve_sheet_id", lambda: "TEST")
    monkeypatch.setattr(common, "sidebar_controls", lambda sid: None)
    monkeypatch.setattr(common, "load_many", lambda sid, specs: {
        config.TAB_WATCHLIST: watch, config.TAB_FORWARD_DAILY: fdaily,
        config.TAB_FUNDAMENTALS: fund})


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


def test_entry_profile_intraday_fixed_horizon_m5_safe(monkeypatch):
    _patch(monkeypatch)
    at = AppTest.from_file("pages/6_Entry_Profile_Intraday.py").run(timeout=30)
    assert not at.exception, f"page crashed: {at.exception}"
    text = _rendered_text(at)
    assert "DESCRIPTIVE" in text or "תיאורי" in text          # banner
    assert "טבלת הפרדה" in text and "הבולטים" in text          # separation + top-10
    assert "רצועת-אופקים" in text                             # multi-horizon strip (B)
    assert "חוצה רצפת-רעש" in text                            # legend
    assert "D+3" in text and "אותו גיל" in text               # FIXED-horizon split (confound removed)
    assert len(at.markdown) >= 1                              # a table rendered
    low = text.lower()
    hits = [t for t in FORBIDDEN if t in low]
    assert not hits, f"M5-forbidden term(s) rendered: {hits}"


def test_entry_profile_gradual_renders_m5_safe(monkeypatch):
    _patch(monkeypatch)                                       # fixture has no gradual rows
    at = AppTest.from_file("pages/7_Entry_Profile_Gradual.py").run(timeout=30)
    assert not at.exception, f"page crashed: {at.exception}"
    low = _rendered_text(at).lower()
    hits = [t for t in FORBIDDEN if t in low]
    assert not hits, f"M5-forbidden term(s) rendered: {hits}"


def test_spy_excess_unavailable_is_loud_not_silent(monkeypatch):
    """SPY blocked (e.g. on cloud) → LOUD warning + honest basis label; NOT a silent
    fall-back that pretends the user chose raw."""
    _patch(monkeypatch)
    monkeypatch.setattr(common, "_spy_closes_for", lambda *a, **k: {})   # simulate yfinance blocked
    at = AppTest.from_file("pages/6_Entry_Profile_Intraday.py").run(timeout=30)
    at.radio[0].set_value("תשואה-עודפת מול SPY").run()
    assert not at.exception, f"page crashed: {at.exception}"
    wtext = " ".join(str(w.value) for w in at.warning)
    assert "לא זמין בדפלוי" in wtext                          # st.warning (loud), not a caption
    assert "נפילה — SPY לא זמין" in _rendered_text(at)         # basis caption is honest (no lie)


def test_spy_excess_available_uses_excess_basis(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(common, "_spy_closes_for",
                        lambda *a, **k: {"2026-06-12": 100.0, "2026-06-17": 103.0})
    at = AppTest.from_file("pages/6_Entry_Profile_Intraday.py").run(timeout=30)
    at.radio[0].set_value("תשואה-עודפת מול SPY").run()
    assert not at.exception
    text = _rendered_text(at)
    assert "תשואה-עודפת מול SPY" in text                       # basis reflects the chosen mode
    assert "לא זמין בדפלוי" not in " ".join(str(w.value) for w in at.warning)   # no fallback


def test_strip_scope_tag_present(monkeypatch):
    """The strip is always raw — the page must say the toggle affects only the D+3 table."""
    _patch(monkeypatch)
    at = AppTest.from_file("pages/6_Entry_Profile_Intraday.py").run(timeout=30)
    assert "משפיע רק על טבלת-D+3" in _rendered_text(at)
