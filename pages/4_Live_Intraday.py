"""pages/4_Live_Intraday.py — live status, ⚡ intraday_drop ONLY (VIEW-ONLY).

Breathing overview (KPIs + pies) + per-event table with click-to-detail, filtered
to drop_kind == "intraday_drop". All logic lives in dashboard_common.render_live_status.
"""
import dashboard_common as common

common.setup_page("Live · Intraday — ReboundPro", "⚡")
common.render_live_status("intraday_drop")
