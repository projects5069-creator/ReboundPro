"""TDD for unit-aware per-metric display formatting (display-only, M5-safe):
percent (%), dollar (abbreviated B/M/K with $), or plain (no suffix), keyed by metric.
"""
import numpy as np
import pandas as pd

import dashboard_common as common


def test_pct_metrics_get_percent_suffix():
    assert common.fmt_metric_value("atr_pct", 12.3) == "12.30%"
    assert common.fmt_metric_value("dist_sma50", -3.0) == "-3.00%"
    assert common.fmt_metric_value("spy_change_pct", 0.0) == "0.00%"


def test_dollar_metrics_abbreviated_with_sign():
    assert common.fmt_metric_value("market_cap", 8e8) == "$800.0M"
    assert common.fmt_metric_value("market_cap", 3.2e9) == "$3.20B"
    assert common.fmt_metric_value("adv_dollar", 1.2e7) == "$12.0M"


def test_plain_metrics_no_suffix():
    assert common.fmt_metric_value("rsi_14", 48.3) == "48.30"
    assert common.fmt_metric_value("vix_level", 18.0) == "18.00"


def test_unknown_metric_defaults_plain():
    assert common.fmt_metric_value("not_a_metric", 5.0) == "5.00"


def test_nan_and_blank_render_as_dash():
    assert common.fmt_metric_value("atr_pct", float("nan")) == "—"
    assert common.fmt_metric_value("market_cap", None) == "—"
    assert common.fmt_metric_value("rsi_14", "") == "—"


def test_metric_table_formats_value_columns_per_row_unit():
    df = pd.DataFrame({"metric": ["atr_pct", "market_cap", "rsi_14"],
                       "median_up": [12.0, 8e8, 50.0]})
    out = common.fmt_metric_table(df, ["median_up"]).set_index("metric")
    assert out.loc["atr_pct", "median_up"] == "12.00%"
    assert out.loc["market_cap", "median_up"] == "$800.0M"
    assert out.loc["rsi_14", "median_up"] == "50.00"
