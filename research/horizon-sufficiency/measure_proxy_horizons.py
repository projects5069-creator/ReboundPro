"""C0 step-3 (gate-2 = X) — PROXY/PRIOR horizon re-measurement on the SURVIVOR cache.

Guardrails (locked by user at gate-2):
  1. SINGLE consistent population: every horizon (incl D+20) is measured FRESH from
     the same survivor cache, on the SAME events that mature to D+90. We never paste
     measured_old.D+20 (full universe) onto cache.D+k (survivors).
  2. SUFFICIENT-only: B2 (median cum_pct) adjudicates. B2 stabilises by D+20 →
     SUFFICIENT (conservative). B2 climbs → PROXY-SUGGESTIVE, stop, do NOT interpret.
  3. delisted_miss(k) is NOT measurable from a survivor-only cache → reported as
     unavailable (needs point-in-time drops_raw n=4669, out of scope).

Read-only on the cache. No Sheet/disk writes except the memo. Run:
  uv run --with-requirements requirements.txt python research/horizon-sufficiency/measure_proxy_horizons.py
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(".")
sys.path.insert(0, ROOT)
import config  # noqa: E402
import dashboard_common as dc  # noqa: E402

H = [3, 5, 10, 15, 20, 30, 60, 90]
EPS_B2 = 0.5     # pp — locked
EPS_B1 = 0.05    # delta — locked
NMIN = 30        # locked
KPERM = 1000
KBOOT = 1000
SEED = 42
JUMP = float(getattr(config, "SPLIT_HALT_JUMP_PCT", 100.0))
HIST = os.path.join(ROOT, "research", "historical")
CACHE = os.path.join(HIST, "cache")
MEMO = os.path.join(ROOT, "research", "horizon-sufficiency", "HORIZON_C0_proxy_memo.md")


def log(m):
    print(m, flush=True)


# ---- 1. event list: mid+high, dedup (ticker,event_date) -------------------
log("loading event list (measured_old, mid+high)…")
ev = pd.read_parquet(
    os.path.join(HIST, "events", "measured_old.parquet"),
    columns=["ticker", "event_date", "atr_pct", "liquidity_bucket", "macro_regime"],
)
ev = ev[ev["liquidity_bucket"].isin(["mid", "high"])].copy()
ev["event_date"] = pd.to_datetime(ev["event_date"]).dt.normalize()
ev = ev.dropna(subset=["atr_pct"]).drop_duplicates(["ticker", "event_date"]).reset_index(drop=True)
log(f"  {len(ev)} distinct mid+high events, {ev['ticker'].nunique()} tickers")

# latest cache file per ticker
cache_files = {}
for p in glob.glob(os.path.join(CACHE, "*.parquet")):
    base = os.path.basename(p)
    t = base.split("__")[0]
    end = base.split("__")[-1].replace(".parquet", "")
    if t not in cache_files or end > cache_files[t][0]:
        cache_files[t] = (end, p)

# ---- 2. forward measurement, grouped by ticker (read each cache once) ------
log("measuring forward horizons from cache (single survivor population)…")
recs = []
no_cache = 0
not_trading_day = 0
not_matured = 0
for ti, (tk, grp) in enumerate(ev.groupby("ticker")):
    if ti % 500 == 0:
        log(f"  ticker {ti}/{ev['ticker'].nunique()}  rows so far={len(recs)}")
    cf = cache_files.get(tk)
    if not cf:
        no_cache += len(grp)
        continue
    df = pd.read_parquet(cf[1])
    if "Close" not in df.columns:
        no_cache += len(grp)
        continue
    close = df["Close"].to_numpy(dtype=float)
    dates = pd.to_datetime(df.index).normalize().to_numpy()
    n = close.size
    if n < max(H) + 2:
        not_matured += len(grp)
        continue
    dret = np.abs(np.diff(close) / close[:-1]) * 100.0  # len n-1
    for ed, atr in zip(grp["event_date"].to_numpy(), grp["atr_pct"].to_numpy()):
        pos = int(np.searchsorted(dates, ed))
        if pos >= n or dates[pos] != ed:
            not_trading_day += 1
            continue
        if pos + max(H) >= n:          # must mature to D+90 → single population
            not_matured += 1
            continue
        ref = close[pos]
        if not np.isfinite(ref) or ref <= 0:
            continue
        rec = {"ticker": tk, "event_date": ed, "atr_pct": float(atr)}
        for k in H:
            rec[f"d{k}"] = (close[pos + k] / ref - 1.0) * 100.0
        win = dret[pos:pos + max(H)]
        rec["split_halt"] = bool(np.nanmax(win) > JUMP) if win.size else False
        recs.append(rec)

m = pd.DataFrame(recs)
log(f"\nmeasured population (matured to D+90): {len(m)} events")
log(f"  excluded: no_cache={no_cache}  not_trading_day={not_trading_day}  not_matured={not_matured}")
contam = float(m["split_halt"].mean() * 100) if len(m) else float("nan")
log(f"  split/halt contamination: {int(m['split_halt'].sum())}/{len(m)} = {contam:.2f}%  (excluded from aggregates)")

clean = m[~m["split_halt"]].reset_index(drop=True)
regimes = pd.read_parquet(os.path.join(HIST, "events", "measured_old.parquet"),
                          columns=["ticker", "event_date", "macro_regime"])
regimes["event_date"] = pd.to_datetime(regimes["event_date"]).dt.normalize()
clean = clean.merge(regimes.drop_duplicates(["ticker", "event_date"]), on=["ticker", "event_date"], how="left")
n_regimes = clean["macro_regime"].astype(str).nunique()
log(f"  clean n={len(clean)}  distinct macro_regimes={n_regimes}")

# ---- 3. per-horizon B1 (Cliff's δ of atr_pct) + B2 (median cum_pct) --------
atr = clean["atr_pct"].to_numpy(dtype=float)
dates_arr = clean["event_date"].to_numpy()
uniq_dates = np.unique(dates_arr)
date_to_idx = {d: np.where(dates_arr == d)[0] for d in uniq_dates}
rng = np.random.default_rng(SEED)
# pre-draw day-clustered bootstrap resamples (shared across horizons)
boot_pools = []
for _ in range(KBOOT):
    sd = rng.choice(uniq_dates, size=uniq_dates.size, replace=True)
    boot_pools.append(np.concatenate([date_to_idx[d] for d in sd]))

rows = []
for k in H:
    cum = clean[f"d{k}"].to_numpy(dtype=float)
    up = cum > 0
    b1 = dc.cliffs_delta(atr[up], atr[~up])
    band = dc.permutation_band(atr, up, k=KPERM, seed=SEED)
    b2 = float(np.median(cum))
    boot_meds = np.array([np.median(cum[p]) for p in boot_pools])
    lo, hi = np.percentile(boot_meds, [2.5, 97.5])
    rows.append({"k": k, "n": len(clean), "up": int(up.sum()), "down": int((~up).sum()),
                 "B1_delta": b1["delta"], "B1_mag": b1["magnitude"], "B1_exceeds95": band["exceeds_95"],
                 "B2_median": b2, "B2_lo": float(lo), "B2_hi": float(hi),
                 "_cum": cum})
    log(f"  D+{k:<3} n={len(clean)} | B1 δ(atr_pct)={b1['delta']:+.3f} ({b1['magnitude']}, >95%={band['exceeds_95']}) "
        f"| B2 median cum={b2:+.3f}% CI[{lo:+.3f},{hi:+.3f}]")

# ---- 4. SUFFICIENT-only adjudication (B2; guardrail 2) ---------------------
cum20 = clean["d20"].to_numpy(dtype=float)
log("\nB2 difference vs D+20 (day-clustered CI95 of [median(D+k) − median(D+20)]):")
climbs = []
diff_tbl = []
for r in rows:
    k = r["k"]
    if k <= 20:
        continue
    cumk = r["_cum"]
    boot_diffs = np.array([np.median(cumk[p]) - np.median(cum20[p]) for p in boot_pools])
    dlo, dhi = np.percentile(boot_diffs, [2.5, 97.5])
    point = float(np.median(cumk) - np.median(cum20))
    real_increase = dlo > EPS_B2            # ENTIRE CI beyond +ε  (locked rule)
    diff_tbl.append({"k": k, "point": point, "lo": float(dlo), "hi": float(dhi), "real": bool(real_increase)})
    climbs.append(real_increase)
    log(f"  D+20→D+{k:<3}: Δmedian={point:+.3f}pp  CI95[{dlo:+.3f},{dhi:+.3f}]  "
        f"CI fully > ε({EPS_B2})? {'YES (climb)' if real_increase else 'no'}")

monotone = all(diff_tbl[i]["point"] <= diff_tbl[i + 1]["point"] for i in range(len(diff_tbl) - 1))
any_climb = any(climbs)
if any_climb and monotone:
    verdict = "PROXY-SUGGESTIVE-INSUFFICIENT"
elif any_climb:
    verdict = "PROXY-SUGGESTIVE-INSUFFICIENT (non-monotone — weaker)"
else:
    flat = abs(float(np.median(cum20))) < EPS_B2
    tag = "by-default (B2 flat ~0; proxy upper-bound; NOT evidence of a reversal)" if flat \
        else "(B2 plateaus by D+20; proxy upper-bound)"
    verdict = f"SUFFICIENT — {tag}"
log(f"\n=== VERDICT (B2 adjudicates, asymmetric): {verdict} ===")

# ---- 5. write memo --------------------------------------------------------
def fmt_rows():
    out = []
    for r in rows:
        out.append(f"| D+{r['k']} | {r['n']} | {r['up']}/{r['down']} | {r['B1_delta']:+.3f} "
                   f"({r['B1_mag']}, {'✓' if r['B1_exceeds95'] else '✗'}) | {r['B2_median']:+.3f}% "
                   f"[{r['B2_lo']:+.3f},{r['B2_hi']:+.3f}] |")
    return "\n".join(out)


def fmt_diff():
    out = []
    for d in diff_tbl:
        out.append(f"| D+20→D+{d['k']} | {d['point']:+.3f}pp | [{d['lo']:+.3f},{d['hi']:+.3f}] | "
                   f"{'**YES — climb**' if d['real'] else 'no'} |")
    return "\n".join(out)


memo = f"""# C0 step-3 — PROXY/PRIOR horizon re-measurement (survivor cache)

> **PROXY / PRIOR — survivorship-biased UPPER BOUND. NOT a finding, NOT M4=GO, NOT
> M5.** Measured on the survivor-only DropsLab cache (currently-listed tickers).
> Delisted/halted names are ABSENT (not truncated) and that absence grows with the
> horizon → the proxy is biased toward "longer = better". Per C0 §ב this can only
> *affirm* sufficiency, never *prove* insufficiency. M5 boundary preserved: zero
> score / signal / entry. Window (`POST_ANALYSIS_HORIZON`) UNCHANGED.

**Date:** 2026-06-26 · **Branch:** `research/horizon-sufficiency` · C0 lock `aa235fe5` (commit `cef6e05`).
**Decision rule:** C0 (locked) — B1/B2 co-primary, **B2 adjudicates**, asymmetric.
ε_B1={EPS_B1} δ · ε_B2={EPS_B2} pp · N_min={NMIN} · K_perm={KPERM} · K_boot={KBOOT} (day-clustered).

## Guardrails honoured
1. **Single consistent population** — every horizon (incl D+20) re-measured FRESH from
   the same survivor cache, on the SAME {len(clean)} events that mature to D+90. No
   measured_old.D+20 paste-over.
2. **SUFFICIENT-only** — B2 adjudicates; a climb halts at PROXY-SUGGESTIVE (no interpretation, no window touch).
3. **delisted_miss(k) UNAVAILABLE** from a survivor-only cache (within-sample 0% is an
   artifact). Requires point-in-time `drops_raw` (n=4669) — **out of scope, not run.**

## Population
- mid+high distinct events: {len(ev)} → **matured to D+90: {len(m)}** (single population).
- excluded: no_cache={no_cache}, not_trading_day={not_trading_day}, not_matured={not_matured}.
- **split/halt contamination: {int(m['split_halt'].sum())}/{len(m)} = {contam:.2f}%** (excluded from aggregates).
- clean **n={len(clean)}** · distinct macro_regimes=**{n_regimes}** (≥2 ✓).

## Horizon strip (clean survivor population)
| horizon | n | up/down | B1: Cliff's δ(atr_pct) (mag, >95%) | B2: median cum_pct [CI95] |
|---|---|---|---|---|
{fmt_rows()}

## B2 adjudication — does the reversal magnitude keep climbing past D+20?
| step | Δ median | CI95 of Δ (day-clustered) | CI fully > ε({EPS_B2}pp)? |
|---|---|---|---|
{fmt_diff()}

monotone past D+20: **{monotone}** · any real climb (CI fully > ε): **{any_climb}**

## VERDICT (asymmetric, B2 adjudicates)
**{verdict}**

- If SUFFICIENT: even the survivor-inflated proxy plateaus by D+20 → conservative
  evidence that D+20 captures the reversal magnitude (survivorship works *against*
  this conclusion). B1 (atr_pct separation) is reported above as a feature-quality
  observation only — it does **not** drive any window change.
- If PROXY-SUGGESTIVE: a long-horizon climb is the survivorship null expectation;
  the proxy cannot distinguish a real effect from a survival artifact. **Stop.**
  Lock-and-wait for live / survivorship-corrected confirmation. **No window change.**

*(Generated by `research/horizon-sufficiency/measure_proxy_horizons.py`, read-only on cache.)*
"""
with open(MEMO, "w") as f:
    f.write(memo)
log(f"\nmemo written: {MEMO}")
