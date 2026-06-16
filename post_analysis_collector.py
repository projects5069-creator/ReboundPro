"""post_analysis_collector.py — ReboundPro M1 Layer-6 collector.

For each recorded watchlist row, collect D1..D+N forward OHLC and outcome
metrics (max recovery, max further drop, touched +X%/-Y%, window). Halts /
delistings are handled EXPLICITLY as an outcome status — never silently dropped.

Usage:
    python post_analysis_collector.py --dry-run
    python post_analysis_collector.py                       # live: write post_analysis
    python post_analysis_collector.py --selftest AAPL 2026-04-08   # verify math
"""
import argparse
import logging
from datetime import date, datetime, timedelta

import pandas as pd
import pytz
import yfinance as yf
import exchange_calendars as ec

import config

ET = pytz.timezone("America/New_York")
log = logging.getLogger("collector")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")

HEADER = [
    "scan_date", "ticker", "ref_close", "horizon", "forward_days_available", "status",
    "max_recovery_pct", "day_of_max_recovery", "max_further_drop_pct", "day_of_max_drop",
    f"touched_up_{int(config.TOUCH_UP_PCT)}pct", "day_touched_up",
    f"touched_down_{int(config.TOUCH_DOWN_PCT)}pct", "day_touched_down",
    "last_close_pct", "dN_date", "collected_at",
] + [f"max_recovery_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS] \
  + [f"max_further_drop_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS] \
  + [  # recovery-from-trough (M3 — DESCRIPTIVE reversal record, NOT an entry signal)
    "trough_price",                    # lowest price touched in the forward window
    "trough_day",                      # D+n of the trough (== day_of_max_drop)
    "recovery_from_trough_pct",        # (last_close - trough)/trough * 100
    "max_recovery_from_trough_pct",    # peak high since the trough vs trough (>=0)
  ] + [  # split/halt contamination detector (NON-DESTRUCTIVE flag for M4 exclusion)
    "split_halt_flag",                 # True if the forward window is contaminated
    "split_halt_reason",               # reverse_split_ratio | inter_day_jump | halt_gap | clean
  ]


def detect_split_halt(fwd, ref_close, status):
    """Flag reverse-split / halt artifacts that would poison the forward outcome
    (a reverse split fakes a multi-hundred-% "recovery"). NON-DESTRUCTIVE: returns
    (flag, reason) only — the caller never drops or mutates the raw row; M4 simply
    EXCLUDES flagged rows from aggregates. Sources, in priority:
      1. yf split feed (the "Stock Splits" column in the history) — source of truth.
      2. extreme inter-day jump > SPLIT_HALT_JUMP_PCT (backup; catches missed/ glitched splits).
      3. halt / trading gap (fewer forward bars than elapsed sessions, or delisted).
    """
    if "Stock Splits" in fwd.columns and (fwd["Stock Splits"].fillna(0) != 0).any():
        return True, "reverse_split_ratio"
    closes = fwd["Close"].astype(float)
    jumps = []
    if ref_close and ref_close > 0:
        jumps.append(abs(closes.iloc[0] / ref_close - 1) * 100)
    jumps += [float(x) for x in closes.pct_change().abs().mul(100).dropna().values]
    if jumps and max(jumps) > config.SPLIT_HALT_JUMP_PCT:
        return True, "inter_day_jump"
    if status in ("partial_gap_possible_halt", "delisted_or_halted"):
        return True, "halt_gap"
    return False, "clean"


FORWARD_LAG_GRACE = 1   # tolerate the most-recent closed session lagging in yfinance


def completed_forward_sessions(scan_date, horizon, now=None):
    """Trading-session DATES after scan_date whose CLOSE has already passed
    (capped at horizon). A session counts only once its close is in the past
    relative to `now` — so a pre-market/intraday run never counts today's
    not-yet-closed (and therefore not-yet-available) session."""
    nyse = ec.get_calendar("XNYS")
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    start = pd.Timestamp(scan_date) + pd.Timedelta(days=1)
    end = pd.Timestamp(now.date())
    if start > end:
        return []
    closed = [s.date() for s in nyse.sessions_in_range(start, end)
              if nyse.session_close(s) <= now]
    return closed[:horizon]


def expected_forward_sessions(scan_date, horizon, now=None):
    """Count of COMPLETED forward sessions (cap horizon). See completed_forward_sessions."""
    return len(completed_forward_sessions(scan_date, horizon, now))


def classify_status(navail, exp, horizon, fwd_dates, expected_dates,
                    grace=FORWARD_LAG_GRACE):
    """Pure forward-status decision — distinguishes a recent data LAG
    (forward_pending) from a real halt/delist GAP. `fwd_dates`/`expected_dates`
    are sorted lists of date. A trailing shortfall within `grace` is just yfinance
    lag; an INTERNAL hole (a closed session before the last available bar is
    missing) or a larger shortfall is a real gap/halt."""
    if navail == 0:
        if exp == 0:
            return "pending_forward"           # forward window not open yet
        if exp <= grace:
            return "forward_pending"           # only the latest closed session(s) lagging
        return "delisted_or_halted"            # several closed sessions, zero data
    avail = set(fwd_dates)
    last_avail = fwd_dates[-1]
    if any(d not in avail for d in expected_dates if d <= last_avail):
        return "partial_gap_possible_halt"     # internal hole = real mid-window halt
    shortfall = exp - navail
    if shortfall > grace:
        return "partial_gap_possible_halt"     # missing more than lag tolerance
    if shortfall > 0:
        return "forward_pending"               # only the most-recent <=grace lagging
    return "ok" if navail == horizon else "partial"


def daily_series(fwd, ref_close, scan_date, ticker):
    """Per-day forward rows (D+1..D+navail) from the ALREADY-FETCHED `fwd` — no
    extra yfinance call. cum_pct_from_ref = (close/ref-1)*100 (from D0);
    daily_change_pct = D+1 vs ref_close, then close-to-close. Returns [] when
    there is no forward data or no valid ref. Descriptive research data, not a
    signal."""
    if fwd is None or len(fwd) == 0 or not ref_close or ref_close <= 0:
        return []
    rows, prev = [], float(ref_close)
    for i in range(len(fwd)):
        c = float(fwd["Close"].iloc[i])
        rows.append({
            "scan_date": str(scan_date), "ticker": ticker, "day_offset": i + 1,
            "date": str(fwd.index[i].date()), "close": round(c, 4),
            "cum_pct_from_ref": round((c / ref_close - 1) * 100, 2),
            "daily_change_pct": round((c / prev - 1) * 100, 2) if prev > 0 else "",
            "high_pct": round((float(fwd["High"].iloc[i]) / ref_close - 1) * 100, 2),
            "low_pct": round((float(fwd["Low"].iloc[i]) / ref_close - 1) * 100, 2),
        })
        prev = c
    return rows


def compute_outcome(ticker, scan_date, ref_close=None, horizon=None):
    """Forward outcome relative to ref_close (default = scan_date close)."""
    horizon = horizon or config.POST_ANALYSIS_HORIZON
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S %Z")
    base = {"scan_date": str(scan_date), "ticker": ticker, "horizon": horizon,
            "collected_at": now}
    try:
        h = yf.Ticker(ticker).history(
            start=str(scan_date - timedelta(days=10)),
            end=str(scan_date + timedelta(days=horizon * 3 + 10)), auto_adjust=True)
    except Exception as e:
        return {**base, "ref_close": ref_close or "", "status": f"yf_error:{e}",
                "forward_days_available": 0}

    h = h[~h.index.duplicated()]
    on_or_before = h[h.index.date <= scan_date]
    if ref_close is None:
        ref_close = float(on_or_before["Close"].iloc[-1]) if len(on_or_before) else None
    fwd = h[h.index.date > scan_date].head(horizon)

    exp_dates = completed_forward_sessions(scan_date, horizon)
    exp = len(exp_dates)
    navail = len(fwd)
    fwd_dates = [d.date() for d in fwd.index]
    status = classify_status(navail, exp, horizon, fwd_dates, exp_dates)

    # explicit halt / delisting / pending handling — never drop
    if navail == 0:
        halted = status == "delisted_or_halted"
        return {**base, "ref_close": round(ref_close, 2) if ref_close else "",
                "status": status, "forward_days_available": 0,
                "max_recovery_pct": "", "day_of_max_recovery": "",
                "max_further_drop_pct": "", "day_of_max_drop": "",
                HEADER[10]: "", "day_touched_up": "", HEADER[12]: "", "day_touched_down": "",
                "last_close_pct": "", "dN_date": "",
                "split_halt_flag": halted,
                "split_halt_reason": "halt_gap" if halted else "clean"}
    if ref_close is None or ref_close <= 0:
        return {**base, "ref_close": "", "status": "no_ref_close",
                "forward_days_available": navail}

    # status already decided by classify_status above (pending / gap / halt / partial / ok)
    highs = (fwd["High"] / ref_close - 1) * 100
    lows = (fwd["Low"] / ref_close - 1) * 100
    closes = (fwd["Close"] / ref_close - 1) * 100

    max_rec = float(highs.max()); day_rec = int(highs.values.argmax()) + 1
    max_drop = float(lows.min()); day_drop = int(lows.values.argmin()) + 1

    up_hits = highs[highs >= config.TOUCH_UP_PCT]
    dn_hits = lows[lows <= -config.TOUCH_DOWN_PCT]
    touched_up = len(up_hits) > 0
    touched_dn = len(dn_hits) > 0
    day_up = (int(list(highs.values).index(up_hits.iloc[0]) ) + 1) if touched_up else ""
    day_dn = (int(list(lows.values).index(dn_hits.iloc[0])) + 1) if touched_dn else ""

    # sub-window metrics (D+3/D+5/D+10/D+20) — enables later window analysis
    sub = {}
    for w in config.POST_ANALYSIS_SUBWINDOWS:
        hw, lw = highs.iloc[:w], lows.iloc[:w]
        sub[f"max_recovery_{w}d"] = round(float(hw.max()), 2) if len(hw) else ""
        sub[f"max_further_drop_{w}d"] = round(float(lw.min()), 2) if len(lw) else ""

    # recovery-from-trough (DESCRIPTIVE reversal record — records the bounce off the
    # low, does NOT decide on it; no entry threshold). Trough = lowest forward Low.
    trough_idx = int(fwd["Low"].values.argmin())
    trough_price = float(fwd["Low"].iloc[trough_idx])
    trough_day = trough_idx + 1                       # D+n (== day_of_max_drop)
    last_close = float(fwd["Close"].iloc[-1])
    if trough_price > 0:
        rec_from_trough = round((last_close - trough_price) / trough_price * 100, 2)
        # peak high from the trough day onward, vs the trough price (>= 0)
        max_high_since = float(fwd.iloc[trough_idx:]["High"].max())
        max_rec_from_trough = round((max_high_since - trough_price) / trough_price * 100, 2)
    else:
        rec_from_trough = max_rec_from_trough = ""
    trough = {"trough_price": round(trough_price, 2), "trough_day": trough_day,
              "recovery_from_trough_pct": rec_from_trough,
              "max_recovery_from_trough_pct": max_rec_from_trough}

    # split/halt contamination flag (non-destructive — raw values above are kept)
    sh_flag, sh_reason = detect_split_halt(fwd, ref_close, status)
    shd = {"split_halt_flag": sh_flag, "split_halt_reason": sh_reason}

    return {**base, "ref_close": round(ref_close, 2), "status": status,
            "forward_days_available": navail,
            "max_recovery_pct": round(max_rec, 2), "day_of_max_recovery": day_rec,
            "max_further_drop_pct": round(max_drop, 2), "day_of_max_drop": day_drop,
            HEADER[10]: touched_up, "day_touched_up": day_up,
            HEADER[12]: touched_dn, "day_touched_down": day_dn,
            "last_close_pct": round(float(closes.iloc[-1]), 2),
            "dN_date": str(fwd.index[-1].date()), **sub, **trough, **shd,
            # ADDITIVE: per-day forward series (not in post HEADER → to_matrix
            # ignores it; written separately to forward_daily). Reuses fwd above.
            "_daily_rows": daily_series(fwd, ref_close, scan_date, ticker)}


def to_matrix(rows):
    return [[("" if r.get(c) is None else r.get(c)) for c in HEADER] for r in rows]


def _build_daily(rows):
    """Flatten every outcome's already-computed _daily_rows (+ collected_at) into
    the forward_daily long rows. Reuses fetched data — no extra yfinance call."""
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S %Z")
    return [{**d, "collected_at": now} for r in rows for d in r.get("_daily_rows", [])]


def _write_forward_daily(sm, rows):
    """Upsert the per-day forward series to forward_daily (keyed
    scan_date/ticker/day_offset; atomic upsert; idempotent). Returns total rows."""
    daily = _build_daily(rows)
    upd, ins, tot = sm.upsert_by_key(config.SHEET_ID, config.TAB_FORWARD_DAILY,
                                     config.FORWARD_DAILY_HEADER, daily,
                                     ["scan_date", "ticker", "day_offset"])
    log.info("Wrote forward_daily: +%d new, %d updated (total %d).", ins, upd, tot)
    return tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", nargs=2, metavar=("TICKER", "DATE"), default=None,
                    help="verify outcome math on a known (ticker, YYYY-MM-DD)")
    ap.add_argument("--backfill-daily", action="store_true",
                    help="populate forward_daily (D+1..D+N per-day series) for every "
                         "watchlist event; writes ONLY forward_daily, not post_analysis")
    args = ap.parse_args()

    if args.selftest:
        t, d = args.selftest[0].upper(), datetime.strptime(args.selftest[1], "%Y-%m-%d").date()
        import json
        out = compute_outcome(t, d)
        print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
        return [out]

    if not config.SHEET_ID:
        log.error("No SHEET_ID configured — cannot read watchlist. Set REBOUND_SHEET_ID.")
        return []

    import sheets_manager as sm
    header, data = sm.read_rows(config.SHEET_ID, config.TAB_WATCHLIST)
    if not data:
        log.info("watchlist_live empty — nothing to collect.")
        return []
    idx = {c: i for i, c in enumerate(header)}
    rows = []
    for r in data:
        t = r[idx["ticker"]]
        sd = datetime.strptime(r[idx["scan_date"]], "%Y-%m-%d").date()
        ref = float(r[idx["price"]]) if r[idx["price"]] else None
        out = compute_outcome(t, sd, ref_close=ref)
        rows.append(out)
        log.info("%s %s -> %s (rec=%s drop=%s)", sd, t, out["status"],
                 out.get("max_recovery_pct"), out.get("max_further_drop_pct"))

    # --backfill-daily: write ONLY forward_daily (explicit one-off; reuses the
    # already-computed _daily_rows — no extra fetch).
    if args.backfill_daily:
        daily = _build_daily(rows)
        if args.dry_run:
            print("\n--- DRY RUN: %d forward_daily rows (%d events) ---" % (len(daily), len(rows)))
            return daily
        _write_forward_daily(sm, rows)
        return daily

    if args.dry_run:
        print("\n--- DRY RUN: %d post_analysis rows ---" % len(rows))
        from collections import Counter
        print("status breakdown:", dict(Counter(r["status"] for r in rows)))
        return rows

    # post_analysis FIRST (the critical write).
    surv, new = sm.upsert_rows(config.SHEET_ID, config.TAB_POST, HEADER, to_matrix(rows))
    log.info("Wrote post_analysis: %d rows (kept %d historical).", new, surv)
    # forward_daily SECOND, ISOLATED — post is already saved, so a forward_daily
    # write failure is logged but never fails the run.
    try:
        _write_forward_daily(sm, rows)
    except Exception as e:
        log.error("forward_daily write failed (post_analysis already written): %s", e)
    return rows


if __name__ == "__main__":
    main()
