"""TDD for the descriptive Entry-Profile page helpers (M5-safe, view-only).

Pure helpers (direct-call, like tests/test_overview.py):
  - current_pct_from_entry: one-source-per-datum current % from entry
    (forward_daily last-day cum if present, else live (price-ref)/ref).
  - metric_distributions: pooled median/IQR/min-max/%filled per numeric metric
    (NOT split up/down).
  - collection_progress: cumulative event count over time + total + by-source.
"""
import math

import pandas as pd

import dashboard_common as common


# ── current_pct_from_entry ────────────────────────────────────────────────────
def _watch():
    return pd.DataFrame([
        {"scan_date": "2026-06-12", "ticker": "AAA", "drop_kind": "intraday_drop",
         "open": 100.0, "ref_close_window": "", "price": 90.0},     # no fwd → live -10
        {"scan_date": "2026-06-12", "ticker": "BBB", "drop_kind": "intraday_drop",
         "open": 100.0, "ref_close_window": "", "price": 110.0},    # has fwd → forward
        {"scan_date": "2026-06-12", "ticker": "CCC", "drop_kind": "gradual_drop",
         "open": "", "ref_close_window": 100.0, "price": 80.0},     # no fwd → live -20
    ])


def _fwd_bbb():
    return pd.DataFrame([
        {"scan_date": "2026-06-12", "ticker": "BBB", "day_offset": 1, "cum_pct_from_ref": 5.0},
        {"scan_date": "2026-06-12", "ticker": "BBB", "day_offset": 2, "cum_pct_from_ref": 8.0},
    ])


def test_current_pct_forward_takes_last_day_and_tags_source():
    res = common.current_pct_from_entry(_watch(), _fwd_bbb())
    by = {r["ticker"]: r for _, r in res.iterrows()}
    assert by["BBB"]["pct_from_entry"] == 8.0           # last day_offset cum
    assert by["BBB"]["pct_source"] == "forward_daily"


def test_current_pct_live_when_no_forward_intraday_and_gradual():
    res = common.current_pct_from_entry(_watch(), _fwd_bbb())
    by = {r["ticker"]: r for _, r in res.iterrows()}
    # intraday active: (90-100)/100*100 = -10, ref=open
    assert by["AAA"]["pct_from_entry"] == -10.0 and by["AAA"]["pct_source"] == "live"
    # gradual active: (80-100)/100*100 = -20, ref=ref_close_window
    assert by["CCC"]["pct_from_entry"] == -20.0 and by["CCC"]["pct_source"] == "live"


def test_current_pct_empty_watch_is_empty():
    res = common.current_pct_from_entry(pd.DataFrame(), _fwd_bbb())
    assert res.empty


# ── metric_distributions (pooled, NOT up/down) ────────────────────────────────
def test_metric_distributions_known_values():
    df = pd.DataFrame({"atr_pct": [1.0, 2.0, 3.0, 4.0], "x": [10, 20, 30, 40]})
    res = common.metric_distributions(df, ["atr_pct"]).set_index("metric").loc["atr_pct"]
    assert res["n_filled"] == 4 and res["pct_filled"] == 100.0
    assert res["median"] == 2.5 and res["q1"] == 1.75 and res["q3"] == 3.25
    assert res["iqr"] == 1.5 and res["vmin"] == 1.0 and res["vmax"] == 4.0


def test_metric_distributions_partial_and_empty_coverage():
    df = pd.DataFrame({"dist_sma200": [10.0, None, None, 30.0], "allnan": [None, None, None, None]})
    res = common.metric_distributions(df, ["dist_sma200", "allnan", "missing"]).set_index("metric")
    assert res.loc["dist_sma200", "n_filled"] == 2 and res.loc["dist_sma200", "pct_filled"] == 50.0
    assert res.loc["allnan", "n_filled"] == 0 and res.loc["allnan", "pct_filled"] == 0.0
    assert math.isnan(res.loc["allnan", "median"])
    assert res.loc["missing", "n_filled"] == 0          # column absent → 0, no crash


# ── count_completed (matured window ≥ horizon) ────────────────────────────────
def test_count_completed_counts_only_matured_events():
    fd = pd.DataFrame(
        [{"scan_date": "2026-05-01", "ticker": "AAA", "day_offset": i} for i in range(1, 21)]  # D+20 → matured
        + [{"scan_date": "2026-05-01", "ticker": "BBB", "day_offset": i} for i in range(1, 6)]  # D+5 → not
    )
    assert common.count_completed(fd, horizon=20) == 1


def test_count_completed_empty_is_zero():
    assert common.count_completed(pd.DataFrame(), horizon=20) == 0


# ── collection_progress ───────────────────────────────────────────────────────
def test_collection_progress_cumulative_total_and_by_source():
    watch = pd.DataFrame([
        {"scan_date": "2026-06-12", "ticker": "AAA", "source": "eod_close"},
        {"scan_date": "2026-06-12", "ticker": "BBB", "source": "intraday"},
        {"scan_date": "2026-06-13", "ticker": "CCC", "source": "eod_close"},
    ])
    cum, total, by_source = common.collection_progress(watch)
    assert total == 3
    assert by_source == {"eod_close": 2, "intraday": 1}
    assert list(cum["scan_date"]) == ["2026-06-12", "2026-06-13"]
    assert list(cum["n"]) == [2, 1]
    assert list(cum["cum_n"]) == [2, 3]
