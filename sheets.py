"""
Google Sheets persistence layer.

Responsibilities
----------------
- Opening / authenticating the spreadsheet
- Ensuring the `tasks` worksheet exists with the correct headers
- CRUD operations on tasks (load, batch-insert, update status)

All functions receive a `gspread.Spreadsheet` object so that the connection
is established once (in app.py) and shared via st.session_state.
"""

from __future__ import annotations

from typing import List, Dict

import streamlit as st
import gspread
from gspread.utils import ValueInputOption, rowcol_to_a1
from google.oauth2.service_account import Credentials

from config import TASKS_SHEET, TASK_HEADERS


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_credentials() -> Credentials:
    """Build Google service-account credentials from Streamlit secrets."""
    sa = st.secrets.get("gcp_service_account")
    if not sa:
        raise RuntimeError(
            "gcp_service_account not found in st.secrets. "
            "See the top of the original app.py for full setup instructions."
        )
    return Credentials.from_service_account_info(
        sa,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ],
    )


def open_spreadsheet() -> gspread.Spreadsheet:
    """Authenticate and open the spreadsheet configured in st.secrets.

    Accepts either SPREADSHEET_ID (sheet key or full URL) or SHEET_URL.
    Creates the `tasks` worksheet automatically if it doesn't exist.
    """
    raw = st.secrets.get("SPREADSHEET_ID") or st.secrets.get("SHEET_URL")
    if not raw:
        raise RuntimeError(
            "SPREADSHEET_ID (or SHEET_URL) is missing from .streamlit/secrets.toml."
        )

    creds = get_credentials()
    client = gspread.authorize(creds)

    if isinstance(raw, str) and ("http" in raw or "docs.google.com" in raw):
        sh = client.open_by_url(raw)
    else:
        sh = client.open_by_key(raw)

    ensure_sheet_exists(sh)
    migrate_schema(sh)
    return sh


# ---------------------------------------------------------------------------
# Schema bootstrapping
# ---------------------------------------------------------------------------

def ensure_sheet_exists(sh: gspread.Spreadsheet) -> None:
    """Create the `tasks` worksheet with header row if it doesn't already exist."""
    existing = {ws.title for ws in sh.worksheets()}
    if TASKS_SHEET not in existing:
        # Use 26 cols so future schema additions never hit the grid limit.
        ws = sh.add_worksheet(title=TASKS_SHEET, rows=20000, cols=26)
        ws.append_row(TASK_HEADERS)


def migrate_schema(sh: gspread.Spreadsheet) -> None:
    """Append any columns in TASK_HEADERS that are missing from the sheet's header row.

    Safe to call on every startup – no-op when the schema is already up to date.
    Resizes the worksheet first so writing beyond the current column count never
    raises an APIError (e.g. when upgrading an existing 6-column sheet to 7+).
    """
    ws = sh.worksheet(TASKS_SHEET)
    current = ws.row_values(1)
    missing = [col for col in TASK_HEADERS if col not in current]
    if not missing:
        return

    # Expand the grid before touching cells outside the current bounds.
    needed = len(current) + len(missing)
    ws.resize(cols=max(needed, 26))

    for col in missing:
        ws.update_cell(1, len(current) + 1, col)
        current.append(col)


# ---------------------------------------------------------------------------
# Public CRUD operations
# ---------------------------------------------------------------------------

def load_all_tasks(sh: gspread.Spreadsheet) -> List[Dict]:
    """Return every task row in the sheet and caches headers to optimize calls."""
    ws = sh.worksheet(TASKS_SHEET)
    rows = ws.get_all_values()
    
    if rows:
        st.session_state["_sheet_headers"] = rows[0]
    else:
        st.session_state["_sheet_headers"] = TASK_HEADERS

    if len(rows) < 2:
        return []
        
    headers = rows[0]
    out = []
    for i, r in enumerate(rows[1:], start=2):
        d = {headers[j]: (r[j] if j < len(r) else "") for j in range(len(headers))}
        d["_row_idx"] = i
        out.append(d)
    return out


def delete_task_by_id(sh: gspread.Spreadsheet, task_id: str, all_tasks: List[Dict]) -> None:
    """Delete the single row whose `id` matches *task_id*."""
    delete_tasks_by_ids(sh, [task_id], all_tasks)


def delete_tasks_by_ids(sh: gspread.Spreadsheet, task_ids: List[str], all_tasks: List[Dict]) -> None:
    """Delete every row whose `id` is in *task_ids*.

    Rewrites the sheet in a single atomic update call so the operation
    is fast even when deleting hundreds of rows at once.
    """
    if not task_ids:
        return
    ws = sh.worksheet(TASKS_SHEET)
    headers = st.session_state.get("_sheet_headers", TASK_HEADERS)
    id_set = set(task_ids)
    
    kept_data = [
        [str(t.get(h, "")) for h in headers]
        for t in all_tasks
        if t.get("id") not in id_set
    ]
    
    ws.clear()
    
    if kept_data:
        ws.update(values=[headers] + kept_data, range_name='A1', value_input_option=ValueInputOption.raw)
    else:
        ws.update(values=[headers], range_name='A1', value_input_option=ValueInputOption.raw)


def add_tasks_batch(sh: gspread.Spreadsheet, tasks: List[Dict]) -> None:
    """Append multiple task dicts to the sheet in a single API call.

    Uses the actual column order from the sheet header row so that a schema
    migration (added columns) never causes data to land in the wrong column.
    """
    if not tasks:
        return
    ws = sh.worksheet(TASKS_SHEET)
    headers = st.session_state.get("_sheet_headers", TASK_HEADERS)
    rows = [[str(t.get(h, "")) for h in headers] for t in tasks]
    ws.append_rows(rows, value_input_option=ValueInputOption.raw)


def update_task_status(sh: gspread.Spreadsheet, row_idx: int, new_status: str) -> None:
    """Update the status cell for the specific row index."""
    update_tasks_fields_batch(sh, {row_idx: {"status": new_status}})


def update_task_week(sh: gspread.Spreadsheet, row_idx: int, new_week_id: str) -> None:
    """Update the week_id cell for the specific row index."""
    update_tasks_fields_batch(sh, {row_idx: {"week_id": new_week_id}})


def update_task_fields(sh: gspread.Spreadsheet, row_idx: int, updates: Dict[str, str]) -> None:
    """Update arbitrary fields for the row matching *row_idx*."""
    update_tasks_fields_batch(sh, {row_idx: updates})


def update_tasks_fields_batch(sh: gspread.Spreadsheet, updates_by_row_idx: Dict[int, Dict[str, str]]) -> None:
    """Update arbitrary fields for multiple rows in a single API call.
    
    *updates_by_row_idx* is a mapping row_idx -> {header -> new string value}.
    """
    if not updates_by_row_idx:
        return
    ws = sh.worksheet(TASKS_SHEET)
    
    headers = st.session_state.get("_sheet_headers", TASK_HEADERS)
    col_map = {h: i + 1 for i, h in enumerate(headers)}
    
    batch_data = []

    for row_idx, updates in updates_by_row_idx.items():
        for h, val in updates.items():
            if h in col_map:
                batch_data.append({
                    'range': rowcol_to_a1(row_idx, col_map[h]),
                    'values': [[str(val)]]
                })
                    
    if batch_data:
        ws.batch_update(batch_data)
