"""gradual_scanner.py — ReboundPro M3 GRADUAL-drop scanner (separate hypothesis).

Finds NASDAQ+NYSE stocks whose latest close is >= GRADUAL_DROP_THRESHOLD below
the close GRADUAL_LOOKBACK_DAYS *trading* days ago — a slow decline, NOT a
one-day crash (that is intraday_drop, handled by scanner.py / intraday_scanner.py).
Applies the SAME hard liquidity floor and records a point-in-time row to
watchlist_live tagged drop_kind="gradual_drop".

Why separate: "fundamentally strong stocks that drifted down may mean-revert" is
a DIFFERENT dynamic from intraday over-reaction, so it is collected separately
and tested separately at M4.

⚠️ value-trap bias — "strong metrics -> rebound" is exactly the claim M4 must
   test, because cheap/strong-looking names can keep falling when the fundamentals
   really did break. Therefore here: fundamentals are captured as a FEATURE, never
   a filter/veto; there is NO entry decision; the net-edge verdict is deferred to
   M4 (MASTERPLAN §5), independently from intraday_drop.

Collection only — NO scoring / signals / ranking.

Dedup: a ticker captured (ANY drop_kind) within GRADUAL_DEDUP_WINDOW trading days
is NOT re-captured as gradual_drop — this is both the cross-strategy dedup
(intraday_drop wins) and the gradual self-cooldown (the 5-day drop persists for
days, so without it the same slow decline would re-fire daily).

Free data: finvizfinance screener "Performance" net (Week = last 5 trading days)
+ yfinance daily OHLC (exact rule re-confirmed) + SPY/sector-ETF regime. Reuses
scanner.py's pure helpers; does not touch its scan/snapshot logic.

Usage:
    python gradual_scanner.py --dry-run
    python gradual_scanner.py --date 2026-06-12 --dry-run
    python gradual_scanner.py                  # live: write to SHEET_ID
"""
import argparse
import logging
import time
from datetime import date, datetime, timedelta

import pandas as pd
import pytz
import yfinance as yf
import exchange_calendars as ec
from finvizfinance.screener.overview import Overview

import config
import scanner as sc

ET = pytz.timezone("America/New_York")
log = logging.getLogger("gradual")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")

HEADER = config.WATCHLIST_HEADER


# ── Finviz candidate fetch (Performance filter — distinct from scanner's Change) ─
def fetch_perf(exchange, perf):
    ov = Overview()
    ov.set_filter(filters_dict={"Exchange": exchange, "Performance": perf})
    df = ov.screener_view()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["_exchange"] = exchange
    return df


def get_candidates():
    frames = []
    pf = config.FINVIZ_PERF_PREFILTER
    for ex in config.EXCHANGES:
        try:
            df = fetch_perf(ex, pf)
        except Exception as e:
            log.warning("Finviz %s with '%s' failed (%s); retrying '%s'",
                        ex, pf, e, config.FINVIZ_PERF_FALLBACK)
            try:
                df = fetch_perf(ex, config.FINVIZ_PERF_FALLBACK)
            except Exception as e2:
                log.error("Finviz %s failed entirely: %s", ex, e2)
                df = pd.DataFrame()
        if not df.empty:
            frames.append(df)
        log.info("Finviz %s: %d rows", ex, 0 if df is None else len(df))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["Ticker"])


# ── dedup / cooldown ─────────────────────────────────────────────────────────
def recent_capture_set(wh, wd, scan_date, cal):
    """Tickers already captured (ANY drop_kind) within GRADUAL_DEDUP_WINDOW
    trading days of scan_date — to be skipped by the gradual scan."""
    if not wd or "ticker" not in wh or "scan_date" not in wh:
        return set()
    sessions = cal.sessions_in_range(
        pd.Timestamp(scan_date - timedelta(days=config.GRADUAL_DEDUP_WINDOW * 3 + 15)),
        pd.Timestamp(scan_date))
    if len(sessions) == 0:
        return set()
    n = config.GRADUAL_DEDUP_WINDOW
    cutoff = sessions[-(n + 1)].date() if len(sessions) > n else sessions[0].date()
    ti, di = wh.index("ticker"), wh.index("scan_date")
    out = set()
    for r in wd:
        if len(r) <= max(ti, di):
            continue
        try:
            sd = datetime.strptime(r[di], "%Y-%m-%d").date()
        except ValueError:
            continue
        if sd >= cutoff:
            out.add(str(r[ti]).strip().upper())
    return out


def ref_trading_date(scan_date, cal):
    """Date of the session GRADUAL_LOOKBACK_DAYS trading days before scan_date."""
    sessions = cal.sessions_in_range(
        pd.Timestamp(scan_date - timedelta(days=config.GRADUAL_LOOKBACK_DAYS * 4 + 15)),
        pd.Timestamp(scan_date))
    k = config.GRADUAL_LOOKBACK_DAYS
    if len(sessions) < k + 1:
        return None
    return sessions[-(k + 1)].date()


# ── per-candidate snapshot ───────────────────────────────────────────────────
def build_snapshot(row, scan_date, ref_date, spy_chg, vix, now):
    ticker = str(row.get("Ticker", "")).strip().upper()
    if not ticker:
        return None, "no_ticker"

    # Floor stage 1 (cheap, from Finviz): price + market cap
    fz_price = sc.parse_num(row.get("Price"))
    mc = sc.parse_market_cap(row.get("Market Cap"))
    if fz_price is None or fz_price != fz_price or fz_price < config.MIN_PRICE:
        return None, "below_min_price"
    if mc is None or mc != mc or mc < config.MIN_MARKET_CAP:
        return None, "below_min_cap"

    try:
        h = yf.Ticker(ticker).history(
            start=str(scan_date - timedelta(days=config.EOD_HISTORY_DAYS)),
            end=str(scan_date + timedelta(days=1)), auto_adjust=True)
    except Exception:
        return None, "yf_error"
    if h is None or h.empty:
        return None, "no_yf_data"
    h = h[h.index.date <= scan_date]
    today = h[h.index.date == scan_date]
    prior = h[h.index.date < scan_date]
    ref = h[h.index.date == ref_date]
    if today.empty or prior.empty:
        return None, "no_session_bar"
    if ref.empty:
        return None, "no_ref_bar"          # point-in-time: require the exact ref session

    bar = today.iloc[-1]
    o, hi, lo, cl = float(bar["Open"]), float(bar["High"]), float(bar["Low"]), float(bar["Close"])
    vol = int(bar["Volume"])
    prev_close = float(prior["Close"].iloc[-1])
    ref_close = float(ref["Close"].iloc[-1])
    if ref_close <= 0:
        return None, "bad_ref_close"

    drop_pct_window = round((cl - ref_close) / ref_close * 100, 2)
    if drop_pct_window > -config.GRADUAL_DROP_THRESHOLD:
        return None, "drop_below_threshold"

    # Floor stage 2: ADV$
    avg_vol_20 = float(prior["Volume"].tail(20).mean()) if len(prior) >= 5 else None
    adv_dollar = round(avg_vol_20 * cl, 0) if avg_vol_20 else None
    if adv_dollar is None or adv_dollar < config.MIN_ADV_DOLLAR:
        return None, "below_min_adv"

    sector = row.get("Sector") or ""
    etf = config.SECTOR_ETF.get(sector)
    sec_chg = sc.etf_change(etf, scan_date) if etf else None
    mom5, mom20 = sc.etf_momentum(etf, scan_date) if etf else (None, None)
    drop_day_rel_vol = round(vol / avg_vol_20, 2) if avg_vol_20 else ""

    snap = {
        "scan_date": str(scan_date), "ticker": ticker, "exchange": row.get("_exchange", ""),
        "company_name": row.get("Company", ""), "sector": sector,
        "industry": row.get("Industry", ""), "country": row.get("Country", ""),
        "detected_at": now, "market_cap": int(mc),
        "market_cap_category": config.classify_market_cap(mc),
        "liquidity_bucket": config.classify_market_cap(mc),
        "price": round(cl, 2), "open": round(o, 2), "high": round(hi, 2),
        "low_so_far": round(lo, 2), "prev_close": round(prev_close, 2),
        "drop_pct_from_open": "", "close_pct_from_open": "",
        "pct_change_prevclose": round((cl - prev_close) / prev_close * 100, 2),
        "volume": vol, "avg_volume_20d": int(avg_vol_20) if avg_vol_20 else "",
        "adv_dollar": int(adv_dollar),
        "volume_ratio": round(vol / avg_vol_20, 2) if avg_vol_20 else "",
        "rsi_14": sc.rsi_14(h["Close"]),
        "spy_change_pct": spy_chg, "sector_etf": etf or "",
        "sector_etf_change_pct": sec_chg, "market_regime": sc.market_regime(spy_chg),
        "drop_type": sc.classify_drop_type(spy_chg, sec_chg), "scanned_at": now,
        "source": "gradual_eod", "drop_kind": "gradual_drop",
        "lookback_trading_days": config.GRADUAL_LOOKBACK_DAYS,
        "drop_pct_window": drop_pct_window, "ref_close_window": round(ref_close, 2),
        "vix_level": vix, "drop_day_rel_volume": drop_day_rel_vol,
        "sector_momentum_5d": mom5, "sector_momentum_20d": mom20,
    }
    snap.update(sc.prior_context(h, prior, cl))   # descriptive context, not a signal
    return snap, "ok"


def scan(scan_date):
    import sheets_manager as sm
    cal = ec.get_calendar("XNYS")
    ref_date = ref_trading_date(scan_date, cal)
    if ref_date is None:
        log.error("Not enough trading sessions before %s to form a lookback window.", scan_date)
        return [], {}
    log.info("Gradual window: %s (D) vs %s (D-%d trading days)",
             scan_date, ref_date, config.GRADUAL_LOOKBACK_DAYS)

    cands = get_candidates()
    log.info("Finviz candidates (pre-floor): %d", len(cands))
    if cands.empty:
        return [], {}

    spy_chg = sc.day_change_pct(config.MARKET_PROXY, scan_date)
    vix = sc.vix_close(scan_date)                     # once per run (same for all tickers)
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S %Z")

    wh, wd = sm.read_rows(config.SHEET_ID, config.TAB_WATCHLIST) if config.SHEET_ID else ([], [])
    recent = recent_capture_set(wh, wd, scan_date, cal)
    log.info("Dedup set (captured within %d td): %d tickers",
             config.GRADUAL_DEDUP_WINDOW, len(recent))

    rows, reasons = [], {}
    for _, r in cands.iterrows():
        ticker = str(r.get("Ticker", "")).strip().upper()
        if ticker and ticker in recent:
            reasons["dedup_recent"] = reasons.get("dedup_recent", 0) + 1
            continue
        snap, why = build_snapshot(r, scan_date, ref_date, spy_chg, vix, now)
        reasons[why] = reasons.get(why, 0) + 1
        if snap:
            rows.append(snap)
        time.sleep(config.RATE_LIMIT_SLEEP)
    log.info("Passed floor + gradual trigger: %d (reasons: %s)", len(rows), reasons)
    return rows, reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    scan_date = sc.last_trading_day(args.date or date.today())
    log.info("Gradual scan date: %s", scan_date)
    rows, _ = scan(scan_date)

    if args.dry_run or not config.SHEET_ID:
        if not config.SHEET_ID and not args.dry_run:
            log.warning("No SHEET_ID configured -> dry-run only.")
        print(f"\n--- DRY RUN: {len(rows)} gradual_drop rows ---")
        if rows:
            import json
            print(json.dumps(rows[0], indent=2, default=str, ensure_ascii=False))
        return rows

    import sheets_manager as sm
    upd, ins, tot = sm.upsert_by_key(config.SHEET_ID, config.TAB_WATCHLIST, HEADER,
                                     rows, ["scan_date", "ticker"])
    log.info("watchlist_live (gradual): +%d new, %d updated (tab total %d).", ins, upd, tot)

    # point-in-time fundamentals snapshot for the same candidates (collection only,
    # same code as the EOD scanner; news + post_analysis + timeseries pick the rows
    # up automatically downstream).
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
