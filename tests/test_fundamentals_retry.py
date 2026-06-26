"""TDD for fundamentals fetch resilience (B1) + PIT cross-day invariant.

Finviz throttles bursty EOD scrapes ('NoneType' object has no attribute
'find_all') → bounded retry/backoff. On exhausted failure write NO row (no
poison FETCH_ERROR stub). The PIT invariant: a (scan_date,ticker) that failed at
its D0 EOD run is NEVER re-fetched on a later day — current Finviz values stamped
on an old D0 = look-ahead, which breaks Group C's point-in-time guarantee.
"""
import pytest

import config
import fundamentals as fund


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(fund.time, "sleep", lambda *a, **k: None)


# ── retry / backoff ───────────────────────────────────────────────────────────
def test_retry_then_succeed(monkeypatch):
    calls = {"n": 0}

    def flaky(tk):
        calls["n"] += 1
        if calls["n"] < 3:
            raise AttributeError("'NoneType' object has no attribute 'find_all'")
        return {"Company": "ACME", "ROA": "5%"}

    monkeypatch.setattr(fund, "fetch", flaky)
    rows = fund.collect([("2026-06-26", "ACME")])
    assert len(rows) == 1 and rows[0]["ticker"] == "ACME"
    assert calls["n"] == 3            # retried twice, then succeeded


def test_give_up_writes_no_stub(monkeypatch):
    monkeypatch.setattr(fund, "fetch", lambda tk: (_ for _ in ()).throw(
        AttributeError("'NoneType' object has no attribute 'find_all'")))
    rows = fund.collect([("2026-06-26", "BUST")])
    assert rows == []                 # NO poison FETCH_ERROR stub row


def test_retry_count_is_bounded(monkeypatch):
    calls = {"n": 0}

    def always_fail(tk):
        calls["n"] += 1
        raise ValueError("boom")

    monkeypatch.setattr(fund, "fetch", always_fail)
    fund.collect([("2026-06-26", "X")])
    assert calls["n"] == config.FINVIZ_FETCH_RETRIES


def test_time_budget_stops_early(monkeypatch):
    vals = [0.0, 0.0, 10_000.0]       # start, iter1 ok, iter2 over budget
    monkeypatch.setattr(fund.time, "monotonic", lambda: vals.pop(0) if vals else 10_000.0)
    monkeypatch.setattr(fund, "fetch", lambda tk: {"Company": tk})
    rows = fund.collect([("2026-06-26", "A"), ("2026-06-26", "B"), ("2026-06-26", "C")],
                        time_budget_s=10)
    assert 1 <= len(rows) < 3         # processed some, then the budget cut it short


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
    """End-to-end of the three legs: D0 failure leaves no row, and a later-day
    run neither selects nor is allowed to fetch that past (scan_date,ticker)."""
    monkeypatch.setattr(fund, "fetch", lambda tk: (_ for _ in ()).throw(RuntimeError("throttled")))
    # leg 1: failure at D0 writes no row
    assert fund.collect([("2026-06-17", "GHOST")]) == []
    # leg 2: a later-day run selects only the later date — GHOST@6/17 excluded
    header = ["scan_date", "ticker"]
    wl = [["2026-06-17", "GHOST"], ["2026-06-26", "FRESH"]]
    assert ("2026-06-17", "GHOST") not in fund.select_target_pairs(wl, header, "2026-06-26")
    # leg 3: explicitly targeting the past date on a later day is PIT-refused
    assert fund.is_pit_refused("2026-06-17", today="2026-06-26", force=False) is True
