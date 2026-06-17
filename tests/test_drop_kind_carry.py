"""TDD for P1 — carry drop_kind + source from watchlist to post_analysis and
forward_daily, migration-safe, with a join-based backfill for EXISTING rows.

CRITICAL: existing rows must NEVER default to intraday_drop — gradual_drop rows
already exist in post/forward, and a blank->intraday_drop default would mislabel
them and corrupt the hypothesis separation. Backfill joins to watchlist on
(scan_date, ticker); a missing match stays "" (unknown), never intraday_drop.
"""
from datetime import date

import pandas as pd

import config
import post_analysis_collector as pac


def _fwd(closes, highs, lows, dates):
    return pd.DataFrame(
        {"Open": closes, "High": highs, "Low": lows, "Close": closes,
         "Stock Splits": [0] * len(closes)},
        index=pd.to_datetime(dates))


class _FakeTicker:
    def __init__(self, df):
        self._df = df

    def history(self, start, end, auto_adjust):
        return self._df


# ── headers carry the new columns (migration-safe additive) ───────────────────
def test_headers_include_drop_kind_and_source():
    assert "drop_kind" in pac.HEADER and "source" in pac.HEADER
    assert "drop_kind" in config.FORWARD_DAILY_HEADER
    assert "source" in config.FORWARD_DAILY_HEADER


# ── (a) NEW rows carry tags from the watchlist event ──────────────────────────
def test_daily_series_carries_drop_kind_and_source():
    fwd = _fwd([100, 120], [110, 121], [95, 105], ["2026-01-06", "2026-01-07"])
    rows = pac.daily_series(fwd, 100.0, date(2026, 1, 5), "AAA",
                            drop_kind="gradual_drop", source="gradual_eod")
    assert rows and all(r["drop_kind"] == "gradual_drop" for r in rows)
    assert all(r["source"] == "gradual_eod" for r in rows)


def test_daily_series_tags_default_blank():
    fwd = _fwd([100], [110], [95], ["2026-01-06"])
    rows = pac.daily_series(fwd, 100.0, date(2026, 1, 5), "AAA")
    assert rows[0]["drop_kind"] == "" and rows[0]["source"] == ""


def test_compute_outcome_carries_tags(monkeypatch):
    df = pd.DataFrame(
        {"Open": [100, 100, 120], "High": [101, 110, 121],
         "Low": [99, 95, 105], "Close": [100, 100, 120],
         "Stock Splits": [0, 0, 0]},
        index=pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]))
    monkeypatch.setattr(pac.yf, "Ticker", lambda t: _FakeTicker(df))
    out = pac.compute_outcome("AAA", date(2026, 1, 5), ref_close=100.0,
                              drop_kind="gradual_drop", source="gradual_eod")
    assert out["drop_kind"] == "gradual_drop" and out["source"] == "gradual_eod"
    assert out["_daily_rows"] and all(
        d["drop_kind"] == "gradual_drop" and d["source"] == "gradual_eod"
        for d in out["_daily_rows"])
    # post write stays valid: every non-_daily key belongs to the post HEADER
    assert set(out) - {"_daily_rows"} <= set(pac.HEADER)


# ── (b) BACKFILL via join — never defaults to intraday_drop ───────────────────
def test_event_tags_exact_or_blank_never_intraday():
    idx = {"scan_date": 0, "ticker": 1, "drop_kind": 2, "source": 3}
    assert pac._event_tags(["2026-06-15", "AAA", "gradual_drop", "gradual_eod"], idx) \
        == ("gradual_drop", "gradual_eod")
    dk, src = pac._event_tags(["2026-06-15", "BBB", "", ""], idx)
    assert dk == "" and src == "" and dk != "intraday_drop"


def test_backfill_tags_existing_gradual_as_gradual_not_intraday():
    # existing post rows under the OLD header (no drop_kind/source columns yet)
    h = ["scan_date", "ticker", "status"]
    rows = [["2026-06-15", "AAA", "partial"],     # gradual in watchlist
            ["2026-06-12", "ZZZ", "partial"]]     # NOT in watchlist -> stays blank
    tagmap = {("2026-06-15", "AAA"): ("gradual_drop", "gradual_eod")}
    out = pac._tag_existing(h, rows, tagmap)
    assert out[0]["drop_kind"] == "gradual_drop" and out[0]["source"] == "gradual_eod"
    # unmatched event -> blank, NEVER intraday_drop
    assert out[1]["drop_kind"] == "" and out[1]["source"] == ""
    assert out[1]["drop_kind"] != "intraday_drop"
