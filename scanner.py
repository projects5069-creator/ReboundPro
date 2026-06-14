"""scanner.py — ReboundPro M1 Layer-1 scanner (free data).

Finds NASDAQ+NYSE stocks that dropped >= threshold (from open) on a session,
applies a HARD liquidity floor (no nano/micro), and records a point-in-time
snapshot per candidate to the watchlist_live tab.

Free data: finvizfinance screener (server-side change pre-filter) + yfinance
(per-candidate OHLC / ADV) + SPY & sector-ETF regime.

Usage:
    python scanner.py --dry-run            # scan last trading day, print only
    python scanner.py --date 2026-06-12 --dry-run
    python scanner.py                      # live: write to SHEET_ID
"""
import argparse
import logging
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytz
import yfinance as yf
import exchange_calendars as ec
from finvizfinance.screener.overview import Overview

import config

ET = pytz.timezone("America/New_York")
log = logging.getLogger("scanner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")

# shared watchlist schema (M1 EOD + M2 intraday columns) — single source in config
HEADER = config.WATCHLIST_HEADER


# ── helpers ──────────────────────────────────────────────────────────────────
def last_trading_day(ref: date) -> date:
    nyse = ec.get_calendar("XNYS")
    s = nyse.sessions_in_range(pd.Timestamp(ref - timedelta(days=14)), pd.Timestamp(ref))
    return s[-1].date()


def parse_market_cap(s):
    """Finviz market cap string ('10.50B','950.00M') -> USD float, or None."""
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s in ("", "-") or s.lower() == "nan":
        return None
    mult = 1.0
    if s[-1] in "BMKT":
        mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[s[-1]]
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def parse_num(s):
    try:
        return float(str(s).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def rsi_14(close: pd.Series):
    if len(close) < 15:
        return None
    d = close.diff()
    g = d.clip(lower=0).ewm(com=13, min_periods=14).mean()
    l = (-d).clip(lower=0).ewm(com=13, min_periods=14).mean()
    rs = g / l
    v = float((100 - 100 / (1 + rs)).iloc[-1])
    return round(v, 2) if v == v else None


def prior_context(h, prior, cl):
    """DESCRIPTIVE prior-decline context at capture — collection only, NOT a signal.

    52W range from the trailing ~252 sessions up to scan_date (`h` is already
    filtered to <= scan_date); prior declines are returns over the 20/60 trading
    days BEFORE the capture day (`prior` = sessions strictly before scan_date).
    Records context — sets NO threshold and makes NO entry decision.
    """
    out = {"pct_from_52w_high": "", "pct_from_52w_low": "",
           "prior_decline_20d_pct": "", "prior_decline_60d_pct": ""}
    win = h.tail(252)
    if len(win):
        hi = float(win["High"].max())
        lo = float(win["Low"].min())
        if hi > 0:
            out["pct_from_52w_high"] = round((cl - hi) / hi * 100, 2)
        if lo > 0:
            out["pct_from_52w_low"] = round((cl - lo) / lo * 100, 2)
    pc = prior["Close"]
    for n, key in ((20, "prior_decline_20d_pct"), (60, "prior_decline_60d_pct")):
        if len(pc) >= n + 1:
            c0 = float(pc.iloc[-(n + 1)])
            c1 = float(pc.iloc[-1])
            if c0 > 0:
                out[key] = round((c1 - c0) / c0 * 100, 2)
    return out


def day_change_pct(ticker, scan_date):
    """(close - prev_close)/prev_close*100 for a single ticker on scan_date."""
    try:
        h = yf.Ticker(ticker).history(start=str(scan_date - timedelta(days=10)),
                                      end=str(scan_date + timedelta(days=1)), auto_adjust=True)
        if len(h) < 2:
            return None
        h = h[h.index.date <= scan_date]
        return round((h["Close"].iloc[-1] / h["Close"].iloc[-2] - 1) * 100, 2)
    except Exception:
        return None


# ── Finviz candidate fetch ───────────────────────────────────────────────────
def fetch_finviz(exchange, change_filter):
    ov = Overview()
    ov.set_filter(filters_dict={"Exchange": exchange, "Change": change_filter})
    df = ov.screener_view()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["_exchange"] = exchange
    return df


def get_candidates():
    frames = []
    cf = config.FINVIZ_CHANGE_PREFILTER
    for ex in config.EXCHANGES:
        try:
            df = fetch_finviz(ex, cf)
        except Exception as e:
            log.warning("Finviz %s with '%s' failed (%s); retrying '%s'",
                        ex, cf, e, config.FINVIZ_CHANGE_FALLBACK)
            try:
                df = fetch_finviz(ex, config.FINVIZ_CHANGE_FALLBACK)
            except Exception as e2:
                log.error("Finviz %s failed entirely: %s", ex, e2)
                df = pd.DataFrame()
        if not df.empty:
            frames.append(df)
        log.info("Finviz %s: %d rows", ex, 0 if df is None else len(df))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["Ticker"])


# ── regime ───────────────────────────────────────────────────────────────────
def etf_change(symbol, scan_date, _cache={}):
    if symbol in _cache:
        return _cache[symbol]
    val = day_change_pct(symbol, scan_date)
    _cache[symbol] = val
    return val


def classify_drop_type(spy_chg, sector_chg):
    if spy_chg is not None and spy_chg <= config.RISK_OFF_SPY_PCT:
        return "systemic"
    if sector_chg is not None and sector_chg <= -1.5:
        return "sector"
    return "idiosyncratic"


def market_regime(spy_chg):
    if spy_chg is None:
        return "unknown"
    if spy_chg <= config.RISK_OFF_SPY_PCT:
        return "risk_off"
    if spy_chg >= 1.0:
        return "risk_on"
    return "neutral"


# ── per-candidate snapshot ───────────────────────────────────────────────────
def build_snapshot(row, scan_date, spy_chg, now_et):
    ticker = str(row.get("Ticker", "")).strip().upper()
    if not ticker:
        return None, "no_ticker"

    # Floor stage 1 (cheap, from Finviz): price + market cap
    fz_price = parse_num(row.get("Price"))
    mc = parse_market_cap(row.get("Market Cap"))
    if fz_price is None or fz_price != fz_price or fz_price < config.MIN_PRICE:
        return None, "below_min_price"
    if mc is None or mc != mc or mc < config.MIN_MARKET_CAP:
        return None, "below_min_cap"

    # yfinance OHLC + history for the from-open rule and ADV
    try:
        h = yf.Ticker(ticker).history(
            start=str(scan_date - timedelta(days=config.EOD_HISTORY_DAYS)),
            end=str(scan_date + timedelta(days=1)), auto_adjust=True)
    except Exception:
        return None, "yf_error"
    if h.empty:
        return None, "no_yf_data"
    h = h[h.index.date <= scan_date]
    today = h[h.index.date == scan_date]
    prior = h[h.index.date < scan_date]
    if today.empty or prior.empty:
        return None, "no_session_bar"

    bar = today.iloc[-1]
    o, hi, lo, cl = float(bar["Open"]), float(bar["High"]), float(bar["Low"]), float(bar["Close"])
    vol = int(bar["Volume"])
    prev_close = float(prior["Close"].iloc[-1])
    if o <= 0:
        return None, "bad_open"

    drop_from_open = round((lo - o) / o * 100, 2)        # low-so-far vs open
    close_from_open = round((cl - o) / o * 100, 2)
    pct_prevclose = round((cl - prev_close) / prev_close * 100, 2)

    # Floor stage 2: ADV$ + exact from-open trigger
    avg_vol_20 = float(prior["Volume"].tail(20).mean()) if len(prior) >= 5 else None
    adv_dollar = round(avg_vol_20 * cl, 0) if avg_vol_20 else None
    if adv_dollar is None or adv_dollar < config.MIN_ADV_DOLLAR:
        return None, "below_min_adv"
    if drop_from_open > -config.DROP_THRESHOLD_FROM_OPEN:
        return None, "drop_below_threshold"

    sector = row.get("Sector") or ""
    etf = config.SECTOR_ETF.get(sector)
    sec_chg = etf_change(etf, scan_date) if etf else None

    snap = {
        "scan_date": str(scan_date), "ticker": ticker, "exchange": row.get("_exchange", ""),
        "company_name": row.get("Company", ""), "sector": sector,
        "industry": row.get("Industry", ""), "country": row.get("Country", ""),
        "detected_at": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "market_cap": int(mc), "market_cap_category": config.classify_market_cap(mc),
        "liquidity_bucket": config.classify_market_cap(mc),
        "price": round(cl, 2), "open": round(o, 2), "high": round(hi, 2),
        "low_so_far": round(lo, 2), "prev_close": round(prev_close, 2),
        "drop_pct_from_open": drop_from_open, "close_pct_from_open": close_from_open,
        "pct_change_prevclose": pct_prevclose,
        "volume": vol, "avg_volume_20d": int(avg_vol_20) if avg_vol_20 else "",
        "adv_dollar": int(adv_dollar), "volume_ratio": round(vol / avg_vol_20, 2) if avg_vol_20 else "",
        "rsi_14": rsi_14(h["Close"]),
        "spy_change_pct": spy_chg, "sector_etf": etf or "",
        "sector_etf_change_pct": sec_chg, "market_regime": market_regime(spy_chg),
        "drop_type": classify_drop_type(spy_chg, sec_chg),
        "scanned_at": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "source": "eod_close", "drop_kind": "intraday_drop",
    }
    snap.update(prior_context(h, prior, cl))   # descriptive context, not a signal
    return snap, "ok"


def scan(scan_date):
    cands = get_candidates()
    log.info("Total Finviz candidates (pre-floor): %d", len(cands))
    if cands.empty:
        return [], {}
    spy_chg = day_change_pct(config.MARKET_PROXY, scan_date)
    log.info("Regime: SPY %s%% on %s -> %s",
             spy_chg, scan_date, market_regime(spy_chg))
    now_et = datetime.now(ET)
    rows, reasons = [], {}
    for i, (_, r) in enumerate(cands.iterrows(), 1):
        snap, reason = build_snapshot(r, scan_date, spy_chg, now_et)
        reasons[reason] = reasons.get(reason, 0) + 1
        if snap:
            rows.append(snap)
        time.sleep(config.RATE_LIMIT_SLEEP)
    log.info("Passed hard floor + trigger: %d / %d", len(rows), len(cands))
    log.info("Reject reasons: %s", reasons)
    return rows, reasons


def to_matrix(rows):
    return [[("" if r.get(c) is None else r.get(c)) for c in HEADER] for r in rows]


SUMMARY_HEADER = [
    "scan_date", "total_finviz_candidates", "passed_floor",
    "below_min_price", "below_min_cap", "below_min_adv", "drop_below_threshold",
    "other_rejects", "scanned_at",
]


def build_summary(scan_date, reasons):
    """One daily collection-health row from the reject-reason counter."""
    known = {"ok", "below_min_price", "below_min_cap", "below_min_adv",
             "drop_below_threshold"}
    total = sum(reasons.values())
    other = sum(v for k, v in reasons.items() if k not in known)
    return {
        "scan_date": str(scan_date),
        "total_finviz_candidates": total,
        "passed_floor": reasons.get("ok", 0),
        "below_min_price": reasons.get("below_min_price", 0),
        "below_min_cap": reasons.get("below_min_cap", 0),
        "below_min_adv": reasons.get("below_min_adv", 0),
        "drop_below_threshold": reasons.get("drop_below_threshold", 0),
        "other_rejects": other,
        "scanned_at": datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    scan_date = last_trading_day(args.date or date.today())
    log.info("Scan date: %s", scan_date)
    rows, reasons = scan(scan_date)

    if args.dry_run or not config.SHEET_ID:
        if not config.SHEET_ID and not args.dry_run:
            log.warning("No SHEET_ID configured -> dry-run only.")
        print("\n--- DRY RUN: %d watchlist rows ---" % len(rows))
        if rows:
            import json
            sample = dict(rows[0])
            print("Sample row:\n" + json.dumps(sample, indent=2, default=str, ensure_ascii=False))
        return rows

    import sheets_manager as sm
    # intraday rows take precedence — don't overwrite a (date,ticker) already
    # captured live intraday with a coarser EOD-close row.
    eh, ed = sm.read_rows(config.SHEET_ID, config.TAB_WATCHLIST)
    intraday_keys = set()
    if ed and "source" in eh:
        si, di, ti = eh.index("source"), eh.index("scan_date"), eh.index("ticker")
        intraday_keys = {(r[di], r[ti]) for r in ed if len(r) > si and r[si] == "intraday"}
    rows_to_write = [r for r in rows if (r["scan_date"], r["ticker"]) not in intraday_keys]
    upd, ins, tot = sm.upsert_by_key(config.SHEET_ID, config.TAB_WATCHLIST, HEADER,
                                     rows_to_write, ["scan_date", "ticker"])
    log.info("watchlist_live: +%d new, %d updated (intraday-owned skipped: %d, tab total %d).",
             ins, upd, len(rows) - len(rows_to_write), tot)

    # daily collection-health row (persist reject breakdown beyond logs)
    try:
        sm.upsert_by_key(config.SHEET_ID, config.TAB_SUMMARY, SUMMARY_HEADER,
                         [build_summary(scan_date, reasons)], ["scan_date"])
        log.info("daily_summary row written for %s.", scan_date)
    except Exception as e:
        log.error("daily_summary write failed: %s", e)

    # point-in-time fundamentals snapshot for the same candidates (collection only)
    if rows:
        try:
            import fundamentals as fund
            frows = fund.collect([(r["scan_date"], r["ticker"]) for r in rows])
            fs, fn = fund.write(frows)
            log.info("Wrote fundamentals_snapshot: %d new rows (kept %d).", fn, fs)
        except Exception as e:
            log.error("fundamentals snapshot failed (watchlist still written): %s", e)
    return rows


if __name__ == "__main__":
    main()
