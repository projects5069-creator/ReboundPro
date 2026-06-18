"""P2 — first test coverage for gradual_scanner.py (was zero).

Covers the core logic: the -10%/D-5 threshold (boundary), the hard liquidity
floor, the gradual_drop/gradual_eod tagging, the dedup helper, and — most
important — a regression lock that the dedup SKIPS a ticker already captured as
intraday_drop, so gradual never overwrites an existing intraday row (the
"anti-clobber" guarantee is structural, via recent_capture_set, not new code).

Hermetic: real XNYS calendar + fixed dates; yfinance / Finviz / Sheet are mocked.
"""
from datetime import date

import pandas as pd
import exchange_calendars as ec

import config
import scanner as sc
import sheets_manager
import gradual_scanner as gs

CAL = ec.get_calendar("XNYS")
SCAN = date(2026, 6, 17)
REF = date(2026, 6, 10)            # 5 trading days before 06-17
HIST_DATES = ["2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11",
              "2026-06-12", "2026-06-15", "2026-06-16", "2026-06-17"]


class _FakeTicker:
    def __init__(self, df):
        self._df = df

    def history(self, start, end, auto_adjust):
        return self._df


def _hist(today_close, vol=1_000_000):
    # ref (06-10) close = 100; every other day = 100; today (06-17) = today_close.
    closes = [100.0] * len(HIST_DATES)
    closes[-1] = today_close
    return pd.DataFrame(
        {"Open": closes, "High": [c * 1.01 for c in closes],
         "Low": [c * 0.99 for c in closes], "Close": closes,
         "Volume": [vol] * len(HIST_DATES)},
        index=pd.to_datetime(HIST_DATES))


def _row(price="50.00", cap="1.00B", ticker="AAA"):
    return {"Ticker": ticker, "Price": price, "Market Cap": cap, "Sector": "",
            "Company": "A Co", "Industry": "", "Country": "USA", "_exchange": "NASDAQ"}


def _snap(monkeypatch, today_close, vol=1_000_000, **rowkw):
    monkeypatch.setattr(gs.yf, "Ticker", lambda t: _FakeTicker(_hist(today_close, vol)))
    return gs.build_snapshot(_row(**rowkw), SCAN, REF, spy_chg=-0.5, vix=20.0,
                             now="2026-06-17 18:00:00 EDT")


# ── T1: recent_capture_set (pure) ─────────────────────────────────────────────
def test_recent_capture_set_within_outside_and_empty():
    wh = ["scan_date", "ticker", "drop_kind"]
    wd = [["2026-06-16", "DUP", "intraday_drop"],   # within 20 td of 06-17
          ["2026-01-02", "OLD", "gradual_drop"]]     # far outside the window
    recent = gs.recent_capture_set(wh, wd, SCAN, CAL)
    assert "DUP" in recent
    assert "OLD" not in recent
    # empty rows / missing columns -> empty set (no dedup possible)
    assert gs.recent_capture_set(wh, [], SCAN, CAL) == set()
    assert gs.recent_capture_set(["foo"], [["x"]], SCAN, CAL) == set()


# ── T2: ref_trading_date (pure) ───────────────────────────────────────────────
def test_ref_trading_date_is_five_sessions_back():
    assert gs.ref_trading_date(SCAN, CAL) == REF


# ── T3: -10% threshold boundary ───────────────────────────────────────────────
def test_threshold_exactly_minus_10_passes(monkeypatch):
    snap, why = _snap(monkeypatch, 90.0)            # (90/100 - 1)*100 == -10.00
    assert why == "ok" and snap is not None
    assert snap["drop_pct_window"] == -10.0


def test_threshold_minus_9_9_rejected(monkeypatch):
    snap, why = _snap(monkeypatch, 90.1)            # -9.9 > -10 -> rejected
    assert snap is None and why == "drop_below_threshold"


# ── T4: hard liquidity floor ──────────────────────────────────────────────────
def test_floor_price_below_min(monkeypatch):
    snap, why = _snap(monkeypatch, 90.0, price="3.00")   # < MIN_PRICE (5)
    assert snap is None and why == "below_min_price"


def test_floor_market_cap_below_min(monkeypatch):
    snap, why = _snap(monkeypatch, 90.0, cap="100.00M")  # < MIN_MARKET_CAP (300M)
    assert snap is None and why == "below_min_cap"


def test_floor_adv_dollar_below_min(monkeypatch):
    snap, why = _snap(monkeypatch, 90.0, vol=100)        # adv = 100*90 = 9k < 5M
    assert snap is None and why == "below_min_adv"


# ── T5: tagging ───────────────────────────────────────────────────────────────
def test_passing_candidate_tagged_gradual(monkeypatch):
    snap, why = _snap(monkeypatch, 90.0)
    assert why == "ok"
    assert snap["drop_kind"] == "gradual_drop"
    assert snap["source"] == "gradual_eod"
    assert snap["lookback_trading_days"] == config.GRADUAL_LOOKBACK_DAYS
    assert snap["drop_pct_from_open"] == ""


# ── T6: anti-clobber — dedup skips a ticker already captured as intraday ───────
def test_scan_dedup_skips_existing_intraday_no_overwrite(monkeypatch):
    # watchlist already holds DUP as intraday_drop, scanned within the dedup window
    wl_header = ["scan_date", "ticker", "source", "drop_kind", "price"]
    wl_rows = [["2026-06-16", "DUP", "intraday", "intraday_drop", "50"]]
    monkeypatch.setattr(sheets_manager, "read_rows", lambda sid, tab: (wl_header, wl_rows))
    monkeypatch.setattr(gs, "get_candidates",
                        lambda: pd.DataFrame([{"Ticker": "DUP", "Price": "50",
                                               "Market Cap": "1.00B", "Sector": ""}]))
    monkeypatch.setattr(gs.sc, "day_change_pct", lambda *a, **k: -0.5)
    monkeypatch.setattr(gs.sc, "vix_close", lambda *a, **k: 20.0)
    called = []
    monkeypatch.setattr(gs, "build_snapshot",
                        lambda row, *a, **k: (called.append(str(row.get("Ticker")).upper()) or (None, "rec")))

    rows, reasons = gs.scan(SCAN)

    assert rows == []                          # gradual produced no row for DUP
    assert reasons.get("dedup_recent") == 1    # it was skipped by the dedup
    assert "DUP" not in called                 # build_snapshot never ran for it -> no overwrite
