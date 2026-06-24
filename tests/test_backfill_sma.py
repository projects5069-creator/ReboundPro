"""TDD: scanner.backfill_sma_metrics — one-time backfill of atr_pct, dist_sma50,
dist_sma200 for existing watchlist rows. Mirrors tests/test_backfill_atr.py.

Locks two requirements:
- atr_pct FULL COVERAGE: a row whose atr_14 is BLANK (old source=intraday row)
  still gets atr_pct — atr_14 is recomputed from `prior` (point-in-time) and
  atr_pct derived from it. No source-correlated gap.
- split_halt_flag events are SKIPPED (split-adjusted history biases their SMA;
  excluded from analysis anyway) and counted.
"""
import pandas as pd

import config
import scanner
import sheets_manager as sm

WH = ["scan_date", "ticker", "source", "drop_kind", "price", "atr_14",
      "atr_pct", "dist_sma50", "dist_sma200"]
WD = [
    # old intraday row — atr_14 BLANK → atr_pct must still be filled (recomputed)
    ["2026-01-20", "AAA", "intraday", "intraday_drop", "90", "", "", "", ""],
    # eod row — atr_pct derived from the EXISTING atr_14=2.0
    ["2026-01-20", "BBB", "eod_close", "intraday_drop", "90", "2.0", "", "", ""],
    # gradual row
    ["2026-01-21", "CCC", "gradual_eod", "gradual_drop", "90", "2.0", "", "", ""],
    # contaminated row — split_halt_flag → SKIPPED
    ["2026-01-22", "DDD", "eod_close", "intraday_drop", "90", "2.0", "", "", ""],
]
PH = ["scan_date", "ticker", "split_halt_flag"]
PD = [["2026-01-22", "DDD", "True"]]


class _FakeTicker:
    def history(self, start, end, auto_adjust):
        sd = pd.Timestamp(end) - pd.Timedelta(days=1)
        idx = pd.bdate_range(end=sd, periods=260)      # >=200 prior bars
        n = len(idx)
        return pd.DataFrame({"Open": [100.0] * n, "High": [101.0] * n, "Low": [99.0] * n,
                             "Close": [100.0] * n, "Volume": [2_000_000] * n}, index=idx)


def _patch(monkeypatch, captured):
    def fake_read(sid, tab):
        return (PH, [list(r) for r in PD]) if tab == config.TAB_POST else (WH, [list(r) for r in WD])
    monkeypatch.setattr(sm, "read_rows", fake_read)
    monkeypatch.setattr(sm, "upsert_by_key",
                        lambda sid, tab, hdr, rows, keys: captured.append(rows) or (0, len(rows), len(rows)))
    monkeypatch.setattr(scanner.yf, "Ticker", lambda t: _FakeTicker())
    monkeypatch.setattr(scanner.time, "sleep", lambda *_: None)


def test_backfill_fills_three_metrics_skips_contaminated(monkeypatch):
    captured = []
    _patch(monkeypatch, captured)
    out, n_targets, counts = scanner.backfill_sma_metrics(dry_run=False)
    by = {r["ticker"]: r for r in out}

    assert set(by) == {"AAA", "BBB", "CCC"}          # DDD skipped (split_halt)
    assert n_targets == 3
    assert counts["split_halt_skipped"] == 1

    # close 90 vs prior SMA 100 → -10 for every row
    assert by["AAA"]["dist_sma50"] == -10.0 and by["AAA"]["dist_sma200"] == -10.0


def test_atr_pct_full_coverage_on_blank_atr_intraday(monkeypatch):
    captured = []
    _patch(monkeypatch, captured)
    out, _, counts = scanner.backfill_sma_metrics(dry_run=False)
    by = {r["ticker"]: r for r in out}

    # AAA had BLANK atr_14 → atr_pct STILL filled (atr recomputed from prior)
    assert by["AAA"]["atr_pct"] not in ("", None)
    # BBB derives atr_pct from existing atr_14=2.0 → 2/90*100
    assert by["BBB"]["atr_pct"] == round(2.0 / 90 * 100, 2)
    # the intraday coverage the user required: atr_pct AND dist_sma200 both counted
    assert counts["atr_pct"]["intraday"] >= 1
    assert counts["dist_sma200"]["intraday"] >= 1


def test_backfill_payload_is_only_three_metrics_plus_keys(monkeypatch):
    captured = []
    _patch(monkeypatch, captured)
    out, _, _ = scanner.backfill_sma_metrics(dry_run=False)
    assert captured and captured[0] == out
    assert set(out[0].keys()) == {"scan_date", "ticker", "atr_pct", "dist_sma50", "dist_sma200"}


def test_dry_run_does_not_write(monkeypatch):
    captured = []
    _patch(monkeypatch, captured)
    out, _, _ = scanner.backfill_sma_metrics(dry_run=True)
    assert out and not captured        # computed, but upsert never called
