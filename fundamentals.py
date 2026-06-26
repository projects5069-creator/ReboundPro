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
import random
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


def _fetch_with_retry(ticker):
    """Finviz fetch with bounded exponential backoff + jitter. Raises the last
    exception only after FINVIZ_FETCH_RETRIES attempts (throttle is transient)."""
    last = None
    for attempt in range(config.FINVIZ_FETCH_RETRIES):
        try:
            return fetch(ticker)
        except Exception as e:  # noqa: BLE001 — Finviz parse/throttle errors vary
            last = e
            if attempt < config.FINVIZ_FETCH_RETRIES - 1:
                back = config.FINVIZ_FETCH_BACKOFF * (2 ** attempt) + random.uniform(0, 1)
                log.info("fundamentals %s retry %d/%d in %.1fs (%s)", ticker,
                         attempt + 1, config.FINVIZ_FETCH_RETRIES, back, e)
                time.sleep(back)
    raise last


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


def collect(pairs, time_budget_s=None):
    """pairs: iterable of (scan_date, ticker). Returns list of row dicts.

    Resilient to Finviz throttle (bounded retry/backoff). On exhausted failure
    writes NO row — no poison FETCH_ERROR stub (kept Group C clean; the pair stays
    uncaptured and the PIT guard in main() prevents a later-day re-fetch). Stops
    when `time_budget_s` (default config.FINVIZ_COLLECT_BUDGET_S) is exhausted so
    the EOD job never exceeds the Actions timeout.
    """
    budget = config.FINVIZ_COLLECT_BUDGET_S if time_budget_s is None else time_budget_s
    start = time.monotonic()
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S %Z")
    pairs = list(pairs)
    rows = []
    for i, (sd, tk) in enumerate(pairs):
        if time.monotonic() - start > budget:
            log.warning("fundamentals collect budget %.0fs exhausted; %d pairs unprocessed",
                        budget, len(pairs) - i)
            break
        try:
            row = build_row(sd, tk, _fetch_with_retry(tk), now)
            n_fields = sum(1 for f in config.FINVIZ_FUNDAMENT_FIELDS if row.get(f))
            rows.append(row)
            log.info("fundamentals %s %s: %d/%d fields", sd, tk, n_fields,
                     len(config.FINVIZ_FUNDAMENT_FIELDS))
        except Exception as e:  # noqa: BLE001
            log.warning("fundamentals %s %s FAILED after %d retries (no row written): %s",
                        sd, tk, config.FINVIZ_FETCH_RETRIES, e)
        time.sleep(config.FINVIZ_FETCH_SLEEP + random.uniform(0, 0.5))
    return rows


def select_target_pairs(watchlist_rows, header, target_date):
    """(scan_date,ticker) pairs for ONE scan_date only — never a cross-date sweep.
    A historical pair that failed at its D0 EOD run is therefore never swept up by
    a later-day run (which would stamp current Finviz values on an old D0)."""
    si, ti = header.index("scan_date"), header.index("ticker")
    return [(r[si], r[ti]) for r in watchlist_rows
            if len(r) > max(si, ti) and r[si] == target_date]


def is_pit_refused(target_date, today, force=False):
    """True when fetching `target_date` would be look-ahead: a PAST scan_date
    (current Finviz values on an old D0). Override only with --force."""
    return (not force) and target_date < today


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

    # PIT guard: only ONE scan_date per run, and never a PAST date without --force
    # (current Finviz values stamped on an old D0 = look-ahead → breaks Group C PIT).
    today = datetime.now(ET).strftime("%Y-%m-%d")
    target = args.date or today
    if is_pit_refused(target, today, args.force):
        log.error("Refusing fundamentals fetch for past scan_date %s (current Finviz "
                  "values on an old D0 = look-ahead). Re-run with --force only if you "
                  "deliberately accept the PIT violation.", target)
        return []

    import sheets_manager as sm
    wh, wd = sm.read_rows(config.SHEET_ID, config.TAB_WATCHLIST)
    if not wd:
        log.info("watchlist_live empty — nothing to enrich.")
        return []
    pairs = select_target_pairs(wd, wh, target)   # single scan_date — no cross-date sweep

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
