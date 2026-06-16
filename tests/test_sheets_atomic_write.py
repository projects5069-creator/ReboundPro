"""TDD for the watchlist-wipe fix (2026-06-16 data-loss incident).

Root cause: upsert_rows/upsert_by_key did ws.clear() THEN ws.update(); a
non-JSON-compliant float (inf/NaN from a delisted ticker) made update() raise
AFTER clear() had already emptied the tab → total data loss. Fix:
  1. sanitize inf/-inf/NaN/None -> "" before writing,
  2. update-first then overwrite trailing stale rows with blanks (no destructive
     clear before a successful write) — a write failure leaves old data intact.

All tests use a fake worksheet — no network.
"""
import math

import pytest

import sheets_manager as sm


class FakeWS:
    """Models a gspread worksheet incl. its JSON-compliance check on update()."""

    def __init__(self, values):
        self.values = [list(r) for r in values]
        self.cleared = False

    def get_all_values(self):
        return [list(r) for r in self.values]

    def clear(self):
        self.cleared = True
        self.values = []

    def update(self, range_name=None, values=None):
        # gspread raises this exact error on inf/NaN during JSON serialization
        for row in values:
            for c in row:
                if isinstance(c, float) and (math.isnan(c) or math.isinf(c)):
                    raise ValueError("Out of range float values are not JSON compliant")
        # A1 full write: replace from the top (trailing rows are overwritten by
        # the caller padding blanks, so a plain replace models it faithfully)
        self.values = [list(r) for r in values]


class FailWS(FakeWS):
    """update() always fails — simulates ANY write error mid-upsert."""
    def update(self, range_name=None, values=None):
        raise ValueError("simulated update failure")


class FakeSS:
    def __init__(self, ws):
        self._ws = ws

    def worksheet(self, title):
        return self._ws

    def add_worksheet(self, title, rows, cols):
        return self._ws


class FakeClient:
    def __init__(self, ws):
        self._ss = FakeSS(ws)

    def open_by_key(self, key):
        return self._ss


@pytest.fixture
def patch(monkeypatch):
    def _install(ws):
        monkeypatch.setattr(sm, "get_client", lambda: FakeClient(ws))
        return ws
    return _install


# ── (א) float sanitization ────────────────────────────────────────────────────
def test_json_safe_neutralizes_bad_floats():
    assert sm._json_safe(float("inf")) == ""
    assert sm._json_safe(float("-inf")) == ""
    assert sm._json_safe(float("nan")) == ""
    assert sm._json_safe(None) == ""
    assert sm._json_safe(1.5) == 1.5
    assert sm._json_safe("AAPL") == "AAPL"
    assert sm._json_safe(0) == 0


# ── (ב) REGRESSION: a failed update must NOT empty an existing tab ─────────────
HEADER = ["scan_date", "ticker", "v"]
EXISTING = [HEADER, ["2026-06-12", "ASTS", "1"], ["2026-06-15", "VCX", "2"]]


def test_upsert_by_key_failed_update_keeps_existing_data(patch):
    ws = patch(FailWS(EXISTING))
    with pytest.raises(Exception):
        sm.upsert_by_key("SID", "watchlist_live", HEADER,
                         [{"scan_date": "2026-06-16", "ticker": "NEW", "v": "9"}],
                         ["scan_date", "ticker"])
    # THE PROOF: old rows survive a write failure (clear must NOT precede update)
    assert ws.get_all_values() == EXISTING, "tab was emptied by a failed update — WIPE BUG"
    assert ws.cleared is False, "clear() ran before a successful update — WIPE BUG"


def test_upsert_rows_failed_update_keeps_existing_data(patch):
    ws = patch(FailWS(EXISTING))
    with pytest.raises(Exception):
        sm.upsert_rows("SID", "post_analysis", HEADER,
                       [["2026-06-16", "NEW", "9"]])
    assert ws.get_all_values() == EXISTING, "tab was emptied by a failed update — WIPE BUG"
    assert ws.cleared is False


# ── (ג) a delisted ticker's inf/NaN must not crash the write ───────────────────
def test_upsert_by_key_inf_value_does_not_crash(patch):
    ws = patch(FakeWS(EXISTING))
    sm.upsert_by_key("SID", "watchlist_live", HEADER,
                     [{"scan_date": "2026-06-16", "ticker": "LILKV", "v": float("inf")}],
                     ["scan_date", "ticker"])
    rows = ws.get_all_values()
    lilkv = [r for r in rows if "LILKV" in r]
    assert lilkv, "row not written"
    assert "" in lilkv[0] and all(str(c) != "inf" for c in lilkv[0]), "inf not sanitized"


# ── (ד) shrink: stale trailing rows must be overwritten (update-then-blank) ───
def test_write_matrix_blanks_trailing_stale_rows():
    ws = FakeWS([["h"], ["old1"], ["old2"], ["old3"]])   # old extent = 4 rows
    sm._write_matrix(ws, [["h"], ["new1"]], old_nrows=4)  # write only 2 rows
    vals = ws.get_all_values()
    assert vals[0] == ["h"] and vals[1] == ["new1"], "new content not written"
    flat = [c for r in vals for c in r]
    assert "old1" not in flat and "old2" not in flat and "old3" not in flat, \
        "stale rows survived — trailing not blanked"
    assert len(vals) >= 4, "old extent not fully overwritten"
