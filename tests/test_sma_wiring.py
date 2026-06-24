"""Wiring: the 3 descriptive metrics (atr_pct, dist_sma50, dist_sma200) are placed
into the snapshot of ALL THREE scanners, computed from `prior` (bars strictly
before scan_date) + the as-of close — the uniform window. Includes the lock that
an intraday event with >=200 prior bars yields a NON-EMPTY dist_sma200 (the reason
HISTORY_DAYS_FETCH was raised to 400). Hermetic: yfinance mocked.
"""
from datetime import date, datetime

import pandas as pd

import scanner as sc
import gradual_scanner as gs
import intraday_scanner as ids

SCAN = date(2026, 6, 17)


def _row(price="90.00", cap="1.00B", ticker="AAA"):
    return {"Ticker": ticker, "Price": price, "Market Cap": cap, "Sector": "",
            "Company": "A Co", "Industry": "", "Country": "USA", "_exchange": "NASDAQ"}


def _long_daily(today_close, n=230, base=100.0, vol=2_000_000, today_ohlc=None):
    """n business-day OHLC ending at SCAN; all prior closes = base, today = today_close."""
    idx = pd.bdate_range(end=pd.Timestamp(SCAN), periods=n)
    closes = [base] * n
    closes[-1] = today_close
    opens = list(closes)
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    if today_ohlc:
        opens[-1], highs[-1], lows[-1] = today_ohlc
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": closes,
                         "Volume": [vol] * n}, index=idx)


class _Fake:
    def __init__(self, df):
        self._df = df

    def history(self, *a, **k):
        return self._df


class _FakeIntraday:
    def __init__(self, daily, intra):
        self._daily, self._intra = daily, intra

    def history(self, *a, **k):
        return self._intra if k.get("interval") == "1m" else self._daily


# ── EOD scanner ───────────────────────────────────────────────────────────────
def test_eod_scanner_wires_three_metrics(monkeypatch):
    fr = _long_daily(today_close=90.0, today_ohlc=(100.0, 100.0, 80.0))  # drop_from_open -20%
    monkeypatch.setattr(sc.yf, "Ticker", lambda t: _Fake(fr))
    snap, why = sc.build_snapshot(_row(), SCAN, spy_chg=-0.5, vix=20.0,
                                  now_et=datetime(2026, 6, 17, 18, 0, 0))
    assert why == "ok" and snap["source"] == "eod_close"
    # prior closes all 100 → SMA50=SMA200=100 ; close 90 → (90-100)/100*100 = -10
    assert snap["dist_sma50"] == -10.0
    assert snap["dist_sma200"] == -10.0
    assert snap["atr_pct"] is not None


# ── gradual scanner ───────────────────────────────────────────────────────────
def test_gradual_scanner_wires_three_metrics(monkeypatch):
    fr = _long_daily(today_close=90.0)
    ref_date = fr.index[-6].date()           # a prior session, close = 100
    monkeypatch.setattr(gs.yf, "Ticker", lambda t: _Fake(fr))
    snap, why = gs.build_snapshot(_row(), SCAN, ref_date, spy_chg=-0.5, vix=20.0,
                                  now="2026-06-17 18:00:00 EDT")
    assert why == "ok" and snap["source"] == "gradual_eod"
    assert snap["dist_sma50"] == -10.0
    assert snap["dist_sma200"] == -10.0
    assert snap["atr_pct"] is not None


# ── intraday scanner — LOCKS non-empty dist_sma200 (the 400d decision) ─────────
def _intraday_1m(o=100.0, last=80.0):
    idx = pd.date_range("2026-06-17 13:30", periods=60, freq="1min", tz="UTC")
    closes = [o] * 60
    closes[-1] = last
    return pd.DataFrame({"Open": [o] * 60, "High": [o] * 60, "Low": [min(last, 85.0)] * 60,
                         "Close": closes, "Volume": [10_000] * 60}, index=idx)


def test_intraday_scanner_wires_three_metrics_incl_sma200(monkeypatch):
    daily = _long_daily(today_close=100.0)   # scan_date bar gets filtered out (< scan_date)
    intra = _intraday_1m(o=100.0, last=80.0)  # drop_from_open -20%
    monkeypatch.setattr(ids.yf, "Ticker", lambda t: _FakeIntraday(daily, intra))
    snap, why = ids.build(_row(price="80.00"), SCAN, spy_chg=-0.5,
                          now="2026-06-17 14:00:00 EDT", existing=None)
    assert why == "ok" and snap["source"] == "intraday"
    # last 80 vs prior SMA 100 → -20 ; CRITICAL: dist_sma200 is NON-EMPTY at 400d
    assert snap["dist_sma50"] == -20.0
    assert snap["dist_sma200"] == -20.0
    assert snap["dist_sma200"] not in ("", None)
    assert snap["atr_pct"] is not None and snap["atr_14"] is not None
