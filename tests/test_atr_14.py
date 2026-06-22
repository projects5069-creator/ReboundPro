"""TDD: scanner.atr_14 — Wilder ATR(14) in price units, point-in-time.
Mirrors scanner.rsi_14 (scalar-or-None, rounded). Descriptive feature only."""
import pandas as pd
import scanner


def _frame(n, high, low, close):
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame({"High": [high] * n, "Low": [low] * n, "Close": [close] * n}, index=idx)


def test_atr_14_constant_true_range():
    # Every bar: High-Low=2, Close mid → True Range = 2 every day → ATR = 2.0
    df = _frame(20, high=101.0, low=99.0, close=100.0)
    assert scanner.atr_14(df) == 2.0


def test_atr_14_insufficient_history_returns_none():
    df = _frame(10, high=101.0, low=99.0, close=100.0)
    assert scanner.atr_14(df) is None
