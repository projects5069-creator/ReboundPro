# Horizon-Sufficiency (C0) — PRE-REGISTRATION: "Is the D+20 collection window sufficient?"

**Status:** LOCKED (sha256 — see `PRE_REGISTRATION_horizon_C0.sha256`). Pre-registered
**before** any extended-horizon (D+30/60/90) backfill was observed, to prevent
horizon-shopping, metric-shopping, and post-hoc threshold/sign selection.
**Date:** 2026-06-26. **Scope:** descriptive horizon-design question only — does the
current forward-collection window (`POST_ANALYSIS_HORIZON = 20`, `config.py:38`)
capture the rebound effect, or does it realize later (D+30/60/90)?

## M5 boundary (explicit)
- **(א) DESIGN/HYPOTHESIS document, not a rule.** A pure horizon-design diagnostic.
  It is **NOT** a score, a signal, an entry/exit rule, or a buy/sell recommendation.
  Nothing here authorizes a trade. Zero scoring anywhere in its outputs.
- **(ב) BOTH outcomes are a finding** — "D+20 sufficient" and "D+20 not-sufficient"
  are equally legitimate descriptive results. There is no automatic win.
- **(ג) A "not-sufficient" result does NOT itself change the collection window.** Any
  window change (`config.py:38` + the `post_analysis_collector.py` end-window +
  `forward_daily` schema) is a **separate, later approval gate**, conditioned on
  live / survivorship-corrected confirmation — **never on proxy alone**.

## Data / survivorship framing (binding)
- Live `forward_daily` is **immature** (~1 week of events, 6/12–18); almost no live
  event has matured even to D+20. The extended horizons can therefore only be
  observed **now** on **backfill** (yfinance / DropsLab-floor universe).
- **ALL backfill is prior/proxy, survivorship-biased — not a finding, not M4=GO,
  not M5** (same framing as TASK-C / TASK-C.1).
- **Survivorship gradient (critical, asymmetric):** yfinance holds currently-listed
  tickers only. Events delisted/halted **before** D+k are ABSENT, and this absence
  **grows with k**. The bias therefore pushes toward "longer horizon = better" — i.e.
  toward the very "not-sufficient" conclusion under test. A monotone climb at long
  horizons is **the survivorship null expectation**, not evidence of a real effect.
  `delisted_miss(k)` (count missing at each horizon) is reported beside every result
  so the gradient is visible.

## The tension being tested
Across the Entry-Profile sessions (23–25/6), the **Cliff's δ of `atr_pct`** between
forward-up and forward-down events **strengthens as the horizon grows toward D+20**.
If the separation/effect is still climbing at the window edge, the rebound may realize
later than D+20 and the window truncates the tail. Question: is D+20 long enough to
capture the effect, or does it realize at D+30/60/90?

## What is measured — two CO-PRIMARY metrics
Computed at every horizon k in the locked strip **H = {3, 5, 10, 15, 20, 30, 60, 90}**.
Outcome groups: **up** = forward outcome > 0 at the horizon; **down** = outcome ≤ 0.

- **B1 — separation strength:** `|Cliff's δ|` of `atr_pct` (point-in-time D0 feature)
  between up/down groups, as a function of k. Reuses `dashboard_common.py`
  `cliffs_delta()` + permutation null-band. **ε_B1 = 0.05** on δ (one "negligible" step).
- **B2 — reversal magnitude:** median `cum_pct_from_ref` as a function of k.
  **ε_B2 = 0.5pp** (half a point; aligns with the §5 0.50% round-trip cost floor).

Per horizon, report: `n(k)`, `delisted_miss(k)`, point estimate + **day-clustered
bootstrap CI95**, and family-wise null-band crossing. **min-n gate:** a horizon is
evaluable only if `n(k) ≥ N_min = 30`; long horizons below the gate are reported as
gated, not silently dropped.

**"Real increase" threshold:** the increase of a metric between D+20 and D+k>20 counts
only if the **entire CI95 of the difference [metric(D+k) − metric(D+20)] lies beyond ε**
(the point estimate alone is insufficient), AND `n(k) ≥ N_min`, AND the sample spans
**≥ 2 distinct market regimes**.

## Decision rule (LOCKED — asymmetric, anti-horizon-shopping)
The permutation null-band tests **absence of separation**; it does **not** correct
survivorship. Because a monotone long-horizon climb is exactly the survivorship null
(see framing above), the verdict is **asymmetric**.

**B2 is the adjudicator** of the horizon-sufficiency question: window sufficiency = whether
the *reversal is realized* = B2's trajectory. **B1 is always reported**, but a B1-only
climb is a separate **feature-quality** observation (M5-adjacent) that does **not** drive
a window change.

- **(א) D+20 = SUFFICIENT — affirmable from proxy.** ⇔ **B2 stabilizes by D+20**:
  CI95 of [B2(D+30) − B2(D+20)] is **not** entirely beyond ε_B2, there is no continued
  monotone climb D+30→60→90 crossing the null-band, and evaluated horizons pass min-n.
  **Reliable because survivorship works AGAINST this conclusion** — if even the inflated
  proxy plateaus by D+20, the real world (less survivorship) plateaus at least as early.
  B1 is reported alongside; a B1 climb here is logged as "atr_pct separation keeps
  improving (feature-quality)" and does **not** trigger a window change.

- **(ב) D+20 = "PROXY-SUGGESTIVE-INSUFFICIENT" — may NOT be decided from proxy alone.**
  ⇔ **B2 climbs monotonically past D+20** (CI of the difference entirely beyond ε_B2,
  crosses the null-band, n ≥ N_min). This is exactly the survivorship null, so the proxy
  **cannot** distinguish a real effect from a survival artifact. Maximum permissible
  statement: *"proxy-suggestive that the rebound realizes beyond D+20 — pending live /
  survivorship-corrected confirmation."* **No window extension on proxy alone.** The
  `delisted_miss(k)` gradient is reported mandatorily beside the verdict.

- **(ג) tie-break B1 ↔ B2 (B2 adjudicates):**
  - **B2 stabilizes, B1 climbs** → **(א) SUFFICIENT**; B1 climb logged as a separate
    feature-quality note, **no window change**.
  - **B1 stabilizes, B2 climbs** → **(ב) PROXY-SUGGESTIVE** (this is what motivates the
    later, separate window-diagnosis gate).
  - **both climb** → **(ב) PROXY-SUGGESTIVE** (strongest; both reported).
  - any mixed state is tagged explicitly: `mixed: <climbing metric> climbs past D+20`.

- **(ד) INCONCLUSIVE / descriptive only** — otherwise (difference CI does not clear ε,
  null-band not crossed, n < N_min, or single regime).

Until a verdict's conditions fully hold: **descriptive only, no claim.** The metric set,
the ε values, the horizon strip, N_min, the asymmetry, and the adjudicator are **locked
as of this file's hash**; we do **not** re-pick the winning horizon, swap the adjudicator,
or flip an ε after seeing data.

## What the sha256 locks
The byte-content of THIS file (`PRE_REGISTRATION_horizon_C0.md`) at lock time: the two
co-primary metrics (B1, B2) and their ε (0.05 δ / 0.5pp), the locked horizon strip H,
N_min = 30, the "real increase" CI-crosses-ε rule, the **asymmetric** verdict (א/ב),
the **B2-as-adjudicator** tie-break (ג), and the M5 + survivorship-gradient statements.
The hash is recorded in `PRE_REGISTRATION_horizon_C0.sha256` and in the locking git commit.
