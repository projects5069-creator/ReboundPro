"""health_monitor.py — ReboundPro pipeline health monitor (READ-ONLY).

Checks the PIPELINE, not the content. It verifies that data goes IN / is BUILT /
goes OUT correctly — it does NOT score, rank, interpret outcomes, or touch the
recovery distribution. Peeking at the outcome distribution would be a forbidden
edge-peek; edge is decided at M4 (see MASTERPLAN §5), never here. Operational
inputs only.

READ-ONLY against the Google Sheet (only sheets_manager.read_rows is ever called).
The single file it writes is a local health_log.jsonl (append) for trend tracking.

10 focused checks across 5 pillars (kept deliberately small — no noise checks):
  Freshness        : 1 scanner-freshness · 2 intraday-freshness · 3 sheet-freshness
  Volume/Complete. : 4 volume-anomaly · 5 continuity · 6 post-analysis-progress
  Schema           : 7 schema-drift (guards the TAB_TIMESERIES class of bug)
  Field health     : 8 field-completeness · 9 duplicates+sanity-bounds
  Ops/contamination: 10 contamination-trend (reported as a trend, never a fail)

Severity: ✅ 0 = healthy · ⚠️ 1 = warning · ❌ 2 = failure. Exit code = max severity.

Usage:
    python health_monitor.py --morning   # "is the system alive & ready for the day?"
    python health_monitor.py --evening   # "did today's collection land correctly?"
    python health_monitor.py             # full report (no mode-specific summary)
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, date, time as dtime

import pandas as pd
import pytz
import exchange_calendars as ec

import config
import sheets_manager as sm
import scanner as sc
import post_analysis_collector as pac
import fundamentals as fund
import catalyst as cat

ET = pytz.timezone("America/New_York")
OK, WARN, FAIL = 0, 1, 2
EMOJI = {OK: "✅", WARN: "⚠️", FAIL: "❌"}
CALM_ICON = "🌙"   # severity stays OK (never affects exit) — visual "market closed, nothing expected"
STATUS_WORD = {OK: "ok", WARN: "warn", FAIL: "fail"}
OVERALL_WORD = {OK: "healthy", WARN: "warning", FAIL: "error"}
LOG_PATH = os.path.join(os.path.dirname(__file__), "health_log.jsonl")

# field-completeness alert threshold: % of rows with a blank context field
COMPLETENESS_WARN_PCT = 50.0
# how many days past the horizon a post row may stay pending before it's "stuck"
POST_STUCK_BUFFER_DAYS = 2

EXPECTED_HEADERS = {
    config.TAB_WATCHLIST: config.WATCHLIST_HEADER,
    config.TAB_POST: pac.HEADER,
    config.TAB_SUMMARY: sc.SUMMARY_HEADER,
    config.TAB_FUNDAMENTALS: fund.FUND_HEADER,
    config.TAB_NEWS: cat.NEWS_HEADER,
    config.TAB_TIMESERIES: config.TIMESERIES_HEADER,
}


# ── helpers ──────────────────────────────────────────────────────────────────
def _parse_f(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _rows_as_dicts(header, rows):
    return [{header[i]: (r[i] if i < len(r) else "") for i in range(len(header))} for r in rows]


def expected_last_scan_date(now, cal):
    """The most recent COMPLETED trading session. The EOD collector runs ~18:30 ET,
    so a session counts as collected only after that; before it, step back one."""
    ltd = sc.last_trading_day(now.date())
    if ltd == now.date() and now.time() < dtime(18, 30):
        ltd = sc.last_trading_day(now.date() - timedelta(days=1))
    return ltd


class Monitor:
    def __init__(self):
        self.findings = []

    def add(self, cid, pillar, status, msg, icon=None):
        # icon overrides the severity emoji (e.g. CALM_ICON for "market closed" —
        # still severity=OK so exit-code is unaffected).
        self.findings.append({"id": cid, "pillar": pillar, "status": status,
                              "msg": msg, "icon": icon})

    def overall(self):
        return max((f["status"] for f in self.findings), default=OK)


# ── the 10 checks ────────────────────────────────────────────────────────────
def run_checks(data, now, cal):
    m = Monitor()
    exp_last = expected_last_scan_date(now, cal)
    exp_last_s = exp_last.isoformat()

    wh, wd = data[config.TAB_WATCHLIST]
    wi = {c: i for i, c in enumerate(wh)} if wh else {}
    wdicts = _rows_as_dicts(wh, wd) if wh else []
    scan_dates = sorted({d.get("scan_date", "") for d in wdicts if d.get("scan_date")})

    # ---- Pillar: Freshness ----
    # 1. scanner-freshness
    if not scan_dates:
        m.add("scanner-freshness", "Freshness", FAIL, "watchlist_live ריק — אין scan כלל.")
    else:
        last = scan_dates[-1]
        if last == exp_last_s:
            m.add("scanner-freshness", "Freshness", OK,
                  f"scan אחרון {last} == יום-מסחר אחרון צפוי.")
        elif last < exp_last_s:
            m.add("scanner-freshness", "Freshness", FAIL,
                  f"scan אחרון {last} מפגר אחרי הצפוי {exp_last_s} — ה-EOD scanner לא רץ.")
        else:
            m.add("scanner-freshness", "Freshness", WARN,
                  f"scan אחרון {last} מאוחר מהצפוי {exp_last_s} (בדוק שעון/לוח).")

    # 2. intraday-freshness — only a real concern when the market is OPEN TODAY.
    #    On a weekend/holiday no intraday collection is expected → CALM (severity OK,
    #    🌙 icon), so "market closed" never shows a yellow ⚠️ that dulls the eye.
    today = now.date()
    if not cal.is_session(pd.Timestamp(today)):
        m.add("intraday-freshness", "Freshness", OK,
              f"שוק XNYS סגור היום ({today}, סופ\"ש/חג) — לא צפוי איסוף intraday.",
              icon=CALM_ICON)
    else:
        has_intraday = any(d.get("scan_date") == exp_last_s and d.get("source") == "intraday"
                           for d in wdicts)
        if has_intraday:
            m.add("intraday-freshness", "Freshness", OK,
                  f"יום-מסחר; יש שורות source=intraday מ-{exp_last_s}.")
        else:
            m.add("intraday-freshness", "Freshness", WARN,
                  f"יום-מסחר ({today}) אך 0 שורות source=intraday ל-{exp_last_s} "
                  "(הסורק התוך-יומי לא רץ / source ריק).")

    # 3. sheet-freshness (all 6 tabs accessible; core non-empty)
    accessible = sum(1 for t in EXPECTED_HEADERS if data[t][0])
    empty_core = [t for t in (config.TAB_WATCHLIST,) if not data[t][0]]
    if empty_core:
        m.add("sheet-freshness", "Freshness", FAIL,
              f"טאב-ליבה ריק/לא-נגיש: {empty_core}.")
    else:
        m.add("sheet-freshness", "Freshness", OK,
              f"{accessible}/6 טאבים נגישים עם header; watchlist פעיל.")

    # ---- Pillar: Volume / Completeness ----
    # 4. volume-anomaly
    per_day = Counter(d["scan_date"] for d in wdicts if d.get("scan_date"))
    if not per_day:
        m.add("volume-anomaly", "Volume", WARN, "אין מועמדים כלל.")
    else:
        last_n = per_day[scan_dates[-1]]
        if last_n == 0:
            m.add("volume-anomaly", "Volume", WARN, f"0 מועמדים ביום האחרון {scan_dates[-1]}.")
        elif len(per_day) >= 3:
            hist = [per_day[d] for d in scan_dates[:-1]]
            mean = sum(hist) / len(hist)
            if mean > 0 and (last_n < 0.2 * mean or last_n > 5 * mean):
                m.add("volume-anomaly", "Volume", WARN,
                      f"מועמדים ביום האחרון={last_n} חריג מול ממוצע היסטורי {mean:.1f}.")
            else:
                m.add("volume-anomaly", "Volume", OK,
                      f"מועמדים/יום בטווח (אחרון={last_n}, ממוצע={mean:.1f}).")
        else:
            m.add("volume-anomaly", "Volume", OK,
                  f"מועמדים ביום האחרון={last_n} (היסטוריה קצרה מדי להשוואת-טווח).")

    # 5. continuity (gap detection within the active collection period)
    if scan_dates:
        try:
            dmin = datetime.strptime(scan_dates[0], "%Y-%m-%d").date()
            sess = cal.sessions_in_range(pd.Timestamp(dmin), pd.Timestamp(exp_last))
            present = set(scan_dates)
            missing = [s.date().isoformat() for s in sess if s.date().isoformat() not in present]
            if missing:
                m.add("continuity", "Volume", FAIL,
                      f"{len(missing)} ימי-מסחר חסרים בין {scan_dates[0]} ל-{exp_last_s}: "
                      f"{missing[:6]}{'…' if len(missing) > 6 else ''}.")
            else:
                m.add("continuity", "Volume", OK,
                      f"רצף מלא {scan_dates[0]}→{exp_last_s} ({len(sess)} ימי-מסחר, אפס פערים).")
        except Exception as e:
            m.add("continuity", "Volume", WARN, f"בדיקת-רצף נכשלה: {e}")
    else:
        m.add("continuity", "Volume", FAIL, "אין scan_dates לבדיקת-רצף.")

    # 6. post_analysis-progress
    ph, pdata = data[config.TAB_POST]
    if not ph:
        m.add("post-progress", "Volume", WARN, "post_analysis ריק — טרם נאספו תוצאות.")
    else:
        pdicts = _rows_as_dicts(ph, pdata)
        sc_status = Counter(d.get("status", "") for d in pdicts)
        stuck = 0
        for d in pdicts:
            if d.get("status") == "pending_forward":
                try:
                    sd = datetime.strptime(d["scan_date"], "%Y-%m-%d").date()
                    if pac.expected_forward_sessions(sd, config.POST_ANALYSIS_HORIZON) >= 1:
                        stuck += 1
                except Exception:
                    pass
        brk = dict(sc_status)
        if stuck:
            m.add("post-progress", "Volume", WARN,
                  f"{stuck} שורות תקועות ב-pending_forward אף שחלפו ימי-מסחר "
                  f"(post_analysis לא רץ?). סטטוסים: {brk}")
        else:
            m.add("post-progress", "Volume", OK, f"סטטוסי post_analysis: {brk}")

    # ---- Pillar: Schema (guards the TAB_TIMESERIES class of bug) ----
    drift = []
    empty_tabs = []
    for tab, exp in EXPECTED_HEADERS.items():
        live = data[tab][0]
        if not live:
            empty_tabs.append(tab)
            continue
        if live != exp:
            miss = [c for c in exp if c not in live]
            extra = [c for c in live if c not in exp]
            order = (live != exp and not miss and not extra)
            drift.append((tab, miss, extra, order))
    if drift:
        parts = []
        for tab, miss, extra, order in drift:
            seg = tab + (f" missing={miss}" if miss else "") + (f" extra={extra}" if extra else "")
            seg += " (order-differs)" if order else ""
            parts.append(seg)
        m.add("schema-drift", "Schema", FAIL, "סטיית-סכימה: " + " | ".join(parts))
    else:
        note = f" (טאבים ריקים, דולגו: {empty_tabs})" if empty_tabs else ""
        m.add("schema-drift", "Schema", OK, f"כל ה-headers החיים תואמים לסכימה{note}.")

    # ---- Pillar: Field health ----
    # 8. field-completeness (context fields)
    if wdicts:
        check_fields = ["drop_kind", "vix_level", "prior_decline_20d_pct"]
        worst = []
        max_status = OK
        for f in check_fields:
            if f not in wi:
                worst.append(f"{f}: עמודה חסרה")
                max_status = max(max_status, WARN)
                continue
            blank = sum(1 for d in wdicts if d.get(f, "") in ("", None))
            pct = blank / len(wdicts) * 100
            if pct > COMPLETENESS_WARN_PCT:
                worst.append(f"{f}: {pct:.0f}% ריק")
                max_status = max(max_status, WARN)
        if max_status == OK:
            m.add("field-completeness", "Field", OK, "שדות-הקשר מאוכלסים מעל הסף.")
        else:
            m.add("field-completeness", "Field", WARN,
                  "שדות-הקשר חסרים (scanner לא כותב?): " + " · ".join(worst))
    else:
        m.add("field-completeness", "Field", WARN, "אין שורות לבדיקת-שלמות.")

    # 9. duplicates + sanity-bounds
    keys = Counter((d.get("scan_date"), d.get("ticker")) for d in wdicts)
    dups = [k for k, n in keys.items() if n > 1]
    sanity = []
    for d in wdicts:
        p = _parse_f(d.get("price"))
        if p is not None and p <= 0:
            sanity.append(f"{d.get('ticker')}:price<=0")
        rsi = _parse_f(d.get("rsi_14"))
        if rsi is not None and not (0 <= rsi <= 100):
            sanity.append(f"{d.get('ticker')}:rsi={rsi}")
        dfo = _parse_f(d.get("drop_pct_from_open"))
        if dfo is not None and dfo > 0:
            sanity.append(f"{d.get('ticker')}:drop_from_open>0")
    if dups:
        m.add("duplicates-sanity", "Field", FAIL,
              f"{len(dups)} מפתחות (scan_date,ticker) כפולים: {dups[:5]}.")
    elif sanity:
        m.add("duplicates-sanity", "Field", WARN,
              f"{len(sanity)} ערכים מחוץ-לטווח: {sanity[:6]}.")
    else:
        m.add("duplicates-sanity", "Field", OK, "אין כפילויות; ערכים בטווח-שפיות.")

    # ---- Pillar: Ops / contamination (trend, never a fail) ----
    if ph and "split_halt_flag" in ph:
        pdicts = _rows_as_dicts(ph, pdata)
        flagged = sum(1 for d in pdicts if str(d.get("split_halt_flag", "")).strip().lower()
                      in ("true", "1"))
        tot = len(pdicts)
        pct = (flagged / tot * 100) if tot else 0
        m.add("contamination-trend", "Ops", OK,
              f"זיהום split/halt: {flagged}/{tot} ({pct:.1f}%) — מעקב-מגמה (יוחרג ב-M4).")
    else:
        m.add("contamination-trend", "Ops", OK,
              "זיהום split/halt: n/a (עמודת split_halt_flag טרם נכתבה ל-post_analysis).")

    return m, exp_last_s


# ── intake summary (evening) ─────────────────────────────────────────────────
def intake_summary(data, exp_last_s):
    wh, wd = data[config.TAB_WATCHLIST]
    if not wh:
        return "אין נתונים."
    wdicts = _rows_as_dicts(wh, wd)
    today = [d for d in wdicts if d.get("scan_date") == exp_last_s]
    if not today:
        return f"אין שורות חדשות ל-{exp_last_s} (יום-מסחר אחרון)."
    sectors = Counter(d.get("sector", "") or "—" for d in today)
    kinds = Counter((d.get("drop_kind", "") or "(ריק)") for d in today)
    top_sectors = ", ".join(f"{s}:{n}" for s, n in sectors.most_common(5))
    kinds_s = ", ".join(f"{k}:{n}" for k, n in kinds.items())
    return (f"נאספו {len(today)} שורות ל-{exp_last_s} · drop_kind[{kinds_s}] · "
            f"סקטורים[{top_sectors}]")


# ── reporting ────────────────────────────────────────────────────────────────
def finding_line(f):
    icon = f.get("icon") or EMOJI[f["status"]]
    return f"{icon} [{f['pillar']:<10}] {f['id']}: {f['msg']}"


def details_text(m):
    """Full per-check explanation lines (newline-joined) — for STEP_SUMMARY, the
    health_log details column, and the dashboard expander."""
    return "\n".join(finding_line(f) for f in m.findings)


def verdict_text(m):
    n_fail = sum(1 for f in m.findings if f["status"] == FAIL)
    n_warn = sum(1 for f in m.findings if f["status"] == WARN)
    n_ok = len(m.findings) - n_fail - n_warn
    verdict = {OK: "בריא ✅", WARN: "אזהרות ⚠️", FAIL: "תקלה ❌"}[m.overall()]
    return f"{verdict} · ❌{n_fail} ⚠️{n_warn} ✅{n_ok}"


def report(m, mode, exp_last_s, data):
    title = {"morning": "🌅 בוקר — המערכת חיה ומוכנה ליום?",
             "evening": "🌆 ערב — האיסוף של היום נכנס תקין?",
             "full": "🩺 ReboundPro — בריאות-צינור (דוח מלא)"}[mode]
    print(f"\n{title}   (יום-מסחר אחרון צפוי: {exp_last_s})")
    print("=" * 64)
    for f in m.findings:
        print(finding_line(f))
    if mode == "evening":
        print("-" * 64)
        print("📥 מה נאסף: " + intake_summary(data, exp_last_s))
    print("=" * 64)
    print(f"סיכום: {verdict_text(m)} · exit={m.overall()}")


def write_log(m, mode, exp_last_s, now):
    rec = {"ts": now.strftime("%Y-%m-%d %H:%M:%S %Z"), "mode": mode,
           "expected_last_scan": exp_last_s, "overall": m.overall(),
           "checks": [{"id": f["id"], "status": f["status"]} for f in m.findings]}
    try:
        with open(LOG_PATH, "a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"(warn: health_log.jsonl write failed: {e})")


def write_sheet_log(m, mode, exp_last_s, now):
    """Append one control row to the health_log tab — the ONLY tab the monitor
    writes. Skips silently if no Sheet/creds (the local jsonl is always written);
    never breaks the run."""
    if not config.SHEET_ID:
        return
    row = {"run_at": now.strftime("%Y-%m-%d %H:%M:%S %Z"), "mode": mode,
           "overall_status": OVERALL_WORD[m.overall()], "exit_code": m.overall(),
           "summary_text": verdict_text(m), "details_text": details_text(m)}
    for f in m.findings:
        row[f["id"]] = STATUS_WORD[f["status"]]
    try:
        sm.upsert_by_key(config.SHEET_ID, config.TAB_HEALTH_LOG,
                         config.HEALTH_LOG_HEADER, [row], ["run_at"])
    except Exception as e:
        print(f"(warn: health_log Sheet write skipped: {e})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--morning", action="store_true")
    ap.add_argument("--evening", action="store_true")
    args = ap.parse_args()
    mode = "morning" if args.morning else "evening" if args.evening else "full"

    if not config.SHEET_ID:
        print("❌ REBOUND_SHEET_ID לא מוגדר — אין מקור נתונים.")
        sys.exit(FAIL)

    now = datetime.now(ET)
    cal = ec.get_calendar("XNYS")
    tabs = list(EXPECTED_HEADERS.keys())
    data = {t: sm.read_rows(config.SHEET_ID, t) for t in tabs}   # READ-ONLY

    m, exp_last_s = run_checks(data, now, cal)
    report(m, mode, exp_last_s, data)
    write_log(m, mode, exp_last_s, now)        # local jsonl (always)
    write_sheet_log(m, mode, exp_last_s, now)  # health_log tab (only tab written)
    sys.exit(m.overall())


if __name__ == "__main__":
    main()
