"""backfill_sma.py — ONE-TIME CLI: backfill atr_pct, dist_sma50, dist_sma200 for
existing watchlist_live rows (point-in-time, DESCRIPTIVE / M5-safe features).

READS yfinance history (read-only) per past scan_date; computes the 3 metrics with
the same uniform `prior` SMA window as the live scanners; atr_pct gets full coverage
(recomputes atr_14 from prior on old intraday rows). WRITES only via partial
upsert_by_key (update-first, no clear, merge by key). split_halt_flag events skipped.

Run:
  cd ~/ReboundPro && uv run --with-requirements requirements.txt python backfill_sma.py --dry-run
  # review the fill counts, then run WITHOUT --dry-run to write.
"""
import argparse
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent


def _load_env(path):
    """Minimal .env loader (no python-dotenv dep) so config.SHEET_ID resolves
    locally. Never echoes values."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env(REPO / ".env")

import config  # noqa: E402
import scanner  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="compute + print counts, no write")
    args = ap.parse_args()
    if not config.SHEET_ID:
        raise SystemExit("REBOUND_SHEET_ID not set (.env not loaded?) — aborting.")

    out, n_targets, counts = scanner.backfill_sma_metrics(dry_run=args.dry_run)

    print("\n" + "=" * 64)
    print("SMA/ATR backfill — " + ("DRY-RUN (no write)" if args.dry_run else "LIVE (wrote via upsert)"))
    print("=" * 64)
    print("  (DESCRIPTIVE / M5-safe features — not signals)")
    print(f"  targets (rows missing >=1 metric, non-contaminated): {n_targets}")
    print(f"  split_halt skipped:                                  {counts.get('split_halt_skipped', 0)}")
    print("  fill counts per metric, by source (strata):")
    for m in ("atr_pct", "dist_sma50", "dist_sma200"):
        bysrc = counts.get(m, {})
        total = sum(bysrc.values())
        detail = "  ".join(f"{s}:{c}" for s, c in sorted(bysrc.items())) or "—"
        print(f"     {m:12s} filled={total:<5} [{detail}]")
    intr = {m: counts.get(m, {}).get("intraday", 0) for m in ("atr_pct", "dist_sma200")}
    print(f"  source=intraday coverage check → atr_pct:{intr['atr_pct']}  "
          f"dist_sma200:{intr['dist_sma200']}")


if __name__ == "__main__":
    main()
