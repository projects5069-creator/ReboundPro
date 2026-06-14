"""intraday_scanner.py — ReboundPro M2 intraday scanner (free data).

Every ~10 min during US market hours: find stocks CURRENTLY >= threshold below
the day's OPEN (Finviz candidate net + yfinance 1-minute bars), apply the same
hard liquidity floor, and maintain the intraday path in watchlist_live with
smart dedup (first cross inserts a flagged row; later scans update the path —
no duplicate rows).

Collection only — NO scoring / signals / ranking. `reversal_confirmed` is a
descriptive price-path fact, not a trade signal.

Scheduling: GitHub cron < 1h is unreliable (skips/delays), so the proven
RidingHigh mechanism is an external pinger (cron-job.org) hitting
workflow_dispatch every 10 min. The workflow also keeps a best-effort cron.

Free-data note: yfinance 1m bars are ~15 min delayed and capped to recent days.
Polygon minute aggregates (paid) would give real-time, gap-free intraday for
exact first-cross timing and reversal detection — a future accuracy upgrade.

Usage:
    python intraday_scanner.py --dry-run
    python intraday_scanner.py                 # live -> watchlist_live
    python intraday_scanner.py --tab watchlist_intraday_test   # isolated test tab
"""
import argparse
import logging
import time
from datetime import date, datetime, time as dtime

import pandas as pd
import pytz
import yfinance as yf
import exchange_calendars as ec

import config
import scanner as sc

ET = pytz.timezone("America/New_York")
MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)


def is_market_hours(now=None):
    """True iff NYSE is open right now: a trading session (calendar-aware,
    handles weekends + holidays) AND 09:30–16:00 ET. Operational guard only."""
    now = now or datetime.now(ET)
    if now.tzinfo is None:
        now = ET.localize(now)
    now = now.astimezone(ET)
    cal = ec.get_calendar("XNYS")
    if not cal.is_session(pd.Timestamp(now.date())):
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE
log = logging.getLogger("intraday")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")


def intraday_bars(ticker):
    h = yf.Ticker(ticker).history(period="1d", interval="1m", prepost=False)
    return h if h is not None and not h.empty else None


def daily_hist(ticker, scan_date):
    from datetime import timedelta
    h = yf.Ticker(ticker).history(
        start=str(scan_date - timedelta(days=config.HISTORY_DAYS_FETCH)),
        end=str(scan_date + timedelta(days=1)), auto_adjust=True)
    if h is None or h.empty:
        return None
    return h[h.index.date < scan_date]


def build(row, scan_date, spy_chg, now, existing):
    ticker = str(row.get("Ticker", "")).strip().upper()
    if not ticker:
        return None, "no_ticker"
    fz_price = sc.parse_num(row.get("Price"))
    mc = sc.parse_market_cap(row.get("Market Cap"))
    if fz_price is None or fz_price != fz_price or fz_price < config.MIN_PRICE:
        return None, "below_min_price"
    if mc is None or mc != mc or mc < config.MIN_MARKET_CAP:
        return None, "below_min_cap"

    im = intraday_bars(ticker)
    if im is None:
        return None, "no_intraday"
    o = float(im["Open"].iloc[0])
    lo = float(im["Low"].min())
    hi = float(im["High"].max())
    last = float(im["Close"].iloc[-1])
    vol = int(im["Volume"].sum())
    lo_at = im["Low"].idxmin()
    if o <= 0:
        return None, "bad_open"

    drop_from_open = round((last - o) / o * 100, 2)        # CURRENT vs open
    if drop_from_open > -config.INTRADAY_DROP_THRESHOLD:
        return None, "drop_below_threshold"

    prior = daily_hist(ticker, scan_date)
    if prior is None or prior.empty:
        return None, "no_daily_hist"
    prev_close = float(prior["Close"].iloc[-1])
    avg_vol_20 = float(prior["Volume"].tail(20).mean()) if len(prior) >= 5 else None
    adv_dollar = round(avg_vol_20 * last, 0) if avg_vol_20 else None
    if adv_dollar is None or adv_dollar < config.MIN_ADV_DOLLAR:
        return None, "below_min_adv"

    # running intraday low (carry forward across scans)
    run_low = lo
    run_low_at = str(lo_at)
    first_at = now
    first_price = round(last, 2)
    first_drop = drop_from_open
    scans = 1
    if existing:
        scans = int(float(existing.get("scans_count") or 0)) + 1
        first_at = existing.get("first_cross_at") or now
        first_price = existing.get("first_cross_price") or round(last, 2)
        first_drop = existing.get("first_cross_drop_pct") or drop_from_open
        prev_low = existing.get("intraday_low")
        try:
            if prev_low not in (None, "") and float(prev_low) <= run_low:
                run_low = float(prev_low)
                run_low_at = existing.get("intraday_low_at") or run_low_at
        except (TypeError, ValueError):
            pass

    recovery = round((last - run_low) / run_low * 100, 2) if run_low > 0 else ""
    reversal = bool(recovery != "" and recovery >= config.REVERSAL_CONFIRM_PCT)

    sector = row.get("Sector") or ""
    etf = config.SECTOR_ETF.get(sector)
    sec_chg = sc.etf_change(etf, scan_date) if etf else None

    snap = {
        "scan_date": str(scan_date), "ticker": ticker, "exchange": row.get("_exchange", ""),
        "company_name": row.get("Company", ""), "sector": sector,
        "industry": row.get("Industry", ""), "country": row.get("Country", ""),
        "detected_at": first_at, "market_cap": int(mc),
        "market_cap_category": config.classify_market_cap(mc),
        "liquidity_bucket": config.classify_market_cap(mc),
        "price": round(last, 2), "open": round(o, 2), "high": round(hi, 2),
        "low_so_far": round(lo, 2), "prev_close": round(prev_close, 2),
        "drop_pct_from_open": drop_from_open, "close_pct_from_open": "",
        "pct_change_prevclose": round((last - prev_close) / prev_close * 100, 2),
        "volume": vol, "avg_volume_20d": int(avg_vol_20) if avg_vol_20 else "",
        "adv_dollar": int(adv_dollar), "volume_ratio": round(vol / avg_vol_20, 2) if avg_vol_20 else "",
        "rsi_14": sc.rsi_14(prior["Close"]),
        "spy_change_pct": spy_chg, "sector_etf": etf or "",
        "sector_etf_change_pct": sec_chg, "market_regime": sc.market_regime(spy_chg),
        "drop_type": sc.classify_drop_type(spy_chg, sec_chg), "scanned_at": now,
        "source": "intraday", "first_cross_at": first_at,
        "first_cross_price": first_price, "first_cross_drop_pct": first_drop,
        "intraday_low": round(run_low, 2), "intraday_low_at": run_low_at,
        "recovery_from_low_pct": recovery, "reversal_confirmed": reversal,
        "scans_count": scans, "last_update_at": now,
    }
    return snap, "ok"


def scan(scan_date, tab):
    import sheets_manager as sm
    cands = sc.get_candidates()
    log.info("Finviz candidates (pre-floor): %d", len(cands))
    if cands.empty:
        return [], {}
    spy_chg = sc.day_change_pct(config.MARKET_PROXY, scan_date)
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S %Z")

    # existing intraday rows for carry-forward
    eh, ed = sm.read_rows(config.SHEET_ID, tab) if config.SHEET_ID else ([], [])
    existing = {}
    if ed and "ticker" in eh:
        di, ti = eh.index("scan_date"), eh.index("ticker")
        for r in ed:
            d = {eh[i]: (r[i] if i < len(r) else "") for i in range(len(eh))}
            existing[(d.get("scan_date"), d.get("ticker"))] = d

    rows, reasons = [], {}
    for _, r in cands.iterrows():
        ex = existing.get((str(scan_date), str(r.get("Ticker", "")).strip().upper()))
        snap, why = build(r, scan_date, spy_chg, now, ex)
        reasons[why] = reasons.get(why, 0) + 1
        if snap:
            rows.append(snap)
        time.sleep(config.RATE_LIMIT_SLEEP)
    log.info("Passed floor + intraday trigger: %d (reasons: %s)", len(rows), reasons)
    return rows, reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tab", default=config.TAB_WATCHLIST)
    ap.add_argument("--force", action="store_true",
                    help="bypass the market-hours guard (testing / off-hours)")
    args = ap.parse_args()

    # operational market-hours guard — exit cleanly when NYSE is closed
    if not args.force and not is_market_hours():
        log.info("Market closed (outside 09:30–16:00 ET or non-trading day) — no-op.")
        return []

    scan_date = sc.last_trading_day(args.date or date.today())
    log.info("Intraday scan date: %s | tab: %s", scan_date, args.tab)
    rows, _ = scan(scan_date, args.tab)

    if args.dry_run or not config.SHEET_ID:
        print(f"\n--- DRY RUN: {len(rows)} intraday rows ---")
        if rows:
            import json
            print(json.dumps(rows[0], indent=2, default=str, ensure_ascii=False))
        return rows

    import sheets_manager as sm
    upd, ins, tot = sm.upsert_by_key(config.SHEET_ID, args.tab, config.WATCHLIST_HEADER,
                                     rows, ["scan_date", "ticker"])
    log.info("%s: +%d new, %d updated (tab total %d).", args.tab, ins, upd, tot)
    return rows


if __name__ == "__main__":
    main()
