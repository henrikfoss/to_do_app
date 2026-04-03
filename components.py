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

def _parse_minutes(task: Dict) -> int:
    """Safely parse time_estimate_minutes from a task dict."""
    try:
        return max(0, int(task.get("time_estimate_minutes") or 0))
    except (ValueError, TypeError):
        return 0


def _fmt_minutes(total: int) -> str:
    """Format a minute count using full Danish words, e.g. '1 time 16 minutter'."""
    if total == 0:
        return "0 minutter"
    h, m = divmod(total, 60)
    hour_str = ("1 time" if h == 1 else f"{h} timer") if h else ""
    min_str  = ("1 minut" if m == 1 else f"{m} minutter") if m else ""
    return f"{hour_str} {min_str}".strip()


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


def _expander_title(name: str, time_str: str) -> str:
    """Build an expander title that pads shorter names with em-spaces so the
    time estimate lands at roughly the same horizontal position regardless of
    how long the task name is.

    An em-space (\u2003) is ~1 em wide; an average proportional character is
    ~0.5 em, so we divide the character gap by 2 to convert characters → em-spaces,
    then add a small fixed minimum so even a 50-char name still has a gap.
    """
    gap = max(2, (TASK_NAME_MAX - len(name)) // 2)
    padding = "\u2003" * gap
    return f"{name}{padding}{time_str}"


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

def render_task(task: Dict, sh, update_status_fn: Callable) -> None:
    """Render a single task as a collapsible expander.

    The title shows: status icon · task name · time estimate.
    Inside: description (if any) and a status drop-down.
    """
    task_id = task.get("id", "")
    status = task.get("status", "todo")
    if status not in STATUSES:
        status = "todo"

    name = task.get("task_name", "Unnamed task")
    time_str = _fmt_minutes(_parse_minutes(task))

    with st.expander(_expander_title(name[:TASK_NAME_MAX], time_str)):
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

        desc = (task.get("description") or "").strip()

        st.markdown("**Beskrivelse**")
        st.code(desc if desc else "Ingen beskrivelse.", language=None)

        st.markdown("**Tidsestimat**")
        st.code(time_str, language=None)

# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def render_analytics(tasks: List[Dict]) -> None:
    """Show time totals per status as a row of three metrics."""
    cols = st.columns(3)
    for i, status in enumerate(STATUSES):
        group = [t for t in tasks if (t.get("status") or "todo") == status]
        total_min = sum(_parse_minutes(t) for t in group)
        with cols[i]:
            st.metric(
                label=f"{STATUS_ICONS[status]} {STATUS_LABELS[status]}",
                value=_fmt_minutes(total_min),
                help=f"{len(group)} task(s)",
            )


# ---------------------------------------------------------------------------
# Weekly task list
# ---------------------------------------------------------------------------

def render_tasks_section(tasks: List[Dict], sh, update_status_fn: Callable, week_id: str = "") -> None:
    """Render tasks grouped by status.

    All three status groups are always shown – empty groups display a small
    placeholder.  Triggers st.balloons() the first time all tasks in the week
    are marked done (once per week_id per browser session).
    """

    for status in STATUSES:
        group = [t for t in tasks if (t.get("status") or "todo") == status]
        total_min = sum(_parse_minutes(t) for t in group)
        st.markdown(
            f"**{STATUS_ICONS[status]} {STATUS_LABELS[status]} — {_fmt_minutes(total_min)}**",
            unsafe_allow_html=True,
        )
        if group:
            for task in group:
                render_task(task, sh, update_status_fn)
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
    from sheets import load_all_tasks, delete_task_by_id, delete_tasks_by_ids

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

    # ── Task info ──────────────────────────────────────────────────────
    st.divider()
    st.markdown(f"### {selected_name}")

    first = instances[0]
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Beskrivelse**")
        with st.container(border=True):
            desc = (first.get("description") or "").strip()
            st.markdown(desc if desc else "_Ingen beskrivelse._")
    with col2:
        st.markdown("**Tidsestimat**")
        with st.container(border=True):
            st.markdown(_fmt_minutes(_parse_minutes(first)))

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

def render_add_task_form(week_id: str) -> Optional[Dict]:
    """Render an inline form for adding a one-off task to *week_id*.

    Returns the new task dict when the form is submitted with valid input,
    otherwise returns None.  The caller is responsible for persisting the
    task and triggering st.rerun().
    """
    st.markdown("---")
    st.subheader("➕ Tilføj en opgave")
    with st.form("add_adhoc", clear_on_submit=True):
        name = st.text_input("Opgavenavn *", max_chars=TASK_NAME_MAX, placeholder="f.eks. Støvsug kontor")
        fc1, fc2 = st.columns([3, 1])
        with fc1:
            desc = st.text_area("Beskrivelse (valgfri)", height=80)
        with fc2:
            time_est = st.number_input(
                "Minutter *", min_value=5, max_value=1440, value=5, step=5
            )
        submitted = st.form_submit_button("Tilføj", use_container_width=True)

    if submitted:
        if not name.strip():
            st.warning("Opgavenavn er påkrævet.")
            return None
        return make_task(name.strip(), desc.strip(), week_id, int(time_est))
    return None



