"""Dashboard aggregates computed from the `transactions` table (see
sql/013_create_transactions_table.sql and rag_pipeline/transactions.py).

Everything here reads via the service-role Supabase client (bypassing RLS,
same as the rest of rag_pipeline) and scopes explicitly to a `user_id`
argument, mirroring `documents.py`'s convention.

The public `get_dashboard_summary`/`get_recent_activity` functions are thin
cached wrappers around `_compute_dashboard_summary`/`_compute_recent_activity`,
which hold the actual Supabase queries; see `dashboard_cache.py` for the
short-TTL, per-user cache itself and for where cache invalidation on write
happens (document upload/delete, in `ingest.py`/`documents.py`).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from rag_pipeline.config import Settings, load_settings
from rag_pipeline.dashboard_cache import cached_activity, cached_summary
from rag_pipeline.retry import execute_with_retry
from rag_pipeline.supabase_client import get_supabase_client

_DEFAULT_ACTIVITY_LIMIT = 20


@dataclass(frozen=True)
class CategoryBreakdown:
    category: str
    amount: float
    percentage: float


@dataclass(frozen=True)
class DashboardSummary:
    total_income: float
    total_spending: float
    net_savings: float
    income_trend: float
    spending_trend: float
    savings_trend: float
    document_count: int
    total_document_count: int
    transaction_count: int
    category_breakdown: list[CategoryBreakdown]


@dataclass(frozen=True)
class TransactionRecord:
    id: str
    description: str
    category: str
    amount: float
    date: str


def _trend(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round((current - previous) / abs(previous) * 100, 1)


def _month_to_date_span(today: date) -> tuple[date, date]:
    """The current month, from day 1 through `today` (inclusive)."""
    return date(today.year, today.month, 1), today


def _previous_month_same_span(today: date) -> tuple[date, date]:
    """The same span of days in the previous calendar month (e.g. if today is
    the 15th, the 1st through the 15th of last month), clamped to that
    month's actual last day for months shorter than the current one.
    """
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1

    last_day_of_prev_month = calendar.monthrange(prev_year, prev_month)[1]
    end_day = min(today.day, last_day_of_prev_month)
    return date(prev_year, prev_month, 1), date(prev_year, prev_month, end_day)


def _fetch_transactions_in_range(
    supabase: Any, user_id: str, start: date, end: date
) -> list[dict[str, Any]]:
    response = execute_with_retry(
        supabase.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .gte("occurred_on", start.isoformat())
        .lte("occurred_on", end.isoformat())
    )
    return response.data


def _sum_income_spending(rows: list[dict[str, Any]]) -> tuple[float, float]:
    income = sum(float(row["amount"]) for row in rows if float(row["amount"]) > 0)
    spending = sum(float(row["amount"]) for row in rows if float(row["amount"]) < 0)
    return income, spending


def get_dashboard_summary(
    user_id: str, settings: Settings | None = None
) -> DashboardSummary:
    """Compute the Overview dashboard's summary: income/spending/net-savings
    totals and trends (current month-to-date vs the same span of the
    previous month), document counts, and a spending-only category
    breakdown.

    Cached per `user_id` for `dashboard_cache.TTL_SECONDS`; see
    `dashboard_cache.py`.
    """
    return cached_summary(user_id, lambda: _compute_dashboard_summary(user_id, settings))


def _compute_dashboard_summary(
    user_id: str, settings: Settings | None = None
) -> DashboardSummary:
    settings = settings or load_settings()
    supabase = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    today = datetime.now(timezone.utc).date()
    current_start, current_end = _month_to_date_span(today)
    previous_start, previous_end = _previous_month_same_span(today)

    current_rows = _fetch_transactions_in_range(supabase, user_id, current_start, current_end)
    previous_rows = _fetch_transactions_in_range(supabase, user_id, previous_start, previous_end)

    current_income, current_spending = _sum_income_spending(current_rows)
    previous_income, previous_spending = _sum_income_spending(previous_rows)

    current_net = current_income + current_spending
    previous_net = previous_income + previous_spending

    documents_response = execute_with_retry(
        supabase.table("documents").select("*").eq("user_id", user_id)
    )
    all_documents = documents_response.data
    total_document_count = len(all_documents)
    document_count = sum(1 for doc in all_documents if doc.get("status") == "completed")

    transactions_response = execute_with_retry(
        supabase.table("transactions").select("*").eq("user_id", user_id)
    )
    all_transactions = transactions_response.data
    transaction_count = len(all_transactions)

    spending_by_category: dict[str, float] = {}
    for row in all_transactions:
        amount = float(row["amount"])
        if amount >= 0:
            continue
        category = row.get("category") or "Uncategorized"
        spending_by_category[category] = spending_by_category.get(category, 0.0) + amount

    total_category_spending = sum(abs(amount) for amount in spending_by_category.values())
    category_breakdown = [
        CategoryBreakdown(
            category=category,
            amount=abs(amount),
            percentage=(
                round(abs(amount) / total_category_spending * 100, 1)
                if total_category_spending
                else 0.0
            ),
        )
        for category, amount in sorted(
            spending_by_category.items(), key=lambda item: item[1]
        )
    ]

    return DashboardSummary(
        total_income=current_income,
        total_spending=current_spending,
        net_savings=current_net,
        income_trend=_trend(current_income, previous_income),
        spending_trend=_trend(current_spending, previous_spending),
        savings_trend=_trend(current_net, previous_net),
        document_count=document_count,
        total_document_count=total_document_count,
        transaction_count=transaction_count,
        category_breakdown=category_breakdown,
    )


def get_recent_activity(
    user_id: str, limit: int = _DEFAULT_ACTIVITY_LIMIT, settings: Settings | None = None
) -> list[TransactionRecord]:
    """Return the `limit` most recent transactions for `user_id`, most
    recently occurred first.

    Cached per `user_id`/`limit` for `dashboard_cache.TTL_SECONDS`; see
    `dashboard_cache.py`.
    """
    return cached_activity(
        user_id, limit, lambda: _compute_recent_activity(user_id, limit, settings)
    )


def _compute_recent_activity(
    user_id: str, limit: int, settings: Settings | None = None
) -> list[TransactionRecord]:
    settings = settings or load_settings()
    supabase = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    response = execute_with_retry(
        supabase.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .order("occurred_on", desc=True)
        .limit(limit)
    )
    return [
        TransactionRecord(
            id=row["id"],
            description=(row.get("description") or "").strip() or (row.get("category") or ""),
            category=row.get("category") or "Uncategorized",
            amount=float(row["amount"]),
            date=row["occurred_on"],
        )
        for row in response.data
    ]
