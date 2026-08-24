"""Tests for GET /dashboard/summary and GET /dashboard/activity."""

from __future__ import annotations

from rag_pipeline import CategoryBreakdown, DashboardSummary, TransactionRecord


def _make_summary(**overrides) -> DashboardSummary:
    defaults = dict(
        total_income=2000.0,
        total_spending=-500.0,
        net_savings=1500.0,
        income_trend=10.0,
        spending_trend=-5.0,
        savings_trend=20.0,
        document_count=2,
        total_document_count=3,
        transaction_count=10,
        category_breakdown=[CategoryBreakdown(category="Housing", amount=300.0, percentage=60.0)],
    )
    defaults.update(overrides)
    return DashboardSummary(**defaults)


def _make_transaction(**overrides) -> TransactionRecord:
    defaults = dict(
        id="tx-1",
        description="Coffee Shop",
        category="Dining",
        amount=-4.5,
        date="2026-01-15",
    )
    defaults.update(overrides)
    return TransactionRecord(**defaults)


def test_get_dashboard_summary_returns_camel_case_shape(client, mocker):
    mocker.patch("rag_pipeline.get_dashboard_summary", return_value=_make_summary())

    response = client.get("/dashboard/summary")

    assert response.status_code == 200
    assert response.json() == {
        "totalIncome": 2000.0,
        "totalSpending": -500.0,
        "netSavings": 1500.0,
        "incomeTrend": 10.0,
        "spendingTrend": -5.0,
        "savingsTrend": 20.0,
        "documentCount": 2,
        "totalDocumentCount": 3,
        "transactionCount": 10,
        "categoryBreakdown": [{"category": "Housing", "amount": 300.0, "percentage": 60.0}],
    }


def test_get_dashboard_summary_scopes_to_the_requesting_user(client, user_id, mocker):
    get_summary = mocker.patch("rag_pipeline.get_dashboard_summary", return_value=_make_summary())

    client.get("/dashboard/summary")

    get_summary.assert_called_once_with(user_id)


def test_get_dashboard_summary_returns_502_on_pipeline_error(client, mocker):
    mocker.patch("rag_pipeline.get_dashboard_summary", side_effect=RuntimeError("supabase down"))

    response = client.get("/dashboard/summary")

    assert response.status_code == 502


def test_get_dashboard_summary_returns_401_when_unauthenticated(unauthenticated_client):
    response = unauthenticated_client.get("/dashboard/summary")

    assert response.status_code == 401


def test_get_dashboard_activity_returns_camel_case_shape(client, mocker):
    mocker.patch("rag_pipeline.get_recent_activity", return_value=[_make_transaction()])

    response = client.get("/dashboard/activity")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "tx-1",
            "description": "Coffee Shop",
            "category": "Dining",
            "amount": -4.5,
            "date": "2026-01-15",
        }
    ]


def test_get_dashboard_activity_scopes_to_the_requesting_user(client, user_id, mocker):
    get_activity = mocker.patch("rag_pipeline.get_recent_activity", return_value=[])

    client.get("/dashboard/activity")

    get_activity.assert_called_once_with(user_id)


def test_get_dashboard_activity_returns_502_on_pipeline_error(client, mocker):
    mocker.patch("rag_pipeline.get_recent_activity", side_effect=RuntimeError("supabase down"))

    response = client.get("/dashboard/activity")

    assert response.status_code == 502


def test_get_dashboard_activity_returns_401_when_unauthenticated(unauthenticated_client):
    response = unauthenticated_client.get("/dashboard/activity")

    assert response.status_code == 401
