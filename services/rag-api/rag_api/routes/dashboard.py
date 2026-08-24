"""Overview dashboard routes: summary aggregates and recent activity.

All calls into rag_pipeline are made as `rag_pipeline.<name>(...)` (module-
qualified attribute access) rather than `from rag_pipeline import <name>`, so
that tests can patch `rag_pipeline.<name>` directly and have it take effect
here without needing to know this module's internal import structure -
mirrors `routes/documents.py`'s convention.
"""

from __future__ import annotations

import logging

import rag_pipeline
from fastapi import APIRouter, Depends, HTTPException, status

from rag_api.auth import require_internal_api_key, require_user_id
from rag_api.schemas import CategoryBreakdownOut, DashboardSummaryOut, TransactionOut

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_internal_api_key)])


@router.get("/dashboard/summary", response_model=DashboardSummaryOut)
def get_dashboard_summary(user_id: str = Depends(require_user_id)) -> DashboardSummaryOut:
    try:
        summary = rag_pipeline.get_dashboard_summary(user_id)
    except Exception:
        logger.exception("Failed to compute dashboard summary")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to load dashboard summary.",
        ) from None
    return DashboardSummaryOut(
        total_income=summary.total_income,
        total_spending=summary.total_spending,
        net_savings=summary.net_savings,
        income_trend=summary.income_trend,
        spending_trend=summary.spending_trend,
        savings_trend=summary.savings_trend,
        document_count=summary.document_count,
        total_document_count=summary.total_document_count,
        transaction_count=summary.transaction_count,
        category_breakdown=[
            CategoryBreakdownOut(
                category=item.category, amount=item.amount, percentage=item.percentage
            )
            for item in summary.category_breakdown
        ],
    )


@router.get("/dashboard/activity", response_model=list[TransactionOut])
def get_dashboard_activity(user_id: str = Depends(require_user_id)) -> list[TransactionOut]:
    try:
        transactions = rag_pipeline.get_recent_activity(user_id)
    except Exception:
        logger.exception("Failed to load recent activity")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to load recent activity.",
        ) from None
    return [
        TransactionOut(
            id=item.id,
            description=item.description,
            category=item.category,
            amount=item.amount,
            date=item.date,
        )
        for item in transactions
    ]
