"""sheets_manager.py — ReboundPro Google Sheets I/O (M1).

Service-account auth (creds file at google_credentials.json). The SA cannot
*create* sheets (Drive quota); the target sheet must be created by the user and
shared with the SA as Editor. Pattern mirrors DropsLab/gsheets_sync.
"""
import gspread
from google.oauth2.service_account import Credentials

import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def get_client():
    creds = Credentials.from_service_account_file(config.CREDS_PATH, scopes=SCOPES)
    return gspread.authorize(creds)


def service_account_email():
    creds = Credentials.from_service_account_file(config.CREDS_PATH, scopes=SCOPES)
    return creds.service_account_email


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
