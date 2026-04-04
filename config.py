"""
App-wide constants and configuration.
"""

# Google Sheets worksheet name for the new unified task store
TASKS_SHEET = "tasks"

# Date format used when persisting to the sheet
DATE_FMT = "%Y-%m-%d"

# Column headers (order matters – rows are written in this order)
TASK_HEADERS = ["id", "task_name", "week_id", "status", "description", "created_at"]

# Status values stored in the sheet
STATUSES = ["todo", "in_progress", "done"]

# Human-readable labels for each status (Danish)
STATUS_LABELS = {
    "todo": "To do",
    "in_progress": "I gang",
    "done": "Færdig",
}

# Emoji icons used in the UI
STATUS_ICONS = {
    "todo": "⬜",
    "in_progress": "🔵",
    "done": "✅",
}

# How many years ahead to generate recurring task instances
YEARS_AHEAD = 5

