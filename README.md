# Spend Tracker

A small expense-tracking service built for the Infinity Consultants backend evaluation. It provides a JSON REST API plus a deliberately lightweight browser UI.

## Run locally

Requires Python 3.10+.

### Windows PowerShell (recommended)

```powershell
.\scripts\build.ps1
.\scripts\run.ps1
```

If PowerShell blocks the scripts for this session, run `Set-ExecutionPolicy -Scope Process Bypass` first.

### Manual setup

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python run.py
```

Open `http://127.0.0.1:5000`. The SQLite database is created automatically at `instance/spend_tracker.sqlite3`.

When `DATABASE_URL` is set, the app uses PostgreSQL instead. Production runs with Gunicorn using `gunicorn run:app`.

Run the tests with:

```bash
pytest
```

## API

| Endpoint | Purpose |
| --- | --- |
| `POST /expenses` | Create an expense with `amount`, `category`, `note`, and ISO `date` |
| `GET /expenses` | List expenses; optional `category`, `start_date`, and `end_date` filters |
| `GET /summary` | Return total spend, category totals, month-over-month spend, and relevant 20% increase insights |

Example:

```bash
curl -X POST http://127.0.0.1:5000/expenses -H "Content-Type: application/json" -d "{\"amount\": 12.50, \"category\": \"Food\", \"note\": \"Lunch\", \"date\": \"2026-09-22\"}"
```

## Design decisions

- SQLite gives this small service durable, queryable storage without a separate infrastructure dependency. Amounts are stored as integer cents to avoid floating-point errors.
- Flask keeps the app compact while still separating application setup, API routes, persistent storage, and static UI.
- Input errors return JSON with a clear message and HTTP 400. The database adds checks and indexes for frequently queried fields.
- Month-over-month compares the current calendar month with the prior calendar month. An insight is shown when a category rises over 20% and has a prior-month baseline.

## With more time

I would add user accounts and authorization, pagination, structured migrations, a currency field, richer date-range reporting, and deploy with a production WSGI server plus managed PostgreSQL.

## AI-use note

I used an AI coding assistant to help scaffold the Flask routes, test cases, and README. I reviewed and adapted the generated approach, including choosing integer-cent storage, adding validation/error cases, and keeping the UI intentionally minimal.
