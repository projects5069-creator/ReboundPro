# Group C (fundamentals) — PRE-REGISTRATION of hypothesized separation directions

**Status:** LOCKED (sha256 — see `PRE_REGISTRATION_groupC.sha256`). Pre-registered
**before** any fundamental metric was fed into the separation table, to prevent
data-mining, sign-flipping, and horizon-shopping after seeing results.
**Date:** 2026-06-25. **Scope:** ReboundPro pages 6/7 descriptive separation table
(fixed-horizon D+3 headline + D+3/5/7/10/15/20 strip, family-wise null band, min-n gate).

## M5 boundary (explicit)
- **(א) This is a HYPOTHESIS document, not a rule.** It defines what we *expect* to
  observe descriptively. It is **NOT** a score, a signal, an entry rule, or a
  buy/sell recommendation. Nothing here authorizes a trade.
- **(ב) The primary prediction is TWO-SIDED** (competing quality-vs-reversal signs):
  **both outcomes are a finding** — there is no automatic win. Confirming the
  reversal direction, confirming the quality direction, *or* finding no separation
  are all legitimate descriptive results.
- **(ג) The fundamentals must NEVER be combined into a unified "fundamental quality
  score" (or any composite) on the page or anywhere user-facing.** Each metric is
  read strictly per-metric (its own Cliff's delta + family-wise band). A combined
  score would be M5 (a unified score / signal) and is forbidden. (This is also why
  Altman-Z / Piotroski-F composites are deliberately EXCLUDED from the set.)

## Central tension being tested
Every "→up" direction below is borrowed from **month–year** horizon evidence
(Flossbach von Storch: durable recovery is the exception; recoverers had high
profitability / sales growth / low debt at the trough. Piotroski F: quality-on-cheap,
strongest ~2y). But the window here is **3–20 trading days**, where the dominant
effect is **short-term reversal** — *stronger in low-quality / distressed / illiquid /
volatile* names. So at 3–20d several "quality→up" directions may **weaken or invert**.

## Confirmatory set (6 metrics, ≤1 per axis — limits collinearity)
Point-in-time at D0 from `fundamentals_snapshot` (Finviz, captured inline at detection;
survivorship-clean forward). Columns are the verified `_num` fields.

Sign convention: **δ = Cliff's delta** of the metric between the **up** group
(forward-rose, outcome>0 at the horizon) and the **down** group (outcome≤0).
**δ>0 ⇒ the metric is HIGHER in the rosers.**

| # | metric (`_num`) | axis | H-quality (long-horizon) | H-reversal (3–20d) | two-sided? |
|---|---|---|---|---|---|
| 1 | `ROA_num` | profitability | δ>0 (high ROA rises) | δ<0 (low-quality bounces) | ✅ opposed |
| 2 | `Debt/Eq_num` | leverage | δ<0 (low debt rises) | **δ>0 (distress bounces)** | ✅ **EPICENTER** |
| 3 | `Current Ratio_num` | liquidity | δ>0 (high liquidity rises) | δ<0 (low-liquidity bounces) | ✅ opposed |
| 4 | `Short Float_num` | distress / sentiment | δ<0 (bearish → falls) | δ>0 (short-squeeze → bounce) | ✅ opposed |
| 5 | `Gross Margin_num` | margin | δ>0 (high margin rises) | δ<0 (low-margin bounces) | ✅ opposed |
| 6 | `P/B_num` (+ derived E/P) | value | δ<0 (low P/B rises) / E/P δ>0 | δ<0 (distressed-cheap bounces) | ⚠️ **NOT a clean two-sided test** |

**Note on #6 (P/B):** LOW-CONFIDENCE, INTERACTION-DEPENDENT. Both hypotheses point the
**same** sign (low P/B → up), so P/B alone cannot distinguish quality from reversal;
value only works *interacted with quality*, which the per-metric table cannot express.
Kept for coverage, but **explicitly flagged as not a two-sided discriminator.** E/P
(from `P/E_num`, guarding negative/zero P/E) is recorded as a companion value check.

## Primary pre-registered prediction (the scientific bet)
For the 5 contested metrics (#1–#5), the **short-horizon (D+3) δ sign is hypothesized
to favor REVERSAL** (distress / low-quality → bigger bounce), and may **decay or flip
toward the quality sign by D+20**. The **horizon strip (D+3→D+20) adjudicates the
sign-evolution.** Because the prediction is two-sided, the quality outcome, the
reversal outcome, and the null are each a finding (per M5 §ב above).

## Decision rule (LOCKED — anti-horizon-shopping)
A metric is "confirmed in a direction at horizon D+k" **only when ALL hold**:
1. its δ at D+k **crosses the family-wise (multiplicity-corrected) null band**, AND
2. the data is **matured** to D+k (events actually reached D+k; min-n gate passed), AND
3. the sample spans **≥ 2 distinct market regimes**.
Until all three hold: **descriptive only, no claim.** The metric set, the competing
signs, the primary prediction, and the horizons are **locked as of this file's hash**;
we do **not** re-pick the "winning" horizon or flip a sign after seeing data.

## What the sha256 locks
The byte-content of THIS file (`PRE_REGISTRATION_groupC.md`) at lock time: the
6-metric set, the two competing signs per metric, the #6 caveat, the primary
two-sided prediction, the decision rule, and the M5 statements. The hash is recorded
in `PRE_REGISTRATION_groupC.sha256` and in the locking git commit.
