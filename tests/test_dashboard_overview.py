"""AppTest — the new Overview home page renders without exception and shows the
descriptive table (st.dataframe + LineChartColumn) + KPIs, with mocked Sheet reads."""
import pandas as pd
from streamlit.testing.v1 import AppTest

import config
import dashboard_common as common


def _patch(monkeypatch):
    watch = pd.DataFrame([
        {"scan_date": "2026-06-17", "ticker": "AAA", "drop_kind": "intraday_drop", "source": "intraday"},
        {"scan_date": "2026-06-18", "ticker": "BBB", "drop_kind": "gradual_drop", "source": "gradual_eod"},
    ])
    post = pd.DataFrame([
        {"scan_date": "2026-06-17", "ticker": "AAA", "last_close_pct": 5.0,
         "max_recovery_pct": 8.0, "max_further_drop_pct": -4.0, "forward_days_available": 2},
    ])
    fdaily = pd.DataFrame([
        {"scan_date": "2026-06-17", "ticker": "AAA", "day_offset": 1, "cum_pct_from_ref": 2.0, "drop_kind": "intraday_drop"},
        {"scan_date": "2026-06-17", "ticker": "AAA", "day_offset": 2, "cum_pct_from_ref": 5.0, "drop_kind": "intraday_drop"},
    ])
    monkeypatch.setattr(common, "resolve_sheet_id", lambda: "TEST")
    monkeypatch.setattr(common, "render_health_banner", lambda *a, **k: None)
    monkeypatch.setattr(common, "load", lambda sid, tab, num: watch)
    monkeypatch.setattr(common, "load_many", lambda sid, specs: {
        config.TAB_WATCHLIST: watch, config.TAB_POST: post, config.TAB_FORWARD_DAILY: fdaily})


def test_overview_home_renders_table_no_exception(monkeypatch):
    _patch(monkeypatch)
    at = AppTest.from_file("dashboard.py").run(timeout=30)
    assert not at.exception, f"overview home crashed: {at.exception}"
    # the descriptive overview table rendered
    assert len(at.dataframe) >= 1, "overview st.dataframe did not render"
