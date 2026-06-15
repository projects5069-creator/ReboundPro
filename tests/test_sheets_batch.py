"""TDD for the 429-mitigation read path (Stage A).

batch_read must read N tabs in exactly 2 Google API calls (one spreadsheets_get
for the sheet titles + one values:batchGet for all tabs) instead of read_rows'
2 calls per tab, and return the SAME (header, rows) shape per tab. A transient
429 must be retried with backoff, not propagated on the first hit. All tests use
a fake HTTPClient — no network, no quota.
"""
import gspread
import pytest

import sheets_manager as sm


class _Resp429:
    status_code = 429
    reason = "Too Many Requests"
    text = '{"error":{"code":429}}'
    headers = {}

    def json(self):
        return {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}


def _api_error_429():
    return gspread.exceptions.APIError(_Resp429())


class FakeHTTP:
    """Counts calls and serves canned metadata + values, optionally failing the
    first `fail_batch_429` values:batchGet calls with a 429."""

    def __init__(self, titles, values_map, fail_batch_429=0):
        self.titles = titles
        self.values_map = values_map
        self.fail_batch_429 = fail_batch_429
        self.calls = []

    def spreadsheets_get(self, id, params=None):
        self.calls.append("meta")
        return {"sheets": [{"properties": {"title": t}} for t in self.titles]}

    def values_batch_get(self, id, ranges, params=None):
        self.calls.append("batch")
        if self.fail_batch_429 > 0:
            self.fail_batch_429 -= 1
            raise _api_error_429()
        vrs = [{"values": self.values_map.get(r.strip("'"), [])} for r in ranges]
        return {"valueRanges": vrs}


class FakeClient:
    def __init__(self, http):
        self.http_client = http


@pytest.fixture
def patch_client(monkeypatch):
    def _install(http):
        monkeypatch.setattr(sm, "get_client", lambda: FakeClient(http))
        # don't actually sleep during retry tests
        monkeypatch.setattr(sm.time, "sleep", lambda *_: None)
        return http
    return _install


def test_batch_read_two_calls_for_many_tabs(patch_client):
    http = patch_client(FakeHTTP(
        titles=["watchlist_live", "post_analysis", "health_log"],
        values_map={
            "watchlist_live": [["ticker", "price"], ["AAPL", "123"]],
            "post_analysis": [["ticker", "status"], ["AAPL", "ok"]],
            "health_log": [["run_at", "mode"], ["2026-06-15", "morning"]],
        },
    ))
    out = sm.batch_read("SID", ["watchlist_live", "post_analysis", "health_log"])
    # exactly 2 API calls regardless of tab count (was 2*3=6 with read_rows)
    assert http.calls == ["meta", "batch"], http.calls
    assert out["watchlist_live"] == (["ticker", "price"], [["AAPL", "123"]])
    assert out["post_analysis"] == (["ticker", "status"], [["AAPL", "ok"]])
    assert out["health_log"][0] == ["run_at", "mode"]


def test_batch_read_missing_tab_returns_empty(patch_client):
    http = patch_client(FakeHTTP(
        titles=["watchlist_live"],                       # other tabs don't exist yet
        values_map={"watchlist_live": [["ticker"], ["AAPL"]]},
    ))
    out = sm.batch_read("SID", ["watchlist_live", "intraday_timeseries"])
    assert out["watchlist_live"] == (["ticker"], [["AAPL"]])
    assert out["intraday_timeseries"] == ([], [])        # missing -> empty, no crash
    # missing tab must NOT be requested in the batch (would 400 the whole call)
    assert http.calls == ["meta", "batch"]


def test_batch_read_retries_on_transient_429(patch_client):
    http = patch_client(FakeHTTP(
        titles=["health_log"],
        values_map={"health_log": [["run_at"], ["2026-06-15"]]},
        fail_batch_429=1,                                # first batch 429s, then ok
    ))
    out = sm.batch_read("SID", ["health_log"])
    assert out["health_log"] == (["run_at"], [["2026-06-15"]])
    # one failed batch + one successful retry
    assert http.calls == ["meta", "batch", "batch"], http.calls


def test_batch_read_raises_after_retries_exhausted(patch_client):
    http = patch_client(FakeHTTP(
        titles=["health_log"],
        values_map={"health_log": [["x"]]},
        fail_batch_429=99,                               # always 429
    ))
    with pytest.raises(gspread.exceptions.APIError):
        sm.batch_read("SID", ["health_log"])
