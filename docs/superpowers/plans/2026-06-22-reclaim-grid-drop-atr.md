# Reclaim/Drop Grid + drop_in_ATR — Implementation Plan (✅ RESOLVED & SHIPPED v0.2.0)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or :executing-plans. TDD, checkbox steps.
> **STATUS: SHIPPED** (v0.2.0, PR #1). This file is the historical planning artifact; the DECISION recommendations below are PRE-decision. See **"Resolved as"** for what was actually built — the code, PROJECT_KNOWLEDGE.md (§M3.9) and TASKS.md are the source of truth.

## ✅ Resolved as (final decisions — what shipped, may differ from the recs below)
- **D1 — column form:** separate column per threshold, **day-or-blank** (13 cols). *(as recommended)*
- **D2 — ATR source:** **NOT** "widen collector history". Final: `scanner.atr_14` computed once at scan time and stored in `watchlist_live.atr_14` (single ATR source); `post_analysis` **reads it** (passed into `compute_outcome(atr=…)` from the watchlist row) — no widened window, no re-fetch. This also yields `drop_in_atr` for free at scan.
- **D3 — down grid:** **%-down only** (ATR-down deferred). *(as recommended; note: ref_close is a fixed anchor, so ATR-down is easy to add later if wanted.)*
- **D4 — drop_in_atr numerator (by drop_kind):** intraday = `open − intraday_low`; **gradual = `ref_close_window − close`** (window decline, NOT open−low). Computed in both `scanner.py` and `gradual_scanner.py`.
- **ATR-from-trough grid:** measured from **the day AFTER the trough** (`trough_idx+1`) = confirmation-timing; **differs on purpose** from `max_recovery_from_trough_pct` (inclusive of trough day = intensity). *(refinement added during review.)*
- **D5 — backfill:** forward-only + one-off `scanner.py --backfill-atr` (watchlist atr_14/drop_in_atr). The post_analysis grid needs **no** backfill — verified the daily collector re-processes every event and upserts.
- **D6 — SMA exposure (TASK-V2):** **deferred** (SMA% already lives as %-distance in `fundamentals_snapshot`).
- Single source of truth for grid column names: `config.RECLAIM_GRID_COLUMNS`. 98 tests green; M5 boundary preserved.

**Goal:** Add two **descriptive-only** data products — (V1) a multi-threshold reclaim/drop grid (fixed-% + ATR-normalized) in `post_analysis`, and (drop_in_ATR) a point-in-time capitulation feature in `watchlist_live` — extending the existing `touched_up_5pct`/`touched_down_8pct`/`recovery-from-trough` pattern.

**Architecture:** V1 reuses the `highs`/`lows`/`trough_price` series already computed in `post_analysis_collector.compute()` (forward-window **outcome labels** — look-ahead is inherent & correct there). drop_in_ATR adds an `atr_14()` helper in `scanner.py` (mirror of `rsi_14()`), computed point-in-time from the existing 400-day history (no extra network call, ≤ scan_date only). All migration-safe via `upsert_by_key` (merge by column name).

**Tech Stack:** Python, pandas, yfinance, Google Sheets (`sheets_manager.upsert_by_key`), pytest.

**M5 guard (binding):** every new column is a *measurement*. No threshold is used for scoring/ranking/entry/exit. Pure descriptive collection (same class as the existing `touched_up_5pct`). Verified legal vs `post_analysis_collector.py:226-231`.

---

## Verified facts (code-checked 2026-06-22)
- `post_analysis_collector.compute()` already builds `highs=(High/ref_close−1)*100`, `lows=(Low/ref_close−1)*100`, and `trough_price/trough_idx` (`post_analysis_collector.py:218-242`). The grid is a loop over these — no new data.
- Collector history window = `scan_date−10d … scan_date+horizon*3+10` (`:183-185`) → **only ~6-7 trading days before D0** → **insufficient for ATR14 as-of D0** (needs widening). See **D2**.
- `scanner.py` has `rsi_14()` (`:69-74`) and pulls `EOD_HISTORY_DAYS=400` history (`:237-238`) → `atr_14()` is a cheap mirror, point-in-time. Existing `drop_pct_from_open`, `open`, `intraday_low`/`low_so_far` available for the numerator.
- Existing `touched_up_5pct`/`touched_down_8pct` (+`day_*`) stay **untouched** (back-compat); the grid is additive.

## File map
- **Modify** `config.py` — add grid constants: `RECLAIM_UP_GRID=[1,2,3,5,8]`, `RECLAIM_DOWN_GRID=[1,2,3,5,8]`, `RECLAIM_ATR_GRID=[0.5,1.0,1.5]`; extend collector history start (D2); add new column names to `WATCHLIST_HEADER` (drop_in_ATR).
- **Modify** `post_analysis_collector.py` — `compute()`: compute the three grids; widen `history(start=…)` (D2); add columns to `HEADER`.
- **Modify** `scanner.py` — add `atr_14()` helper; compute `drop_in_ATR`; write to watchlist row. (+ `gradual_scanner.py` if **D4** says symmetric.)
- **Tests** `tests/test_reclaim_grid.py`, `tests/test_drop_in_atr.py` (synthetic OHLC frames; assert day-of-first-cross & ATR math; no network).
- **Docs** update `PROJECT_KNOWLEDGE.md` (schema), `TASKS.md` (V1/drop_in_ATR → DONE), `VARDAN_GAP_ANALYSIS.md` (status).

---

## DECISION points (resolve before code)

**D1 — Grid column storage form.**
- (rec) **day-or-blank**: one column per threshold = first-cross D+n, blank if never (non-blank ⇒ reached). 13 cols total (5 up + 5 down + 3 ATR). Compact, self-describing.
- alt: flag+day per threshold (mirrors current style) → 26 cols. Heavier on the sheet.

**D2 — ATR14-as-of-D0 source for the ATR-reclaim grid.**
- (rec) **widen the collector's history start** to `scan_date − 45d` (same single call, ~zero cost) and compute ATR14 from pre-D0 bars only (no look-ahead).
- alt: read `ATR (14)_num` from `fundamentals_snapshot` (same (scan_date,ticker) key) — but that's Finviz $ATR at capture + a cross-tab join + coupling. Recommend widen-history.

**D3 — ATR-normalized DOWN grid?**
- Your ask: symmetric **%-down** grid on `lows` (✓ included). Question: also add **ATR-normalized down** (drawdown-from-a-peak in ATR units)?
- (rec) **%-down only** for now (clean symmetry with %-up). ATR-down needs a peak anchor (ambiguous) → defer.

**D4 — drop_in_ATR: numerator + scope.**
- (rec) numerator = **intraday drop in $** = `open − intraday_low` (the captured crash span), denominator = **ATR14 in $** as-of scan_date → "drop spanned N×ATR". Point-in-time.
- scope: compute in `scanner.py` (intraday_drop EOD). **Also** in `gradual_scanner.py` (gradual uses window drop, not from-open)? (rec) yes — symmetric, using its window drop in $.

**D5 — Backfill existing rows?**
- (rec) **forward-only** for the daily workflow + a **one-off `--backfill` flag** (mirror `scanner.py --backfill-context`) to recompute the grid for historical `post_analysis` rows and fill drop_in_ATR for old watchlist rows. Not in the daily cron.
- alt: forward-only, no backfill.

**D6 — TASK-V2 (SMA% exposure to watchlist) — include now?**
- It is NOT free here: SMA% lives in `fundamentals_snapshot` (Finviz, separate tab/key); exposing to `watchlist_live` means either a cross-tab join or recomputing SMA20/50/200 distance from the scanner's 400d history.
- (rec) **defer** (separate small task) unless you want the scanner-recompute now (cheap-ish, ~3 extra columns). Your call.

---

## Task outline (finalized to full TDD steps after D1–D6)
1. **config constants + header columns** (per D1/D2/D4/D6) — commit.
2. **`atr_14()` helper in scanner** + unit test (synthetic series vs known ATR) — TDD, commit.
3. **drop_in_ATR in scanner (+gradual per D4)** + test + watchlist write — TDD, commit.
4. **reclaim/drop grids in collector** (widen history per D2; loop UP/DOWN/ATR grids; day-or-blank per D1) + test (synthetic fwd frame: assert each threshold's first-cross day; ATR-from-trough math) — TDD, commit.
5. **(D5) `--backfill` path** for collector grid + watchlist drop_in_ATR + dry-run test — TDD, commit.
6. **(D6 if yes) SMA exposure** — TDD, commit.
7. **dashboard exposure** (view-only columns in Watchlist/Post-Analysis tabs via `dashboard_common`) — commit.
8. **docs update** (PROJECT_KNOWLEDGE schema + TASKS + gap-analysis) — commit.

## Verification (end-to-end)
- `pytest tests/test_reclaim_grid.py tests/test_drop_in_atr.py -v` all pass (synthetic, no network).
- Manual: run collector on 1-2 known events; confirm grid day-of-cross matches a hand-checked OHLC slice; confirm ATR14 as-of D0 uses only pre-D0 bars (print the bar dates).
- Schema: `health_monitor.py` schema-drift check passes (new columns appended, not reordered).
- M5 audit: grep the diff for any use of a grid value in a comparison that drives output/selection — must be none (measurement only).
