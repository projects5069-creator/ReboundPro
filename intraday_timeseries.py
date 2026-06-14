"""intraday_timeseries.py — ReboundPro M3 tiered intraday time-series collector.

For every stock already in watchlist_live, append a time-series point
(price, pct_from_open, volume) to the `intraday_timeseries` tab at a resolution
that STEPS DOWN with the number of trading days since the drop day (D0 = scan_date):

  • D0–D3   : every 10 min during market hours (rides the existing intraday trigger).
  • D4–D20  : ~3 points/day — open / mid / close approximations.
  • > D20   : window closed, not tracked.

The D4–D20 tier self-gates: on each 10-min run it records at most one point per
"slot" (open/mid/close) per day, by checking which slots already exist for the
stock today. This makes it robust to cron drift (a missed exact tick is filled
by the next tick still inside the same slot window) and re-run safe.

Keyed (scan_date, ticker, timestamp) and written via upsert_by_key, so re-runs
never duplicate. The 10-min tier rounds `timestamp` to the 10-min grid for the
same reason. Does NOT touch post_analysis (that remains the daily outcome layer).

Protections preserved:
  • Liquidity floor — inherited; only stocks already past the floor (in
    watchlist_live) are tracked here.
  • Market-hours guard — reused from intraday_scanner.is_market_hours().

Collection only — NO scoring / signals / ranking. pct_from_open is measured vs
the current day's open (a descriptive intraday fact, not a trade signal).

Usage:
    python intraday_timeseries.py --dry-run
    python intraday_timeseries.py                 # live -> intraday_timeseries
    python intraday_timeseries.py --force         # bypass the market-hours guard
    python intraday_timeseries.py --tab intraday_timeseries_test
"""
import argparse
import logging
import time
from datetime import date, datetime, time as dtime, timedelta

import pandas as pd
import pytz
import exchange_calendars as ec

import config
from intraday_scanner import is_market_hours, intraday_bars

ET = pytz.timezone("America/New_York")
log = logging.getLogger("timeseries")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")

# D4–D20 slot windows (ET). Each slot is recorded at most once/day; the first
# 10-min tick that lands inside a window fills it (≈ open / midday / close).
SLOTS = [
    ("open",  dtime(9, 30), dtime(10, 10)),
    ("mid",   dtime(12, 20), dtime(13, 0)),
    ("close", dtime(15, 20), dtime(16, 0)),
]


def days_since_d0(scan_date, today, cal):
    """Trading sessions elapsed since the drop day. D0 (==scan_date) -> 0."""
    if today <= scan_date:
        return 0
    sess = cal.sessions_in_range(pd.Timestamp(scan_date + timedelta(days=1)),
                                 pd.Timestamp(today))
    return len(sess)


def tier_for(d):
    """'10min' (D0–D3), '3h' (D4–D20), or None (window closed)."""
    if 0 <= d <= config.TS_TIER1_MAX_DAY:
        return "10min"
    if config.TS_TIER1_MAX_DAY < d <= config.TS_TIER2_MAX_DAY:
        return "3h"
    return None


def slot_of(t):
    """Map a time-of-day to its D4–D20 slot name, or None if outside all slots."""
    for name, a, b in SLOTS:
        if a <= t <= b:
            return name
    return None


def round10(dt):
    """Floor a datetime to the 10-minute grid (idempotent timestamps)."""
    return dt.replace(minute=dt.minute - dt.minute % 10, second=0, microsecond=0)


def measure(ticker):
    """Current intraday point from yfinance 1m bars, or None if no data today."""
    im = intraday_bars(ticker)
    if im is None:
        return None
    o = float(im["Open"].iloc[0])
    if o <= 0:
        return None
    last = float(im["Close"].iloc[-1])
    vol = int(im["Volume"].sum())
    return {"price": round(last, 2),
            "pct_from_open": round((last - o) / o * 100, 2),
            "volume": vol}


def collect(now, tab):
    """Build the time-series points due on this run for all tracked stocks."""
    import sheets_manager as sm
    cal = ec.get_calendar("XNYS")
    today = now.date()
    ts10 = round10(now).strftime("%Y-%m-%d %H:%M")
    cur_slot = slot_of(now.time())

    wh, wd = sm.read_rows(config.SHEET_ID, config.TAB_WATCHLIST)
    if not wd:
        log.info("watchlist_live empty — nothing to track.")
        return []
    wi = {c: i for i, c in enumerate(wh)}
    pairs = {(r[wi["scan_date"]], r[wi["ticker"]])
             for r in wd if r[wi["scan_date"]] and r[wi["ticker"]]}

    # existing slots filled TODAY (for D4–D20 self-gating)
    filled = set()
    th, td = sm.read_rows(config.SHEET_ID, tab)
    if td and "timestamp" in th:
        ti = {c: i for i, c in enumerate(th)}
        for r in td:
            try:
                tdt = datetime.strptime(r[ti["timestamp"]], "%Y-%m-%d %H:%M")
            except (ValueError, IndexError):
                continue
            if tdt.date() == today:
                s = slot_of(tdt.time())
                if s:
                    filled.add((r[ti["scan_date"]], r[ti["ticker"]], s))

    rows, counts = [], {}
    for sd, tk in sorted(pairs):
        try:
            scan_d = datetime.strptime(sd, "%Y-%m-%d").date()
        except ValueError:
            counts["bad_date"] = counts.get("bad_date", 0) + 1
            continue
        tier = tier_for(days_since_d0(scan_d, today, cal))
        if tier is None:
            counts["window_closed"] = counts.get("window_closed", 0) + 1
            continue
        if tier == "3h":
            if cur_slot is None:
                counts["not_in_slot"] = counts.get("not_in_slot", 0) + 1
                continue
            if (sd, tk, cur_slot) in filled:
                counts["slot_filled"] = counts.get("slot_filled", 0) + 1
                continue
        m = measure(tk)
        time.sleep(config.RATE_LIMIT_SLEEP)
        if m is None:
            counts["no_data"] = counts.get("no_data", 0) + 1
            continue
        rows.append({"scan_date": sd, "ticker": tk, "timestamp": ts10, **m})
        counts[tier] = counts.get(tier, 0) + 1
    log.info("time-series points due: %d (breakdown: %s)", len(rows), counts)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tab", default=config.TAB_TIMESERIES)
    ap.add_argument("--force", action="store_true",
                    help="bypass the market-hours guard (testing / off-hours)")
    args = ap.parse_args()

    if not args.force and not is_market_hours():
        log.info("Market closed (outside 09:30–16:00 ET or non-trading day) — no-op.")
        return []

    now = datetime.now(ET)
    log.info("Time-series run @ %s | tab: %s", now.strftime("%Y-%m-%d %H:%M %Z"), args.tab)

    if not config.SHEET_ID:
        log.warning("No SHEET_ID configured — dry-run only.")
        args.dry_run = True
    rows = collect(now, args.tab) if config.SHEET_ID else []

    if args.dry_run:
        print(f"\n--- DRY RUN: {len(rows)} time-series rows ---")
        if rows:
            import json
            print(json.dumps(rows[0], indent=2, default=str, ensure_ascii=False))
        return rows

    import sheets_manager as sm
    upd, ins, tot = sm.upsert_by_key(config.SHEET_ID, args.tab,
                                     config.TIMESERIES_HEADER, rows,
                                     ["scan_date", "ticker", "timestamp"])
    log.info("%s: +%d new, %d updated (tab total %d).", args.tab, ins, upd, tot)
    return rows


if __name__ == "__main__":
    main()
