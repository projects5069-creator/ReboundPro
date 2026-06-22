"""TDD: post_analysis_collector reclaim/drop grid (descriptive forward-window
labels — M5 safe). Day-or-blank, separate column per threshold.
 - up%   grid: first D+n where forward High >= +thr% of ref_close
 - down% grid: first D+n where forward Low  <= -thr% of ref_close
 - ATR-from-trough grid: first D+n (>= trough day) where (High - trough)/ATR >= thr
ATR is supplied by the caller (watchlist atr_14) — never recomputed here."""
from datetime import date
import pandas as pd
import post_analysis_collector as pac

SCAN = date(2026, 6, 1)


class _FakeTicker:
    def __init__(self, df): self._df = df
    def history(self, start, end, auto_adjust): return self._df


def _frame(rows):
    # rows: list of (date_str, open, high, low, close)
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {"Open": [r[1] for r in rows], "High": [r[2] for r in rows],
         "Low": [r[3] for r in rows], "Close": [r[4] for r in rows]}, index=idx)


def test_up_and_down_pct_grid_days(monkeypatch):
    f = _frame([
        ("2026-06-01", 100, 100, 100, 100),     # scan day (ref=100)
        ("2026-06-02", 100, 102.0, 99.0, 100),  # D+1: +2% / -1%
        ("2026-06-03", 100, 103.5, 97.0, 100),  # D+2: +3% / -3%
        ("2026-06-04", 100, 108.5, 91.0, 100),  # D+3: +8% / -9%
    ])
    monkeypatch.setattr(pac.yf, "Ticker", lambda t: _FakeTicker(f))
    out = pac.compute_outcome("AAA", SCAN, ref_close=100.0, atr=2.0)
    assert out["up_reach_day_1pct"] == 1
    assert out["up_reach_day_2pct"] == 1
    assert out["up_reach_day_3pct"] == 2
    assert out["up_reach_day_5pct"] == 3
    assert out["up_reach_day_8pct"] == 3
    assert out["down_reach_day_1pct"] == 1
    assert out["down_reach_day_2pct"] == 2
    assert out["down_reach_day_3pct"] == 2
    assert out["down_reach_day_5pct"] == 3
    assert out["down_reach_day_8pct"] == 3


def test_atr_from_trough_grid_days(monkeypatch):
    # trough is a doji at 90 on D+1 (no intraday bounce), then highs rise 91/92/93.
    f = _frame([
        ("2026-06-01", 100, 100, 100, 100),   # scan day
        ("2026-06-02", 90, 90, 90, 90),        # D+1 trough = 90
        ("2026-06-03", 90, 91, 90, 91),        # D+2: (91-90)/2 = 0.5 ATR
        ("2026-06-04", 90, 92, 90, 92),        # D+3: 1.0 ATR
        ("2026-06-05", 90, 93, 90, 93),        # D+4: 1.5 ATR
    ])
    monkeypatch.setattr(pac.yf, "Ticker", lambda t: _FakeTicker(f))
    out = pac.compute_outcome("AAA", SCAN, ref_close=100.0, atr=2.0)
    assert out["reclaim_atr_day_0_5x"] == 2
    assert out["reclaim_atr_day_1x"] == 3
    assert out["reclaim_atr_day_1_5x"] == 4


def test_atr_grid_excludes_intraday_reversal_on_trough_day(monkeypatch):
    # Trough day (D+1) has a big intraday bounce (High 96 vs Low 90 = 3 ATRs), but
    # later days stay flat at the low. Reclaim is a CONFIRMATION-TIMING feature, so
    # the trough day's own intraday spike must NOT count → all blank.
    f = _frame([
        ("2026-06-01", 100, 100, 100, 100),
        ("2026-06-02", 90, 96, 90, 90),        # D+1 trough Low=90, intraday High=96
        ("2026-06-03", 90, 90, 90, 90),        # D+2 flat at low
        ("2026-06-04", 90, 90, 90, 90),        # D+3 flat at low
    ])
    monkeypatch.setattr(pac.yf, "Ticker", lambda t: _FakeTicker(f))
    out = pac.compute_outcome("AAA", SCAN, ref_close=100.0, atr=2.0)
    assert out["reclaim_atr_day_0_5x"] == ""
    assert out["reclaim_atr_day_1x"] == ""
    assert out["reclaim_atr_day_1_5x"] == ""


def test_atr_grid_blank_when_no_atr(monkeypatch):
    f = _frame([
        ("2026-06-01", 100, 100, 100, 100),
        ("2026-06-02", 90, 95, 90, 95),
    ])
    monkeypatch.setattr(pac.yf, "Ticker", lambda t: _FakeTicker(f))
    out = pac.compute_outcome("AAA", SCAN, ref_close=100.0, atr=None)
    assert out["reclaim_atr_day_0_5x"] == ""
    assert out["reclaim_atr_day_1x"] == ""
    assert out["reclaim_atr_day_1_5x"] == ""
