"""pages/4_Live_Status.py — ReboundPro live intraday status (VIEW-ONLY).

One row per tracked (scan_date, ticker) with its latest intraday point from
intraday_timeseries — current price, % from open, update time (ET), and
days-since-entry (D+n), sorted by intraday move size. Descriptive only:
NO score / signal / ranking / entry decision (M5 boundary). Auto-refreshes
every 300s and breathes only during market hours. All logic lives in
dashboard_common.render_live_status — this page is just a thin wrapper.
"""
import dashboard_common as common

common.setup_page("Live Status — ReboundPro", "📡")
common.render_live_status()
