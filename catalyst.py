"""catalyst.py — ReboundPro point-in-time NEWS capture (Finnhub).

For each drop candidate, pull Finnhub company-news in a window around scan_date
and store it RAW to the `news_snapshot` tab, keyed by (scan_date, ticker).
Also flags earnings-proximity from the Finnhub earnings calendar.

COLLECTION ONLY — no filtering, no veto, no classification, no scoring. (LLM
catalyst classification from the stored headlines is a later M4/M5 step.)

Runs once/day at EOD (NOT in the 10-min intraday loop — Finnhub free tier is
rate-limited). Captures all of the day's candidates (intraday + EOD).

No-op (logged) if FINNHUB_API_KEY is unset, so it never breaks the EOD pipeline.

Usage:
    python catalyst.py                       # capture today's watchlist (missing only)
    python catalyst.py --date 2026-06-12
    python catalyst.py --force               # re-pull even if captured
    python catalyst.py --selftest ASTS 2026-06-12
"""
import argparse
import logging
import time
from datetime import date, datetime, timedelta, timezone

import requests

import config

log = logging.getLogger("catalyst")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")

BASE = "https://finnhub.io/api/v1"

NEWS_HEADER = ["scan_date", "ticker", "captured_at", "news_count", "has_news",
               "earnings_within_7d"]
for _i in range(1, config.NEWS_MAX_HEADLINES + 1):
    NEWS_HEADER += [f"headline_{_i}", f"datetime_{_i}", f"source_{_i}", f"url_{_i}"]


def _get(path, params):
    params = {**params, "token": config.FINNHUB_API_KEY}
    r = requests.get(f"{BASE}/{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_news(ticker, frm, to):
    data = _get("company-news", {"symbol": ticker, "from": frm, "to": to})
    if not isinstance(data, list):
        return []
    # most-recent first
    return sorted(data, key=lambda d: d.get("datetime", 0), reverse=True)


def earnings_near(ticker, scan_date, window):
    frm = str(scan_date - timedelta(days=window))
    to = str(scan_date + timedelta(days=window))
    try:
        data = _get("calendar/earnings", {"symbol": ticker, "from": frm, "to": to})
        return bool(data.get("earningsCalendar"))
    except Exception:
        return ""


def build_row(scan_date, ticker, news, earnings_flag, now):
    row = {"scan_date": str(scan_date), "ticker": ticker, "captured_at": now,
           "news_count": len(news), "has_news": len(news) > 0,
           "earnings_within_7d": earnings_flag}
    for i in range(1, config.NEWS_MAX_HEADLINES + 1):
        n = news[i - 1] if i - 1 < len(news) else None
        if n:
            ts = n.get("datetime")
            iso = (datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                   if ts else "")
            row[f"headline_{i}"] = str(n.get("headline", "")).replace("\n", " ").strip()
            row[f"datetime_{i}"] = iso
            row[f"source_{i}"] = n.get("source", "")
            row[f"url_{i}"] = n.get("url", "")
        else:
            row[f"headline_{i}"] = row[f"datetime_{i}"] = row[f"source_{i}"] = row[f"url_{i}"] = ""
    return row


def capture_one(scan_date, ticker):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    frm = str(scan_date - timedelta(days=config.NEWS_LOOKBACK_DAYS))
    to = str(scan_date)
    news = fetch_news(ticker, frm, to)
    eflag = earnings_near(ticker, scan_date, config.NEWS_EARNINGS_WINDOW_DAYS)
    return build_row(scan_date, ticker, news, eflag, now)


def collect(pairs):
    rows = []
    for sd, tk in pairs:
        try:
            row = capture_one(datetime.strptime(sd, "%Y-%m-%d").date() if isinstance(sd, str) else sd, tk)
            rows.append(row)
            log.info("news %s %s: count=%s earnings=%s", sd, tk, row["news_count"],
                     row["earnings_within_7d"])
        except Exception as e:
            log.warning("news %s %s FAILED: %s", sd, tk, e)
            rows.append({"scan_date": str(sd), "ticker": tk, "news_count": "",
                         "has_news": f"FETCH_ERROR:{e}"})
        time.sleep(config.FINNHUB_RATE_SLEEP)
    return rows


def write(rows):
    import sheets_manager as sm
    return sm.upsert_by_key(config.SHEET_ID, config.TAB_NEWS, NEWS_HEADER, rows,
                            ["scan_date", "ticker"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", nargs=2, metavar=("TICKER", "DATE"), default=None)
    args = ap.parse_args()

    if not config.FINNHUB_API_KEY:
        log.warning("FINNHUB_API_KEY unset — news capture skipped (no-op). "
                    "Pipeline continues normally.")
        return []

    if args.selftest:
        import json
        t, d = args.selftest[0].upper(), datetime.strptime(args.selftest[1], "%Y-%m-%d").date()
        print(json.dumps(capture_one(d, t), indent=2, ensure_ascii=False))
        return

    if not config.SHEET_ID:
        log.error("No SHEET_ID configured.")
        return []

    import sheets_manager as sm
    wh, wd = sm.read_rows(config.SHEET_ID, config.TAB_WATCHLIST)
    if not wd:
        log.info("watchlist_live empty — nothing to capture.")
        return []
    wi = {c: i for i, c in enumerate(wh)}
    pairs = [(r[wi["scan_date"]], r[wi["ticker"]]) for r in wd]
    if args.date:
        pairs = [p for p in pairs if p[0] == args.date]

    if not args.force:
        nh, nd = sm.read_rows(config.SHEET_ID, config.TAB_NEWS)
        if nd:
            ni = {c: i for i, c in enumerate(nh)}
            have = {(r[ni["scan_date"]], r[ni["ticker"]]) for r in nd}
            before = len(pairs)
            pairs = [p for p in pairs if p not in have]
            log.info("Skipping %d already-captured; %d to fetch.", before - len(pairs), len(pairs))

    if not pairs:
        log.info("Nothing to fetch.")
        return []

    rows = collect(pairs)
    if args.dry_run:
        print(f"DRY RUN: would write {len(rows)} news rows ({len(NEWS_HEADER)} cols).")
        return rows
    upd, ins, tot = write(rows)
    log.info("news_snapshot: +%d new, %d updated (tab total %d).", ins, upd, tot)
    return rows


if __name__ == "__main__":
    main()
