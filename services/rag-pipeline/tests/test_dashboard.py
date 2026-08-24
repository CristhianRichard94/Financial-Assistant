"""Tests for rag_pipeline.dashboard: get_dashboard_summary and
get_recent_activity."""

from __future__ import annotations

from datetime import datetime, timezone

from rag_pipeline.dashboard import get_dashboard_summary, get_recent_activity

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"


def _today() -> datetime:
    return datetime.now(timezone.utc)


def _seed_transaction(fake_supabase, **overrides):
    row = {
        "id": overrides.pop("id", None) or f"tx-{len(fake_supabase.tables.get('transactions', []))}",
        "document_id": "doc-1",
        "user_id": USER_ID,
        "occurred_on": _today().date().isoformat(),
        "amount": "0",
        "category": "Uncategorized",
        "description": "",
    }
    row.update(overrides)
    fake_supabase.tables.setdefault("transactions", []).append(row)
    return row


def _seed_document(fake_supabase, status: str, user_id: str = USER_ID):
    fake_supabase.tables.setdefault("documents", []).append(
        {
            "id": f"doc-{len(fake_supabase.tables.get('documents', []))}",
            "filename": "statement.csv",
            "status": status,
            "user_id": user_id,
            "upload_date": _today().isoformat(),
            "metadata": {},
        }
    )


def test_totals_and_document_transaction_scoping(fake_supabase, fake_settings):
    today = _today().date()
    _seed_transaction(fake_supabase, amount="2000.00", occurred_on=today.isoformat())
    _seed_transaction(fake_supabase, amount="-500.00", occurred_on=today.isoformat())
    # A different user's transaction must never be counted.
    _seed_transaction(fake_supabase, user_id=OTHER_USER_ID, amount="9999.00")

    _seed_document(fake_supabase, status="completed")
    _seed_document(fake_supabase, status="pending")
    _seed_document(fake_supabase, status="completed", user_id=OTHER_USER_ID)

    summary = get_dashboard_summary(USER_ID, settings=fake_settings)

    assert summary.total_income == 2000.00
    assert summary.total_spending == -500.00
    assert summary.net_savings == 1500.00
    assert summary.total_document_count == 2
    assert summary.document_count == 1
    assert summary.transaction_count == 2


def test_trend_calc_current_vs_previous_month(fake_supabase, fake_settings):
    today = _today()
    current_month_start = today.replace(day=1)
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1

    _seed_transaction(
        fake_supabase, amount="1000.00", occurred_on=current_month_start.date().isoformat()
    )
    _seed_transaction(
        fake_supabase,
        amount="500.00",
        occurred_on=f"{prev_year:04d}-{prev_month:02d}-01",
    )

    summary = get_dashboard_summary(USER_ID, settings=fake_settings)

    # (1000 - 500) / abs(500) * 100 = 100.0
    assert summary.income_trend == 100.0


def test_trend_calc_zero_previous_period_is_zero_not_error(fake_supabase, fake_settings):
    today = _today().date()
    _seed_transaction(fake_supabase, amount="1000.00", occurred_on=today.isoformat())

    summary = get_dashboard_summary(USER_ID, settings=fake_settings)

    assert summary.income_trend == 0.0
    assert summary.spending_trend == 0.0
    assert summary.savings_trend == 0.0


def test_category_breakdown_percentages_and_sort_order(fake_supabase, fake_settings):
    _seed_transaction(fake_supabase, amount="-300.00", category="Housing")
    _seed_transaction(fake_supabase, amount="-100.00", category="Groceries")
    # Income rows must never appear in the (spending-only) breakdown.
    _seed_transaction(fake_supabase, amount="1000.00", category="Income")

    summary = get_dashboard_summary(USER_ID, settings=fake_settings)

    assert [c.category for c in summary.category_breakdown] == ["Housing", "Groceries"]
    assert summary.category_breakdown[0].amount == 300.00
    assert summary.category_breakdown[0].percentage == 75.0
    assert summary.category_breakdown[1].amount == 100.00
    assert summary.category_breakdown[1].percentage == 25.0


def test_category_breakdown_empty_when_no_spending(fake_supabase, fake_settings):
    _seed_transaction(fake_supabase, amount="1000.00", category="Income")

    summary = get_dashboard_summary(USER_ID, settings=fake_settings)

    assert summary.category_breakdown == []


def test_get_recent_activity_orders_by_date_desc_and_scopes_to_user(
    fake_supabase, fake_settings
):
    _seed_transaction(
        fake_supabase, id="tx-old", occurred_on="2026-01-01", description="Old", amount="-1.00"
    )
    _seed_transaction(
        fake_supabase, id="tx-new", occurred_on="2026-02-01", description="New", amount="-2.00"
    )
    _seed_transaction(fake_supabase, user_id=OTHER_USER_ID, occurred_on="2026-03-01")

    activity = get_recent_activity(USER_ID, settings=fake_settings)

    assert [tx.id for tx in activity] == ["tx-new", "tx-old"]


def test_get_recent_activity_falls_back_to_category_when_description_blank(
    fake_supabase, fake_settings
):
    _seed_transaction(fake_supabase, description="", category="Dining", amount="-5.00")

    activity = get_recent_activity(USER_ID, settings=fake_settings)

    assert activity[0].description == "Dining"


def test_get_recent_activity_respects_limit(fake_supabase, fake_settings):
    for i in range(5):
        _seed_transaction(fake_supabase, id=f"tx-{i}", occurred_on=f"2026-01-0{i + 1}")

    activity = get_recent_activity(USER_ID, limit=2, settings=fake_settings)

    assert len(activity) == 2
