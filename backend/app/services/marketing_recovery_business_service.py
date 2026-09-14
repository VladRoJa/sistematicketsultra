from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable

from app.extensions import db
from app.models.marketing import MarketingReactivationCampaignRecipientORM
from app.models.marketing_reactivation_outcome import (
    MarketingReactivationCampaignRecipientOutcomeORM,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


BUSINESS_RESULT_RENEWAL = "RENOVACION"
BUSINESS_RESULT_REACTIVATION = "REACTIVACION"


def classify_recovery_business_result(
    *,
    expiration_date: date | None,
    recovered_at_local: datetime | None,
) -> str | None:
    """Clasifica una recuperación según la regla operativa de Ultra.

    - mismo mes calendario del vencimiento y pago: RENOVACION;
    - vencimiento anterior al primer día del mes del pago: REACTIVACION;
    - datos faltantes o cronológicamente inconsistentes: sin clasificación.
    """

    if expiration_date is None or recovered_at_local is None:
        return None

    recovered_date = recovered_at_local.date()
    if expiration_date > recovered_date:
        return None

    recovery_month_start = recovered_date.replace(day=1)
    if expiration_date < recovery_month_start:
        return BUSINESS_RESULT_REACTIVATION

    return BUSINESS_RESULT_RENEWAL


def _apply_business_counts(
    payload: dict[str, Any],
    *,
    renewals: int,
    reactivations: int,
    unclassified: int,
) -> None:
    recovered = int(payload.get("reactivated") or 0)
    payload["recovered"] = recovered
    payload["renewals"] = int(renewals)
    payload["reactivations"] = int(reactivations)
    payload["unclassified_recovered"] = int(unclassified)


def enrich_outcome_summary_with_business_results(
    result: dict[str, Any],
    *,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    selected_sucursal_keys: Iterable[str] | None = None,
    session: Any | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    campaign_rows = result.get("campaigns") or []
    campaign_ids = {
        int(row["campaign_id"])
        for row in campaign_rows
        if row.get("campaign_id") is not None
    }

    selected = (
        {
            key
            for key in (
                normalize_socios_vencidos_branch_key(value)
                for value in selected_sucursal_keys
            )
            if key is not None
        }
        if selected_sucursal_keys is not None
        else None
    )
    allowed = set(allowed_sucursal_keys) if allowed_sucursal_keys is not None else None

    counts_by_campaign: dict[int, dict[str, int]] = defaultdict(
        lambda: {
            BUSINESS_RESULT_RENEWAL: 0,
            BUSINESS_RESULT_REACTIVATION: 0,
            "UNCLASSIFIED": 0,
        }
    )

    if campaign_ids:
        rows = (
            active_session.query(
                MarketingReactivationCampaignRecipientORM,
                MarketingReactivationCampaignRecipientOutcomeORM,
            )
            .join(
                MarketingReactivationCampaignRecipientOutcomeORM,
                MarketingReactivationCampaignRecipientOutcomeORM.campaign_recipient_id
                == MarketingReactivationCampaignRecipientORM.id,
            )
            .filter(
                MarketingReactivationCampaignRecipientORM.campaign_id.in_(campaign_ids),
                MarketingReactivationCampaignRecipientOutcomeORM.status == "REACTIVATED",
            )
            .all()
        )

        for recipient, outcome in rows:
            branch_key = normalize_socios_vencidos_branch_key(recipient.sucursal)
            if branch_key is None:
                continue
            if allowed is not None and branch_key not in allowed:
                continue
            if selected is not None and branch_key not in selected:
                continue

            business_result = classify_recovery_business_result(
                expiration_date=recipient.fecha_vencimiento_date,
                recovered_at_local=outcome.reactivated_at_local,
            )
            bucket = business_result or "UNCLASSIFIED"
            counts_by_campaign[int(recipient.campaign_id)][bucket] += 1

    total_renewals = 0
    total_reactivations = 0
    total_unclassified = 0

    for campaign_row in campaign_rows:
        campaign_id = int(campaign_row["campaign_id"])
        counts = counts_by_campaign[campaign_id]
        renewals = counts[BUSINESS_RESULT_RENEWAL]
        reactivations = counts[BUSINESS_RESULT_REACTIVATION]
        unclassified = counts["UNCLASSIFIED"]
        _apply_business_counts(
            campaign_row,
            renewals=renewals,
            reactivations=reactivations,
            unclassified=unclassified,
        )
        total_renewals += renewals
        total_reactivations += reactivations
        total_unclassified += unclassified

    summary = result.setdefault("summary", {})
    _apply_business_counts(
        summary,
        renewals=total_renewals,
        reactivations=total_reactivations,
        unclassified=total_unclassified,
    )
    return result


def enrich_campaign_outcome_detail_with_business_results(
    result: dict[str, Any],
) -> dict[str, Any]:
    renewals = 0
    reactivations = 0
    unclassified = 0

    for row in result.get("rows") or []:
        business_result = None
        if row.get("status") == "REACTIVATED":
            expiration_date = None
            expiration_raw = row.get("fecha_vencimiento")
            recovered_at = None
            recovered_raw = row.get("reactivated_at_local")

            if expiration_raw:
                try:
                    expiration_date = date.fromisoformat(str(expiration_raw)[:10])
                except ValueError:
                    expiration_date = None
            if recovered_raw:
                try:
                    recovered_at = datetime.fromisoformat(str(recovered_raw))
                except ValueError:
                    recovered_at = None

            business_result = classify_recovery_business_result(
                expiration_date=expiration_date,
                recovered_at_local=recovered_at,
            )
            if business_result == BUSINESS_RESULT_RENEWAL:
                renewals += 1
            elif business_result == BUSINESS_RESULT_REACTIVATION:
                reactivations += 1
            else:
                unclassified += 1

        row["business_result"] = business_result

    summary = result.setdefault("summary", {})
    _apply_business_counts(
        summary,
        renewals=renewals,
        reactivations=reactivations,
        unclassified=unclassified,
    )
    return result
