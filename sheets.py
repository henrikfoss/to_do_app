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
from gspread.utils import ValueInputOption
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
# Internal helpers
# ---------------------------------------------------------------------------

def _sheet_to_dicts(ws: gspread.Worksheet) -> List[Dict]:
    """Return all data rows as a list of dicts keyed by header names."""
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []
    headers = rows[0]
    return [
        {headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))}
        for r in rows[1:]
    ]


# ---------------------------------------------------------------------------
# Public CRUD operations
# ---------------------------------------------------------------------------

def load_tasks_for_week(sh: gspread.Spreadsheet, week_id: str) -> List[Dict]:
    """Return all tasks whose `week_id` matches the given ISO week string."""
    ws = sh.worksheet(TASKS_SHEET)
    return [r for r in _sheet_to_dicts(ws) if r.get("week_id") == week_id]


def load_unscheduled_tasks(sh: gspread.Spreadsheet) -> List[Dict]:
    """Return all tasks that do not have a week_id (unscheduled tasks).

    A task is considered unscheduled when its `week_id` cell is empty or
    only contains whitespace.
    """
    ws = sh.worksheet(TASKS_SHEET)
    return [r for r in _sheet_to_dicts(ws) if not (r.get("week_id") or "").strip()]


def load_all_tasks(sh: gspread.Spreadsheet) -> List[Dict]:
    """Return every task row in the sheet."""
    ws = sh.worksheet(TASKS_SHEET)
    return _sheet_to_dicts(ws)


def delete_task_by_id(sh: gspread.Spreadsheet, task_id: str) -> None:
    """Delete the single row whose `id` matches *task_id*."""
    ws = sh.worksheet(TASKS_SHEET)
    rows = ws.get_all_values()
    if not rows:
        return
    id_col = rows[0].index("id") if "id" in rows[0] else 0
    for row_idx, row in enumerate(rows[1:], start=2):
        if len(row) > id_col and row[id_col] == task_id:
            ws.delete_rows(row_idx)
            return


def delete_tasks_by_ids(sh: gspread.Spreadsheet, task_ids: List[str]) -> None:
    """Delete every row whose `id` is in *task_ids*.

    Rewrites the sheet in two API calls (clear + append) so the operation
    is fast even when deleting hundreds of rows at once.
    """
    if not task_ids:
        return
    ws = sh.worksheet(TASKS_SHEET)
    rows = ws.get_all_values()
    if not rows:
        return
    headers = rows[0]
    id_col = headers.index("id") if "id" in headers else 0
    id_set = set(task_ids)
    kept_data = [
        row for row in rows[1:]
        if not (len(row) > id_col and row[id_col] in id_set)
    ]
    ws.clear()
    ws.append_row(headers, value_input_option=ValueInputOption.raw)
    if kept_data:
        ws.append_rows(kept_data, value_input_option=ValueInputOption.raw)


def add_tasks_batch(sh: gspread.Spreadsheet, tasks: List[Dict]) -> None:
    """Append multiple task dicts to the sheet in a single API call.

    Uses the actual column order from the sheet header row so that a schema
    migration (added columns) never causes data to land in the wrong column.
    """
    if not tasks:
        return
    ws = sh.worksheet(TASKS_SHEET)
    sheet_headers = ws.row_values(1)           # actual order in the sheet
    rows = [[str(t.get(h, "")) for h in sheet_headers] for t in tasks]
    ws.append_rows(rows, value_input_option=ValueInputOption.raw)


def update_task_status(sh: gspread.Spreadsheet, task_id: str, new_status: str) -> None:
    """Find the row with the given *task_id* and update its status cell."""
    ws = sh.worksheet(TASKS_SHEET)
    all_rows = ws.get_all_values()
    if not all_rows:
        return

    headers = all_rows[0]
    try:
        id_col = headers.index("id")
        status_col = headers.index("status") + 1  # gspread uses 1-based column index
    except ValueError:
        return

    for row_idx, row in enumerate(all_rows[1:], start=2):
        if len(row) > id_col and row[id_col] == task_id:
            ws.update_cell(row_idx, status_col, new_status)
            return


def update_task_week(sh: gspread.Spreadsheet, task_id: str, new_week_id: str) -> None:
    """Find the row with the given *task_id* and update its week_id cell."""
    ws = sh.worksheet(TASKS_SHEET)
    all_rows = ws.get_all_values()
    if not all_rows:
        return

    headers = all_rows[0]
    try:
        id_col = headers.index("id")
        week_col = headers.index("week_id") + 1  # 1-based
    except ValueError:
        return

    for row_idx, row in enumerate(all_rows[1:], start=2):
        if len(row) > id_col and row[id_col] == task_id:
            ws.update_cell(row_idx, week_col, new_week_id)
            return


def update_task_fields(sh: gspread.Spreadsheet, task_id: str, updates: Dict[str, str]) -> None:
    """Update arbitrary fields for the row matching *task_id*.

    *updates* is a mapping header -> new string value. Only headers present
    in the sheet will be updated.
    """
    if not updates:
        return
    ws = sh.worksheet(TASKS_SHEET)
    all_rows = ws.get_all_values()
    if not all_rows:
        return

    headers = all_rows[0]
    try:
        id_col = headers.index("id")
    except ValueError:
        return

    # Map header -> 1-based column index for present headers
    col_map = {h: i + 1 for i, h in enumerate(headers)}

    for row_idx, row in enumerate(all_rows[1:], start=2):
        if len(row) > id_col and row[id_col] == task_id:
            # Update each supplied header that exists in the sheet
            for h, val in updates.items():
                if h in col_map:
                    try:
                        ws.update_cell(row_idx, col_map[h], str(val))
                    except Exception:
                        # Best-effort: ignore individual cell update failures
                        pass
            return


