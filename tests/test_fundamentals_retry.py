"""TDD for fundamentals fetch resilience + PIT cross-day invariant (GATE-A).

Finviz BURST-throttles the EOD scrape ('NoneType'...find_all'). It is NOT an IP
block — the intraday scanner gets ~79% from the same Actions IP because it is
low-burst. So the fix is FEWER requests: single attempt (no retry amplification —
retries=4 took 6/26 EOD 50%→0%) + slow pacing. On exhausted failure write NO row
(no poison stub). PIT invariant: a (scan_date,ticker) that failed at its D0 EOD
run is NEVER re-fetched on a later day (current Finviz values on an old D0 =
look-ahead, breaks Group C).
"""
import pytest

import config
import fundamentals as fund


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(fund.time, "sleep", lambda *a, **k: None)


# ── de-burst config intent (locked) ───────────────────────────────────────────
def test_config_is_low_burst():
    assert config.FINVIZ_FETCH_RETRIES <= 2, "retry amplification must stay low (burst-throttle)"
    assert config.FINVIZ_FETCH_SLEEP >= 2.0, "pacing must be slow enough to de-burst Finviz"


# ── no retry-burst ─────────────────────────────────────────────────────────────
def test_no_retry_burst_on_failure(monkeypatch):
    calls = {"n": 0}

    def always_fail(tk):
        calls["n"] += 1
        raise AttributeError("'NoneType' object has no attribute 'find_all'")

    monkeypatch.setattr(fund, "fetch", always_fail)
    rows = fund.collect([("2026-06-26", "BUST")])
    assert rows == []                                  # no poison stub
    assert calls["n"] == config.FINVIZ_FETCH_RETRIES   # exactly N attempts — NO amplification
    assert calls["n"] <= 2                             # and that N is small


def test_success_writes_row(monkeypatch):
    monkeypatch.setattr(fund, "fetch", lambda tk: {"Company": "ACME"})
    rows = fund.collect([("2026-06-26", "ACME")])
    assert len(rows) == 1 and rows[0]["ticker"] == "ACME"


# ── per-RUN time budget (not per-call) ─────────────────────────────────────────
def test_per_run_budget_stops_early(monkeypatch):
    # pretend the process started long ago → elapsed >> budget → stop on first item
    monkeypatch.setattr(fund, "_PROCESS_START", fund.time.monotonic() - 10_000)
    monkeypatch.setattr(fund, "fetch", lambda tk: {"Company": tk})
    rows = fund.collect([("2026-06-26", "A"), ("2026-06-26", "B")])
    assert rows == []                                  # per-run budget already blown


def test_budget_is_per_run_across_calls(monkeypatch):
    # the budget spans the whole process: a 2nd collect() in the same run also stops
    monkeypatch.setattr(fund, "_PROCESS_START", fund.time.monotonic() - 10_000)
    monkeypatch.setattr(fund, "fetch", lambda tk: {"Company": tk})
    assert fund.collect([("2026-06-26", "A")]) == []
    assert fund.collect([("2026-06-26", "B")]) == []   # not reset per-call


# ── PIT cross-day invariant ─────────────────────────────────────────────────────
def test_selection_is_single_date_no_cross_date_sweep():
    header = ["scan_date", "ticker"]
    rows = [["2026-06-17", "OLD"], ["2026-06-26", "NEW"], ["2026-06-26", "NEW2"]]
    pairs = fund.select_target_pairs(rows, header, "2026-06-26")
    assert ("2026-06-17", "OLD") not in pairs          # past date NOT swept up
    assert ("2026-06-26", "NEW") in pairs and ("2026-06-26", "NEW2") in pairs


def test_pit_guard_refuses_past_date_without_force():
    assert fund.is_pit_refused("2026-06-17", today="2026-06-26", force=False) is True
    assert fund.is_pit_refused("2026-06-26", today="2026-06-26", force=False) is False
    assert fund.is_pit_refused("2026-06-17", today="2026-06-26", force=True) is False


def test_invariant_failed_d0_pair_not_refetched_on_later_day(monkeypatch):
    monkeypatch.setattr(fund, "fetch", lambda tk: (_ for _ in ()).throw(RuntimeError("throttled")))
    assert fund.collect([("2026-06-17", "GHOST")]) == []          # leg 1: failure → no row
    header = ["scan_date", "ticker"]
    wl = [["2026-06-17", "GHOST"], ["2026-06-26", "FRESH"]]
    assert ("2026-06-17", "GHOST") not in fund.select_target_pairs(wl, header, "2026-06-26")  # leg 2
    assert fund.is_pit_refused("2026-06-17", today="2026-06-26", force=False) is True          # leg 3
