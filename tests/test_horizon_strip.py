"""TDD for the multi-horizon delta strip engine (B): per (metric, horizon) the
Cliff's delta + direction + crosses (family-wise WITHIN that horizon) + ok (the
horizon is well-powered AND the metric is non-empty). Reuses the fixed-horizon
engine + build_separation_table — no new stats math. DESCRIPTIVE / M5-safe.
"""
import numpy as np
import pandas as pd

import dashboard_common as common


def _fixture():
    """12 events all reach D+3 (6 up +5 / 6 down −5). Only 4 also reach D+5
    (2 up / 2 down → thin). None reach D+10."""
    watch = pd.DataFrame([{
        "scan_date": "2026-06-12", "ticker": f"T{i}",
        "good": (100.0 + i) if i < 6 else float(i),     # up high / down low → separates
    } for i in range(12)])
    rows = []
    for i in range(12):
        c3 = 5.0 if i < 6 else -5.0
        seq = [(1, 1.0), (2, 2.0), (3, c3)]
        if i in (0, 1, 6, 7):                            # these 4 also reach D+5
            seq += [(4, 4.0), (5, c3)]
        for k, cum in seq:
            rows.append({"scan_date": "2026-06-12", "ticker": f"T{i}",
                         "day_offset": k, "cum_pct_from_ref": cum, "date": "2026-06-17"})
    return watch, pd.DataFrame(rows)


def test_horizon_strip_ok_and_direction_per_horizon():
    watch, fd = _fixture()
    long, meta = common.horizon_strip(watch, fd, ["good"], [3, 5, 10], k=200)
    g3 = long[(long.metric == "good") & (long.horizon == 3)].iloc[0]
    assert g3["ok"] and g3["direction"] == "🟢" and g3["delta"] > 0           # well-powered separator
    g5 = long[(long.metric == "good") & (long.horizon == 5)].iloc[0]
    assert not g5["ok"]                                                       # D+5 thin (n=2/2)
    g10 = long[(long.metric == "good") & (long.horizon == 10)].iloc[0]
    assert not g10["ok"]                                                      # nobody reached D+10


def test_horizon_strip_meta_counts():
    watch, fd = _fixture()
    _, meta = common.horizon_strip(watch, fd, ["good"], [3, 5, 10], k=200)
    assert meta[3]["enough"] and meta[3]["n_reached"] == 12
    assert not meta[5]["enough"] and meta[5]["n_reached"] == 4
    assert not meta[10]["enough"] and meta[10]["n_reached"] == 0


def test_horizon_strip_empty_metric_not_ok():
    watch, fd = _fixture()
    watch["allnan"] = np.nan
    long, _ = common.horizon_strip(watch, fd, ["allnan"], [3], k=200)
    row = long.iloc[0]
    assert not row["ok"] and row["direction"] == "▬"          # structurally empty → neutral, not ok


# ── _strip_cell: arrow + numeric Cliff's delta visible in-cell ────────────────
def test_strip_cell_shows_arrow_and_delta():
    txt, css = common._strip_cell("🟢", False, True, 0.42)
    assert txt == "▲ +0.42" and "background-color:#e9f7ef" in css
    txt2, css2 = common._strip_cell("🔴", True, True, -0.55)
    assert txt2 == "▼ −0.55"                                   # unicode minus
    assert "font-weight:700" in css2 and "border:2px solid" in css2   # crosser pops
    assert common._strip_cell("▬", False, True, 0.0)[0] == "· +0.00"  # neutral keeps the number


def test_strip_cell_thin_or_unreached_is_dash_only():
    txt, _ = common._strip_cell("🟢", True, False, 0.9)        # not ok → no arrow / no number
    assert txt == "—"
