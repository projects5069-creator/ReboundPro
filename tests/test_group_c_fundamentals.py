"""TDD for Group-C wiring (display/data only, M5-safe): join the 6 locked Finviz
fundamental _num fields (+ derived E/P) from fundamentals_snapshot into the events
frame so the EXISTING separation engine consumes them. Per the sha256-locked
pre-registration (032f10eb...). No new stats math; no composite score (M5).
"""
import re

import numpy as np
import pandas as pd

import config
import dashboard_common as common

LOCKED = ["ROA_num", "Debt/Eq_num", "Current Ratio_num", "Short Float_num",
          "Gross Margin_num", "P/B_num"]


# ── pre-registration compatibility ────────────────────────────────────────────
def test_locked_fields_are_real_finviz_parses():
    for base in ["ROA", "Debt/Eq", "Current Ratio", "Short Float", "Gross Margin", "P/B", "P/E"]:
        assert base in config.FUND_NUMERIC, f"{base} not a real Finviz _num field"


def test_group_c_fields_fed_with_correct_units():
    for f in LOCKED + ["E/P_num"]:
        assert f in common.ENTRY_PROFILE_METRICS, f"{f} not fed into the separation table"
    assert common.METRIC_UNITS["ROA_num"] == "pct"
    assert common.METRIC_UNITS["Short Float_num"] == "pct"
    assert common.METRIC_UNITS["Gross Margin_num"] == "pct"
    assert common.METRIC_UNITS["E/P_num"] == "pct"
    assert common.METRIC_UNITS["Debt/Eq_num"] == "plain"
    assert common.METRIC_UNITS["Current Ratio_num"] == "plain"
    assert common.METRIC_UNITS["P/B_num"] == "plain"


# ── join correctness ──────────────────────────────────────────────────────────
def test_join_matches_snapshot_no_dup_no_overwrite_missing_is_nan():
    events = pd.DataFrame({"scan_date": ["2026-06-12", "2026-06-12"],
                           "ticker": ["AAA", "BBB"], "rsi_14": [50.0, 60.0]})
    fund = pd.DataFrame([{
        "scan_date": "2026-06-12", "ticker": "AAA", "ROA_num": 5.3, "Debt/Eq_num": 1.2,
        "Current Ratio_num": 2.1, "Short Float_num": 8.5, "Gross Margin_num": 45.0,
        "P/B_num": 3.4, "P/E_num": 20.0}])              # BBB has NO snapshot
    out = common.join_fundamentals(events, fund)
    assert len(out) == 2                                 # no row duplication
    assert out.loc[out.ticker == "AAA", "rsi_14"].iloc[0] == 50.0   # existing col untouched
    aaa = out[out.ticker == "AAA"].iloc[0]
    assert aaa["ROA_num"] == 5.3 and aaa["P/B_num"] == 3.4          # joined values match snapshot
    assert aaa["E/P_num"] == 5.0                                    # 100/20
    bbb = out[out.ticker == "BBB"].iloc[0]
    assert np.isnan(bbb["ROA_num"]) and np.isnan(bbb["E/P_num"])    # missing → NaN, not error


def test_ep_guards_negative_and_zero_pe_to_nan():
    events = pd.DataFrame({"scan_date": ["d"] * 3, "ticker": ["A", "B", "C"]})
    fund = pd.DataFrame([{"scan_date": "d", "ticker": "A", "P/E_num": 25.0},
                         {"scan_date": "d", "ticker": "B", "P/E_num": -5.0},
                         {"scan_date": "d", "ticker": "C", "P/E_num": 0.0}])
    out = common.join_fundamentals(events, fund).set_index("ticker")
    assert out.loc["A", "E/P_num"] == 4.0                # 100/25
    assert np.isnan(out.loc["B", "E/P_num"]) and np.isnan(out.loc["C", "E/P_num"])


def test_join_empty_fundamentals_is_safe():
    events = pd.DataFrame({"scan_date": ["d"], "ticker": ["A"], "rsi_14": [50.0]})
    out = common.join_fundamentals(events, pd.DataFrame())
    assert len(out) == 1 and np.isnan(out.iloc[0]["ROA_num"])       # all-NaN, no crash


# ── M5 guard: no composite / unified score ────────────────────────────────────
def test_no_composite_score_field_in_metrics():
    bad = [m for m in common.ENTRY_PROFILE_METRICS
           if re.search(r"score|composite|quality_|fund_score|ציון", m, re.I)]
    assert not bad, f"composite/score field leaked into metrics: {bad}"
