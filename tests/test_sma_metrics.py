"""TDD: scanner.sma / scanner.dist_from_sma / scanner.atr_pct — DESCRIPTIVE
entry features (M5-safe; never signals/thresholds). Point-in-time SMA + the two
normalized distances used by the confirmatory predictor set (atr_pct, dist_sma50,
dist_sma200). Mirrors the style of tests/test_atr_14.py.
"""
import pandas as pd

import config
import scanner


def _frame(closes):
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes}, index=idx)


# ── sma ───────────────────────────────────────────────────────────────────────
def test_sma_mean_of_last_n_closes():
    # last 5 closes = 10,20,30,40,50 → mean 30.0  (earlier bars ignored)
    h = _frame([1, 2, 3, 10, 20, 30, 40, 50])
    assert scanner.sma(h, 5) == 30.0


def test_sma_insufficient_history_returns_none():
    h = _frame([100.0] * 49)
    assert scanner.sma(h, 50) is None


def test_sma_exact_length_ok():
    h = _frame([100.0] * 50)
    assert scanner.sma(h, 50) == 100.0


# ── dist_from_sma = (close - sma)/sma * 100 ───────────────────────────────────
def test_dist_from_sma_above_is_positive():
    # close 110, sma 100 → +10.0%
    assert scanner.dist_from_sma(110.0, 100.0) == 10.0


def test_dist_from_sma_below_is_negative():
    # close 90, sma 100 → -10.0%
    assert scanner.dist_from_sma(90.0, 100.0) == -10.0


def test_dist_from_sma_none_or_zero_guard():
    assert scanner.dist_from_sma(100.0, None) is None
    assert scanner.dist_from_sma(100.0, 0) is None
    assert scanner.dist_from_sma(None, 100.0) is None


# ── atr_pct = atr / close * 100 ───────────────────────────────────────────────
def test_atr_pct_value():
    # atr 2, close 100 → 2.0%
    assert scanner.atr_pct(2.0, 100.0) == 2.0


def test_atr_pct_none_or_zero_guard():
    assert scanner.atr_pct(None, 100.0) is None
    assert scanner.atr_pct(2.0, 0) is None
    assert scanner.atr_pct(2.0, None) is None


# ── header migration-safety: append-only after drop_in_atr ───────────────────
def test_watchlist_header_appends_three_metrics_after_drop_in_atr():
    h = config.WATCHLIST_HEADER
    assert h[-4:] == ["drop_in_atr", "atr_pct", "dist_sma50", "dist_sma200"]
