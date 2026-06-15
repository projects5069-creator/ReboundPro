"""TDD for dashboard 429 resilience (Stage A, part 3).

A transient Sheets 429 must NOT surface as a red traceback that kills the whole
page. The health banner (top of Home) and the System Health page read the Sheet
with no guard today; on a 429 they should show a friendly "try again in a minute"
message and let the rest of the page render.
"""
import gspread
import pytest
from streamlit.testing.v1 import AppTest

import dashboard_common as common


class _Resp429:
    status_code = 429
    text = '{"error":{"code":429}}'
    headers = {}

    def json(self):
        return {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}


def _raise_429(*a, **k):
    raise gspread.exceptions.APIError(_Resp429())


def _md(at):
    chunks = []
    for attr in ("markdown", "info", "warning", "error"):
        for el in getattr(at, attr, []):
            chunks.append(getattr(el, "value", "") or getattr(el, "body", "") or "")
    return "\n".join(chunks)


def test_health_banner_429_shows_friendly_message_not_exception(monkeypatch):
    monkeypatch.setattr(common, "resolve_sheet_id", lambda: "TEST_SHEET")
    # banner's Sheet read 429s; the page must survive it.
    monkeypatch.setattr(common, "load_health", _raise_429)
    # the rest of Home still needs watch data (a separate, succeeding read)
    import pandas as pd
    monkeypatch.setattr(common, "load",
                        lambda sid, tab, num: pd.DataFrame(
                            [{"drop_kind": "intraday_drop", "scan_date": "2026-06-15",
                              "ticker": "AAPL"}]))
    at = AppTest.from_file("dashboard.py").run(timeout=30)
    assert not at.exception, f"home crashed on 429: {at.exception}"
    assert "מכסה" in _md(at), "no friendly quota message shown"


def test_system_health_page_429_shows_friendly_message(monkeypatch):
    monkeypatch.setattr(common, "resolve_sheet_id", lambda: "TEST_SHEET")
    monkeypatch.setattr(common, "load_health", _raise_429)
    at = AppTest.from_file("pages/3_System_Health.py").run(timeout=30)
    assert not at.exception, f"system health crashed on 429: {at.exception}"
    assert "מכסה" in _md(at), "no friendly quota message shown"
