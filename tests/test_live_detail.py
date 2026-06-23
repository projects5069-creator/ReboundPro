"""Regression tests for the live-status detail panel (_live_event_detail).

These verify the BUILDING of the panel — the daily-path chart with green/red
per-day-move annotations, and the descriptive outcome cards (MFE / MAE / now /
3-day trend) + event facts. They do NOT exercise the dataframe row-click itself:
that is proven working in-browser, and AppTest cannot simulate a dataframe
selection (no .select() on the Dataframe element). This is the right coverage —
it locks the panel's render so the polish can't silently regress.

VIEW-ONLY (M5): the panel is descriptive — no score / signal / recommendation.
"""
import pandas as pd
from streamlit.testing.v1 import AppTest

import dashboard_common as common

SCAN_DATE, TICKER = "2026-06-13", "ARQQ"


def _fdaily_mature():
    """Matured forward_daily: D+1..D+5, cum_pct_from_ref + daily_change_pct, mixed signs.

    cum path (incl. D+0 anchor 0): [0, 3, 1, 5, 2, -4]
      → MFE=+5.0  MAE=-4.0  now=-4.0  trend3 = cum(D+5) - cum(D+2) = -4 - 1 = -5.0
    daily_change_pct signs: + - + - -  → both green and red labels appear.
    """
    rows = [
        (1, "2026-06-16", 3.0, 3.00),
        (2, "2026-06-17", 1.0, -1.94),
        (3, "2026-06-18", 5.0, 3.96),
        (4, "2026-06-19", 2.0, -2.86),
        (5, "2026-06-20", -4.0, -5.88),
    ]
    return pd.DataFrame(
        [{"scan_date": SCAN_DATE, "ticker": TICKER, "day_offset": o, "date": d,
          "cum_pct_from_ref": cum, "daily_change_pct": chg} for o, d, cum, chg in rows]
    )


def _watch():
    return pd.DataFrame([{"scan_date": SCAN_DATE, "ticker": TICKER,
                          "drop_kind": "intraday_drop", "open": 1.50, "volume": 1234567}])


def _render(fdaily, watch, captured):
    """Render _live_event_detail inside an AppTest, capturing the plotly fig.

    plot() is monkeypatched on the dashboard_common module so the real px figure
    (with our annotations) is captured instead of drawn. Frames are stashed on the
    module because AppTest runs the script in-process and shares sys.modules.
    """
    orig_plot = common.plot
    common.plot = lambda target, fig: captured.append(fig)
    common._test_fd = fdaily
    common._test_watch = watch
    try:
        script = (
            "import dashboard_common as common\n"
            f"common._live_event_detail(None, common._test_watch, common._test_fd, "
            f"{SCAN_DATE!r}, {TICKER!r})\n"
        )
        at = AppTest.from_string(script, default_timeout=30).run()
    finally:
        common.plot = orig_plot
        common.__dict__.pop("_test_fd", None)
        common.__dict__.pop("_test_watch", None)
    return at


def _labels(at):
    return {m.label: m.value for m in at.metric}


def test_mature_event_cards_are_descriptive_outcome():
    """Mature event → window-outcome + event-fact cards, correct values, no 'סוג'."""
    captured = []
    at = _render(_fdaily_mature(), _watch(), captured)
    assert not at.exception, [str(e.value) for e in at.exception]
    labels = _labels(at)
    # the four descriptive outcome cards + three event-fact cards exist
    for lbl in ("שיא בחלון", "שפל בחלון", "מצב נוכחי", "מגמת 3 ימים",
                "מחיר-ייחוס", "נפח (כניסה)", "ימי-מסחר בחלון"):
        assert lbl in labels, f"missing card: {lbl} (have {list(labels)})"
    # the removed card must be gone
    assert "סוג" not in labels
    # values (descriptive, no signal): MFE/MAE/now from the cum path, trend over 3 days
    assert labels["שיא בחלון"] == "+5.0%"
    assert labels["שפל בחלון"] == "-4.0%"
    assert labels["מצב נוכחי"] == "-4.0%"
    assert "▼" in labels["מגמת 3 ימים"] and "-5.0" in labels["מגמת 3 ימים"]
    assert labels["ימי-מסחר בחלון"] == "5"


def test_mature_event_chart_has_colored_daily_change_labels():
    """The daily-path fig carries per-point % annotations, green up / red down."""
    captured = []
    at = _render(_fdaily_mature(), _watch(), captured)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert captured, "plot() was never called — no chart built"
    anns = captured[0].layout.annotations
    assert anns, "no per-day annotations on the chart"
    texts = [a.text for a in anns]
    colors = {a.font.color for a in anns}
    assert all(t.endswith("%") for t in texts), texts
    assert common.GREEN in colors and common.RED in colors, colors  # both signs labelled


def test_immature_event_shows_info_and_no_crash():
    """No forward_daily yet → info message, dashes on outcome cards, no exception."""
    captured = []
    at = _render(pd.DataFrame(), _watch(), captured)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.info, "expected the 'forward window not matured' info message"
    labels = _labels(at)
    assert labels.get("שיא בחלון") == "—"
    assert labels.get("מצב נוכחי") == "—"
    assert labels.get("ימי-מסחר בחלון") == "0"
    assert not captured, "no chart should be built for an immature event"
