"""C0 gate-2 read-only diagnosis: live maturity per horizon + backfill universe +
survivorship gradient. NO writes (Sheet or disk) — pure read. Run via:
    uv run --with-requirements requirements.txt python research/horizon-sufficiency/diagnose_horizon_maturity.py
"""
import json
import os
from collections import Counter
from datetime import date, timedelta

import pandas as pd

H = [3, 5, 10, 15, 20, 30, 60, 90]
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIST = os.path.join(ROOT, "research", "historical")


def section(t):
    print(f"\n{'='*60}\n{t}\n{'='*60}")


# ---------- 1. LIVE: maturity per horizon from the Sheet ----------
section("1. LIVE DATA (Google Sheet) — maturity per horizon")
try:
    import config
    import sheets_manager as sm

    sid = config.SHEET_ID
    batch = sm.batch_read(sid, [config.TAB_WATCHLIST, config.TAB_POST, config.TAB_FORWARD_DAILY])

    wl_h, wl_r = batch[config.TAB_WATCHLIST]
    print(f"watchlist_live: {len(wl_r)} events")
    if wl_h and "drop_kind" in wl_h:
        i = wl_h.index("drop_kind")
        print("  by drop_kind:", dict(Counter(r[i] for r in wl_r if len(r) > i)))

    p_h, p_r = batch[config.TAB_POST]
    print(f"post_analysis: {len(p_r)} rows")
    if p_h:
        if "status" in p_h:
            si = p_h.index("status")
            print("  status:", dict(Counter(r[si] for r in p_r if len(r) > si)))
        if "forward_days_available" in p_h:
            fi = p_h.index("forward_days_available")
            fwd = []
            for r in p_r:
                if len(r) > fi:
                    try:
                        fwd.append(int(float(r[fi])))
                    except (ValueError, TypeError):
                        pass
            print(f"  forward_days_available: min={min(fwd) if fwd else '-'} max={max(fwd) if fwd else '-'}")
            print("  MATURITY per horizon k (events with >= k forward days):")
            for k in H:
                print(f"    D+{k:<3} reached by {sum(1 for v in fwd if v >= k):>4} / {len(fwd)} events")

    fd_h, fd_r = batch[config.TAB_FORWARD_DAILY]
    print(f"forward_daily: {len(fd_r)} rows")
    if fd_h and "day_offset" in fd_h:
        di = fd_h.index("day_offset")
        offs = []
        for r in fd_r:
            if len(r) > di:
                try:
                    offs.append(int(float(r[di])))
                except (ValueError, TypeError):
                    pass
        print(f"  day_offset range: {min(offs) if offs else '-'}..{max(offs) if offs else '-'}")
        print("  NOTE: live horizon is capped at config.POST_ANALYSIS_HORIZON =",
              config.POST_ANALYSIS_HORIZON, "→ no live D+k for k>20 BY CONSTRUCTION")
except Exception as e:
    print(f"LIVE READ FAILED ({type(e).__name__}: {e}) — reporting backfill only")


# ---------- 2. BACKFILL universe ----------
section("2. BACKFILL UNIVERSE (local, survivorship-biased proxy)")
cache_dir = os.path.join(HIST, "cache")
n_cache = len([f for f in os.listdir(cache_dir) if f.endswith(".parquet")]) if os.path.isdir(cache_dir) else 0
print(f"per-ticker OHLCV parquet files in cache/: {n_cache}")

events_pl = os.path.join(HIST, "events", "events_post_live.parquet")
if os.path.exists(events_pl):
    ev = pd.read_parquet(events_pl)
    print(f"events_post_live.parquet: shape={ev.shape}")
    print("  columns:", list(ev.columns)[:40])
    for c in ("scan_date", "date", "event_date"):
        if c in ev.columns:
            print(f"  {c} range: {ev[c].min()} .. {ev[c].max()}")
            break
    hcols = [c for c in ev.columns if any(str(k) in c for k in (30, 60, 90))]
    print("  cols mentioning 30/60/90 (possible extended-horizon backfill):", hcols[:20])


# ---------- 3. SURVIVORSHIP GRADIENT ----------
section("3. SURVIVORSHIP GRADIENT — delisted_miss proxy vs horizon")
slog = os.path.join(HIST, "events", "survivorship_log.json")
if os.path.exists(slog):
    with open(slog) as f:
        s = json.load(f)
    surv = s.get("survivorship", [])
    hist_end = pd.to_datetime(s.get("history_end"))
    print(f"attempted_symbols={s.get('attempted_symbols')}  tracked={len(surv)}  history_end={s.get('history_end')}")
    flagged = [t for t in surv if t.get("flags")]
    print(f"tickers with non-empty flags (delist/halt/split markers): {len(flagged)}")
    allflags = Counter(fl for t in surv for fl in t.get("flags", []))
    print("  flag types:", dict(allflags))
    # gradient: a ticker whose last_date precedes (history_end - k cal days) cannot
    # supply a +k forward window for an event dated near its last bar → proxy of how
    # many names "go dark" before horizon k. Grows with k = the survivorship gradient.
    last_dates = [pd.to_datetime(t["last_date"]) for t in surv if t.get("last_date")]
    print("  delisted_miss(k) PROXY = names whose data ends >k cal-days before history_end:")
    for k in H:
        cutoff = hist_end - timedelta(days=k)
        miss = sum(1 for d in last_dates if d < cutoff)
        print(f"    k={k:<3} → {miss:>4} / {len(last_dates)} names dark before D+{k}  ({100*miss/max(1,len(last_dates)):.1f}%)")

print("\n[done] read-only diagnosis complete — no writes performed.")
