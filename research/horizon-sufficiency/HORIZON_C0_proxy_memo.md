# C0 step-3 — PROXY/PRIOR horizon re-measurement (survivor cache)

> **PROXY / PRIOR — survivorship-biased UPPER BOUND. NOT a finding, NOT M4=GO, NOT
> M5.** Measured on the survivor-only DropsLab cache (currently-listed tickers).
> Delisted/halted names are ABSENT (not truncated) and that absence grows with the
> horizon → the proxy is biased toward "longer = better". Per C0 §ב this can only
> *affirm* sufficiency, never *prove* insufficiency. M5 boundary preserved: zero
> score / signal / entry. Window (`POST_ANALYSIS_HORIZON`) UNCHANGED.

**Date:** 2026-06-26 · **Branch:** `research/horizon-sufficiency` · C0 lock `aa235fe5` (commit `cef6e05`).
**Decision rule:** C0 (locked) — B1/B2 co-primary, **B2 adjudicates**, asymmetric.
ε_B1=0.05 δ · ε_B2=0.5 pp · N_min=30 · K_perm=1000 · K_boot=1000 (day-clustered).

## Guardrails honoured
1. **Single consistent population** — every horizon (incl D+20) re-measured FRESH from
   the same survivor cache, on the SAME 241962 events that mature to D+90. No
   measured_old.D+20 paste-over.
2. **SUFFICIENT-only** — B2 adjudicates; a climb halts at PROXY-SUGGESTIVE (no interpretation, no window touch).
3. **delisted_miss(k) UNAVAILABLE** from a survivor-only cache (within-sample 0% is an
   artifact). Requires point-in-time `drops_raw` (n=4669) — **out of scope, not run.**

## Population
- mid+high distinct events: 245021 → **matured to D+90: 245021** (single population).
- excluded: no_cache=0, not_trading_day=0, not_matured=0.
- **split/halt contamination: 3059/245021 = 1.25%** (excluded from aggregates).
- clean **n=241962** · distinct macro_regimes=**8** (≥2 ✓).

## Horizon strip (clean survivor population)
| horizon | n | up/down | B1: Cliff's δ(atr_pct) (mag, >95%) | B2: median cum_pct [CI95] |
|---|---|---|---|---|
| D+3 | 241962 | 119600/122362 | -0.056 (negligible, ✓) | +0.000% [-0.396,+0.256] |
| D+5 | 241962 | 120214/121748 | -0.055 (negligible, ✓) | +0.000% [-0.451,+0.413] |
| D+10 | 241962 | 121177/120785 | -0.063 (negligible, ✓) | +0.048% [-0.540,+0.638] |
| D+15 | 241962 | 120679/121283 | -0.088 (negligible, ✓) | +0.000% [-0.694,+0.710] |
| D+20 | 241962 | 119919/122043 | -0.093 (negligible, ✓) | -0.135% [-0.941,+0.713] |
| D+30 | 241962 | 117941/124021 | -0.125 (negligible, ✓) | -0.617% [-1.640,+0.471] |
| D+60 | 241962 | 121255/120707 | -0.154 (small, ✓) | +0.122% [-1.460,+1.650] |
| D+90 | 241962 | 117688/124274 | -0.165 (small, ✓) | -1.182% [-2.924,+0.573] |

## B2 adjudication — does the reversal magnitude keep climbing past D+20?
| step | Δ median | CI95 of Δ (day-clustered) | CI fully > ε(0.5pp)? |
|---|---|---|---|
| D+20→D+30 | -0.483pp | [-0.957,+0.047] | no |
| D+20→D+60 | +0.257pp | [-0.828,+1.407] | no |
| D+20→D+90 | -1.048pp | [-2.333,+0.364] | no |

monotone past D+20: **False** · any real climb (CI fully > ε): **False**

## VERDICT (asymmetric, B2 adjudicates)
**SUFFICIENT — by-default (B2 flat ~0; proxy upper-bound; NOT evidence of a reversal)**

- If SUFFICIENT: even the survivor-inflated proxy plateaus by D+20 → conservative
  evidence that D+20 captures the reversal magnitude (survivorship works *against*
  this conclusion). B1 (atr_pct separation) is reported above as a feature-quality
  observation only — it does **not** drive any window change.
- If PROXY-SUGGESTIVE: a long-horizon climb is the survivorship null expectation;
  the proxy cannot distinguish a real effect from a survival artifact. **Stop.**
  Lock-and-wait for live / survivorship-corrected confirmation. **No window change.**

## Interpretation (honest — read before citing)
1. **The SUFFICIENT here is "sufficient by default", not "a reversal that completes by
   D+20".** B2 (median `cum_pct`) sits at **≈0 at every horizon** (−1.2%…+0.1%, every
   CI95 spans 0). There is **no reversal-magnitude effect accruing anywhere** in this
   broad mid+high universe — so D+20 cannot be truncating a climbing tail, because no
   climbing tail exists. This is consistent with **TASK-C.1** (no robust net edge in the
   liquid subset). Do **not** read this as "a rebound exists and D+20 captures it."
2. **The motivating observation (B1) replicates AND continues past D+20 — but it is
   feature-quality, not magnitude.** `|Cliff's δ|` of `atr_pct` grows monotonically
   **0.056 (D+3) → 0.093 (D+20) → 0.165 (D+90)** (negligible→small, all >95% band).
   So "atr_pct separation strengthens with the horizon" is real and does **not** plateau
   by D+20. Per C0 this is an **M5-adjacent feature-quality** signal (how well a D0
   feature sorts outcomes), **not** the reversal magnitude the collection window exists
   to capture → by the locked rule (B2 adjudicates) it **does not justify extending the
   window.** (δ is negative = `atr_pct` is *lower* in the up group; descriptive only.)
3. **Net answer to "is D+20 enough?" (proxy/upper-bound):** for the reversal **magnitude**
   the window exists to capture — **yes**, D+20 is sufficient (nothing accrues past it,
   even survivor-inflated). The atr_pct-separation phenomenon that *does* keep growing is
   a separate, descriptive feature-quality question, outside the window-design decision.
4. **Caveats:** survivor-only proxy (upper bound; delisted absent — guardrail 3); split/
   halt + zero-price bars excluded (1.25%, conservative); single mid+high population, not
   VIX-regime sliced. Live confirmation still pending data maturity (months).

*(Generated by `research/horizon-sufficiency/measure_proxy_horizons.py`, read-only on cache.)*
