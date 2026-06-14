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
  + [f"max_further_drop_{w}d" for w in config.POST_ANALYSIS_SUBWINDOWS]


def expected_forward_sessions(scan_date, horizon):
    """How many trading sessions AFTER scan_date have already occurred (cap horizon)."""
    nyse = ec.get_calendar("XNYS")
    today = date.today()
    if today <= scan_date:
        return 0
    sess = nyse.sessions_in_range(pd.Timestamp(scan_date + timedelta(days=1)), pd.Timestamp(today))
    return min(len(sess), horizon)


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

    exp = expected_forward_sessions(scan_date, horizon)
    navail = len(fwd)

    # explicit halt / delisting / pending handling — never drop
    if navail == 0:
        status = "pending_forward" if exp == 0 else "delisted_or_halted"
        return {**base, "ref_close": round(ref_close, 2) if ref_close else "",
                "status": status, "forward_days_available": 0,
                "max_recovery_pct": "", "day_of_max_recovery": "",
                "max_further_drop_pct": "", "day_of_max_drop": "",
                HEADER[10]: "", "day_touched_up": "", HEADER[12]: "", "day_touched_down": "",
                "last_close_pct": "", "dN_date": ""}
    if ref_close is None or ref_close <= 0:
        return {**base, "ref_close": "", "status": "no_ref_close",
                "forward_days_available": navail}

    status = "ok" if navail >= exp and navail == horizon else (
        "partial" if navail < horizon else "ok")
    # if we got fewer than the sessions that already elapsed -> a gap (halt)
    if navail < exp:
        status = "partial_gap_possible_halt"

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

    return {**base, "ref_close": round(ref_close, 2), "status": status,
            "forward_days_available": navail,
            "max_recovery_pct": round(max_rec, 2), "day_of_max_recovery": day_rec,
            "max_further_drop_pct": round(max_drop, 2), "day_of_max_drop": day_drop,
            HEADER[10]: touched_up, "day_touched_up": day_up,
            HEADER[12]: touched_dn, "day_touched_down": day_dn,
            "last_close_pct": round(float(closes.iloc[-1]), 2),
            "dN_date": str(fwd.index[-1].date()), **sub}


def to_matrix(rows):
    return [[("" if r.get(c) is None else r.get(c)) for c in HEADER] for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", nargs=2, metavar=("TICKER", "DATE"), default=None,
                    help="verify outcome math on a known (ticker, YYYY-MM-DD)")
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

    if args.dry_run:
        print("\n--- DRY RUN: %d post_analysis rows ---" % len(rows))
        from collections import Counter
        print("status breakdown:", dict(Counter(r["status"] for r in rows)))
        return rows

    surv, new = sm.upsert_rows(config.SHEET_ID, config.TAB_POST, HEADER, to_matrix(rows))
    log.info("Wrote post_analysis: %d rows (kept %d historical).", new, surv)
    return rows


if __name__ == "__main__":
    main()
