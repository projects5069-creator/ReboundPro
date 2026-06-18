"""TDD — scanner-freshness + volume-anomaly refinements (precondition for H3).

Root cause of the recurring benign WARNs: the intraday scanner writes
scan_date=today on the first same-day capture, but expected_last_scan_date()
steps back to the previous session until 18:30 ET. So in the pre-EOD window the
watchlist "leads" the expectation (scanner-freshness WARN) and today's partial
intraday-only cohort looks anomalously thin (volume-anomaly WARN).

Refinements:
  1. scanner-freshness: last == today (a session) AND now < 18:30 ET -> OK/CALM
     (intraday legitimately ahead). The last < expected branch (FAIL = EOD did
     not run) MUST stay intact. last > today (a real future date) stays WARN.
  2. volume-anomaly: evaluate COMPLETED sessions only (scan_date <= exp_last),
     so the still-open current session is never compared to a full-day average.

Tests are hermetic: `now` is injected into run_checks (no live clock).
Calendar dates chosen are real XNYS sessions (2026-06-15..18 are Mon-Thu;
Juneteenth 06-19 is a holiday, deliberately avoided as a "session" date).
"""
from datetime import datetime

import pytz
import exchange_calendars as ec

import config
import health_monitor as hm

ET = pytz.timezone("America/New_York")
CAL = ec.get_calendar("XNYS")
WL_HEADER = ["scan_date", "ticker", "source"]


def _data(watch_rows):
    """run_checks `data` dict: watchlist populated, every other accessed tab empty."""
    d = {t: ([], []) for t in hm.EXPECTED_HEADERS}
    d[config.TAB_WATCHLIST] = (WL_HEADER, watch_rows)
    return d


def _now(y, mo, da, h, mi=0):
    return ET.localize(datetime(y, mo, da, h, mi))


def _finding(m, cid):
    return next(f for f in m.findings if f["id"] == cid)


def _rows(date_counts, source="eod_close"):
    out = []
    for d, n in date_counts:
        out += [[d, f"T{d}_{i}", source] for i in range(n)]
    return out


# ── scanner-freshness ─────────────────────────────────────────────────────────
def test_scanner_freshness_intraday_ahead_is_calm_not_warn():
    # today 06-18 (session), 15:00 ET (pre-EOD) -> exp_last steps back to 06-17.
    # watchlist already has today's scan_date from intraday -> legitimate, not WARN.
    m, _ = hm.run_checks(_data([["2026-06-18", "AAA", "intraday"]]), _now(2026, 6, 18, 15), CAL)
    f = _finding(m, "scanner-freshness")
    assert f["status"] == hm.OK, f"expected OK/CALM, got {f['status']}: {f['msg']}"
    assert f.get("icon") == hm.CALM_ICON


def test_scanner_freshness_eod_missing_still_fails():
    # 06-18 19:00 ET (>18:30) -> exp_last=06-18; last scan=06-17 < expected -> FAIL.
    # Guards the "EOD did not run" branch against the refinement.
    m, _ = hm.run_checks(_data([["2026-06-17", "AAA", "eod_close"]]), _now(2026, 6, 18, 19), CAL)
    assert _finding(m, "scanner-freshness")["status"] == hm.FAIL


def test_scanner_freshness_future_date_warns():
    # last scan 06-19 > today 06-18 and != today -> genuine clock/calendar bug -> WARN.
    m, _ = hm.run_checks(_data([["2026-06-19", "AAA", "eod_close"]]), _now(2026, 6, 18, 15), CAL)
    assert _finding(m, "scanner-freshness")["status"] == hm.WARN


# ── volume-anomaly ────────────────────────────────────────────────────────────
def test_volume_anomaly_ignores_open_session():
    # 3 full completed days (~30 each) + today's open intraday cohort (1 row).
    # Pre-EOD (15:00) -> exp_last=06-17; the open 06-18 partial must be excluded.
    rows = _rows([("2026-06-15", 30), ("2026-06-16", 30), ("2026-06-17", 30)])
    rows += [["2026-06-18", "OPEN1", "intraday"]]
    m, _ = hm.run_checks(_data(rows), _now(2026, 6, 18, 15), CAL)
    assert _finding(m, "volume-anomaly")["status"] == hm.OK


def test_volume_anomaly_still_flags_real_anomaly_on_completed_day():
    # A genuinely anomalous COMPLETED last day (1 vs history ~30) still warns.
    rows = _rows([("2026-06-15", 30), ("2026-06-16", 30), ("2026-06-17", 1)])
    m, _ = hm.run_checks(_data(rows), _now(2026, 6, 18, 19), CAL)
    assert _finding(m, "volume-anomaly")["status"] == hm.WARN
