"""fundamentals.py — ReboundPro point-in-time Finviz fundamentals snapshot.

Pulls the full Finviz quote (ticker_fundament, ~90 fields) per candidate and
stores it to the `fundamentals_snapshot` tab, keyed by (scan_date, ticker).
Some fields (Short Float, Inst Own, Recom, Perf*) cannot be reconstructed
later — so they are captured AS-IS at detection time.

Collection only — NO scoring / signals / ranking.

Usage:
    python fundamentals.py                 # backfill all watchlist rows missing fundamentals
    python fundamentals.py --date 2026-06-12
    python fundamentals.py --force         # re-pull even if already captured
"""
import argparse
import logging
import time
from datetime import datetime

import pytz
from finvizfinance.quote import finvizfinance

import config

ET = pytz.timezone("America/New_York")
log = logging.getLogger("fundamentals")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")

# header: keys + clean numeric parses + 52W distance parses
FUND_HEADER = (["scan_date", "ticker", "captured_at"]
               + config.FINVIZ_FUNDAMENT_FIELDS
               + [f + "_num" for f in config.FUND_NUMERIC]
               + ["52W High_dist_num", "52W Low_dist_num"])


def parse_num(s):
    """Clean numeric: strip %, commas, B/M/K/T suffix. First token of compound."""
    if s is None:
        return None
    s = str(s).strip()
    if s in ("", "-", "- -", "—"):
        return None
    s = s.split()[0].replace(",", "").replace("%", "").replace("$", "")
    if not s:
        return None
    mult = 1.0
    if s[-1] in "BMKT":
        mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[s[-1]]
        s = s[:-1]
    try:
        return round(float(s) * mult, 6)
    except ValueError:
        return None


def dist_token(s):
    """'133.86 -38.44%' -> -38.44 (distance-from-52W as Finviz reports it)."""
    if not s:
        return None
    parts = str(s).split()
    return parse_num(parts[1]) if len(parts) >= 2 else None


def fetch(ticker):
    return finvizfinance(ticker).ticker_fundament()


def build_row(scan_date, ticker, raw, captured_at):
    row = {"scan_date": scan_date, "ticker": ticker, "captured_at": captured_at}
    for f in config.FINVIZ_FUNDAMENT_FIELDS:
        v = raw.get(f, "")
        row[f] = "" if v is None else str(v).replace("\n", " ").strip()
    for f in config.FUND_NUMERIC:
        row[f + "_num"] = parse_num(raw.get(f))
    row["52W High_dist_num"] = dist_token(raw.get("52W High"))
    row["52W Low_dist_num"] = dist_token(raw.get("52W Low"))
    return row


def collect(pairs):
    """pairs: iterable of (scan_date, ticker). Returns list of row dicts."""
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S %Z")
    rows, n_fields = [], 0
    for sd, tk in pairs:
        try:
            raw = fetch(tk)
            row = build_row(sd, tk, raw, now)
            n_fields = sum(1 for f in config.FINVIZ_FUNDAMENT_FIELDS if row.get(f))
            rows.append(row)
            log.info("fundamentals %s %s: %d/%d fields", sd, tk, n_fields,
                     len(config.FINVIZ_FUNDAMENT_FIELDS))
        except Exception as e:
            log.warning("fundamentals %s %s FAILED: %s", sd, tk, e)
            rows.append({"scan_date": sd, "ticker": tk, "captured_at": now,
                         "Company": f"FETCH_ERROR:{e}"})
        time.sleep(config.RATE_LIMIT_SLEEP)
    return rows


def to_matrix(rows):
    return [[("" if r.get(c) is None else r.get(c)) for c in FUND_HEADER] for r in rows]


def write(rows):
    import sheets_manager as sm
    return sm.upsert_rows(config.SHEET_ID, config.TAB_FUNDAMENTALS, FUND_HEADER,
                          to_matrix(rows), date_col="scan_date")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="only this scan_date")
    ap.add_argument("--force", action="store_true", help="re-pull even if captured")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not config.SHEET_ID:
        log.error("No SHEET_ID configured.")
        return []

    import sheets_manager as sm
    wh, wd = sm.read_rows(config.SHEET_ID, config.TAB_WATCHLIST)
    if not wd:
        log.info("watchlist_live empty — nothing to enrich.")
        return []
    wi = {c: i for i, c in enumerate(wh)}
    pairs = [(r[wi["scan_date"]], r[wi["ticker"]]) for r in wd]
    if args.date:
        pairs = [p for p in pairs if p[0] == args.date]

    # skip already-captured (unless --force)
    if not args.force:
        fh, fd = sm.read_rows(config.SHEET_ID, config.TAB_FUNDAMENTALS)
        if fd:
            fi = {c: i for i, c in enumerate(fh)}
            have = {(r[fi["scan_date"]], r[fi["ticker"]]) for r in fd}
            before = len(pairs)
            pairs = [p for p in pairs if p not in have]
            log.info("Skipping %d already-captured; %d to fetch.", before - len(pairs), len(pairs))

    if not pairs:
        log.info("Nothing to fetch.")
        return []

    rows = collect(pairs)
    if args.dry_run:
        print(f"DRY RUN: would write {len(rows)} fundamentals rows ({len(FUND_HEADER)} cols).")
        return rows
    surv, new = write(rows)
    log.info("Wrote fundamentals_snapshot: %d new rows (kept %d).", new, surv)
    return rows


if __name__ == "__main__":
    main()
