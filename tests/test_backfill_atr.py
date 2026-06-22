"""TDD: scanner._drop_dollars_for_kind — pick the $-drop numerator matching the
row's drop_kind, from STORED watchlist fields (used by the one-off atr backfill).
intraday/legacy: open - low_so_far ; gradual: ref_close_window - price."""
import scanner


def test_intraday_uses_open_minus_low():
    assert scanner._drop_dollars_for_kind("intraday_drop", open_=100.0, low_so_far=90.0,
                                          ref_close_window=None, price=None) == 10.0


def test_legacy_blank_kind_treated_as_intraday():
    assert scanner._drop_dollars_for_kind("", open_=100.0, low_so_far=90.0,
                                          ref_close_window=None, price=None) == 10.0


def test_gradual_uses_refwindow_minus_price():
    assert scanner._drop_dollars_for_kind("gradual_drop", open_=None, low_so_far=None,
                                          ref_close_window=100.0, price=85.0) == 15.0


def test_missing_inputs_return_none():
    assert scanner._drop_dollars_for_kind("intraday_drop", None, 90.0, None, None) is None
    assert scanner._drop_dollars_for_kind("gradual_drop", None, None, 100.0, None) is None


# ── integration: backfill_atr orchestration (mock sheets + yfinance) ──────────
import pandas as pd
import sheets_manager


class _FakeTicker:
    def __init__(self, df): self._df = df
    def history(self, start, end, auto_adjust): return self._df


def _atr2_history():
    # 20 bars, TR=2 every day → Wilder ATR(14) = 2.0
    idx = pd.date_range("2026-01-01", periods=20, freq="D")
    return pd.DataFrame({"Open": [100.0] * 20, "High": [101.0] * 20,
                         "Low": [99.0] * 20, "Close": [100.0] * 20}, index=idx)


HDR = ["scan_date", "ticker", "open", "low_so_far", "price", "ref_close_window",
       "drop_kind", "atr_14", "drop_in_atr"]
ROWS = [
    ["2026-01-20", "AAA", "100", "90", "92", "", "intraday_drop", "", ""],   # compute
    ["2026-01-20", "BBB", "50", "45", "46", "", "intraday_drop", "3.0", "2.0"],  # skip (has atr)
    ["2026-01-21", "CCC", "", "", "85", "100", "gradual_drop", "", ""],       # compute (window)
]


def _patch(monkeypatch, captured):
    monkeypatch.setattr(sheets_manager, "read_rows", lambda sid, tab: (HDR, [list(r) for r in ROWS]))
    monkeypatch.setattr(sheets_manager, "upsert_by_key",
                        lambda sid, tab, hdr, rows, keys: captured.append(rows) or (0, len(rows), len(rows)))
    monkeypatch.setattr(scanner.yf, "Ticker", lambda t: _FakeTicker(_atr2_history()))
    monkeypatch.setattr(scanner.time, "sleep", lambda *_: None)


def test_backfill_atr_computes_by_kind_and_skips_existing(monkeypatch):
    captured = []
    _patch(monkeypatch, captured)
    out, n = scanner.backfill_atr(dry_run=False)
    assert n == 2                                   # AAA + CCC missing atr; BBB skipped
    by = {r["ticker"]: r for r in out}
    assert set(by) == {"AAA", "CCC"}
    assert by["AAA"]["atr_14"] == 2.0 and by["AAA"]["drop_in_atr"] == 5.0   # (100-90)/2
    assert by["CCC"]["atr_14"] == 2.0 and by["CCC"]["drop_in_atr"] == 7.5   # (100-85)/2
    assert captured and captured[0] == out          # upsert called with computed rows


def test_backfill_atr_dry_run_does_not_write(monkeypatch):
    captured = []
    _patch(monkeypatch, captured)
    out, n = scanner.backfill_atr(dry_run=True)
    assert n == 2 and len(out) == 2
    assert captured == []                            # no upsert in dry-run
