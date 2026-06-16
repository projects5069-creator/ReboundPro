"""TDD for auto-wiring forward_daily into the normal post run.

The normal (no-flag, auto-EOD) run must write BOTH post_analysis AND forward_daily,
with post written FIRST and forward_daily second and ISOLATED: a forward_daily
write failure must NOT bring down the run (post is already written).
"""
import sys
from datetime import date

import pandas as pd
import pytest

import config
import post_analysis_collector as pac
import sheets_manager as sm

_WATCH_HEADER = ["scan_date", "ticker", "price"]
_WATCH_DATA = [["2026-01-05", "AAA", "100"]]
_CANNED = pd.DataFrame(
    {"Open": [98, 100, 100, 120, 95], "High": [99, 101, 110, 121, 99],
     "Low": [97, 99, 95, 105, 90], "Close": [98, 100, 100, 120, 95],
     "Stock Splits": [0, 0, 0, 0, 0]},
    index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06",
                          "2026-01-07", "2026-01-08"]))


class _FakeTicker:
    def __init__(self, t):
        pass

    def history(self, start, end, auto_adjust):
        return _CANNED


@pytest.fixture
def calls(monkeypatch):
    monkeypatch.setattr(config, "SHEET_ID", "TEST")
    monkeypatch.setattr(pac.yf, "Ticker", _FakeTicker)
    monkeypatch.setattr(sm, "read_rows",
                        lambda sid, tab: (_WATCH_HEADER, [list(r) for r in _WATCH_DATA]))
    c = {"post": 0, "fd": 0, "fd_rows": None}

    def fake_post(sid, tab, header, matrix, date_col="scan_date"):
        c["post"] += 1
        return (0, len(matrix))

    def fake_fd(sid, tab, header, rows, key_cols):
        c["fd"] += 1
        c["fd_rows"] = rows
        return (0, len(rows), len(rows))

    monkeypatch.setattr(sm, "upsert_rows", fake_post)
    monkeypatch.setattr(sm, "upsert_by_key", fake_fd)
    return c


# (א) normal run writes BOTH
def test_normal_run_writes_post_and_forward_daily(calls, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["post_analysis_collector.py"])
    pac.main()
    assert calls["post"] == 1, "post_analysis not written"
    assert calls["fd"] == 1, "forward_daily NOT written on a normal run (auto-wiring missing)"
    assert calls["fd_rows"] and len(calls["fd_rows"]) == 3, "forward_daily rows wrong"


# (ב) CRITICAL isolation: forward_daily failure must NOT break post / crash the run
def test_forward_daily_failure_does_not_break_post(calls, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["post_analysis_collector.py"])

    def boom(sid, tab, header, rows, key_cols):
        calls["fd"] += 1
        raise RuntimeError("forward_daily write boom")

    monkeypatch.setattr(sm, "upsert_by_key", boom)
    pac.main()   # must NOT raise
    assert calls["post"] == 1, "post must be written even when forward_daily write fails"
    assert calls["fd"] == 1, "forward_daily write should have been attempted"


# (ג) --backfill-daily still writes ONLY forward_daily (behavior preserved)
def test_backfill_daily_writes_only_forward_daily(calls, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["post_analysis_collector.py", "--backfill-daily"])
    pac.main()
    assert calls["fd"] == 1 and calls["post"] == 0, "backfill-daily must write only forward_daily"
