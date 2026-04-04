"""
Reusable Streamlit UI components.

Responsibilities
----------------
- Week navigation bar (◀ week selectbox ▶)
- Week selector widget for use inside forms (single selectbox)
- Individual task card (bordered card + status slider)
- Weekly task list – always shows all three status groups, even when empty
- Week analytics – time totals per status displayed as metrics
- Inline add-task form (returns task dict on valid submit)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

import streamlit as st

from config import STATUSES, STATUS_ICONS, STATUS_LABELS
from tasks import make_task, week_id_from_date, week_start_from_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Time estimates removed — no helpers for minutes


# Danish abbreviated month names (strftime returns English on most systems)
_DA_MONTHS = {
    "Jan": "jan", "Feb": "feb", "Mar": "mar", "Apr": "apr",
    "May": "maj", "Jun": "jun", "Jul": "jul", "Aug": "aug",
    "Sep": "sep", "Oct": "okt", "Nov": "nov", "Dec": "dec",
}


def _da_date(d: date) -> str:
    """Return a Danish-formatted date, e.g. '30. mar'."""
    month = _DA_MONTHS.get(d.strftime("%b"), d.strftime("%b").lower())
    return f"{d.day}. {month}"


# Maximum task name length enforced everywhere in the UI.
TASK_NAME_MAX = 25


def _expander_title(name: str) -> str:
    """Build an expander title that pads shorter names with em-spaces so the
    time estimate lands at roughly the same horizontal position regardless of
    how long the task name is.

    An em-space (\u2003) is ~1 em wide; an average proportional character is
    ~0.5 em, so we divide the character gap by 2 to convert characters → em-spaces,
    then add a small fixed minimum so even a 50-char name still has a gap.
    """
    # Keep the title simple now that time estimates are removed.
    return name


def _week_label(wid: str) -> str:
    """Human-readable Danish label: '30. mar – 5. apr 2026  (2026-W14)'."""
    s = week_start_from_id(wid)
    e = s + timedelta(days=6)
    return f"{_da_date(s)} – {_da_date(e)} {e.year}  ({wid})"


def _build_week_opts(weeks_back: int, weeks_ahead: int) -> List[str]:
    """Return a list of week_id strings centred around today."""
    today = date.today()
    start = today - timedelta(weeks=weeks_back)
    start -= timedelta(days=start.weekday())   # snap to Monday
    end = today + timedelta(weeks=weeks_ahead)
    weeks, cur = [], start
    while cur <= end:
        weeks.append(week_id_from_date(cur))
        cur += timedelta(weeks=1)
    return weeks


# ---------------------------------------------------------------------------
# Week navigation
# ---------------------------------------------------------------------------

def render_week_navigator() -> str:
    """Render the week selectbox and return the current week_id."""

    # Calculate today's week ID once to avoid redundant calls
    today_wid = week_id_from_date(date.today())
    week_opts = _build_week_opts(weeks_back=52, weeks_ahead=156)

    # 1. Initialize state directly on the key the widget will use
    if "week_id" not in st.session_state:
        # Fallback to index 0 just in case today_wid somehow isn't in week_opts
        st.session_state["week_id"] = today_wid if today_wid in week_opts else week_opts[0]

    def _label(wid: str) -> str:
        base = _week_label(wid)
        return f"{base}  (Denne uge)" if wid == today_wid else base

    # 2. Render the selectbox
    st.selectbox(
        "**Vælg Uge**",  # Streamlit labels support Markdown naturally
        options=week_opts,
        format_func=_label,
        key="week_id",  # Automatically reads/writes st.session_state["week_id"]
    )

    return st.session_state["week_id"]


def render_week_selector(label: str, key: str) -> str:
    """Single-selectbox week picker for use inside forms.

    Shows entries like 'Mar 30 – Apr 05, 2026 (2026-W14)'.
    Covers from the current week to ~5 years ahead.
    """
    today = date.today()
    opts = _build_week_opts(weeks_back=0, weeks_ahead=5 * 52)
    today_wid = week_id_from_date(today)
    default_idx = opts.index(today_wid) if today_wid in opts else 0

    st.markdown(f"**{label}**")
    selected = st.selectbox(
        label,
        opts,
        index=default_idx,
        format_func=_week_label,
        key=key,
        label_visibility="collapsed",
    )
    return selected


# ---------------------------------------------------------------------------
# Individual task card
# ---------------------------------------------------------------------------

def render_task(task: Dict, sh, update_status_fn: Callable, update_fields_fn: Optional[Callable] = None) -> None:
    """Render a single task as a collapsible expander.

    The title shows: status icon · task name · time estimate.
    Inside: description (if any) and a status drop-down.
    """
    task_id = task.get("id", "")
    status = task.get("status", "todo")
    if status not in STATUSES:
        status = "todo"

    name = task.get("task_name", "Unnamed task")

    with st.expander(_expander_title(name[:TASK_NAME_MAX])):
        new_status = st.selectbox(
            "**Status**",
            options=STATUSES,
            index=STATUSES.index(status),
            format_func=lambda s: f"{STATUS_ICONS[s]}  {STATUS_LABELS[s]}",
            key=f"status-{task_id}",
        )
        if new_status != status:
            with st.spinner("Gemmer…"):
                update_status_fn(sh, task_id, new_status)
            st.rerun()

        # Description: if an update function is provided, allow editing inline
        cur_desc = (task.get("description") or "").strip()
        if update_fields_fn:
            desc_key = f"board_desc_{task_id}"
            new_desc = st.text_area("**Beskrivelse**", value=cur_desc, key=desc_key, height=120)
            if st.button("Gem ændringer", key=f"btn_board_save_{task_id}"):
                with st.spinner("Gemmer…"):
                    update_fields_fn(sh, task_id, {"description": new_desc.strip()})
                st.session_state["_board_msg"] = (
                    f"✅ Gemte ændringer for **{name}**."
                )
                st.rerun()
        else:
            st.code(cur_desc if cur_desc else "Ingen beskrivelse.", language=None)

        # Time estimates removed


def render_unscheduled_task(task: Dict, sh, assign_week_fn: Callable, update_fields_fn: Callable) -> None:
    """Render a single unscheduled task as a collapsible expander.

    Inside the expander the user can pick a week to assign the task to.
    The *assign_week_fn* should accept (sh, task_id, new_week_id).
    """
    task_id = task.get("id", "")
    name = task.get("task_name", "Unnamed task")

    with st.expander(_expander_title(name[:TASK_NAME_MAX])):
        # Editable description
        cur_desc = (task.get("description") or "").strip()
        desc_key = f"uns_desc_{task_id}"
        new_desc = st.text_area("Beskrivelse", value=cur_desc, key=desc_key, height=120)

        save_key = f"btn_save_{task_id}"
        if st.button("Gem ændringer", key=save_key, use_container_width=True):
            with st.spinner("Gemmer…"):
                updates = {"description": new_desc.strip()}
                update_fields_fn(sh, task_id, updates)
            st.session_state["_unscheduled_msg"] = (
                f"✅ Gemte ændringer for **{name}**."
            )
            st.rerun()
        pick_key = f"uns_assign_{task_id}"
        week_choice = render_week_selector("Tildel til uge", key=pick_key)
        if st.button("Tildel denne opgave", key=f"btn_assign_{task_id}", use_container_width=True):
            with st.spinner("Tildeler…"):
                assign_week_fn(sh, task_id, week_choice)
            st.session_state["_unscheduled_msg"] = (
                f"✅ Tildelte **{name}** til **{week_choice}**."
            )
            st.rerun()

# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def render_analytics(tasks: List[Dict]) -> None:
    """Show task counts per status as a row of three metrics."""
    cols = st.columns(3)
    for i, status in enumerate(STATUSES):
        group = [t for t in tasks if (t.get("status") or "todo") == status]
        with cols[i]:
            st.metric(
                label=f"{STATUS_ICONS[status]} {STATUS_LABELS[status]}",
                value=f"{len(group)} opgave(r)",
                help=None,
            )


# ---------------------------------------------------------------------------
# Weekly task list
# ---------------------------------------------------------------------------

def render_tasks_section(tasks: List[Dict], sh, update_status_fn: Callable, week_id: str = "", update_fields_fn: Optional[Callable] = None) -> None:
    """Render tasks grouped by status.

    All three status groups are always shown – empty groups display a small
    placeholder.  Triggers st.balloons() the first time all tasks in the week
    are marked done (once per week_id per browser session).
    """

    for status in STATUSES:
        group = [t for t in tasks if (t.get("status") or "todo") == status]
        st.markdown(
            f"**{STATUS_ICONS[status]} {STATUS_LABELS[status]} — {len(group)} opgave(r)**",
            unsafe_allow_html=True,
        )
        if group:
            for task in group:
                render_task(task, sh, update_status_fn, update_fields_fn)
        else:
            st.caption("_Intet her endnu._")
        st.write("")  # breathing room between groups

    # ── Celebration ────────────────────────────────────────────────────
    if (
        tasks
        and all(t.get("status") == "done" for t in tasks)
        and st.session_state.get("_celebrated_week") != week_id
    ):
        st.session_state["_celebrated_week"] = week_id
        st.balloons()


# ---------------------------------------------------------------------------
# Edit / delete tasks tab
# ---------------------------------------------------------------------------

def render_edit_tab(sh, current_week_id: str) -> None:
    """Render the ✏️ Edit Tasks tab.

    Lets the user search for a task by name (Streamlit's selectbox has
    built-in keyboard filtering), inspect its future schedule, and delete
    either a single week's instance or every future instance at once.
    """
    from sheets import load_all_tasks, delete_task_by_id, delete_tasks_by_ids, update_task_fields

    if "_edit_msg" in st.session_state:
        st.success(st.session_state.pop("_edit_msg"))

    st.subheader("🔍 Find en opgave")

    with st.spinner("Indlæser opgaver…"):
        all_tasks = load_all_tasks(sh)

    # Only tasks scheduled from the current week onwards
    future = [t for t in all_tasks if t.get("week_id", "") >= current_week_id]

    if not future:
        st.info("Ingen fremtidige opgaver fundet.")
        return

    # Unique names sorted – selectbox supports typing-to-filter out of the box
    names = sorted({t["task_name"] for t in future})
    selected_name = st.selectbox(
        "Vælg opgave  (skriv for at søge)",
        names,
        key="edit_task_name_sel",
    )
    if not selected_name:
        return

    instances = sorted(
        [t for t in future if t["task_name"] == selected_name],
        key=lambda t: t["week_id"],
    )


    # ── Edit description / time for a specific occurrence or all future ──
    st.divider()
    st.markdown("**✏️ Rediger beskrivelse**")

    # Prefill editable fields from the first instance; user can change scope below
    first_target = instances[0]
    edit_desc_key = f"edit_desc_{first_target['id']}"
    new_desc = st.text_area("Beskrivelse", value=(first_target.get("description") or "").strip(), key=edit_desc_key, height=120)

    # Scope: default to editing all future occurrences
    scope = st.radio(
        "Anvend ændringer på",
        options=["Rediger for en enkel uge", "Rediger for alle fremtidige forekomster"],
        index=1,
        key="edit_scope",
    )

    # If editing a single week, show the week selector under the fields
    selected_ids: List[str]
    if scope.startswith("Rediger for en enkel uge"):
        edit_weeks = [t["week_id"] for t in instances]
        sel_wid = st.selectbox(
            "Vælg forekomst at redigere",
            edit_weeks,
            index=0,
            format_func=_week_label,
            key="edit_target_wid",
        )
        target = next((t for t in instances if t["week_id"] == sel_wid), instances[0])
        selected_ids = [target["id"]]
    else:
        # Apply to all future instances
        selected_ids = [t["id"] for t in instances]

    if st.button("Gem Ændringer", use_container_width=True):
        updates = {"description": new_desc.strip()}
        with st.spinner("Gemmer ændringer…"):
            for tid in selected_ids:
                update_task_fields(sh, tid, updates)
        scope_txt = "kun valgt forekomst" if scope.startswith("Rediger for en enkel uge") else "alle fremtidige"
        st.session_state["_edit_msg"] = (
            f"✅ Gemte ændringer for **{selected_name}** ({scope_txt})."
        )
        st.rerun()

    st.markdown(f"**Kommende uger** — {len(instances)} forekomst(er)")
    with st.container(border=True):
        for inst in instances[:15]:
            wid = inst["week_id"]
            s = week_start_from_id(wid)
            e = s + timedelta(days=6)
            icon = STATUS_ICONS.get(inst.get("status", "todo"), "⬜")
            st.markdown(
                f"{icon} &nbsp; {_da_date(s)} – {_da_date(e)} {e.year} "
                f"<span style='color:#aaa;font-size:0.82em'>({wid})</span>",
                unsafe_allow_html=True,
            )
        if len(instances) > 15:
            st.caption(f"…og {len(instances) - 15} mere")

    # ── Delete one week ────────────────────────────────────────────────
    st.divider()
    st.markdown("**Slet en bestemt uge**")
    del_wid = st.selectbox(
        "Uge der skal slettes",
        [t["week_id"] for t in instances],
        format_func=_week_label,
        key="edit_del_week_sel",
    )
    if st.button("🗑 Slet kun denne uge", use_container_width=True):
        target = next((t for t in instances if t["week_id"] == del_wid), None)
        if target:
            with st.spinner("Sletter…"):
                delete_task_by_id(sh, target["id"])
            st.session_state["_edit_msg"] = (
                f"Slettede **{selected_name}** for {del_wid}."
            )
            st.rerun()

    # ── Delete all future ──────────────────────────────────────────────
    st.divider()
    st.markdown("**Slet alle fremtidige forekomster**")
    confirm = st.checkbox(
        f"Ja, slet permanent alle {len(instances)} fremtidige forekomst(er) af "
        f"**{selected_name}**",
        key="edit_confirm_all",
    )
    if confirm:
        if st.button(
            f"🗑 Slet alle {len(instances)} forekomster",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner(f"Sletter {len(instances)} rækker…"):
                delete_tasks_by_ids(sh, [t["id"] for t in instances])
            st.session_state.pop("edit_task_name_sel", None)
            st.session_state.pop("edit_confirm_all", None)
            st.session_state["_edit_msg"] = (
                f"Slettede alle **{len(instances)}** fremtidige forekomster af "
                f"**{selected_name}**."
            )
            st.rerun()


# ---------------------------------------------------------------------------
# Inline add-task form
# ---------------------------------------------------------------------------

def render_add_task_form(week_id: str, form_key: str = "add_adhoc") -> Optional[Dict]:
    """Render an inline form for adding a one-off task to *week_id*.

    Returns the new task dict when the form is submitted with valid input,
    otherwise returns None.  The caller is responsible for persisting the
    task and triggering st.rerun().
    """
    st.markdown("---")
    st.subheader("➕ Tilføj en opgave")
    with st.form(form_key, clear_on_submit=True):
        name = st.text_input("Opgavenavn *", max_chars=TASK_NAME_MAX, placeholder="f.eks. Støvsug kontor")
        fc1, fc2 = st.columns([3, 1])
        with fc1:
            desc = st.text_area("Beskrivelse (valgfri)", height=80)
        with fc2:
            # time estimates removed; keep the column empty for layout
            st.empty()
        submitted = st.form_submit_button("Tilføj", use_container_width=True)

    if submitted:
        if not name.strip():
            st.warning("Opgavenavn er påkrævet.")
            return None
        return make_task(name.strip(), desc.strip(), week_id)
    return None



