"""TDD for the post_analysis forward-classification over-flagging fix (2026-06-16).

The collector ran pre-market; expected_forward_sessions counted the not-yet-closed
session, so navail<exp and events were mis-classified delisted_or_halted /
partial_gap_possible_halt (a timing false-positive, not real delisting).

Fix:
  1. expected_forward_sessions / completed_forward_sessions count ONLY sessions
     whose close has passed (session_close <= now).
  2. classify_status distinguishes forward_pending (recent tail lag, <=grace,
     contiguous) from delisted_or_halted / partial_gap_possible_halt (real gaps:
     internal hole, or shortfall > grace, or zero data after several closed
     sessions).

Per the directive: the date tests exercise the REAL exchange_calendars (only
`now` is injected) so an API problem in session_close is caught here.
"""
from datetime import date

import pandas as pd

import post_analysis_collector as pac

PRE_CLOSE = pd.Timestamp("2026-06-16 12:00", tz="UTC")   # before 6/16 close (20:00 UTC EDT)
POST_CLOSE = pd.Timestamp("2026-06-16 21:00", tz="UTC")  # after 6/16 close


# ── (ד) expected sessions count only CLOSED sessions — REAL calendar ──────────
def test_completed_sessions_excludes_unclosed_today():
    sess = pac.completed_forward_sessions(date(2026, 6, 12), 20, now=PRE_CLOSE)
    assert date(2026, 6, 15) in sess, "6/15 (closed) must count"
    assert date(2026, 6, 16) not in sess, "6/16 session not closed yet → must NOT count"


def test_completed_sessions_includes_today_after_close():
    sess = pac.completed_forward_sessions(date(2026, 6, 12), 20, now=POST_CLOSE)
    assert date(2026, 6, 16) in sess, "6/16 closed → must count"
    assert {date(2026, 6, 15), date(2026, 6, 16)} <= set(sess)


def test_expected_forward_sessions_matches_completed_len():
    assert pac.expected_forward_sessions(date(2026, 6, 12), 20, now=PRE_CLOSE) == 1
    assert pac.expected_forward_sessions(date(2026, 6, 15), 20, now=PRE_CLOSE) == 0


# ── (א) pre-market run → today's event is pending, NOT delisted ────────────────
def test_premarket_today_event_is_pending_not_delisted():
    exp_dates = pac.completed_forward_sessions(date(2026, 6, 15), 20, now=PRE_CLOSE)  # []
    status = pac.classify_status(0, len(exp_dates), 20, [], exp_dates)
    assert status == "pending_forward", f"got {status} — over-flagged as halt"


def test_premarket_prior_cohort_is_partial_not_gap():
    exp_dates = pac.completed_forward_sessions(date(2026, 6, 12), 20, now=PRE_CLOSE)  # [6/15]
    status = pac.classify_status(1, len(exp_dates), 20, [date(2026, 6, 15)], exp_dates)
    assert status == "partial", f"got {status} — over-flagged as gap"


# ── (ב) full window → ok ──────────────────────────────────────────────────────
def test_full_window_ok():
    dates = [date(2026, 1, d + 1) for d in range(20)]
    assert pac.classify_status(20, 20, 20, dates, dates) == "ok"


# ── (ג) CRITICAL: real internal gap stays a halt signal ───────────────────────
def test_internal_gap_is_halt_signal():
    expected = [date(2026, 1, d) for d in (2, 5, 6, 7, 8)]   # 5 closed sessions
    available = [date(2026, 1, d) for d in (2, 5, 6, 8)]     # 1/7 missing (internal hole), 1/8 present
    status = pac.classify_status(len(available), len(expected), 20, available, expected)
    assert status == "partial_gap_possible_halt", \
        f"got {status} — real mid-window halt must NOT be downgraded to pending"


# ── (ה) tail lag within grace → forward_pending; beyond grace → gap ───────────
def test_tail_lag_within_grace_is_pending():
    expected = [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)]
    available = [date(2026, 1, 2), date(2026, 1, 5)]        # missing only the latest (tail), shortfall=1
    assert pac.classify_status(2, 3, 20, available, expected) == "forward_pending"


def test_tail_lag_beyond_grace_is_gap():
    expected = [date(2026, 1, d) for d in (2, 5, 6, 7)]
    available = [date(2026, 1, 2)]                          # shortfall=3 > grace
    assert pac.classify_status(1, 4, 20, available, expected) == "partial_gap_possible_halt"


def test_zero_forward_many_closed_sessions_is_delisted():
    expected = [date(2026, 1, d) for d in (2, 5, 6, 7)]     # 4 closed, none available
    assert pac.classify_status(0, 4, 20, [], expected) == "delisted_or_halted"
