import os
import sqlite3
import hmac
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, request


def _is_postgres(database):
    return database.startswith(("postgres://", "postgresql://"))


def _connect(database):
    if _is_postgres(database):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(database, row_factory=dict_row)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    return connection


def create_app(test_config=None):
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config.from_mapping(
        DATABASE=os.environ.get("DATABASE_URL", os.path.join(app.instance_path, "spend_tracker.sqlite3"))
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    @app.before_request
    def require_api_key():
        expected = app.config.get("API_KEY") or os.environ.get("API_KEY")
        if expected and request.path in {"/expenses", "/summary"}:
            supplied = request.headers.get("X-API-Key", "")
            if not hmac.compare_digest(supplied, expected):
                return jsonify(error="A valid API key is required."), 401

    def db():
        return _connect(app.config["DATABASE"])

    def placeholders(sql):
        return sql.replace("?", "%s") if _is_postgres(app.config["DATABASE"]) else sql

    def initialize_database():
        connection = db()
        id_column = "BIGSERIAL PRIMARY KEY" if _is_postgres(app.config["DATABASE"]) else "INTEGER PRIMARY KEY AUTOINCREMENT"
        connection.execute(f"""
            CREATE TABLE IF NOT EXISTS expenses (
                id {id_column},
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                category TEXT NOT NULL CHECK (length(category) BETWEEN 1 AND 80),
                note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 500),
                expense_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)")
        connection.commit()
        connection.close()

    initialize_database()

    def error(message, status=400):
        return jsonify(error=message), status

    def parse_date(value, field):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD).")

    def filters():
        category = request.args.get("category")
        start = request.args.get("start_date")
        end = request.args.get("end_date")
        if start:
            start = parse_date(start, "start_date").isoformat()
        if end:
            end = parse_date(end, "end_date").isoformat()
        if start and end and start > end:
            raise ValueError("start_date must be before or equal to end_date.")
        return category, start, end

    def matching_rows(category, start, end):
        sql, params = "SELECT * FROM expenses WHERE 1=1", []
        if category:
            sql += " AND category = ?"
            params.append(category)
        if start:
            sql += " AND expense_date >= ?"
            params.append(start)
        if end:
            sql += " AND expense_date <= ?"
            params.append(end)
        sql += " ORDER BY expense_date DESC, id DESC"
        connection = db()
        rows = connection.execute(placeholders(sql), params).fetchall()
        connection.close()
        return rows

    def expense_json(row):
        return {"id": row["id"], "amount": row["amount_cents"] / 100, "category": row["category"],
                "note": row["note"], "date": row["expense_date"]}

    @app.post("/expenses")
    def create_expense():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return error("Request body must be a JSON object.")
        try:
            amount = Decimal(str(payload.get("amount")))
            if amount <= 0 or amount.as_tuple().exponent < -2:
                raise ValueError
        except (InvalidOperation, ValueError):
            return error("amount must be a positive number with at most two decimal places.")
        category = payload.get("category")
        note = payload.get("note", "")
        if not isinstance(category, str) or not category.strip() or len(category.strip()) > 80:
            return error("category is required and must be 1-80 characters.")
        if not isinstance(note, str) or len(note) > 500:
            return error("note must be a string of up to 500 characters.")
        try:
            expense_date = parse_date(payload.get("date"), "date").isoformat()
        except ValueError as exc:
            return error(str(exc))
        connection = db()
        values = (int(amount * 100), category.strip(), note.strip(), expense_date)
        if _is_postgres(app.config["DATABASE"]):
            row = connection.execute(
                "INSERT INTO expenses (amount_cents, category, note, expense_date) VALUES (%s, %s, %s, %s) RETURNING *",
                values,
            ).fetchone()
        else:
            cursor = connection.execute(
                "INSERT INTO expenses (amount_cents, category, note, expense_date) VALUES (?, ?, ?, ?)", values
            )
            row = connection.execute("SELECT * FROM expenses WHERE id = ?", (cursor.lastrowid,)).fetchone()
        connection.commit()
        connection.close()
        return jsonify(expense_json(row)), 201

    @app.get("/expenses")
    def list_expenses():
        try:
            rows = matching_rows(*filters())
        except ValueError as exc:
            return error(str(exc))
        return jsonify([expense_json(row) for row in rows])

    @app.get("/summary")
    def summary():
        try:
            category, start, end = filters()
            rows = matching_rows(category, start, end)
        except ValueError as exc:
            return error(str(exc))
        total_cents = sum(row["amount_cents"] for row in rows)
        by_category = {}
        for row in rows:
            by_category[row["category"]] = by_category.get(row["category"], 0) + row["amount_cents"]
        today = app.config.get("TODAY", date.today())
        current_prefix = today.strftime("%Y-%m")
        previous_prefix = (today.replace(day=1).toordinal() - 1)
        previous_prefix = date.fromordinal(previous_prefix).strftime("%Y-%m")
        current = sum(r["amount_cents"] for r in rows if r["expense_date"].startswith(current_prefix))
        previous = sum(r["amount_cents"] for r in rows if r["expense_date"].startswith(previous_prefix))
        change = None if previous == 0 else round((current - previous) / previous * 100, 2)
        insights = [f"{name} spend is up {round((sum(r['amount_cents'] for r in rows if r['category'] == name and r['expense_date'].startswith(current_prefix)) / sum(r['amount_cents'] for r in rows if r['category'] == name and r['expense_date'].startswith(previous_prefix)) - 1) * 100)}% month-over-month."
                    for name in by_category
                    if sum(r['amount_cents'] for r in rows if r['category'] == name and r['expense_date'].startswith(previous_prefix)) > 0
                    and sum(r['amount_cents'] for r in rows if r['category'] == name and r['expense_date'].startswith(current_prefix)) > sum(r['amount_cents'] for r in rows if r['category'] == name and r['expense_date'].startswith(previous_prefix)) * 1.2]
        return jsonify(total_spend=total_cents / 100,
                       spend_by_category={key: value / 100 for key, value in sorted(by_category.items())},
                       month_over_month={"current_month": current / 100, "previous_month": previous / 100, "percent_change": change},
                       insights=insights)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    return app
