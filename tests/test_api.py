from datetime import date

import pytest
from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite"), "TODAY": date(2026, 9, 22)})
    return app.test_client()


def expense(client, amount="12.50", category="Food", expense_date="2026-09-10"):
    return client.post("/expenses", json={"amount": amount, "category": category, "note": "Lunch", "date": expense_date})


def test_create_and_filter_expenses(client):
    assert expense(client).status_code == 201
    expense(client, "20", "Transport", "2026-09-11")
    response = client.get("/expenses?category=Food&start_date=2026-09-01&end_date=2026-09-30")
    assert response.status_code == 200
    assert response.json == [{"id": 1, "amount": 12.5, "category": "Food", "note": "Lunch", "date": "2026-09-10"}]


@pytest.mark.parametrize("payload", [
    {"amount": "0", "category": "Food", "date": "2026-09-10"},
    {"amount": "4.123", "category": "Food", "date": "2026-09-10"},
    {"amount": "4", "category": "", "date": "2026-09-10"},
    {"amount": "4", "category": "Food", "date": "10/09/2026"},
])
def test_rejects_invalid_expense(client, payload):
    assert client.post("/expenses", json=payload).status_code == 400


def test_summary_and_mom_change(client):
    expense(client, "120", "Food", "2026-09-05")
    expense(client, "100", "Food", "2026-08-05")
    expense(client, "30", "Travel", "2026-09-12")
    summary = client.get("/summary").json
    assert summary["total_spend"] == 250
    assert summary["spend_by_category"] == {"Food": 220, "Travel": 30}
    assert summary["month_over_month"]["percent_change"] == 50
    assert "Food spend is up 20% month-over-month." in summary["insights"]


def test_invalid_date_range(client):
    response = client.get("/expenses?start_date=2026-10-01&end_date=2026-09-01")
    assert response.status_code == 400
