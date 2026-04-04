"""
Week utilities and task generation logic.

Responsibilities
----------------
- Converting between calendar dates and ISO week identifiers (e.g. "2026-W14")
- Generating a flat list of task dicts for recurring tasks (one row per matching week)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import List, Dict

from config import DATE_FMT, YEARS_AHEAD


# ---------------------------------------------------------------------------
# Week helpers
# ---------------------------------------------------------------------------

def week_id_from_date(d: date) -> str:
    """Return the ISO week identifier for the week that contains *d*.

    Example: date(2026, 4, 3)  →  "2026-W14"
    """
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def week_start_from_id(week_id: str) -> date:
    """Return the Monday of the given ISO week identifier.

    Example: "2026-W14"  →  date(2026, 3, 30)
    """
    year_str, week_str = week_id.split("-W")
    return datetime.strptime(f"{year_str}-W{int(week_str):02d}-1", "%G-W%V-%u").date()


def week_label(week_id: str) -> str:
    """Human-readable label for a week, e.g. "Mar 30 – Apr 05, 2026 (2026-W14)"."""
    start = week_start_from_id(week_id)
    end = start + timedelta(days=6)
    return f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}  ({week_id})"


# ---------------------------------------------------------------------------
# Task generation
# ---------------------------------------------------------------------------

def make_task(task_name: str, description: str, week_id: str) -> Dict:
    """Return a single task dict ready to be written to the sheet."""
    return {
        "id": str(uuid.uuid4()),
        "task_name": task_name,
        "week_id": week_id,
        "status": "todo",
        "description": description,
        # time_estimate_minutes removed
        "created_at": date.today().strftime(DATE_FMT),
    }


def generate_recurring_instances(
    task_name: str,
    description: str,
    start_date: date,
    interval_weeks: int,
) -> List[Dict]:
    """Generate one task dict per matching week from *start_date* to ~5 years from today.

    The start_date is aligned to the Monday of its ISO week so that all
    generated instances fall neatly on week boundaries.

    Parameters
    ----------
    task_name:      Name that will appear in every generated task.
    description:    Optional description copied to every instance.
    start_date:     Any date within the first desired week.
    interval_weeks: Repeat cadence (1 = every week, 2 = bi-weekly, …).

    Returns
    -------
    List of task dicts (not yet saved to the sheet).
    """
    today = date.today()
    end_date = date(today.year + YEARS_AHEAD, today.month, today.day)

    # Align to Monday of the start week
    monday = start_date - timedelta(days=start_date.weekday())

    tasks: List[Dict] = []
    current = monday
    while current <= end_date:
        tasks.append(make_task(task_name, description, week_id_from_date(current)))
        current += timedelta(weeks=interval_weeks)

    return tasks
