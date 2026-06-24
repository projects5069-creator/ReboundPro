"""TDD for the ported pure separation stats in dashboard_common (Cliff's delta +
permutation null band, pure numpy) AND the build_separation_table / top_separation
builders that drive the Finviz-style metric tables. DESCRIPTIVE / M5-safe.
"""
import numpy as np
import pandas as pd

import dashboard_common as common


# ── build_separation_table / top_separation ──────────────────────────────────
def _sep_events(n=12):
    """n up events (pct +5) + n down events (pct -5), with metrics that perfectly
    separate (good ↑, neg ↓), do not separate (noise), or are empty."""
    return pd.DataFrame({
        "pct_from_entry": [5.0] * n + [-5.0] * n,
        "good":  list(np.arange(100.0, 100.0 + n)) + list(np.arange(0.0, n)),   # up high → δ +1
        "neg":   list(np.arange(0.0, n)) + list(np.arange(100.0, 100.0 + n)),   # up low  → δ −1
        "noise": list(np.arange(0.0, n)) + list(np.arange(0.0, n)),             # identical → δ 0
        "empty": [np.nan] * (2 * n),
    })


def test_separation_table_directions_deltas_and_crosses():
    tbl = common.build_separation_table(_sep_events(), ["good", "neg", "noise", "empty"], k=300)
    by = tbl.set_index("metric")
    assert by.loc["good", "delta"] == 1.0 and by.loc["good", "direction"] == "🟢"
    assert by.loc["neg", "delta"] == -1.0 and by.loc["neg", "direction"] == "🔴"
    assert by.loc["noise", "delta"] == 0.0 and by.loc["noise", "direction"] == "▬"
    assert by.loc["good", "n_up"] == 12 and by.loc["good", "n_down"] == 12
    # perfect separators cross the family-wise null band; noise does not
    assert bool(by.loc["good", "crosses"]) and bool(by.loc["neg", "crosses"])
    assert not bool(by.loc["noise", "crosses"])


def test_separation_table_side_fractions_at_midpoint():
    by = common.build_separation_table(_sep_events(), ["good"], k=200).set_index("metric")
    # midpoint = mean(median_up=105.5, median_down=5.5) = 55.5 → up all above, down none
    assert by.loc["good", "pct_upside_up"] == 100.0 and by.loc["good", "pct_upside_down"] == 0.0


def test_separation_table_empty_metric_is_nan_not_crossing():
    by = common.build_separation_table(_sep_events(), ["empty"], k=100).set_index("metric")
    assert np.isnan(by.loc["empty", "delta"]) and by.loc["empty", "n_up"] == 0
    assert not bool(by.loc["empty", "crosses"])


def test_top_separation_orders_by_abs_delta():
    tbl = common.build_separation_table(_sep_events(), ["good", "neg", "noise", "empty"], k=200)
    top = common.top_separation(tbl, n=2)
    assert set(top["metric"]) == {"good", "neg"}        # |δ|=1 beat noise(0) / empty(nan)


def test_separation_table_empty_events_returns_empty():
    assert common.build_separation_table(pd.DataFrame(), ["good"], k=50).empty


# ── split_groups ──────────────────────────────────────────────────────────────


# ── split_groups ──────────────────────────────────────────────────────────────
def test_split_groups_sign_boundary():
    up, down = common.split_groups([0.0, 1.0, -1.0, 0.5])
    assert list(up) == [False, True, False, True]      # 0 → down
    assert list(down) == [True, False, True, False]


# ── cliffs_delta ──────────────────────────────────────────────────────────────
def test_cliffs_delta_all_up_greater_is_plus_one():
    assert common.cliffs_delta([5, 6, 7], [1, 2, 3])["delta"] == 1.0


def test_cliffs_delta_symmetric_is_zero():
    assert common.cliffs_delta([1, 2, 3], [1, 2, 3])["delta"] == 0.0


def test_cliffs_delta_ties_excluded_from_numerator():
    assert common.cliffs_delta([3, 3], [1, 3])["delta"] == 0.5


def test_cliffs_delta_empty_group_is_nan():
    res = common.cliffs_delta([1, 2], [])
    assert np.isnan(res["delta"]) and res["n_y"] == 0


def test_cliffs_delta_n1_each_side():
    assert common.cliffs_delta([5], [1])["delta"] == 1.0
    assert common.cliffs_delta([1], [5])["delta"] == -1.0


def test_cliffs_delta_drops_nan():
    assert common.cliffs_delta([5, 6, np.nan], [1, 2, np.nan])["delta"] == \
           common.cliffs_delta([5, 6], [1, 2])["delta"]


def test_magnitude_bands():
    assert common.magnitude_label(0.10) == "negligible"
    assert common.magnitude_label(0.147) == "small"
    assert common.magnitude_label(0.33) == "medium"
    assert common.magnitude_label(0.474) == "large"
    assert common.magnitude_label(float("nan")) == "—"


# ── thresholds / side fractions ───────────────────────────────────────────────
def test_midpoint_threshold_is_mean_of_medians():
    assert common.midpoint_threshold([1, 2, 3, 4], [10, 20])["threshold"] == 8.75


def test_side_fractions_count_above():
    up_a, down_a = common.side_fractions([1, 2, 3, 4], [0, 5], 2.5)
    assert up_a == 50.0 and down_a == 50.0


# ── permutation null band ─────────────────────────────────────────────────────
def test_permutation_band_seed_reproducible():
    vals = np.array([10.0, 11, 12, 1, 2, 3])
    up = np.array([True, True, True, False, False, False])
    a = common.permutation_band(vals, up, k=200, seed=7)
    b = common.permutation_band(vals, up, k=200, seed=7)
    assert np.array_equal(a["null"], b["null"])


def test_permutation_band_percentile_flags():
    up = np.array([True] * 10 + [False] * 10)
    sep = np.concatenate([np.arange(100, 110), np.arange(0, 10)]).astype(float)
    res = common.permutation_band(sep, up, k=1000, seed=1)
    assert res["observed_abs_delta"] == 1.0 and res["exceeds_95"] and res["exceeds_99"]
    flat = np.tile(np.arange(10, dtype=float), 2)
    res2 = common.permutation_band(flat, up, k=1000, seed=1)
    assert res2["observed_abs_delta"] == 0.0 and not res2["exceeds_95"]


def test_family_wise_max_null_dominates_each_metric(monkeypatch=None):
    up = np.array([True, True, True, False, False, False])
    m1 = np.array([10.0, 11, 12, 1, 2, 3])
    m2 = np.array([3.0, 2, 1, 12, 11, 10])
    maxnull = common.family_wise_max_null([m1, m2], up, k=300, seed=5)
    assert maxnull.shape == (300,)
    b1 = common.permutation_band(m1, up, k=300, seed=5)
    b2 = common.permutation_band(m2, up, k=300, seed=5)
    assert np.all(maxnull >= b1["null"] - 1e-9) and np.all(maxnull >= b2["null"] - 1e-9)
