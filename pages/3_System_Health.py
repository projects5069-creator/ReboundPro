"""pages/3_System_Health.py — ReboundPro operational health history (VIEW-ONLY).

Shows the health_log written by health_monitor.py: run history by date, an
overall-status trend, and a filterable table. Operational control only — what the
monitor checked and when (is the system running / working / logged) — NOT a
data-quality analysis of the collected data and NOT edge. All logic lives in
dashboard_common.
"""
import dashboard_common as common

common.setup_page("System Health — ReboundPro", "🩺")
common.render_system_health(common.resolve_sheet_id())
