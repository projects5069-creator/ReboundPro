"""research/phase0/taskC_parity.py — TASK-C parity analysis (READ-ONLY).

Question (TASK-C): HYP-002's edge was discovered on DropsLab (close-to-close
>=10%/session, all-cap universe, n~3988). ReboundPro collects a DIFFERENT
population (intraday open->low >=10%  + gradual 5d; mid+large only). Do the
HYP-002 z-constants and the score<=-1.7733 LONG-decile threshold transfer to
ReboundPro's population, or must they be re-derived?

This script answers it with three layers (see docs/HYP-002 + the plan):
  1   ticker/date overlap between the two live datasets (per drop_kind)
  1b  DEFINITION re-derivation inside drops_raw (date-robust): of DropsLab
      close-to-close drops, what fraction ALSO satisfy ReboundPro's intraday
      open->low >=10% rule (and vice-versa)
  1c  UNIVERSE layer: how many DropsLab rows survive ReboundPro's hard
      liquidity floor (price>=$5, ADV$>=$5M, cap>=$300M)
  2   distress-factor distributions (pct_from_52w_high, rsi_14) across the 4
      populations vs the frozen discovery constants
  3   calibration transfer: apply the discovery z + threshold to ReboundPro,
      then re-derive ReboundPro's own mean/sd + bottom-decile cutoff

READ-ONLY GUARANTEE: both sheets are opened with the spreadsheets.readonly
OAuth scope, so the API itself rejects any write. Only get_all_records() is
called. No sheet is written, no live code / stub / scanner / workflow is
touched. Output is printed to stdout only (the decision memo is authored
separately from these numbers).

Run (after approval):
  cd ~/ReboundPro && uv run --with-requirements requirements.txt python \
      research/phase0/taskC_parity.py
"""
import os
import sys
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# ── frozen HYP-002 discovery constants (docs/HYP-002 lines 16-20) ────────────
MU_52W, SD_52W = -59.2650, 28.1903
MU_RSI, SD_RSI = 43.0331, 11.7443
SCORE_THRESH = -1.7733            # LONG = bottom decile
DROP = 10.0                       # % threshold (both systems)

# read-only scope → API rejects writes even if code tried
RO_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

DROPSLAB_CREDS = Path.home() / "DropsLab" / "google_credentials.json"
DROPSLAB_SHEET = "1XM-qId7HAwEu-8-1GGHcy3RoyyAnsYshjZfDrKFnTMI"
DROPSLAB_TAB = "drops_raw"

REBOUND_CREDS = Path(__file__).resolve().parents[2] / "google_credentials.json"
REBOUND_TAB = "watchlist_live"


def _hr(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _rebound_sheet_id():
    sid = os.environ.get("REBOUND_SHEET_ID", "").strip()
    if sid:
        return sid
    # fall back to local .env (do NOT print the value)
    env = Path(__file__).resolve().parents[2] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("REBOUND_SHEET_ID="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("REBOUND_SHEET_ID not set (env or .env).")


def ro_records(creds_path, sheet_id, tab):
    """Read-only fetch of a whole tab → DataFrame (str cells from gspread)."""
    creds = Credentials.from_service_account_file(str(creds_path), scopes=RO_SCOPES)
    client = gspread.authorize(creds)
    ws = client.open_by_key(sheet_id).worksheet(tab)
    return pd.DataFrame(ws.get_all_records())


def num(df, col):
    return pd.to_numeric(df.get(col), errors="coerce") if col in df.columns else pd.Series(dtype=float)


def describe(label, s):
    s = s.dropna()
    if s.empty:
        print(f"  {label:<34} n=0   (no data)")
        return
    print(f"  {label:<34} n={len(s):<5} mean={s.mean():+8.3f}  sd={s.std():7.3f}  "
          f"median={s.median():+8.3f}")


def long_rate(p52, rsi, mu52, sd52, murs, sdrs, thr):
    """Fraction with composite score <= thr, using the given z-calibration."""
    df = pd.DataFrame({"p": p52, "r": rsi}).dropna()
    if df.empty or sd52 == 0 or sdrs == 0:
        return None, 0
    score = -1.0 * ((df["p"] - mu52) / sd52) + 1.0 * ((df["r"] - murs) / sdrs)
    return float((score <= thr).mean()), len(df)


def main():
    # ── load both datasets (read-only) ──────────────────────────────────────
    _hr("LOAD (read-only, spreadsheets.readonly scope)")
    dl = ro_records(DROPSLAB_CREDS, DROPSLAB_SHEET, DROPSLAB_TAB)
    print(f"  DropsLab/{DROPSLAB_TAB}: {len(dl)} rows, {len(dl.columns)} cols")
    rb = ro_records(REBOUND_CREDS, _rebound_sheet_id(), REBOUND_TAB)
    print(f"  ReboundPro/{REBOUND_TAB}: {len(rb)} rows, {len(rb.columns)} cols")

    # numeric views — DropsLab
    dl_pct_change = num(dl, "pct_change")          # close vs prev_close
    dl_open, dl_low, dl_close = num(dl, "open"), num(dl, "low"), num(dl, "close")
    dl_cap = num(dl, "market_cap")
    dl_avgvol = num(dl, "avg_volume_10d")
    dl_52 = num(dl, "pct_from_52w_high")
    dl_rsi = num(dl, "rsi_14")
    dl_low_from_open = (dl_low - dl_open) / dl_open * 100.0      # ReboundPro-style

    # ── confirm DropsLab definition ─────────────────────────────────────────
    _hr("DropsLab drop definition sanity")
    meets_cc = dl_pct_change <= -DROP
    print(f"  rows with pct_change <= -{DROP:.0f}% (close-to-close): "
          f"{int(meets_cc.sum())}/{meets_cc.notna().sum()}")

    # ── 1b. definition re-derivation inside drops_raw (date-robust) ─────────
    _hr("1b. DEFINITION gap inside drops_raw (date-independent)")
    meets_intraday = dl_low_from_open <= -DROP
    both = (meets_cc & meets_intraday)
    base_cc = int(meets_cc.sum())
    if base_cc:
        print(f"  of {base_cc} close-to-close drops, also intraday open->low >=10%: "
              f"{int(both.sum())} ({100*both.sum()/base_cc:.1f}%)")
        print(f"  close-to-close drops that do NOT meet intraday rule:           "
              f"{base_cc-int(both.sum())} ({100*(base_cc-both.sum())/base_cc:.1f}%)")
    base_intra = int(meets_intraday.sum())
    if base_intra:
        print(f"  of {base_intra} intraday open->low drops, also close-to-close >=10%: "
              f"{int(both.sum())} ({100*both.sum()/base_intra:.1f}%)")

    # ── 1c. universe layer: ReboundPro liquidity floor on DropsLab ──────────
    _hr("1c. UNIVERSE gap — ReboundPro floor applied to DropsLab")
    adv_dollar = dl_close * dl_avgvol
    floor = (dl_close >= 5) & (adv_dollar >= 5_000_000) & (dl_cap >= 300_000_000)
    nfloor = int(floor.sum())
    print(f"  price>=$5 & ADV$>=$5M & cap>=$300M: {nfloor}/{len(dl)} "
          f"({100*nfloor/len(dl):.1f}%) survive ReboundPro's floor")
    if "market_cap_category" in dl.columns:
        print("  DropsLab market_cap_category breakdown (full sample):")
        print(dl["market_cap_category"].value_counts().to_string().replace("\n", "\n    "))

    # ── ReboundPro split by drop_kind ───────────────────────────────────────
    _hr("ReboundPro events by drop_kind")
    kind = rb.get("drop_kind", pd.Series([""] * len(rb))).fillna("").replace("", "legacy/intraday")
    print(kind.value_counts().to_string().replace("\n", "\n  "))
    src = rb.get("source", pd.Series([""] * len(rb))).fillna("")
    print("\n  source breakdown:")
    print(src.replace("", "(blank)").value_counts().to_string().replace("\n", "\n  "))
    # distress coverage (blank for source=intraday by design)
    print(f"\n  pct_from_52w_high non-null: {int(num(rb,'pct_from_52w_high').notna().sum())}/{len(rb)}")
    print(f"  rsi_14 non-null:           {int(num(rb,'rsi_14').notna().sum())}/{len(rb)}")

    rb_intra = rb[kind.isin(["intraday_drop", "legacy/intraday"])]
    rb_grad = rb[kind == "gradual_drop"]

    # ── 1. ticker/date overlap between the live datasets ────────────────────
    _hr("1. ticker/date overlap (live datasets)")
    def keyset(df, dcol, tcol):
        if dcol not in df.columns or tcol not in df.columns:
            return set()
        d = df[dcol].astype(str).str.strip().str[:10]
        t = df[tcol].astype(str).str.strip().str.upper()
        return set(zip(d, t))
    dl_keys = keyset(dl, "date", "ticker")
    for name, sub in [("intraday", rb_intra), ("gradual", rb_grad)]:
        rk = keyset(sub, "scan_date", "ticker")
        inter = dl_keys & rk
        print(f"  DropsLab ∩ ReboundPro-{name}: {len(inter)} "
              f"(DropsLab dates {_range(dl,'date')}, RB-{name} {_range(sub,'scan_date')}, n={len(sub)})")

    # ── 2. distress distributions across 4 populations ──────────────────────
    _hr("2. distress distributions vs discovery constants")
    print(f"  discovery: pct_from_52w_high mu={MU_52W} sd={SD_52W} | "
          f"rsi_14 mu={MU_RSI} sd={SD_RSI}")
    print("\n  pct_from_52w_high:")
    describe("DropsLab-all", dl_52)
    describe("DropsLab ∩ RB-floor", dl_52[floor])
    describe("ReboundPro-intraday", num(rb_intra, "pct_from_52w_high"))
    describe("ReboundPro-gradual", num(rb_grad, "pct_from_52w_high"))
    print("\n  rsi_14:")
    describe("DropsLab-all", dl_rsi)
    describe("DropsLab ∩ RB-floor", dl_rsi[floor])
    describe("ReboundPro-intraday", num(rb_intra, "rsi_14"))
    describe("ReboundPro-gradual", num(rb_grad, "rsi_14"))

    # ── 3. calibration transfer ─────────────────────────────────────────────
    _hr("3. calibration transfer (threshold -1.7733)")
    # apply DISCOVERY calibration to each population → expected LONG-rate ~10%
    for name, p, r in [
        ("DropsLab-all", dl_52, dl_rsi),
        ("DropsLab ∩ RB-floor", dl_52[floor], dl_rsi[floor]),
        ("ReboundPro-intraday", num(rb_intra, "pct_from_52w_high"), num(rb_intra, "rsi_14")),
        ("ReboundPro-gradual", num(rb_grad, "pct_from_52w_high"), num(rb_grad, "rsi_14")),
    ]:
        rate, n = long_rate(p, r, MU_52W, SD_52W, MU_RSI, SD_RSI, SCORE_THRESH)
        rate_s = f"{100*rate:.1f}%" if rate is not None else "n/a"
        print(f"  {name:<24} LONG-rate@discovery-calib = {rate_s:<7} (n={n}; ~10% ⇒ calibrated)")
    # re-derive ReboundPro-intraday's own decile cutoff
    p = num(rb_intra, "pct_from_52w_high")
    r = num(rb_intra, "rsi_14")
    d = pd.DataFrame({"p": p, "r": r}).dropna()
    if len(d) >= 10:
        z = -1.0 * ((d["p"] - d["p"].mean()) / d["p"].std()) + 1.0 * ((d["r"] - d["r"].mean()) / d["r"].std())
        print(f"\n  RB-intraday self-derived: pct_from_52w_high mu={d['p'].mean():+.3f} sd={d['p'].std():.3f} | "
              f"rsi_14 mu={d['r'].mean():+.3f} sd={d['r'].std():.3f}")
        print(f"  RB-intraday self bottom-decile cutoff = {z.quantile(0.10):+.4f} "
              f"(discovery cutoff was {SCORE_THRESH})")
    else:
        print(f"\n  RB-intraday: only {len(d)} rows with both factors — too few to re-derive a decile.")

    _hr("DONE — numbers above feed TASK-C_parity_memo.md")


def _range(df, col):
    if col not in df.columns or df.empty:
        return "n/a"
    d = df[col].astype(str).str.strip().str[:10]
    d = d[d != ""]
    return f"{d.min()}..{d.max()}" if not d.empty else "n/a"


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}", file=sys.stderr)
        raise
