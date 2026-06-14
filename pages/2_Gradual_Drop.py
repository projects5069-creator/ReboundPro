"""pages/2_Gradual_Drop.py — ReboundPro hypothesis page: gradual_drop (VIEW-ONLY).

Slow 5-day declines (separate hypothesis). Shows ONLY drop_kind == "gradual_drop"
rows across the full tab set. All logic is in dashboard_common — this page just
sets the filter. No drop_kind multiselect (the page is the filter).

⚠️ value-trap: fundamentals are a FEATURE here, never a filter; no entry decision
   — the net-edge verdict is deferred to M4 (see MASTERPLAN §2/§5).
"""
import dashboard_common as common

common.setup_page("Gradual Drop — ReboundPro", "🐢")
common.render(
    "gradual_drop",
    "🐢 Gradual Drop — ירידה הדרגתית (5 ימי-מסחר)",
    "מניות שירדו ≥10% לאורך 5 ימי-מסחר (לא קריסה יומית). עמודת-הצניחה: drop_pct_window + lookback_trading_days + ref_close_window.",
)
