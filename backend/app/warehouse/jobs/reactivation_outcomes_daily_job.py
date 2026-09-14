from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import or_

from app.extensions import db
from app.models.marketing import (
    MarketingReactivationCampaignORM,
    MarketingReactivationCampaignRecipientORM,
)
from app.models.marketing_reactivation_outcome import (
    MarketingReactivationCampaignRecipientOutcomeORM,
)
from app.services.marketing_reactivation_outcome_service import (
    OUTCOME_PENDING,
    OUTCOME_REVIEW,
    run_marketing_reactivation_outcomes,
)


def _campaign_ids_requiring_daily_check() -> list[int]:
    rows = (
        db.session.query(MarketingReactivationCampaignORM.id)
        .join(
            MarketingReactivationCampaignRecipientORM,
            MarketingReactivationCampaignRecipientORM.campaign_id
            == MarketingReactivationCampaignORM.id,
        )
        .outerjoin(
            MarketingReactivationCampaignRecipientOutcomeORM,
            MarketingReactivationCampaignRecipientOutcomeORM.campaign_recipient_id
            == MarketingReactivationCampaignRecipientORM.id,
        )
        .filter(
            MarketingReactivationCampaignORM.status == "SENT",
            MarketingReactivationCampaignORM.sent_at.isnot(None),
            or_(
                MarketingReactivationCampaignRecipientOutcomeORM.id.is_(None),
                MarketingReactivationCampaignRecipientOutcomeORM.status.in_(
                    (OUTCOME_PENDING, OUTCOME_REVIEW)
                ),
            ),
        )
        .distinct()
        .all()
    )
    return [int(row[0]) for row in rows]


def run_job(
    *,
    business_date: date | None = None,
    requested_by: str = "reports_scheduler",
) -> dict[str, Any]:
    """Reevalúa campañas abiertas; las cerradas quedan para reconciliación manual."""

    effective_date = business_date or datetime.now(timezone.utc).date()
    try:
        campaign_ids = _campaign_ids_requiring_daily_check()
        result = run_marketing_reactivation_outcomes(
            campaign_ids=campaign_ids,
            session=db.session,
        )
    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "completed",
        "business_date": effective_date.isoformat(),
        "requested_by": requested_by,
        "campaigns_requested": len(campaign_ids),
        **result,
    }
