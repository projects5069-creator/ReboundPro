"""pages/6_Entry_Profile_Intraday.py — Entry-condition profile, ⚡ intraday_drop ONLY (VIEW-ONLY).

DESCRIPTIVE / M5-safe: per-event entry metrics + current change-from-entry (status,
not outcome), collection status, coverage, and pooled per-metric distributions.
No scores/signals/ranking/thresholds/up-vs-down. All logic in
dashboard_common.render_entry_profile.
"""
import dashboard_common as common

common.setup_page("Entry Profile · Intraday — ReboundPro", "🔬")
common.render_entry_profile("intraday_drop")
