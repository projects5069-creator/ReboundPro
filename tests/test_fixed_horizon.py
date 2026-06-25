"""TDD for the fixed-horizon split engine (removes the age confound; B-ready via the
day_offset param). Pure helpers in dashboard_common that feed the EXISTING
build_separation_table via pct_col — no new stats math. DESCRIPTIVE / M5-safe.
"""
import numpy as np
import pandas as pd

import dashboard_common as common


def _fwd():
    """AAA reaches D+5 (cum@3=+2, cum@5=+8, D+5 date 2026-06-20);
    BBB reaches only D+3 (cum@3=-4)."""
    rows = []
    for k, cum, dt in [(1, 0.0, "2026-06-13"), (2, 1.0, "2026-06-16"),
                       (3, 2.0, "2026-06-17"), (4, 5.0, "2026-06-18"), (5, 8.0, "2026-06-20")]:
        rows.append({"scan_date": "2026-06-12", "ticker": "AAA", "day_offset": k,
                     "cum_pct_from_ref": cum, "date": dt})
    for k, cum, dt in [(1, -1.0, "2026-06-13"), (2, -2.0, "2026-06-16"), (3, -4.0, "2026-06-17")]:
        rows.append({"scan_date": "2026-06-12", "ticker": "BBB", "day_offset": k,
                     "cum_pct_from_ref": cum, "date": dt})
    return pd.DataFrame(rows)


# ── fixed_horizon_outcome ─────────────────────────────────────────────────────
def test_fixed_horizon_picks_exact_offset_and_excludes_unreached():
    s5 = common.fixed_horizon_outcome(_fwd(), 5)
    assert s5.loc[("2026-06-12", "AAA")] == 8.0     # exactly day_offset==5
    assert ("2026-06-12", "BBB") not in s5.index    # BBB never reached D+5 → absent (not imputed)


def test_fixed_horizon_smaller_offset_includes_more():
    s3 = common.fixed_horizon_outcome(_fwd(), 3)
    assert s3.loc[("2026-06-12", "AAA")] == 2.0
    assert s3.loc[("2026-06-12", "BBB")] == -4.0


# ── spy_excess_outcome ────────────────────────────────────────────────────────
def test_spy_excess_subtracts_market_return():
    # scan_date SPY=100, AAA D+5 date (2026-06-20) SPY=105 → SPY_cum +5 ; excess = 8 - 5 = 3
    spy = {"2026-06-12": 100.0, "2026-06-20": 105.0}
    ex = common.spy_excess_outcome(_fwd(), 5, spy)
    assert round(float(ex.loc[("2026-06-12", "AAA")]), 6) == 3.0


def test_spy_excess_nan_when_spy_missing():
    ex = common.spy_excess_outcome(_fwd(), 5, {})     # no SPY closes
    assert np.isnan(float(ex.loc[("2026-06-12", "AAA")]))


# ── horizon_split_counts ──────────────────────────────────────────────────────
def test_horizon_split_counts_honest_n():
    c = common.horizon_split_counts(common.fixed_horizon_outcome(_fwd(), 3))
    assert c == {"n_reached": 2, "n_up": 1, "n_down": 1}     # AAA +2 up, BBB -4 down
    c5 = common.horizon_split_counts(common.fixed_horizon_outcome(_fwd(), 5))
    assert c5 == {"n_reached": 1, "n_up": 1, "n_down": 0}    # only AAA reached D+5


# ── engine feeds the EXISTING build_separation_table via pct_col (no new math) ─
def test_engine_feeds_build_separation_table():
    # 6 events, a metric that separates by the fixed-horizon sign
    ev = pd.DataFrame({
        "scan_date": ["2026-06-12"] * 6,
        "ticker": [f"T{i}" for i in range(6)],
        "good": [10.0, 11, 12, 1, 2, 3],
    })
    # synthetic fixed-horizon outcome: first 3 up, last 3 down
    outcome = pd.Series([5.0, 5, 5, -5, -5, -5],
                        index=pd.MultiIndex.from_arrays(
                            [ev["scan_date"], ev["ticker"]], names=["scan_date", "ticker"]))
    merged = ev.merge(outcome.rename("pct_k"), on=["scan_date", "ticker"], how="left")
    tbl = common.build_separation_table(merged, ["good"], pct_col="pct_k", k=200)
    assert tbl.set_index("metric").loc["good", "delta"] == 1.0      # perfect separation
