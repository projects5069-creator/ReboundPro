"""Regression tests for the live-status detail panel (_live_event_detail).

These verify the BUILDING of the panel — the daily-path chart with green/red
per-day-move annotations, and the descriptive outcome cards (peak / trough since
entry + 3-day trend) + event facts. They do NOT exercise the dataframe row-click itself:
that is proven working in-browser, and AppTest cannot simulate a dataframe
selection (no .select() on the Dataframe element). This is the right coverage —
it locks the panel's render so the polish can't silently regress.

VIEW-ONLY (M5): the panel is descriptive — no score / signal / recommendation.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import dashboard_common as common

SCAN_DATE, TICKER = "2026-06-13", "ARQQ"


def _fdaily_mature():
    """Matured forward_daily: D+1..D+5, cum_pct_from_ref + daily_change_pct, mixed signs.

    cum path (incl. D+0 anchor 0): [0, 3, 1, 5, 2, -4]
      → peak=+5.0  trough=-4.0  trend3 = cum(D+5) - cum(D+2) = -4 - 1 = -5.0
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


def _fdaily_all_negative():
    """A path that only ever falls: cum < 0 on every forward day → the peak must be
    the D+0 entry (0%), NOT the least-negative day. Locks 'peak ≥ 0% since entry'.

    cum path (incl. D+0 anchor 0): [0, -2, -5, -3.5, -8] → peak=+0.0  trough=-8.0
    """
    rows = [
        (1, "2026-06-16", -2.0, -2.00),
        (2, "2026-06-17", -5.0, -3.06),
        (3, "2026-06-18", -3.5, 1.58),
        (4, "2026-06-19", -8.0, -4.66),
    ]
    return pd.DataFrame(
        [{"scan_date": SCAN_DATE, "ticker": TICKER, "day_offset": o, "date": d,
          "cum_pct_from_ref": cum, "daily_change_pct": chg} for o, d, cum, chg in rows]
    )


def _watch():
    return pd.DataFrame([{"scan_date": SCAN_DATE, "ticker": TICKER,
                          "drop_kind": "intraday_drop", "open": 1.50, "volume": 1234567}])


def _render(fdaily, watch, captured, live_pct=None):
    """Render _live_event_detail inside an AppTest, capturing the plotly fig.

    plot() is monkeypatched on the dashboard_common module so the real px figure
    (with our annotations) is captured instead of drawn. Frames are stashed on the
    module because AppTest runs the script in-process and shares sys.modules.
    `live_pct` is the live cum%-from-entry the caller would pass from _live_build.
    """
    orig_plot = common.plot
    common.plot = lambda target, fig: captured.append(fig)
    common._test_fd = fdaily
    common._test_watch = watch
    try:
        script = (
            "import dashboard_common as common\n"
            f"common._live_event_detail(None, common._test_watch, common._test_fd, "
            f"{SCAN_DATE!r}, {TICKER!r}, live_pct={live_pct!r})\n"
        )
        at = AppTest.from_string(script, default_timeout=30).run()
    finally:
        common.plot = orig_plot
        common.__dict__.pop("_test_fd", None)
        common.__dict__.pop("_test_watch", None)
    return at


def _labels(at):
    return {m.label: m.value for m in at.metric}


def _texts(at):
    """All markdown headers + captions joined — for source-tag / sentence assertions."""
    return " | ".join([m.value for m in at.markdown] + [c.value for c in at.caption])


def test_mature_event_cards_are_descriptive_outcome():
    """Mature event → forward_daily outcome group + live group + entry facts, all
    source-tagged. live_pct=-20.6 sits below the historical trough (-4.0%)."""
    captured = []
    at = _render(_fdaily_mature(), _watch(), captured, live_pct=-20.6)
    assert not at.exception, [str(e.value) for e in at.exception]
    labels = _labels(at)
    # forward_daily outcome cards + live card + entry-fact cards all present
    for lbl in ("נקודת שיא מאז הכניסה", "נקודת שפל מאז הכניסה", "מגמה (3 ימים)",
                "טווח בחלון", "ימי עלייה / ירידה", "מיקום נוכחי · חי",
                "מחיר-כניסה", "נפח (כניסה)", "ימי-מסחר בחלון"):
        assert lbl in labels, f"missing card: {lbl} (have {list(labels)})"
    # retired/source-leak cards stay gone
    for gone in ("מצב נוכחי", "סוג", "מגמת 3 ימים"):
        assert gone not in labels
    # forward_daily values (peak/trough incl. D+0 anchor; range = peak-trough; days +/-)
    assert labels["נקודת שיא מאז הכניסה"] == "+5.0%"
    assert labels["נקודת שפל מאז הכניסה"] == "-4.0%"
    assert labels["טווח בחלון"] == "9.0%"
    # ↑/↓ from the per-day move (_chg signs: + − + − − → 2 up, 3 down), NOT cum
    assert labels["ימי עלייה / ירידה"] == "2 ↑ / 3 ↓"
    assert labels["מגמה (3 ימים)"] == "▬ מעורבת"        # last 3 closes mixed
    # live group: position vs the historical extremes (THE clarity datum)
    assert labels["מיקום נוכחי · חי"] == "-20.6%"
    txt = _texts(at)
    assert "forward_daily" in txt and "מצב חי" in txt    # both source tags are shown
    assert "מתחת לשפל ההיסטורי" in txt                   # the explaining sentence


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


def _parse_updown(value):
    """'2 ↑ / 3 ↓' -> (2, 3)."""
    up = int(value.split("↑")[0].strip())
    down = int(value.split("/")[1].split("↓")[0].strip())
    return up, down


@pytest.mark.parametrize("fdaily", [_fdaily_mature(), _fdaily_all_negative()])
def test_days_updown_card_matches_chart_green_red_labels(fdaily):
    """THE real proof the fix works: the ↑/↓ on the 'ימי עלייה / ירידה' card must
    equal EXACTLY the number of green/red daily-move labels on the chart. Same
    threshold drives both (d >= 0 → green/↑, d < 0 → red/↓), so they can never
    diverge — that's the whole point of counting _chg, not cum_pct_from_ref."""
    captured = []
    at = _render(fdaily, _watch(), captured)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert captured, "plot() was never called — no chart built"
    anns = captured[0].layout.annotations
    n_green = sum(1 for a in anns if a.font.color == common.GREEN)
    n_red = sum(1 for a in anns if a.font.color == common.RED)
    up, down = _parse_updown(_labels(at)["ימי עלייה / ירידה"])
    assert up == n_green, f"↑={up} but {n_green} green labels on chart"
    assert down == n_red, f"↓={down} but {n_red} red labels on chart"
    # and every labelled day is counted on one side or the other
    assert up + down == len(anns), f"{up}+{down} != {len(anns)} chart labels"


def test_all_negative_forward_peak_is_entry_zero():
    """A name that only ever fell → peak = entry = +0.0% (≥0), trough = the low.

    This is the bug-fix lock: peak/trough are computed from the path INCLUDING the
    D+0=0% anchor, so a never-recovered name cannot show a negative 'peak'.
    """
    captured = []
    at = _render(_fdaily_all_negative(), _watch(), captured)
    assert not at.exception, [str(e.value) for e in at.exception]
    labels = _labels(at)
    assert labels["נקודת שיא מאז הכניסה"] == "+0.0%"   # the entry anchor, never negative
    assert labels["נקודת שפל מאז הכניסה"] == "-8.0%"
    assert labels["טווח בחלון"] == "8.0%"               # 0.0 - (-8.0)
    # D+3 ROSE on its own day (_chg=+1.58) → 1 up, even though cum stayed < 0 the
    # whole window. This is the bug the fix targets: count daily moves, not cum.
    # _chg signs: − − + − → 1 up, 3 down.
    assert labels["ימי עלייה / ירידה"] == "1 ↑ / 3 ↓"


def test_live_position_vs_historical_extremes():
    """The live group describes where the live price sits vs the forward_daily band."""
    # below the historical trough (the case that confused entry vs daily-closes)
    at = _render(_fdaily_mature(), _watch(), [], live_pct=-20.6)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "מתחת לשפל ההיסטורי" in _texts(at)
    # inside the band (between trough -4 and peak +5)
    at = _render(_fdaily_mature(), _watch(), [], live_pct=1.0)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "בין השיא והשפל ההיסטוריים" in _texts(at)


def test_immature_event_shows_info_and_no_crash():
    """No forward_daily yet → info message, dashes on outcome cards, no exception."""
    captured = []
    at = _render(pd.DataFrame(), _watch(), captured, live_pct=-12.0)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.info, "expected the 'forward window not matured' info message"
    labels = _labels(at)
    assert labels.get("נקודת שיא מאז הכניסה") == "—"
    assert labels.get("נקודת שפל מאז הכניסה") == "—"
    assert labels.get("טווח בחלון") == "—"
    assert labels.get("ימי עלייה / ירידה") == "—"
    assert "מצב נוכחי" not in labels
    assert labels.get("ימי-מסחר בחלון") == "0"
    # live price still shown, but no historical band to compare against yet
    assert labels.get("מיקום נוכחי · חי") == "-12.0%"
    assert "אין עדיין קצוות היסטוריים" in _texts(at)
    assert not captured, "no chart should be built for an immature event"
