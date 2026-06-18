"""TDD — Overview home-page pure helpers (M3, descriptive only; no signals).

The Streamlit rendering (render_overview) is thin glue tested via AppTest; these
tests lock the PURE logic: status classification (thresholds +3/-3/-10/pending),
the watch x post x forward_daily assembly (LEFT JOIN, missing post -> pending),
the average recovery curve, and the outcome histogram.
"""
import math

import pandas as pd

import dashboard_common as common


# ── classify_overview_status (thresholds) ─────────────────────────────────────
def test_status_recovering_at_plus_3():
    assert common.classify_overview_status(3.0, True) == "recovering"
    assert common.classify_overview_status(12.5, True) == "recovering"


def test_status_stable_band():
    assert common.classify_overview_status(2.9, True) == "stable"
    assert common.classify_overview_status(-3.0, True) == "stable"   # -3 is the stable boundary


def test_status_down_band():
    assert common.classify_overview_status(-3.1, True) == "down"
    assert common.classify_overview_status(-10.0, True) == "down"    # -10 is the down boundary


def test_status_falling_below_minus_10():
    assert common.classify_overview_status(-10.1, True) == "falling"


def test_status_pending_when_no_forward_or_nan():
    assert common.classify_overview_status(5.0, False) == "pending"
    assert common.classify_overview_status(float("nan"), True) == "pending"
    assert common.classify_overview_status(None, True) == "pending"


# ── build_overview_table (LEFT JOIN watch x post x forward_daily) ─────────────
def _frames():
    watch = pd.DataFrame([
        {"scan_date": "2026-06-17", "ticker": "AAA", "drop_kind": "intraday_drop", "source": "intraday"},
        {"scan_date": "2026-06-18", "ticker": "BBB", "drop_kind": "gradual_drop", "source": "gradual_eod"},
    ])
    post = pd.DataFrame([
        {"scan_date": "2026-06-17", "ticker": "AAA", "last_close_pct": 5.0,
         "max_recovery_pct": 8.0, "max_further_drop_pct": -4.0, "forward_days_available": 2},
        # BBB has no post row yet (entered today, pre-EOD)
    ])
    fdaily = pd.DataFrame([
        {"scan_date": "2026-06-17", "ticker": "AAA", "day_offset": 2, "cum_pct_from_ref": 5.0, "drop_kind": "intraday_drop"},
        {"scan_date": "2026-06-17", "ticker": "AAA", "day_offset": 1, "cum_pct_from_ref": 2.0, "drop_kind": "intraday_drop"},
    ])
    return watch, post, fdaily


def test_build_table_one_row_per_event_newest_first():
    t = common.build_overview_table(*_frames())
    assert list(t["ticker"]) == ["BBB", "AAA"]          # sorted by scan_date desc
    assert len(t) == 2


def test_build_table_joins_post_scalars_and_status():
    t = common.build_overview_table(*_frames()).set_index("ticker")
    assert t.loc["AAA", "days"] == 2
    assert t.loc["AAA", "pct_from_entry"] == 5.0
    assert t.loc["AAA", "status"] == "recovering"       # +5% >= +3


def test_build_table_event_without_post_is_pending():
    t = common.build_overview_table(*_frames()).set_index("ticker")
    assert t.loc["BBB", "status"] == "pending"
    assert t.loc["BBB", "days"] == 0
    assert math.isnan(float(t.loc["BBB", "pct_from_entry"]))


def test_build_table_trajectory_ordered_by_day_offset():
    t = common.build_overview_table(*_frames()).set_index("ticker")
    assert list(t.loc["AAA", "trajectory"]) == [2.0, 5.0]   # offset 1 then 2
    assert list(t.loc["BBB", "trajectory"]) == []           # no forward yet


# ── recovery_curve (mean cum_pct_from_ref per day_offset per drop_kind) ───────
def test_recovery_curve_means_per_offset_and_kind():
    fdaily = pd.DataFrame([
        {"day_offset": 1, "drop_kind": "intraday_drop", "cum_pct_from_ref": 2.0},
        {"day_offset": 1, "drop_kind": "intraday_drop", "cum_pct_from_ref": 4.0},
        {"day_offset": 1, "drop_kind": "gradual_drop", "cum_pct_from_ref": -1.0},
    ])
    c = common.recovery_curve(fdaily).set_index(["drop_kind", "day_offset"])["mean_cum_pct"]
    assert c.loc[("intraday_drop", 1)] == 3.0
    assert c.loc[("gradual_drop", 1)] == -1.0


# ── outcome_histogram (count of events per last_close_pct bucket) ─────────────
def test_outcome_histogram_counts_per_bucket():
    s = pd.Series([5.0, 1.0, -5.0, -20.0, 4.0])   # recovering, stable, down, falling, recovering
    h = common.outcome_histogram(s).set_index("bucket")["count"]
    assert h.sum() == 5
    assert h.get("recovering", 0) == 2
    assert h.get("falling", 0) == 1
