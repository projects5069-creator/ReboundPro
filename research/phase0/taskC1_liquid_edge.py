"""research/phase0/taskC1_liquid_edge.py — TASK-C.1 liquid-subset net edge (READ-ONLY).

Question: in the liquidity subset that MATCHES ReboundPro's universe (DropsLab
drops_raw restricted to price>=$5, ADV$>=$5M, cap>=$300M; n~591), does a
long-on-drop -> D5-close trade retain a NET-of-cost edge — or is it absent in
the liquid names (as the literature expects)?

PROXY / PRIOR on DropsLab — NOT validation. The only validation is ReboundPro's
own forward data at M4. Nothing here is an M4=GO signal or an M5 release.

Pre-registration (anti-bias, MASTERPLAN §5): the literature expects a weak/absent
net edge in liquid names. A LARGE result here is a red flag for
overfit/survivorship/look-ahead, reported as such — not celebrated.

READ-ONLY: DropsLab sheets opened with spreadsheets.readonly scope; only
get_all_records(). Optional ^VIX / SPY via yfinance are read-only network pulls.
No sheet write, no live code/stub/scanner/workflow touched. Output to stdout.

Run (after approval):
  cd ~/ReboundPro && uv run --with-requirements requirements.txt python \
      research/phase0/taskC1_liquid_edge.py
"""
from pathlib import Path

import gspread
import numpy as np
import pandas as pd
from google.oauth2.service_account import Credentials

RO_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
DL_CREDS = Path.home() / "DropsLab" / "google_credentials.json"
DL_SHEET = "1XM-qId7HAwEu-8-1GGHcy3RoyyAnsYshjZfDrKFnTMI"
COST_RT = 0.50           # % round-trip stress cost (MASTERPLAN §5)
BOOT_N = 2000
SEED = 42
HORIZONS = ["d1_pct", "d3_pct", "d5_pct"]   # D5 = HYP-002 exit; D1/D3 = context


def _hr(t):
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)


def ro_records(sheet_id, tab):
    creds = Credentials.from_service_account_file(str(DL_CREDS), scopes=RO_SCOPES)
    ws = gspread.authorize(creds).open_by_key(sheet_id).worksheet(tab)
    return pd.DataFrame(ws.get_all_records())


def num(df, col):
    return pd.to_numeric(df.get(col), errors="coerce")


def daycluster_ci(df, valcol, n=BOOT_N, seed=SEED):
    """Day-clustered bootstrap 95% CI of the mean (resample scan_date groups)."""
    d = df[["date", valcol]].dropna()
    if d.empty:
        return None
    groups = [g[valcol].to_numpy() for _, g in d.groupby("date")]
    k = len(groups)
    rng = np.random.default_rng(seed)
    means = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, k, k)
        means[i] = np.concatenate([groups[j] for j in idx]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def edge_row(label, df, col):
    s = num(df, col)
    g = df.assign(_v=s).dropna(subset=["_v"])
    if g.empty:
        print(f"  {label:<28} n=0")
        return
    gross = g["_v"].mean()
    net = gross - COST_RT
    win = (g["_v"] > 0).mean() * 100
    g_net = g.assign(date=df.loc[g.index, "date"], _v=g["_v"] - COST_RT)
    ci = daycluster_ci(g_net.rename(columns={"_v": "net"}), "net")
    ci_s = f"[{ci[0]:+.2f},{ci[1]:+.2f}]{'  ⚠INCLUDES 0' if ci[0] <= 0 <= ci[1] else '  >0'}" if ci else "n/a"
    print(f"  {label:<28} n={len(g):<4} gross={gross:+6.2f}%  net={net:+6.2f}%  "
          f"win={win:4.1f}%  net-CI95(day)={ci_s}")


def main():
    _hr("LOAD (read-only, spreadsheets.readonly)")
    raw = ro_records(DL_SHEET, "drops_raw")
    post = ro_records(DL_SHEET, "drops_post")
    print(f"  drops_raw  {len(raw)} rows | drops_post {len(post)} rows")

    # ── liquid floor on drops_raw (ReboundPro universe) ─────────────────────
    close, avgvol, cap = num(raw, "close"), num(raw, "avg_volume_10d"), num(raw, "market_cap")
    o, lo = num(raw, "open"), num(raw, "low")
    floor = (close >= 5) & (close * avgvol >= 5_000_000) & (cap >= 300_000_000)
    liq = raw[floor].copy()
    liq["date"] = liq["date"].astype(str).str[:10]
    liq["ticker"] = liq["ticker"].astype(str).str.upper().str.strip()
    liq["intraday_flag"] = ((lo[floor] - o[floor]) / o[floor] * 100) <= -10.0
    _hr("liquid subset (RB floor)")
    print(f"  n_floor = {len(liq)} / {len(raw)} ({100*len(liq)/len(raw):.1f}%)")

    # ── join forward returns from drops_post ────────────────────────────────
    post = post.copy()
    post["scan_date"] = post["scan_date"].astype(str).str[:10]
    post["ticker"] = post["ticker"].astype(str).str.upper().str.strip()
    cols = ["scan_date", "ticker", "scan_close", "d1_date", "d5_date",
            *HORIZONS, "max_recovery_5d_pct", "max_further_drop_5d_pct", "pattern_tag"]
    cols = [c for c in cols if c in post.columns]
    m = liq.merge(post[cols], left_on=["date", "ticker"],
                  right_on=["scan_date", "ticker"], how="left")

    _hr("D5 coverage / data-quality (halt/delist appear as missing d5)")
    has_post = m["scan_date"].notna()
    d5 = num(m, "d5_pct")
    print(f"  with a drops_post row:      {int(has_post.sum())}/{len(m)}")
    print(f"  with FINAL d5_pct:          {int(d5.notna().sum())}/{len(m)} "
          f"({100*d5.notna().mean():.1f}% coverage)")
    print(f"  missing d5 (no post / not-ripe / halt/delist): {int(d5.isna().sum())}")
    if "pattern_tag" in m.columns:
        print("  pattern_tag (rows with d5):")
        print("    " + m.loc[d5.notna(), "pattern_tag"].value_counts().to_string().replace("\n", "\n    "))

    md5 = m[d5.notna()].copy()        # analysis set = liquid ∩ has-final-D5

    _hr("2-3. EDGE by horizon (long; gross + net-0.50%; day-clustered CI)")
    print(f"  cost={COST_RT}% round-trip · bootstrap n={BOOT_N} seed={SEED}")
    for col in HORIZONS:
        if col in md5.columns:
            edge_row(col.upper().replace("_PCT", ""), md5, col)
    # MFE/MAE context
    mfe, mae = num(md5, "max_recovery_5d_pct"), num(md5, "max_further_drop_5d_pct")
    if mfe.notna().any():
        print(f"  MFE(max_recovery_5d) mean={mfe.mean():+.2f}%  |  "
              f"MAE(max_further_drop_5d) mean={mae.mean():+.2f}%")

    _hr("4. EXPLORATORY — split by RB intraday-rule flag (D5 net)  [pre-registered, marked]")
    for name, sub in [("intraday low/open<=-10%", md5[md5["intraday_flag"]]),
                      ("NOT intraday (close-only)", md5[~md5["intraday_flag"]])]:
        edge_row(name, sub, "d5_pct")

    # ── 5. VIX regime variant (external yfinance, read-only) ────────────────
    _hr("5. VARIANT — VIX regime (external ^VIX via yfinance)  [secondary]")
    try:
        import yfinance as yf
        dmin, dmax = md5["date"].min(), md5["date"].max()
        vix = yf.download("^VIX", start=dmin, end=(pd.Timestamp(dmax) + pd.Timedelta(days=2)).strftime("%Y-%m-%d"),
                          progress=False, auto_adjust=False)["Close"]
        vix.index = vix.index.astype(str).str[:10]
        vmap = vix.to_dict() if hasattr(vix, "to_dict") else {}
        # vix may be a DataFrame col; coerce to scalar dict
        md5 = md5.assign(vix=md5["date"].map(lambda d: float(vmap.get(d)) if vmap.get(d) is not None else np.nan)
                         if not isinstance(vix, pd.DataFrame) else
                         md5["date"].map(lambda d: float(vix.loc[d].iloc[0]) if d in vix.index else np.nan))
        cov = md5["vix"].notna().mean()
        print(f"  ^VIX matched for {100*cov:.0f}% of rows")
        edge_row("VIX>=20", md5[md5["vix"] >= 20], "d5_pct")
        edge_row("VIX<18", md5[md5["vix"] < 18], "d5_pct")
        edge_row("18<=VIX<20", md5[(md5["vix"] >= 18) & (md5["vix"] < 20)], "d5_pct")
    except Exception as e:
        print(f"  NOT RUN — yfinance ^VIX unavailable: {type(e).__name__}: {e}")

    # ── 6. SPY-relative variant (external yfinance, read-only) ──────────────
    _hr("6. VARIANT — SPY-relative alpha over scan->D5 (yfinance)  [secondary]")
    try:
        import yfinance as yf
        dmin, dmax = md5["date"].min(), md5["d5_date"].astype(str).str[:10].max()
        spy = yf.download("SPY", start=dmin, end=(pd.Timestamp(dmax) + pd.Timedelta(days=2)).strftime("%Y-%m-%d"),
                          progress=False, auto_adjust=False)["Close"]
        spy.index = spy.index.astype(str).str[:10]
        sclose = (lambda d: (float(spy.loc[d].iloc[0]) if isinstance(spy, pd.DataFrame) else float(spy[d]))
                  if d in spy.index else np.nan)
        s0 = md5["date"].map(sclose)
        s5 = md5["d5_date"].astype(str).str[:10].map(sclose)
        spy_ret = (s5 / s0 - 1) * 100
        alpha = num(md5, "d5_pct") - spy_ret
        a = alpha.dropna()
        if not a.empty:
            print(f"  n={len(a)}  mean SPY-5d={spy_ret.dropna().mean():+.2f}%  "
                  f"mean alpha(d5−SPY)={a.mean():+.2f}%  net-alpha={a.mean()-COST_RT:+.2f}%")
        else:
            print("  NOT RUN — no SPY overlap")
    except Exception as e:
        print(f"  NOT RUN — yfinance SPY unavailable: {type(e).__name__}: {e}")

    _hr("DONE — numbers feed TASK-C1_liquid_edge_memo.md  (PROXY/PRIOR, not M4/M5)")


if __name__ == "__main__":
    main()
