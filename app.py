"""
Household Weekly Tasks — Streamlit App
=======================================

Setup & Google Sheets Instructions
-----------------------------------
1) Enable the Google Sheets API at https://console.cloud.google.com
2) Create a Service Account (IAM & Admin → Service Accounts → Create)
   and download its JSON key.
3) Share your Google Sheet with the service account e-mail (Editor access).
4) Create `.streamlit/secrets.toml` in this project root:

    SPREADSHEET_ID = "<your-sheet-id-or-full-url>"

    [gcp_service_account]
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
    client_email = "...@...gserviceaccount.com"
    client_id = "..."
    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    token_uri = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
    client_x509_cert_url = "..."

5) Run:  streamlit run app.py

Architecture
------------
app.py          – entry point (this file); wires everything together
config.py       – constants (sheet name, status enums, …)
sheets.py       – Google Sheets connection & CRUD helpers
tasks.py        – week utilities & recurring-task generation
components.py   – reusable Streamlit UI components

Data model (single worksheet "tasks")
--------------------------------------
id                      UUID, primary key
task_name               Free text
week_id                 ISO week string, e.g. "2026-W14"
status                  "todo" | "in_progress" | "done"
description             Free text (optional)
time_estimate_minutes   Integer stored as string
created_at              YYYY-MM-DD
"""

from __future__ import annotations

import streamlit as st

try:
    import gspread  # noqa: F401
    from google.oauth2.service_account import Credentials  # noqa: F401
except ImportError:
    st.error("Required packages missing. Run:  pip install -r requirements.txt")
    raise

from sheets import open_spreadsheet, load_tasks_for_week, add_tasks_batch, update_task_status
from tasks import generate_recurring_instances, week_id_from_date
from datetime import date
from components import (
    render_week_navigator,
    render_week_selector,
    render_tasks_section,
    render_add_task_form,
    render_edit_tab,
    TASK_NAME_MAX,
)


def main() -> None:
    st.set_page_config(page_title="Dulaerk Opgave Manager", page_icon="✅", layout="centered")
    st.title("✅  Dulaerk Opgave Manager")

    # ------------------------------------------------------------------
    # Connect to Google Sheets once per browser session
    # ------------------------------------------------------------------
    if "_sh" not in st.session_state:
        with st.spinner("Forbinder til Google Sheets…"):
            try:
                st.session_state["_sh"] = open_spreadsheet()
            except Exception as exc:
                st.error(
                    "Kunne ikke åbne regnearket. Mulige årsager:\n"
                    "- SPREADSHEET_ID mangler eller er forkert i secrets.toml\n"
                    "- Arket er ikke delt med service-kontoen"
                )
                st.exception(exc)
                st.stop()

    sh = st.session_state["_sh"]

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------
    tab_board, tab_recurring, tab_edit = st.tabs(
        ["📅 Ugeoversigt", "🔁 Gentagende opgaver", "✏️ Rediger opgaver"]
    )

    # ── This Week ──────────────────────────────────────────────────────
    with tab_board:
        # Show any pending success message (set before a st.rerun() call)
        if "_board_msg" in st.session_state:
            st.success(st.session_state.pop("_board_msg"))

        week_id = render_week_navigator()
        st.write("")

        # Always load fresh data from the sheet on every rerun so that
        # tasks created in the Recurring Tasks tab are immediately visible
        # after the st.rerun() that follows every write operation.
        with st.spinner("Indlæser…"):
            tasks = load_tasks_for_week(sh, week_id)

        render_tasks_section(tasks, sh, update_task_status, week_id=week_id)

        # Inline add-task form (returns the new task dict on valid submit)
        new_task = render_add_task_form(week_id)
        if new_task:
            with st.spinner("Gemmer…"):
                add_tasks_batch(sh, [new_task])
            st.session_state["_board_msg"] = f"✅ '{new_task['task_name']}' tilføjet til **{week_id}**!"
            st.rerun()

    # ── Recurring Tasks ────────────────────────────────────────────────
    with tab_recurring:
        if "_recurring_msg" in st.session_state:
            st.success(st.session_state.pop("_recurring_msg"))

        st.subheader("Opret en gentagende opgave")

        with st.form("add_recurring", clear_on_submit=True):
            r_name = st.text_input("Opgavenavn *", max_chars=TASK_NAME_MAX)
            rf1, rf2 = st.columns([3, 1])
            with rf1:
                r_desc = st.text_area("Beskrivelse (valgfri)", height=80)
            with rf2:
                r_time = st.number_input(
                    "Minutter *", min_value=5, max_value=1440, value=5, step=5
                )
            r_wid = render_week_selector("Startende fra uge", key="recurring_start")
            r_interval = st.selectbox(
                "Gentag hver",
                options=[1, 2, 3, 4],
                format_func=lambda x: f"{x} uge{'r' if x > 1 else ''}",
            )
            r_submit = st.form_submit_button("Opret opgaver", use_container_width=True)

        if r_submit:
            if not r_name.strip():
                st.warning("Opgavenavn er påkrævet.")
            else:
                from tasks import week_start_from_id
                start_date = week_start_from_id(r_wid)
                instances = generate_recurring_instances(
                    r_name.strip(), r_desc.strip(), start_date, int(r_interval), int(r_time)
                )
                with st.spinner(f"Skriver {len(instances)} opgaverækker til arket…"):
                    add_tasks_batch(sh, instances)
                st.session_state["_recurring_msg"] = (
                    f"✅ Oprettede **{len(instances)}** opgaveforekomster "
                    f"(hver {r_interval} uge(r) startende {r_wid})."
                )
                st.rerun()

    # ── Edit Tasks ─────────────────────────────────────────────────────
    with tab_edit:
        render_edit_tab(sh, current_week_id=week_id_from_date(date.today()))


if __name__ == "__main__":
    main()
