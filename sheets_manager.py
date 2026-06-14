"""sheets_manager.py — ReboundPro Google Sheets I/O (M1).

Service-account auth (creds file at google_credentials.json). The SA cannot
*create* sheets (Drive quota); the target sheet must be created by the user and
shared with the SA as Editor. Pattern mirrors DropsLab/gsheets_sync.
"""
import json
import os

import gspread
from google.oauth2.service_account import Credentials

import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def _load_credentials():
    """Creds priority: local file (dev) -> Streamlit secrets (cloud) -> env JSON.
    Mirrors DropsLab/gsheets_sync so the same code runs locally and on the cloud.
    """
    # 1. local service-account file (local dev / GitHub Actions writes it)
    if os.path.exists(config.CREDS_PATH):
        return Credentials.from_service_account_file(config.CREDS_PATH, scopes=SCOPES)
    # 2. Streamlit Cloud secrets
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
            return Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"]), scopes=SCOPES)
    except Exception:
        pass
    # 3. env var with raw JSON
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
    if raw:
        return Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    raise EnvironmentError(
        "No Google credentials: provide google_credentials.json, "
        "st.secrets['gcp_service_account'], or GOOGLE_CREDENTIALS_JSON.")


def get_client():
    return gspread.authorize(_load_credentials())


def service_account_email():
    return _load_credentials().service_account_email


def get_or_create_worksheet(ss, title, rows=2000, cols=40):
    try:
        return ss.worksheet(title)
    except gspread.WorksheetNotFound:
        return ss.add_worksheet(title=title, rows=rows, cols=cols)


def upsert_rows(sheet_id, tab, header, rows, date_col="scan_date"):
    """Date-based upsert: drop existing rows whose date matches the batch, then
    rebuild header + surviving + new. One row per (ticker, date), re-run safe.
    """
    if not rows:
        return 0, 0
    client = get_client()
    ss = client.open_by_key(sheet_id)
    ws = get_or_create_worksheet(ss, tab, cols=len(header))
    existing = ws.get_all_values()
    batch_dates = {r[header.index(date_col)] for r in rows}
    surviving = []
    if existing and existing[0] == header:
        dci = header.index(date_col)
        surviving = [r for r in existing[1:] if r and r[dci] not in batch_dates]
    ws.clear()
    ws.update(range_name="A1", values=[header] + surviving + rows)
    return len(surviving), len(rows)


def upsert_by_key(sheet_id, tab, header, new_dicts, key_cols):
    """Merge rows by composite key, column-NAME-safe (migration-safe).

    Existing rows are remapped from their stored header to `header` by column
    name (so adding columns never misaligns old rows). Rows whose key matches a
    new row are REPLACED; all other existing rows are preserved. Returns
    (n_updated, n_inserted, n_total).
    """
    client = get_client()
    ss = client.open_by_key(sheet_id)
    ws = get_or_create_worksheet(ss, tab, cols=len(header))
    existing = ws.get_all_values()

    merged = {}          # key -> dict
    order = []           # preserve row order
    if existing and len(existing) > 1:
        old_header = existing[0]
        for r in existing[1:]:
            d = {old_header[i]: (r[i] if i < len(r) else "") for i in range(len(old_header))}
            k = tuple(d.get(c, "") for c in key_cols)
            if k not in merged:
                order.append(k)
            merged[k] = {c: d.get(c, "") for c in header}

    updated = inserted = 0
    for nd in new_dicts:
        k = tuple(str(nd.get(c, "")) for c in key_cols)
        if k in merged:
            merged[k].update({c: nd.get(c, merged[k].get(c, "")) for c in header})
            updated += 1
        else:
            merged[k] = {c: nd.get(c, "") for c in header}
            order.append(k)
            inserted += 1

    matrix = [[("" if merged[k].get(c) is None else merged[k].get(c)) for c in header]
              for k in order]
    ws.clear()
    ws.update(range_name="A1", values=[header] + matrix)
    return updated, inserted, len(order)


def read_rows(sheet_id, tab):
    client = get_client()
    ss = client.open_by_key(sheet_id)
    try:
        ws = ss.worksheet(tab)
    except gspread.WorksheetNotFound:
        return [], []
    vals = ws.get_all_values()
    if not vals:
        return [], []
    return vals[0], vals[1:]
