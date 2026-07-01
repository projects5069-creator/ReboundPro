"""TDD: scanner.backfill_intraday_prior_context — the once-a-day EOD fill for
source="intraday" rows must populate the FULL context set (the 4 prior-decline
fields it already fills PLUS vix_level / drop_day_rel_volume / sector_momentum_5d
/ sector_momentum_20d), by delegating to scanner._context_for_row.

ROOT 2 fix (intraday context empty since 2026-06-15). Forward-only: scoped to
the passed scan_date's intraday rows — never a cross-date historical sweep.
Point-in-time: every value computed from bars <= scan_date. Partial upsert:
only the context columns are written (merge-by-name preserves all others —
this is the $LILKV contract).
"""
from datetime import date

import pandas as pd
import pytest

import config
import scanner
import sheets_manager as sm

SCAN = date(2026, 7, 1)
CONTEXT = set(scanner.CONTEXT_FIELDS)          # the 8 fields this backfill owns
SIGNALS = {"vix_level", "drop_day_rel_volume",
           "sector_momentum_5d", "sector_momentum_20d"}   # the 3(+1) newly-added
DECLINE = {"pct_from_52w_high", "pct_from_52w_low",
           "prior_decline_20d_pct", "prior_decline_60d_pct"}

WH = ["scan_date", "ticker", "source", "sector", "company_name", "price",
      "prior_decline_20d_pct", "prior_decline_60d_pct",
      "pct_from_52w_high", "pct_from_52w_low",
      "vix_level", "drop_day_rel_volume",
      "sector_momentum_5d", "sector_momentum_20d"]


def _row(scan_date, ticker, source, sector="Technology", name="ACME Corp",
         price="90", prior20=""):
    d = {"scan_date": scan_date, "ticker": ticker, "source": source,
         "sector": sector, "company_name": name, "price": price,
         "prior_decline_20d_pct": prior20}
    return [d.get(c, "") for c in WH]


class _FakeTicker:
    """Flat 260-bar history ending on scan_date (Close=100, High=101, Vol=2M).
    Used for ^VIX and the sector ETF too (yf.Ticker is patched globally)."""
    def history(self, start, end, auto_adjust):
        sd = pd.Timestamp(end) - pd.Timedelta(days=1)      # = scan_date
        idx = pd.bdate_range(end=sd, periods=260)
        n = len(idx)
        return pd.DataFrame({"Open": [100.0] * n, "High": [101.0] * n,
                             "Low": [99.0] * n, "Close": [100.0] * n,
                             "Volume": [2_000_000] * n}, index=idx)


class _FakeTickerFuture(_FakeTicker):
    """Appends a wild bar STRICTLY AFTER scan_date — must be excluded (PIT)."""
    def history(self, start, end, auto_adjust):
        df = super().history(start, end, auto_adjust)
        future_day = df.index[-1] + pd.Timedelta(days=1)
        fut = pd.DataFrame({"Open": [9e4], "High": [9e4], "Low": [9e4],
                            "Close": [9e4], "Volume": [9]}, index=[future_day])
        return pd.concat([df, fut])


@pytest.fixture(autouse=True)
def _clear_caches():
    """vix_close / etf_momentum / etf_change memoize in a default-arg dict —
    clear between tests so a prior scan_date value never leaks."""
    for fn in (scanner.vix_close, scanner.etf_momentum, scanner.etf_change):
        fn.__defaults__[0].clear()
    yield


def _patch(monkeypatch, wd, ticker_cls=_FakeTicker):
    captured = []
    monkeypatch.setattr(sm, "read_rows", lambda sid, tab: (WH, [list(r) for r in wd]))
    monkeypatch.setattr(sm, "upsert_by_key",
                        lambda sid, tab, hdr, rows, keys: captured.append(rows) or (0, len(rows), len(rows)))
    monkeypatch.setattr(scanner.yf, "Ticker", lambda t: ticker_cls())
    monkeypatch.setattr(scanner.time, "sleep", lambda *_: None)
    return captured


# 1 — the fix: intraday row gains the 3(+1) context signals, non-empty
def test_intraday_row_gets_context_signals(monkeypatch):
    cap = _patch(monkeypatch, [_row("2026-07-01", "AAA", "intraday")])
    scanner.backfill_intraday_prior_context(SCAN)
    row = {r["ticker"]: r for r in cap[0]}["AAA"]
    for f in SIGNALS:
        assert row[f] not in ("", None), f"{f} still empty"


# 2 — regression: the 4 prior-decline fields stay IDENTICAL to prior_context()
def test_prior_decline_fields_unchanged(monkeypatch):
    cap = _patch(monkeypatch, [_row("2026-07-01", "AAA", "intraday")])
    scanner.backfill_intraday_prior_context(SCAN)
    row = {r["ticker"]: r for r in cap[0]}["AAA"]
    # recompute what prior_context alone would have produced on the same history
    h = _FakeTicker().history(start=None, end=str(SCAN + pd.Timedelta(days=1)), auto_adjust=True)
    h = h[h.index.date <= SCAN]
    prior = h[h.index.date < SCAN]
    expected = scanner.prior_context(h, prior, float(h["Close"].iloc[-1]))
    for f in DECLINE:
        assert row[f] == expected[f], f"{f} regressed: {row[f]} != {expected[f]}"


# 3 — forward-only: a PAST-date intraday row is out of scope, untouched
def test_forward_only_past_date_not_touched(monkeypatch):
    wd = [_row("2026-06-20", "OLD", "intraday"),
          _row("2026-07-01", "NEW", "intraday")]
    cap = _patch(monkeypatch, wd)
    scanner.backfill_intraday_prior_context(SCAN)
    tickers = {r["ticker"] for r in cap[0]}
    assert tickers == {"NEW"}, f"historical row leaked: {tickers}"


# 4 — PIT: bars after scan_date are excluded (no look-ahead)
def test_pit_excludes_future_bars(monkeypatch):
    cap = _patch(monkeypatch, [_row("2026-07-01", "AAA", "intraday")],
                 ticker_cls=_FakeTickerFuture)
    scanner.backfill_intraday_prior_context(SCAN)
    row = {r["ticker"]: r for r in cap[0]}["AAA"]
    assert row["vix_level"] == 100.0                       # scan_date close, not 9e4
    assert row["pct_from_52w_high"] == round((100 - 101) / 101 * 100, 2)  # not dominated by 9e4


# 5 — scope: eod_close / gradual rows are never in scope (only source=="intraday")
def test_non_intraday_sources_out_of_scope(monkeypatch):
    wd = [_row("2026-07-01", "EOD", "eod_close"),
          _row("2026-07-01", "GRAD", "gradual_eod"),
          _row("2026-07-01", "INTRA", "intraday")]
    cap = _patch(monkeypatch, wd)
    scanner.backfill_intraday_prior_context(SCAN)
    assert {r["ticker"] for r in cap[0]} == {"INTRA"}


# 6 — graceful degradation: blank sector → signals still fill, sector_momentum empty, no crash
def test_blank_sector_degrades_gracefully(monkeypatch):
    cap = _patch(monkeypatch, [_row("2026-07-01", "AAA", "intraday", sector="")])
    scanner.backfill_intraday_prior_context(SCAN)
    row = {r["ticker"]: r for r in cap[0]}["AAA"]
    assert row["vix_level"] not in ("", None)
    assert row["drop_day_rel_volume"] not in ("", None)
    assert row["sector_momentum_5d"] in ("", None)         # no ETF → no momentum


# 7 — $LILKV contract lock: partial payload = ONLY {scan_date,ticker}+context; no other columns
def test_payload_is_only_context_columns(monkeypatch):
    cap = _patch(monkeypatch, [_row("2026-07-01", "AAA", "intraday",
                                    name="ACME Corp", price="90")])
    scanner.backfill_intraday_prior_context(SCAN)
    keys = set(cap[0][0].keys())
    assert keys == {"scan_date", "ticker"} | CONTEXT
    # non-context columns must NOT appear (merge-by-name preserves them on the sheet)
    assert not (keys & {"source", "sector", "company_name", "price"})
