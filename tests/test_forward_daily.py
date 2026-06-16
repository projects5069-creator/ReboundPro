"""TDD for #4 — forward_daily series (D+1..D+N) persistence.

daily_series() is PURE and reuses the already-fetched `fwd` (no extra yfinance
call). compute_outcome gains only an ADDITIVE "_daily_rows" key — its status and
aggregates (protected by the morning's classify fix + its 10 tests) must stay
identical. forward_daily is written via the atomic upsert (no-wipe).
"""
import math
from datetime import date

import pandas as pd
import pytest

import config
import post_analysis_collector as pac


def _fwd(closes, highs, lows, dates):
    return pd.DataFrame(
        {"Open": closes, "High": highs, "Low": lows, "Close": closes,
         "Stock Splits": [0] * len(closes)},
        index=pd.to_datetime(dates))


# ── daily_series (pure) ───────────────────────────────────────────────────────
def test_daily_series_offsets_cum_and_change():
    fwd = _fwd([100, 120, 95], [110, 121, 99], [95, 105, 90],
               ["2026-01-06", "2026-01-07", "2026-01-08"])
    rows = pac.daily_series(fwd, 100.0, date(2026, 1, 5), "AAA")
    assert [r["day_offset"] for r in rows] == [1, 2, 3]
    assert [r["date"] for r in rows] == ["2026-01-06", "2026-01-07", "2026-01-08"]
    # cum % from D0 ref (100)
    assert [r["cum_pct_from_ref"] for r in rows] == [0.0, 20.0, -5.0]
    # daily change: D+1 vs ref(100)=0 ; D+2 vs 100=+20 ; D+3 vs 120 = -20.83
    assert rows[0]["daily_change_pct"] == 0.0
    assert rows[1]["daily_change_pct"] == 20.0
    assert rows[2]["daily_change_pct"] == round((95 / 120 - 1) * 100, 2)
    assert rows[0]["high_pct"] == 10.0 and rows[0]["low_pct"] == -5.0
    assert rows[0]["ticker"] == "AAA" and rows[0]["scan_date"] == "2026-01-05"


def test_daily_series_last_cum_matches_last_close_formula():
    fwd = _fwd([100, 120, 95], [110, 121, 99], [95, 105, 90],
               ["2026-01-06", "2026-01-07", "2026-01-08"])
    rows = pac.daily_series(fwd, 100.0, date(2026, 1, 5), "AAA")
    assert rows[-1]["cum_pct_from_ref"] == round((95 / 100 - 1) * 100, 2)   # == last_close_pct


def test_daily_series_partial_window_no_fabrication():
    fwd = _fwd([100, 101], [102, 103], [99, 100], ["2026-01-06", "2026-01-07"])
    rows = pac.daily_series(fwd, 100.0, date(2026, 1, 5), "AAA")
    assert len(rows) == 2                       # navail rows only, no D+3..D+20


def test_daily_series_empty_when_no_data_or_no_ref():
    empty = _fwd([], [], [], [])
    assert pac.daily_series(empty, 100.0, date(2026, 1, 5), "AAA") == []
    fwd = _fwd([100], [101], [99], ["2026-01-06"])
    assert pac.daily_series(fwd, 0, date(2026, 1, 5), "AAA") == []


# ── config tab/header exist ───────────────────────────────────────────────────
def test_forward_daily_config_present():
    assert config.TAB_FORWARD_DAILY == "forward_daily"
    for c in ("scan_date", "ticker", "day_offset", "date", "close",
              "cum_pct_from_ref", "daily_change_pct"):
        assert c in config.FORWARD_DAILY_HEADER


# ── (e) REGRESSION: compute_outcome unchanged aggregates + additive _daily ─────
class _FakeTicker:
    def __init__(self, df):
        self._df = df

    def history(self, start, end, auto_adjust):
        return self._df


def test_compute_outcome_additive_daily_does_not_change_aggregates(monkeypatch):
    df = pd.DataFrame(
        {"Open": [98, 100, 100, 120, 95], "High": [99, 101, 110, 121, 99],
         "Low": [97, 99, 95, 105, 90], "Close": [98, 100, 100, 120, 95],
         "Stock Splits": [0, 0, 0, 0, 0]},
        index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06",
                              "2026-01-07", "2026-01-08"]))
    monkeypatch.setattr(pac.yf, "Ticker", lambda t: _FakeTicker(df))
    out = pac.compute_outcome("AAA", date(2026, 1, 5), ref_close=100.0)

    # additive key present, length == navail (3 forward rows)
    assert "_daily_rows" in out and len(out["_daily_rows"]) == 3
    # aggregates computed from fwd are unchanged (independent expectation)
    assert out["forward_days_available"] == 3
    assert out["last_close_pct"] == -5.0                       # (95/100-1)*100
    assert out["max_recovery_pct"] == round((121 / 100 - 1) * 100, 2)   # 21.0
    assert out["max_further_drop_pct"] == round((90 / 100 - 1) * 100, 2)  # -10.0
    # post write is unaffected: every non-_daily key belongs to the post HEADER
    assert set(out) - {"_daily_rows"} <= set(pac.HEADER)


# ── idempotency: forward_daily upsert keyed (scan_date,ticker,day_offset) ──────
class _FakeWS:
    def __init__(self):
        self.values = []

    def get_all_values(self):
        # gspread returns every cell as a string — mirror that for key fidelity
        return [[str(c) for c in r] for r in self.values]

    def update(self, range_name=None, values=None):
        self.values = [list(r) for r in values]

    def clear(self):
        self.values = []


class _FakeSS:
    def __init__(self, ws):
        self._ws = ws

    def worksheet(self, t):
        return self._ws

    def add_worksheet(self, title, rows, cols):
        return self._ws


def test_forward_daily_upsert_idempotent(monkeypatch):
    import sheets_manager as sm
    ws = _FakeWS()
    monkeypatch.setattr(sm, "get_client", lambda: type("C", (), {"_ss": _FakeSS(ws),
                        "open_by_key": lambda self, k: self._ss})())
    rows = [{"scan_date": "2026-01-05", "ticker": "AAA", "day_offset": i,
             "close": 100 + i} for i in (1, 2, 3)]
    sm.upsert_by_key(config.SHEET_ID, config.TAB_FORWARD_DAILY,
                     config.FORWARD_DAILY_HEADER, rows, ["scan_date", "ticker", "day_offset"])
    sm.upsert_by_key(config.SHEET_ID, config.TAB_FORWARD_DAILY,
                     config.FORWARD_DAILY_HEADER, rows, ["scan_date", "ticker", "day_offset"])
    data = ws.get_all_values()[1:]              # minus header
    assert len(data) == 3, f"idempotency broken: {len(data)} rows after 2 identical upserts"
