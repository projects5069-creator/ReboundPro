# HYP-002 — Long Mean-Reversion (oversold-bounce) · DRAFT

נרשם: 2026-06-18 · סטטוס: מבוסס-in-sample, טרם-forward · verdict: **Refine**

## תזה
מניה שצנחה ≥10% ביום-מסחר נוטה לתיקון-למעלה (overreaction; Chan 2003) — **בתנאי-regime**.
**LONG-only** (short של אותו מבנה נאכל ב-HTB borrow → net שלילי).

## Universe
drop-events ≥10%/session (DropsLab live), penny-excluded (close ≥ $1).

## Signal (composite, 2 גורמים — מאומת leave-one-out)
```
score = −1·z(pct_from_52w_high) + (+1)·z(rsi_14)
```
z מול **קבועי-discovery קבועים** (לא distribution עתידי):
- `pct_from_52w_high`: mean −59.2650, sd 28.1903
- `rsi_14`: mean +43.0331, sd 11.7443

**LONG = bottom-decile** (score ≤ −1.7733) = near-52w-high + oversold.
`volume_ratio` + `intraday_reversal` **נזנחו** (volume אינרטי sd=89.76; reversal מינורי).

## Regime-gate (מאומת, 2 אינדיקטורים עצמאיים)
- **VIX ≥ ~20 → long פעיל** (med d5 +5.2% / 74%-up) · **VIX < 18 → long מת** (0.0% / 50%-up).
- SPX-downtrend מאשר (+5.5%/75% מול uptrend +1.6%/56%).
- מנגנון: short-term-reversal = **liquidity-provision**, predictable-by-VIX (NY Fed sr513).

## Entry / Exit
- Entry = **MOC ביום-ה-drop** (scan_close); look-ahead-clean (VIX-close ידוע ב-entry).
- Exit = **D5 close** (5 ימי-מסחר). grid D1–D20 = שאלת-forward.

## Cost / Fitness
- long net ≈ **+2.3%** (slip 1%, ללא borrow) בתנאי-regime → **primary**.
- short net ≈ −1.8% (borrow ~6.8% + slip ~4% ב-HTB) → **secondary-exploratory**.
- GO = bootstrap day-cluster CI של net-P&L מעבר-ל-0, forward.

## Evidence (in-sample, n≈3018–3988, 4/02–6/10)
temporal-OOS (test +4.1/64% ≈ in-sample) · random×5 יציב · gradient מונוטוני decile→tercile ·
2 regime-proxies עצמאיים · מנגנון מתועד-בספרות · data-mining נמוך (4 גורמים + composite אחד).

## פערים (כנים)
- **in-sample בלבד.**
- fear אמיתי תת-נדגם (VIX≥22 n=16, ≥25 n=3; טווח 17–21).
- צריך VIX/SPX פר-scan_date forward (הוכח-ישים).
- forward multi-regime טרם נעשה.
- ה-gate מונע **הון-מת**, לא הפסדים.

## Hold-out
discovery n≈3018 נשרף, נעול. validation = **forward-only אחרי-רישום**, n≥150/צד.

## Integration: HYP-002 = Phase-0 של ReboundPro
HYP-002 ממלא בדיוק את החלל החוסם את **M5**:
- composite distress+rsi → `agent/scoring.py` (#9, כיום stub)
- VIX/SPX-gate → `agent/market_context.py` (#4, כיום stub)
- long-only + penny-exclude + net-cost → `costs.py` (כיום stub)
- HYP-002 verdict (Refine) → `research/phase0/` → משחרר תכנון M5 (paper-only, **לא** deploy)

ReboundPro מוסיף ל-HYP-002: **news-falling-knife filter** (Chan, מדויק מ-"distress" הגס) · entry-window-matrix · forward-collection חי.

⚠️ **blocker-לאינטגרציה:** שאלת-דאטה — Phase-0 על DropsLab (n=3988) או דאטת-ReboundPro (~77)?
הגדרות-צניחה דומות-לא-זהות (DropsLab ≥10%/session מול ReboundPro intraday ≥10%/open + gradual 5d). → **TASK-C**.

## Sources
DropsLab live `1XM-qId7…` (drops_raw 4669×38 ⋈ drops_post 3988) · NY Fed sr513 (short-term reversal) ·
Chan 2003 (overreaction) · López de Prado DSR/CPCV (overfit) · Pardo walk-forward · יום-מחקר 2026-06-18.
