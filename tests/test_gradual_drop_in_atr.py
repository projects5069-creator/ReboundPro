"""TDD: gradual_scanner.build_snapshot carries atr_14 + drop_in_atr, and the
gradual numerator is the WINDOW drop (ref_close - close), NOT open-intraday_low.
Descriptive only — M5 safe."""
from datetime import date
import pandas as pd
import gradual_scanner as gs

SCAN = date(2026, 6, 17)
REF = date(2026, 6, 10)
# 16 business days (>=15 so ATR(14) is defined), incl REF (06-10) and SCAN (06-17).
DATES = ["2026-05-27", "2026-05-28", "2026-05-29", "2026-06-01", "2026-06-02",
         "2026-06-03", "2026-06-04", "2026-06-05", "2026-06-08", "2026-06-09",
         "2026-06-10", "2026-06-11", "2026-06-12", "2026-06-15", "2026-06-16",
         "2026-06-17"]


class _FakeTicker:
    def __init__(self, df): self._df = df
    def history(self, start, end, auto_adjust): return self._df


def _hist(today_close):
    closes = [100.0] * len(DATES)
    closes[-1] = today_close                       # gradual window drop vs ref=100
    return pd.DataFrame(
        {"Open": closes, "High": [c * 1.01 for c in closes],
         "Low": [c * 0.99 for c in closes], "Close": closes,
         "Volume": [1_000_000] * len(DATES)},
        index=pd.to_datetime(DATES))


def _row():
    return {"Ticker": "AAA", "Price": "85.00", "Market Cap": "1.00B", "Sector": "",
            "Company": "A Co", "Industry": "", "Country": "USA", "_exchange": "NASDAQ"}


def test_gradual_snap_has_atr_and_window_based_drop_in_atr(monkeypatch):
    monkeypatch.setattr(gs.yf, "Ticker", lambda t: _FakeTicker(_hist(85.0)))
    snap, status = gs.build_snapshot(_row(), SCAN, REF, spy_chg=-0.5, vix=20.0,
                                     now="2026-06-17 18:00:00 EDT")
    assert status == "ok"
    atr = snap["atr_14"]
    assert isinstance(atr, float) and atr > 0          # ATR defined on >=15 bars
    # numerator MUST be the window drop (ref_close - close = 100 - 85 = 15),
    # NOT open-intraday_low (~0.85). Derive expected from snap's own atr.
    assert snap["drop_in_atr"] == round((100.0 - 85.0) / atr, 2)
