from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.extensions import db
from app.services.marketing_reactivation_outcome_service import (
    run_marketing_reactivation_outcomes,
)


def run_job(
    *,
    business_date: date | None = None,
    requested_by: str = "reports_scheduler",
) -> dict[str, Any]:
    """Reevalúa resultados de campañas SENT usando fuentes canónicas disponibles."""

    effective_date = business_date or datetime.now(timezone.utc).date()
    try:
        result = run_marketing_reactivation_outcomes(
            session=db.session,
        )
    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "completed",
        "business_date": effective_date.isoformat(),
        "requested_by": requested_by,
        **result,
    }
