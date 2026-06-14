"""pages/1_Intraday_Drop.py — ReboundPro hypothesis page: intraday_drop (VIEW-ONLY).

Sharp same-day drops (sharp intraday over-reaction). Shows ONLY drop_kind ==
"intraday_drop" rows across the full tab set. All logic is in dashboard_common —
this page just sets the filter. No drop_kind multiselect (the page is the filter).
"""
import dashboard_common as common

common.setup_page("Intraday Drop — ReboundPro", "⚡")
common.render(
    "intraday_drop",
    "⚡ Intraday Drop — צניחה חדה תוך-יומית",
    "מניות נזילות שצנחו חזק תוך-יומי (תגובת-יתר → reversal). עמודת-הצניחה: drop_pct_from_open + מסלול תוך-יומי.",
)
