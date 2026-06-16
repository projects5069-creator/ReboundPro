"""TDD for the unified 'reboundpro' chart theme (display-only).

A single registered plotly template + px.defaults so every chart inherits one
professional look; a pure sign_colors() for %-bars; and removal of the redundant
blue sub-window max-recovery chart (its 4 numbers stay in the post table).
The 4-page render-0-exceptions test (test_dashboard_overflow) guards the
cross-cutting plot() wrapper; colours/grid/modebar themselves are visual and
verified in Cloud.
"""
import pathlib

import plotly.express as px
import plotly.io as pio

import dashboard_common as common


def test_reboundpro_template_registered_and_default():
    assert "reboundpro" in pio.templates, "template not registered"
    assert px.defaults.template == "reboundpro", "px.defaults.template not set"


def test_sign_colors_green_red_grey():
    # >=0 green, <0 red, NaN/None grey
    assert common.sign_colors([1.0, -2.0, 0.0, float("nan"), None]) == \
        ["#26a69a", "#ef5350", "#26a69a", "#cccccc", "#cccccc"]


def test_blue_subwindow_chart_removed_from_source():
    # plotly titles are not exposed in AppTest markdown → assert removal at source.
    src = pathlib.Path("dashboard_common.py").read_text(encoding="utf-8")
    assert "max recovery לפי תת-חלון" not in src, "blue sub-window chart still present"
