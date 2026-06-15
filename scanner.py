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


def vix_close(scan_date, _cache={}):
    """^VIX close on scan_date — same for all tickers that day, fetched once per
    date (Nagel: reversal premium ~ VIX). Cache keyed by DATE so a multi-date
    backfill stays point-in-time. Descriptive context, NOT a signal."""
    if scan_date in _cache:
        return _cache[scan_date]
    val = ""
    try:
        h = yf.Ticker("^VIX").history(start=str(scan_date - timedelta(days=10)),
                                      end=str(scan_date + timedelta(days=1)), auto_adjust=True)
        h = h[h.index.date <= scan_date]
        val = round(float(h["Close"].iloc[-1]), 2) if len(h) else ""
    except Exception:
        pass
    _cache[scan_date] = val
    return val


def etf_momentum(symbol, scan_date, _cache={}):
    """(5d, 20d) trailing return of a sector ETF up to scan_date. Cache keyed by
    (symbol, DATE) — one fetch per ETF per date, and correct point-in-time when a
    backfill spans multiple scan_dates. Descriptive context, NOT a signal."""
    key = (symbol, scan_date)
    if key in _cache:
        return _cache[key]
    val = (None, None)
    try:
        h = yf.Ticker(symbol).history(start=str(scan_date - timedelta(days=60)),
                                      end=str(scan_date + timedelta(days=1)), auto_adjust=True)
        c = h[h.index.date <= scan_date]["Close"]
        m5 = round(float(c.iloc[-1] / c.iloc[-6] - 1) * 100, 2) if len(c) >= 6 else None
        m20 = round(float(c.iloc[-1] / c.iloc[-21] - 1) * 100, 2) if len(c) >= 21 else None
        val = (m5, m20)
    except Exception:
        pass
    _cache[key] = val
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
def build_snapshot(row, scan_date, spy_chg, vix, now_et):
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
    mom5, mom20 = etf_momentum(etf, scan_date) if etf else (None, None)
    drop_day_rel_vol = round(vol / avg_vol_20, 2) if avg_vol_20 else ""

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
        "vix_level": vix, "drop_day_rel_volume": drop_day_rel_vol,
        "sector_momentum_5d": mom5, "sector_momentum_20d": mom20,
    }
    snap.update(prior_context(h, prior, cl))   # descriptive context, not a signal
    return snap, "ok"


def scan(scan_date):
    cands = get_candidates()
    log.info("Total Finviz candidates (pre-floor): %d", len(cands))
    if cands.empty:
        return [], {}
    spy_chg = day_change_pct(config.MARKET_PROXY, scan_date)
    vix = vix_close(scan_date)                       # once per run (same for all tickers)
    log.info("Regime: SPY %s%% on %s -> %s | VIX %s",
             spy_chg, scan_date, market_regime(spy_chg), vix)
    now_et = datetime.now(ET)
    rows, reasons = [], {}
    for i, (_, r) in enumerate(cands.iterrows(), 1):
        snap, reason = build_snapshot(r, scan_date, spy_chg, vix, now_et)
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


def backfill_intraday_prior_context(scan_date):
    """Coverage fix (M3.6 gap): intraday_scanner stays light (no year-long pull in
    the 10-min loop), so source="intraday" rows lack prior-decline context. Fill it
    HERE in the once-a-day EOD run — only for this scan_date's intraday rows that are
    still missing it, one history pull per such ticker. Returns count filled.
    (Descriptive context only — no signal, no decision.)"""
    import sheets_manager as sm
    wh, wd = sm.read_rows(config.SHEET_ID, config.TAB_WATCHLIST)
    if not wd:
        return 0
    idx = {c: i for i, c in enumerate(wh)}
    if not all(k in idx for k in ("scan_date", "ticker", "source", "prior_decline_20d_pct")):
        return 0
    sdc, tkc, srcc, pcc = idx["scan_date"], idx["ticker"], idx["source"], idx["prior_decline_20d_pct"]
    need = [r[tkc] for r in wd
            if r[sdc] == str(scan_date) and r[srcc] == "intraday"
            and (pcc >= len(r) or r[pcc] in ("", None))]
    if not need:
        return 0
    log.info("Backfilling prior-decline for %d intraday rows of %s.", len(need), scan_date)
    rows = []
    for tk in need:
        try:
            h = yf.Ticker(tk).history(
                start=str(scan_date - timedelta(days=config.EOD_HISTORY_DAYS)),
                end=str(scan_date + timedelta(days=1)), auto_adjust=True)
            h = h[h.index.date <= scan_date]
            prior = h[h.index.date < scan_date]
            today = h[h.index.date == scan_date]
            if h.empty or today.empty:
                continue
            cl = float(today["Close"].iloc[-1])
            # partial row: upsert_by_key merges by column NAME, preserving all others
            rows.append({"scan_date": str(scan_date), "ticker": tk,
                         **prior_context(h, prior, cl)})
        except Exception as e:
            log.warning("backfill %s failed: %s", tk, e)
        time.sleep(config.RATE_LIMIT_SLEEP)
    if rows:
        sm.upsert_by_key(config.SHEET_ID, config.TAB_WATCHLIST, HEADER, rows,
                         ["scan_date", "ticker"])
    return len(rows)


# context fields filled by this one-time backfill (descriptive — collection only)
CONTEXT_FIELDS = ["pct_from_52w_high", "pct_from_52w_low",
                  "prior_decline_20d_pct", "prior_decline_60d_pct",
                  "vix_level", "drop_day_rel_volume",
                  "sector_momentum_5d", "sector_momentum_20d"]


def _context_for_row(scan_d, ticker, sector):
    """Compute all CONTEXT_FIELDS point-in-time (<= scan_d) from ONE history pull.
    Returns a partial dict (scan_date+ticker+fields) or None if no bar on scan_d."""
    h = yf.Ticker(ticker).history(
        start=str(scan_d - timedelta(days=config.EOD_HISTORY_DAYS)),
        end=str(scan_d + timedelta(days=1)), auto_adjust=True)
    h = h[h.index.date <= scan_d]
    prior = h[h.index.date < scan_d]
    today = h[h.index.date == scan_d]
    if h.empty or today.empty:
        return None
    cl = float(today["Close"].iloc[-1])
    vol = float(today["Volume"].iloc[-1])
    avg20 = float(prior["Volume"].tail(20).mean()) if len(prior) >= 5 else None
    rel = round(vol / avg20, 2) if avg20 else ""
    etf = config.SECTOR_ETF.get(sector)
    m5, m20 = etf_momentum(etf, scan_d) if etf else (None, None)
    return {"scan_date": str(scan_d), "ticker": ticker,
            "vix_level": vix_close(scan_d), "drop_day_rel_volume": rel,
            "sector_momentum_5d": m5, "sector_momentum_20d": m20,
            **prior_context(h, prior, cl)}


def backfill_missing_context(dry_run=False):
    """ONE-TIME backfill: fill the descriptive context fields for every
    watchlist_live row (any source / any scan_date) that is missing at least one
    of them. point-in-time per the row's OWN scan_date (history sliced <= scan_date;
    VIX/sector-momentum of that day). Partial merge-safe upsert by (scan_date,ticker)
    — full rows are untouched, no field is overwritten. Returns (computed_rows,
    n_targets). NOT wired into the daily workflow. Collection only — no decision."""
    import sheets_manager as sm
    wh, wd = sm.read_rows(config.SHEET_ID, config.TAB_WATCHLIST)
    if not wd:
        log.info("watchlist_live empty — nothing to backfill.")
        return [], 0
    idx = {c: i for i, c in enumerate(wh)}
    if not all(k in idx for k in ("scan_date", "ticker")):
        log.error("watchlist_live missing scan_date/ticker columns.")
        return [], 0

    def row_needs_context(r):
        # a field is "missing" if its column is absent from the live header (schema
        # not migrated yet) OR present-but-blank in this row.
        for c in CONTEXT_FIELDS:
            if c not in idx:
                return True
            i = idx[c]
            if i >= len(r) or r[i] in ("", None):
                return True
        return False

    targets = []
    for r in wd:
        sd, tk = r[idx["scan_date"]], r[idx["ticker"]]
        if not sd or not tk:
            continue
        if row_needs_context(r):
            sector = r[idx["sector"]] if "sector" in idx and idx["sector"] < len(r) else ""
            targets.append((sd, tk, sector))
    log.info("Context backfill: %d/%d rows missing >=1 of %d context fields.",
             len(targets), len(wd), len(CONTEXT_FIELDS))

    out = []
    for sd, tk, sector in targets:
        try:
            scan_d = datetime.strptime(sd, "%Y-%m-%d").date()
        except ValueError:
            log.warning("backfill skip bad date %s %s", sd, tk)
            continue
        try:
            row = _context_for_row(scan_d, tk, sector)
            if row is None:
                log.warning("backfill %s %s: no bar on scan_date — skipped.", sd, tk)
                continue
            out.append(row)
            log.info("ctx %s %s: 52wH=%s 52wL=%s d20=%s d60=%s vix=%s relvol=%s sm5=%s sm20=%s",
                     sd, tk, row["pct_from_52w_high"], row["pct_from_52w_low"],
                     row["prior_decline_20d_pct"], row["prior_decline_60d_pct"],
                     row["vix_level"], row["drop_day_rel_volume"],
                     row["sector_momentum_5d"], row["sector_momentum_20d"])
        except Exception as e:
            log.warning("backfill %s %s failed: %s", sd, tk, e)
        time.sleep(config.RATE_LIMIT_SLEEP)

    if out and not dry_run:
        upd, ins, tot = sm.upsert_by_key(config.SHEET_ID, config.TAB_WATCHLIST, HEADER,
                                         out, ["scan_date", "ticker"])
        log.info("Context backfill written: %d rows updated (tab total %d).", upd, tot)
    return out, len(targets)


def backfill_missing_tags(dry_run=False):
    """ONE-TIME: fill drop_kind + source for legacy watchlist rows (pre-M3.4) whose
    drop_kind is blank. drop_kind -> "intraday_drop" (their original capture, and
    what the dashboard coalesce already assumes). source -> kept if already set,
    else inferred: "intraday" when an intraday-path field is present (first_cross_at
    / scans_count), otherwise "eod_close" (the EOD scanner is the canonical daily
    capture). Partial merge-safe upsert by (scan_date,ticker) — writes only these
    two fields, never overwrites a row already tagged. Returns (rows, n_targets)."""
    import sheets_manager as sm
    wh, wd = sm.read_rows(config.SHEET_ID, config.TAB_WATCHLIST)
    if not wd:
        log.info("watchlist_live empty — nothing to tag.")
        return [], 0
    idx = {c: i for i, c in enumerate(wh)}
    if not all(k in idx for k in ("scan_date", "ticker")):
        log.error("watchlist_live missing scan_date/ticker columns.")
        return [], 0

    def val(r, c):
        i = idx.get(c)
        return r[i] if (i is not None and i < len(r)) else ""

    out = []
    for r in wd:
        sd, tk = val(r, "scan_date"), val(r, "ticker")
        if not sd or not tk:
            continue
        if val(r, "drop_kind") not in ("", None):
            continue                          # already tagged — don't touch
        src = val(r, "source")
        if src in ("", None):                 # infer from intraday-path presence
            has_path = bool(val(r, "first_cross_at") or val(r, "scans_count"))
            src = "intraday" if has_path else "eod_close"
        out.append({"scan_date": sd, "ticker": tk,
                    "drop_kind": "intraday_drop", "source": src})
    log.info("Tag backfill: %d watchlist rows missing drop_kind.", len(out))
    if out and not dry_run:
        upd, ins, tot = sm.upsert_by_key(config.SHEET_ID, config.TAB_WATCHLIST, HEADER,
                                         out, ["scan_date", "ticker"])
        log.info("Tag backfill written: %d rows updated (tab total %d).", upd, tot)
    return out, len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backfill-context", action="store_true",
                    help="ONE-TIME: fill descriptive context fields for existing "
                         "watchlist rows missing them (point-in-time). No scan.")
    ap.add_argument("--backfill-tags", action="store_true",
                    help="ONE-TIME: fill drop_kind/source for legacy rows missing "
                         "them. No scan.")
    args = ap.parse_args()

    # one-time context backfill path (does NOT scan; not in the daily workflow)
    if args.backfill_context:
        if not config.SHEET_ID:
            log.error("No SHEET_ID configured — cannot backfill context.")
            return []
        out, ntargets = backfill_missing_context(dry_run=args.dry_run)
        mode = "DRY RUN" if args.dry_run else "WROTE"
        print(f"\n--- BACKFILL CONTEXT ({mode}): {ntargets} rows missing context; "
              f"computed {len(out)} ---")
        if out:
            import json
            print(json.dumps(out[0], indent=2, default=str, ensure_ascii=False))
        return out

    # one-time tag backfill (drop_kind/source for legacy rows) — no scan
    if args.backfill_tags:
        if not config.SHEET_ID:
            log.error("No SHEET_ID configured — cannot backfill tags.")
            return []
        out, n = backfill_missing_tags(dry_run=args.dry_run)
        mode = "DRY RUN" if args.dry_run else "WROTE"
        print(f"\n--- BACKFILL TAGS ({mode}): {n} rows missing drop_kind ---")
        for r in out:
            print(f"  {r['scan_date']} {r['ticker']}: drop_kind={r['drop_kind']} source={r['source']}")
        return out

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

    # coverage fix: fill prior-decline for this day's intraday-captured rows
    try:
        n = backfill_intraday_prior_context(scan_date)
        if n:
            log.info("Backfilled prior-decline for %d intraday rows.", n)
    except Exception as e:
        log.error("intraday prior-decline backfill failed: %s", e)
    return rows


if __name__ == "__main__":
    main()
