# Household Weekly Tasks

A Streamlit app for managing household tasks week-by-week, backed by a single Google Sheet.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Google Sheets setup

1. Enable the **Google Sheets API** at <https://console.cloud.google.com>
2. Create a **Service Account** (IAM & Admin → Service Accounts → Create) and download its JSON key.
3. **Share** your Google Sheet with the service-account e-mail (Editor access).
4. Create `.streamlit/secrets.toml` in the project root:

```toml
SPREADSHEET_ID = "<your-sheet-id-or-full-url>"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@...gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

The app will automatically create a **`tasks`** worksheet in your spreadsheet on first run.

## Project structure

| File | Responsibility |
|---|---|
| `app.py` | Entry point — page config & tab layout |
| `config.py` | App-wide constants (sheet name, status enums, date format) |
| `sheets.py` | Google Sheets connection & all CRUD operations |
| `tasks.py` | Week utilities and recurring-task generation logic |
| `components.py` | Reusable Streamlit UI widgets (week navigator, task expanders) |

## Data model

One worksheet called **`tasks`**:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `task_name` | string | Free text |
| `week_id` | string | ISO week, e.g. `2026-W14` |
| `status` | enum | `todo` · `in_progress` · `done` |
| `description` | string | Optional |
| `created_at` | date | `YYYY-MM-DD` |

## Features

- **📅 This Week tab** — browse tasks week-by-week with ← / → navigation. Each task is an expandable card showing its description and a status dropdown.
- **➕ Add Task tab** — create a one-off task for any week.
- **🔁 Recurring Tasks tab** — schedule a task every 1 / 2 / 3 / 4 weeks starting from a chosen week. All instances for the next 5 years are written as individual rows so each week's completion is tracked independently.
