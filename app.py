"""
=============================================================================
 Household Weekly Kanban To-Do App
=============================================================================

HOW TO SET UP GOOGLE SHEETS INTEGRATION
========================================

Step 1 — Create a Google Cloud Project
  1. Go to https://console.cloud.google.com/
  2. Click "Select a project" → "New Project".
  3. Give it a name (e.g. "household-todo") and click "Create".

Step 2 — Enable the Google Sheets & Drive APIs
  1. In your new project, go to "APIs & Services" → "Library".
  2. Search for "Google Sheets API" and click "Enable".
  3. Search for "Google Drive API" and click "Enable".

Step 3 — Create a Service Account
  1. Go to "APIs & Services" → "Credentials".
  2. Click "Create Credentials" → "Service Account".
  3. Fill in a name (e.g. "todo-service-account") and click "Done".
  4. Click the new service account → "Keys" tab → "Add Key" →
     "Create new key" → "JSON". Download the file.

Step 4 — Share your Google Sheet with the Service Account
  1. Open (or create) the Google Sheet you want to use.
  2. Note the spreadsheet ID from the URL:
       https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit
  3. In the sheet, click "Share" and paste the service account email
     (looks like todo-service-account@project.iam.gserviceaccount.com).
  4. Give it "Editor" access and click "Send".

Step 5 — Create .streamlit/secrets.toml
  Copy .streamlit/secrets.toml.example to .streamlit/secrets.toml and
  fill in your real credentials from the downloaded JSON key file.

Step 6 — Sheet structure (auto-created on first run)
  The app creates two worksheets automatically:
    • "tasks"           — ad-hoc and auto-generated weekly task instances
    • "scheduled_tasks" — recurring task definitions

  tasks columns:
    id | title | description | time_estimate_minutes | status | week_start | created_at

  scheduled_tasks columns:
    id | title | description | time_estimate_minutes | start_date | frequency_weeks
=============================================================================
"""

import uuid
from datetime import date, timedelta

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="🏠 Household To-Do",
    page_icon="✅",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Mobile-friendly CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Wider content on small screens */
    .block-container { padding: 1rem 0.75rem 2rem; max-width: 100%; }

    /* Task cards */
    .task-card {
        background: #f8f9fa;
        border-left: 4px solid #6c757d;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }
    .task-card.todo   { border-left-color: #dc3545; }
    .task-card.doing  { border-left-color: #fd7e14; }
    .task-card.done   { border-left-color: #198754; }

    /* Column headers */
    .col-header {
        font-weight: 700;
        font-size: 1rem;
        padding: 0.4rem 0;
        margin-bottom: 0.5rem;
        text-align: center;
        border-radius: 4px;
    }
    .col-todo  { background: #ffe0e3; color: #842029; }
    .col-doing { background: #ffe8d6; color: #7c3100; }
    .col-done  { background: #d1e7dd; color: #0a3622; }

    /* Summary table */
    .summary-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    .summary-table th, .summary-table td {
        border: 1px solid #dee2e6;
        padding: 0.4rem 0.6rem;
        text-align: center;
    }
    .summary-table th { background: #e9ecef; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STATUSES = ["To-Do", "In Progress", "Done"]
STATUS_CSS = {"To-Do": "todo", "In Progress": "doing", "Done": "done"}
COL_CSS = {"To-Do": "col-todo", "In Progress": "col-doing", "Done": "col-done"}
FREQ_OPTIONS = {"Weekly (every 1 week)": 1, "Every 2 weeks": 2, "Every 4 weeks": 4}

TASKS_HEADERS = ["id", "title", "description", "time_estimate_minutes", "status", "week_start", "created_at"]
SCHED_HEADERS = ["id", "title", "description", "time_estimate_minutes", "start_date", "frequency_weeks"]

# ---------------------------------------------------------------------------
# Google Sheets helpers
# ---------------------------------------------------------------------------

@st.cache_resource
def get_spreadsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["SPREADSHEET_ID"])


def get_or_create_worksheet(spreadsheet, title, headers):
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        ws.append_row(headers)
    return ws


def load_tasks(ws):
    records = ws.get_all_records()
    return records  # list of dicts


def week_start_for(d: date) -> date:
    """Return the Monday of the week containing `d`."""
    return d - timedelta(days=d.weekday())


def week_label(monday: date) -> str:
    sunday = monday + timedelta(days=6)
    return f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------

def add_task(ws, title, description, time_estimate_minutes, week_start: date, status="To-Do"):
    row = [
        str(uuid.uuid4()),
        title,
        description,
        int(time_estimate_minutes),
        status,
        week_start.isoformat(),
        date.today().isoformat(),
    ]
    ws.append_row(row)


def update_task_status(ws, task_id, new_status):
    cell = ws.find(task_id, in_column=1)
    if cell:
        status_col = TASKS_HEADERS.index("status") + 1
        ws.update_cell(cell.row, status_col, new_status)


def delete_task(ws, task_id):
    cell = ws.find(task_id, in_column=1)
    if cell:
        ws.delete_rows(cell.row)


# ---------------------------------------------------------------------------
# Scheduled task CRUD
# ---------------------------------------------------------------------------

def add_scheduled_task(ws, title, description, time_estimate_minutes, start_date: date, frequency_weeks: int):
    row = [
        str(uuid.uuid4()),
        title,
        description,
        int(time_estimate_minutes),
        start_date.isoformat(),
        int(frequency_weeks),
    ]
    ws.append_row(row)


def delete_scheduled_task(ws, task_id):
    cell = ws.find(task_id, in_column=1)
    if cell:
        ws.delete_rows(cell.row)


def get_recurring_tasks_for_week(scheduled_tasks, week_start: date):
    """Return scheduled task dicts that are active for the given week."""
    active = []
    for t in scheduled_tasks:
        try:
            t_start = date.fromisoformat(str(t["start_date"]))
            freq = int(t["frequency_weeks"])
        except (ValueError, KeyError):
            continue
        t_week = week_start_for(t_start)
        if week_start < t_week:
            continue
        delta_weeks = (week_start - t_week).days // 7
        if delta_weeks % freq == 0:
            active.append(t)
    return active


def ensure_recurring_tasks_exist(tasks_ws, scheduled_ws, week_start: date):
    """
    For the given week, check each recurring task and create a task instance
    in the tasks sheet if one doesn't already exist.
    """
    existing = load_tasks(tasks_ws)
    week_str = week_start.isoformat()
    scheduled = load_tasks(scheduled_ws)

    due = get_recurring_tasks_for_week(scheduled, week_start)
    for sched in due:
        already = any(
            t.get("week_start") == week_str and t.get("title") == sched["title"]
            for t in existing
        )
        if not already:
            add_task(
                tasks_ws,
                title=sched["title"],
                description=sched.get("description", ""),
                time_estimate_minutes=sched["time_estimate_minutes"],
                week_start=week_start,
                status="To-Do",
            )


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "current_week" not in st.session_state:
    st.session_state.current_week = week_start_for(date.today())

# ---------------------------------------------------------------------------
# Connect to Google Sheets
# ---------------------------------------------------------------------------

try:
    spreadsheet = get_spreadsheet()
    tasks_ws = get_or_create_worksheet(spreadsheet, "tasks", TASKS_HEADERS)
    sched_ws = get_or_create_worksheet(spreadsheet, "scheduled_tasks", SCHED_HEADERS)
    sheets_ok = True
except Exception as exc:
    sheets_ok = False
    sheets_error = str(exc)

# ---------------------------------------------------------------------------
# App header
# ---------------------------------------------------------------------------

st.title("🏠 Household To-Do")

if not sheets_ok:
    st.error(
        f"⚠️ Could not connect to Google Sheets: {sheets_error}\n\n"
        "Please set up your `.streamlit/secrets.toml` as described in the setup guide "
        "(see `secrets.toml.example` and the docstring at the top of `app.py`)."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_board, tab_schedule = st.tabs(["📋 Weekly Board", "🔁 Schedule"])

# ===========================================================================
# TAB 1 — WEEKLY BOARD
# ===========================================================================
with tab_board:
    # --- Week navigation ---
    col_prev, col_label, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("◀", help="Previous week", use_container_width=True):
            st.session_state.current_week -= timedelta(weeks=1)
            st.rerun()
    with col_label:
        st.markdown(
            f"<div style='text-align:center; font-weight:600; padding-top:6px;'>"
            f"📅 {week_label(st.session_state.current_week)}</div>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("▶", help="Next week", use_container_width=True):
            st.session_state.current_week += timedelta(weeks=1)
            st.rerun()

    current_week = st.session_state.current_week

    # Auto-populate recurring tasks for this week
    ensure_recurring_tasks_exist(tasks_ws, sched_ws, current_week)

    # Load tasks for this week
    all_tasks = load_tasks(tasks_ws)
    week_tasks = [t for t in all_tasks if t.get("week_start") == current_week.isoformat()]

    st.divider()

    # --- Kanban board ---
    col_todo, col_doing, col_done = st.columns(3)
    columns = {
        "To-Do": col_todo,
        "In Progress": col_doing,
        "Done": col_done,
    }
    col_headers = {
        "To-Do": "🔴 To-Do",
        "In Progress": "🟠 In Progress",
        "Done": "🟢 Done",
    }

    for status, col in columns.items():
        with col:
            css_class = COL_CSS[status]
            st.markdown(
                f"<div class='col-header {css_class}'>{col_headers[status]}</div>",
                unsafe_allow_html=True,
            )
            status_tasks = [t for t in week_tasks if t.get("status") == status]
            if not status_tasks:
                st.caption("_No tasks_")
            for task in status_tasks:
                card_css = STATUS_CSS[status]
                mins = task.get("time_estimate_minutes", 0)
                desc = task.get("description", "")
                with st.container():
                    st.markdown(
                        f"<div class='task-card {card_css}'>"
                        f"<strong>{task['title']}</strong><br>"
                        f"⏱ {mins} min"
                        f"{'<br><small>' + str(desc) + '</small>' if desc else ''}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    with st.expander("⚙️ Edit", expanded=False):
                        new_status = st.selectbox(
                            "Move to",
                            STATUSES,
                            index=STATUSES.index(status),
                            key=f"status_{task['id']}",
                        )
                        col_save, col_del = st.columns(2)
                        with col_save:
                            if st.button("Save", key=f"save_{task['id']}", use_container_width=True):
                                if new_status != status:
                                    update_task_status(tasks_ws, task["id"], new_status)
                                st.rerun()
                        with col_del:
                            if st.button("🗑 Delete", key=f"del_{task['id']}", use_container_width=True):
                                delete_task(tasks_ws, task["id"])
                                st.rerun()

    st.divider()

    # --- Add ad-hoc task ---
    with st.expander("➕ Add a task for this week", expanded=False):
        with st.form("add_task_form", clear_on_submit=True):
            t_title = st.text_input("Title *", placeholder="e.g. Clean bathroom")
            t_mins = st.number_input("Time estimate (minutes) *", min_value=1, value=30, step=5)
            t_desc = st.text_area("Description (optional)", placeholder="Any notes…")
            t_status = st.selectbox("Initial status", STATUSES)
            submitted = st.form_submit_button("Add Task", use_container_width=True)
            if submitted:
                if not t_title.strip():
                    st.warning("Title is required.")
                else:
                    add_task(tasks_ws, t_title.strip(), t_desc.strip(), int(t_mins), current_week, t_status)
                    st.success(f"✅ Task '{t_title}' added!")
                    st.rerun()

    st.divider()

    # --- Weekly summary footer ---
    st.subheader("📊 Weekly Summary")
    summary = {s: {"count": 0, "minutes": 0} for s in STATUSES}
    for task in week_tasks:
        s = task.get("status", "To-Do")
        if s in summary:
            summary[s]["count"] += 1
            try:
                summary[s]["minutes"] += int(task.get("time_estimate_minutes", 0))
            except (ValueError, TypeError):
                pass

    total_mins = sum(v["minutes"] for v in summary.values())
    total_count = sum(v["count"] for v in summary.values())

    rows_html = ""
    for s in STATUSES:
        m = summary[s]["minutes"]
        h, rem = divmod(m, 60)
        time_str = f"{h}h {rem}m" if h else f"{rem}m"
        rows_html += (
            f"<tr><td>{s}</td>"
            f"<td>{summary[s]['count']}</td>"
            f"<td>{time_str}</td></tr>"
        )

    total_h, total_rem = divmod(total_mins, 60)
    total_str = f"{total_h}h {total_rem}m" if total_h else f"{total_rem}m"
    rows_html += (
        f"<tr style='font-weight:700; background:#e9ecef;'>"
        f"<td>Total</td><td>{total_count}</td><td>{total_str}</td></tr>"
    )

    st.markdown(
        f"""
        <table class='summary-table'>
          <thead><tr><th>Status</th><th>Tasks</th><th>Time</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

# ===========================================================================
# TAB 2 — SCHEDULE (Recurring Tasks)
# ===========================================================================
with tab_schedule:
    st.subheader("🔁 Manage Recurring Tasks")

    # --- Add recurring task ---
    with st.expander("➕ Add a recurring task", expanded=False):
        with st.form("add_sched_form", clear_on_submit=True):
            s_title = st.text_input("Title *", placeholder="e.g. Vacuum living room")
            s_mins = st.number_input("Time estimate (minutes) *", min_value=1, value=30, step=5)
            s_desc = st.text_area("Description (optional)")
            s_start = st.date_input("Start date *", value=date.today())
            s_freq_label = st.selectbox("Recurrence", list(FREQ_OPTIONS.keys()))
            sched_submitted = st.form_submit_button("Save Recurring Task", use_container_width=True)
            if sched_submitted:
                if not s_title.strip():
                    st.warning("Title is required.")
                else:
                    add_scheduled_task(
                        sched_ws,
                        title=s_title.strip(),
                        description=s_desc.strip(),
                        time_estimate_minutes=int(s_mins),
                        start_date=s_start,
                        frequency_weeks=FREQ_OPTIONS[s_freq_label],
                    )
                    st.success(f"✅ Recurring task '{s_title}' saved!")
                    st.rerun()

    st.divider()

    # --- Existing recurring tasks ---
    st.subheader("📋 Existing Recurring Tasks")
    scheduled = load_tasks(sched_ws)

    if not scheduled:
        st.info("No recurring tasks yet. Add one above!")
    else:
        task_labels = [f"{t['title']} — every {t['frequency_weeks']} week(s)" for t in scheduled]
        selected_idx = st.selectbox(
            "Select a task to view / delete",
            range(len(task_labels)),
            format_func=lambda i: task_labels[i],
            key="sched_select",
        )
        selected = scheduled[selected_idx]

        freq_label = next(
            (k for k, v in FREQ_OPTIONS.items() if v == int(selected.get("frequency_weeks", 1))),
            f"Every {selected.get('frequency_weeks', '?')} weeks",
        )

        st.markdown(
            f"""
            **Title:** {selected['title']}

            **Time estimate:** {selected['time_estimate_minutes']} minutes

            **Description:** {selected.get('description') or '_none_'}

            **Start date:** {selected['start_date']}

            **Recurrence:** {freq_label}
            """
        )

        if st.button("🗑 Delete this recurring task", type="primary", use_container_width=True):
            delete_scheduled_task(sched_ws, selected["id"])
            st.success(f"Deleted '{selected['title']}'.")
            st.rerun()
