# Vardan Trade → ReboundPro — Gap Analysis (descriptive)

*Research/mapping only. **No trading logic** — scoring/signals/entry-decisions are out-of-scope until M4=go / M5
(MASTERPLAN §5). No edge claims. Source: Vardan decode in `~/Downloads/vardan/` (methodology.md, reference_level_decode.md,
fingerprint.md, vardan_trades_final.csv) vs ReboundPro `config.py` + collectors. Created 2026-06-22.*

## What Vardan is (for context)
A momentum/**breakout-up** long service: it publishes a setup with an entry zone set **~2% ABOVE** the current
price, a tight band (~1.0% ≈ 0.30× ATR14), a +16% target / −13.7% stop (R:R ~1.31), an ATR-based A/B/C volatility
grade, and a 30/48/50-day horizon. ReboundPro is the **opposite thesis** (long *rebound* after a ≥10% drop —
mean-reversion). So several Vardan params map to "different thesis", not "missing".

## Vardan inventory
**Raw per-trade fields:** entry_low/high (zone), stop_price/stop_pct, target_price/target_pct, days_elapsed/days_max,
risk_grade (A/B/C), result_pct/result_color (a *stock-vs-zone tracking* metric, NOT realized P&L), status
(active/can-enter/closed/expired), exit_date, current_price, company/symbol, feed_messages, publication_date.
**Decoded mechanics:** entry zone ~2% above price (breakout-up); band ≈0.30×ATR14; risk_grade = ATR% volatility tier
(A<~4%, B>~4%, 100% separable); R:R~1.31; horizon scales with grade (A→48d, B→30d); 3-state exit TP/STOP/TIME; the
actual fill trigger is intraday/discretionary and **not reproducible** from daily bars.

## ReboundPro inventory (collected fields)
- **watchlist_live:** identity/regime/path — incl. `drop_pct_from_open, volume_ratio, rsi_14, spy_change_pct,
  market_regime, sector_etf_change_pct, vix_level, drop_day_rel_volume, sector_momentum_5d/20d, pct_from_52w_high/low,
  prior_decline_20d/60d_pct, intraday_low, recovery_from_low_pct, reversal_confirmed, drop_kind, …`
- **post_analysis:** `ref_close, status, max_recovery_pct/day, max_further_drop_pct/day, touched_up_5pct/day_touched_up,
  touched_down_8pct/day_touched_down, last_close_pct, max_recovery_{3,5,10,20}d, max_further_drop_{3,5,10,20}d,
  trough_price/trough_day/recovery_from_trough_pct/max_recovery_from_trough_pct, split_halt_flag/reason`
- **forward_daily:** `day_offset, close, cum_pct_from_ref, daily_change_pct, high_pct, low_pct, …`
- **intraday_timeseries:** `timestamp, price, pct_from_open, volume`
- **fundamentals_snapshot:** ~89 Finviz fields incl. `ATR (14), RSI (14), Beta, Volatility W/M, SMA20/50/200,
  52W High/Low, Rel Volume, Short Float, Target Price` (numeric `_num` variants for most).

## Gap table
Legend: ✅ have · 🟡 partial · ❌ absent · ⛔ out-of-scope until M4/M5

| Vardan param | ReboundPro equivalent | Status | Relevance (long rebound after a drop) |
|---|---|---|---|
| entry zone (entry_low/high) | none (no entry defined); `price/ref_close/intraday_low` | ⛔ M5 | entry-zone = entry decision → after M4 |
| stop_pct | `max_further_drop_pct`, `touched_down_8pct`, `max_further_drop_{w}d` | 🟡 | **measured** descriptively → SL grid input for M4 |
| target_pct | `max_recovery_pct`, `touched_up_5pct`, `max_recovery_{w}d` | 🟡 | **measured** descriptively → TP grid input for M4 |
| days_max (horizon) | `horizon=20` + subwindows 3/5/10/20 + forward_daily | ✅ | core — D1..D+20 window |
| risk_grade (the A/B/C tag) | — (tagging = scoring) | ⛔ M5 | grade tagging = scoring → M5 |
| risk_grade = ATR-tier (the raw) | `ATR (14)`, `Volatility W/M`, `Beta` | ✅ | raw ATR captured; **bucketing** is M5 |
| result_pct (tracker) | `last_close_pct`, `recovery_from_trough_pct`, forward_daily `cum_pct_from_ref` | ✅ | ReboundPro **richer** — real multi-day path, not a target-capped tracker |
| R:R | derived from SL/TP, not prescribed | ⛔ M5 | decision parameter → M5 |
| 3-state exit TP/STOP/TIME | `touched_up_5pct`/`touched_down_8pct`/`last_close_pct`+`status` | 🟡 | a 3-state **outcome label** is derivable in M4 (descriptive, not a signal) |
| status (trade state) | `status` (ok/pending/halt/delist = data availability) | 🟡 | different semantics (theirs=trade, ours=collection) |
| exit_date | `dN_date`, `day_of_max_recovery/drop` | ✅ | descriptive |
| current_price | `price`, `last_close_pct` | ✅ | — |
| company/symbol | `ticker, company_name, sector, industry, country` | ✅ | richer |
| feed (narrative) | `news_snapshot` (catalyst) | 🟡 | trade-management narrative = N/A (no trades); catalyst yes |
| publication_date | `scan_date`, `detected_at` | ✅ | — |
| entry direction (breakout-up) | **opposite thesis**: capture after ≥10% drop | ❌ different | the core difference — no direct map |
| band ≈0.3×ATR | `ATR (14)` present; no band | ⛔ M5 | ATR-relative sizing = M4/M5 design input |
| entry trigger | none (no entry decision) | ⛔ M5 | even at Vardan, not reproducible |
| reference level (zone) | `SMA20/50/200, 52W High/Low, pct_from_52w_*` | ✅ (raw) | levels captured; use-for-decision = M5 |
| *(absent at Vardan)* market/sector regime | `spy_change_pct, market_regime, vix_level, sector_momentum_5d/20d, drop_day_rel_volume` | ✅ **RB superior** | Vardan has no regime context |
| *(absent at Vardan)* validity guards | `split_halt_flag/reason, prior_decline_20d/60d, explicit liquidity floor` | ✅ **RB superior** | prevents fake recovery + survivorship |

## Verified candidates (code-checked 2026-06-22)
1. **SMA exposure (NOT dist_to_SMA).** Verified `fundamentals.parse_num` strips `%`, and Finviz reports SMA20/50/200
   as **% distance of price from the SMA** → `SMA20_num`/`SMA50_num` already ARE % distance; `52W High/Low_dist_num`
   too. So computing a distance is **redundant**. Real gap = these live only in `fundamentals_snapshot`, not in
   `watchlist_live`; and `SMA200` is raw-only (not in `FUND_NUMERIC`, no `_num`). → descriptive exposure/parse, not new math.
2. **Multi-threshold reclaim grid — M3-legal.** Verified `touched_up_5pct` is computed as `highs[highs>=TOUCH_UP_PCT]`
   + first-cross day, a **purely descriptive fact** (no scoring/decision). Generalizing to thresholds [1,2,3,5,8]% with
   day-of-first-reach is the **same kind** of computation off the same `highs` series → descriptive, M3-legal. Approved Tier-1.
   *(Secondary/optional: `drop_in_ATR` = drop normalized by ATR14 — descriptive capitulation magnitude; not yet approved.)*

## Discipline
No code touched. No scoring/signal/entry. M5 boundary preserved. result_pct shown to be a tracker, not P&L — no edge claims.
