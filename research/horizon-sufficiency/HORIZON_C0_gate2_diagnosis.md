# C0 gate-2 — read-only data-maturity & backfill diagnosis

**Date:** 2026-06-26 · **Branch:** `research/horizon-sufficiency` · **Status:** read-only, no writes.
**Script:** `research/horizon-sufficiency/diagnose_horizon_maturity.py` (+ ad-hoc reads).
C0 locked first: `aa235fe5…` (commit `cef6e05`).

## 1. LIVE data CANNOT answer the question now
From the Sheet (`watchlist_live` / `post_analysis`, read 2026-06-26):
- **527 events** (150 `intraday_drop` + 377 `gradual_drop`); `post_analysis` status = **478 partial + 49 pending_forward**.
- **Maturity per horizon** (events with ≥ k closed forward sessions):
  - D+3 → 283/527 · D+5 → 130/527 · **D+10 → 0** · D+15 → 0 · D+20 → 0.
- **No live event has reached even D+10.** The forward frontier is ~D+5–9.
- `POST_ANALYSIS_HORIZON = 20` ⇒ **D+30/60/90 are structurally impossible live, by construction.**
- **Conclusion:** the horizon question is unanswerable from live data now and for weeks; only **backfill (proxy)** can look past D+20 today.

## 2. A large historical proxy universe EXISTS — but is measured only to D+20
`research/historical/` (untracked) is a DropsLab-derived backfill harness:
- `measured_old.parquet` — **786,872 events**, `event_date` **2015-01-02 → 2025-06-11**.
- liquidity buckets: micro 354,498 · **mid 187,584 · high 85,112** (RB-floor = mid+high ≈ **272,696**) · low 158,744.
- Cache = **5,093 per-ticker OHLCV parquet** files (2015 → **2026-06-20**). **All** 786,872 events have cache room to **+90** (events end 2025-06, cache ends 2026-06 → ≥1yr buffer).
- **BUT the measured product stops at D+20** (`cum_pct_d3/d5/d10/d20`, `car_spy_d20`, `car_sector_d20`). **No d30/d60/d90 columns exist anywhere.**
- ⇒ **Step-3 must RE-MEASURE** the cache to D+30/60/90 (read-only on cache, but real compute over ~272k floor events × extended window). It is not a matter of reading existing columns.

## 3. Survivorship gradient is NOT directly measurable from this cache (reinforces C0 asymmetry)
- The cache is **survivor-only**: 5,093 tickers that yfinance still serves. `survivorship_log.json`: 5,035 tracked, **only 1 flagged** (`identity_drift`); within-sample "data goes dark before D+k" = **0% at every k**.
- That 0% is an **artifact, not reassurance**: delisted/halted names that dropped ≥10% and then vanished were **never fetched** — they are **absent**, not truncated. The cache cannot exhibit the survivorship gradient *from within*.
- The true `delisted_miss(k)` (which **grows with k**) is **unmeasurable** from the survivor-only cache; it needs a **point-in-time constituent / delisting source** (e.g. the full DropsLab `drops_raw` n=4669 which included the excluded names, or a survivorship-free universe feed).
- **This is exactly why C0 is asymmetric:** the proxy structurally **hides** the survivorship inflation at long horizons → any "still climbing past D+20" on this proxy is maximally confounded → admissible only as **(ב) PROXY-SUGGESTIVE**, never a window-extension trigger. A **plateau** by D+20 (even survivor-inflated) remains a credible **(א) SUFFICIENT** affirmation.

## Gate-2 decision (yours)
- **Doc correction surfaced:** live count is **527** (150+377), not the stale "~200"/"~77" in PROJECT_STATE/PK — fixed in step-0.
- **Path X — proceed to step-3 (re-measure proxy to D+90):** asymmetric value — *can affirm* "D+20 SUFFICIENT" (conservative, survivorship works against it), *cannot prove* "insufficient" (only PROXY-SUGGESTIVE). Cost: extend the measure harness to D+30/60/90 over ~272k floor events, read-only on cache.
- **Path Y — lock-and-wait:** C0 is locked; defer measurement until live `forward_daily` matures (months) and/or a survivorship-free source is wired. No proxy compute now.
- **Recommendation:** **Path X, scoped to the SUFFICIENT-affirmation only** — if the survivor-inflated proxy already plateaus by D+20, that credibly answers "yes, D+20 is enough"; if it climbs, we stop at PROXY-SUGGESTIVE and wait. Either way, no window change on proxy alone (C0 §ג).
