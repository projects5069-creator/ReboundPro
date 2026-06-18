"""H3 (A+) — lock the verdict->exit-code signal that drives the reboundpro-warn ping.

health.yml pings reboundpro-warn /fail vs /success based on `$code`, which is
`Monitor.overall()` (max severity) -> sys.exit(). That mapping was untested; these
pure tests lock it so the alert signal can't silently drift.
"""
import health_monitor as hm


def _overall(*statuses):
    m = hm.Monitor()
    for i, s in enumerate(statuses):
        m.add(f"c{i}", "Pillar", s, "msg")
    return m.overall()


def test_overall_all_ok_is_0():
    assert _overall(hm.OK, hm.OK, hm.OK) == hm.OK == 0


def test_overall_warn_when_any_warn_no_fail_is_1():
    assert _overall(hm.OK, hm.WARN, hm.OK) == hm.WARN == 1


def test_overall_fail_dominates_warn_is_2():
    assert _overall(hm.WARN, hm.FAIL, hm.OK) == hm.FAIL == 2
