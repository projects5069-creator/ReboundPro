"""pages/5_Live_Gradual.py — live status, 🐢 gradual_drop ONLY (VIEW-ONLY).

Breathing overview (KPIs + pies) + per-event table with click-to-detail, filtered
to drop_kind == "gradual_drop". All logic lives in dashboard_common.render_live_status.
"""
import dashboard_common as common

common.setup_page("Live · Gradual — ReboundPro", "🐢")
common.render_live_status("gradual_drop")
