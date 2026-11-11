"""One operator action for an already prepared cobranza campaign.

All quota, manifest, authorization, and provider dispatch rules remain in the
existing Campaign V2 services. This function only orchestrates them.
"""
from __future__ import annotations

import secrets
from typing import Any

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2DispatchApprovalORM,
    MarketingCampaignV2GovernedExecutionORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.models.marketing_campaign_v2_background_job import MarketingCampaignV2BackgroundJobORM
from app.services.marketing_campaign_v2_background_job_service import enqueue_background_job
from app.services.marketing_campaign_v2_dispatch_approval_service import approve_dispatch_reservation
from app.services.marketing_campaign_v2_governed_dispatch_service import (
    authorize_governed_dispatch, manifest_digest,
)
from app.services.marketing_campaign_v2_manifest_service import materialize_approved_manifest
from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
from app.services.marketing_campaign_v2_usd_pricing_service import estimate_automatic_usd_maximum
from app.warehouse.jobs.cobranza_iventas_preparation import CAMPAIGN_PREFIX, JOB_KEY


class CobranzaSendConflict(ValueError):
    pass


def is_prepared_cobranza_campaign(*, campaign: MarketingCampaignV2ORM) -> bool:
    metadata = (campaign.audience_definition_json or {}).get("source_metadata") or {}
    return (
        campaign.source == "EXCEL_IMPORT"
        and campaign.name.startswith(CAMPAIGN_PREFIX + " - ")
        and metadata.get("automation_job") == JOB_KEY
        and bool(metadata.get("business_date"))
        and type(metadata.get("template_id_at_freeze")) is int
    )


def enqueue_cobranza_send(
    *, campaign_id: int, actor_user_id: int,
    allowed_sucursal_keys: Any, session: Any | None = None,
) -> dict[str, Any]:
    """Reserve, materialize, authorize and queue once; never call provider here."""
    active = session if session is not None else db.session
    campaign = active.get(MarketingCampaignV2ORM, campaign_id)
    if campaign is None or not is_prepared_cobranza_campaign(campaign=campaign):
        raise CobranzaSendConflict("No es una campaña automática de cobranza.")
    metadata = campaign.audience_definition_json["source_metadata"]
    template_id = metadata["template_id_at_freeze"]
    plan = build_campaign_v2_preflight(
        campaign_id=campaign_id, template_id=template_id,
        allowed_sucursal_keys=allowed_sucursal_keys, session=active,
    )
    if not plan.ready or not plan.batches:
        raise CobranzaSendConflict("La cobranza tiene destinatarios o canales pendientes.")
    quote = estimate_automatic_usd_maximum(plan=plan)
    if quote["status"] != "COMPLETE":
        raise CobranzaSendConflict("La estimacion de cobranza no esta completa.")

    # Each existing service commits its own durable stage. A repeated request
    # continues an incomplete preparation but never creates a second approval,
    # execution or provider job for the same campaign.
    approval = active.query(MarketingCampaignV2DispatchApprovalORM).filter(
        MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == campaign_id,
    ).order_by(MarketingCampaignV2DispatchApprovalORM.revision_no.desc()).first()
    if approval is None:
        created = approve_dispatch_reservation(
            campaign_id=campaign_id, template_id=template_id,
            expected_dispatch_fingerprint=plan.dispatch_fingerprint,
            expected_quote_fingerprint=quote["quote_fingerprint"],
            expected_recipients=len(plan.sendable_phones),
            expected_total_mxn=None, pricing_currency="USD",
            actor_user_id=actor_user_id,
            allowed_sucursal_keys=allowed_sucursal_keys, session=active,
        )
        approval_id = created["approval_id"]
        digest = manifest_digest(created["manifest"])
    else:
        if approval.template_id != template_id or approval.dispatch_fingerprint != plan.dispatch_fingerprint:
            raise CobranzaSendConflict("La aprobacion anterior ya no coincide con el publico.")
        approval_id = int(approval.id)
        digest = manifest_digest(approval.manifest_json)

    execution = active.query(MarketingCampaignV2GovernedExecutionORM).filter(
        MarketingCampaignV2GovernedExecutionORM.approval_id == approval_id,
    ).one_or_none()
    if execution is None:
        materialize_approved_manifest(
            campaign_id=campaign_id, actor_user_id=actor_user_id,
            allowed_sucursal_keys=allowed_sucursal_keys, session=active,
        )
        authorized = authorize_governed_dispatch(
            campaign_id=campaign_id, approval_id=approval_id,
            expected_digest=digest, expected_ready_recipients=len(plan.sendable_phones),
            confirmed=True, actor_user_id=actor_user_id,
            allowed_sucursal_keys=allowed_sucursal_keys, session=active,
        )
        execution_id = authorized["execution_id"]
    else:
        if execution.manifest_digest != digest or execution.status != "AUTHORIZED":
            raise CobranzaSendConflict("La ejecucion requiere revision antes de continuar.")
        execution_id = int(execution.id)

    existing_job = active.query(MarketingCampaignV2BackgroundJobORM).filter(
        MarketingCampaignV2BackgroundJobORM.execution_id == execution_id,
    ).one_or_none()
    if existing_job is not None:
        return {
            "campaign_id": campaign_id,
            "status": existing_job.status,
            "job_id": int(existing_job.id),
            "recipient_count": len(plan.sendable_phones),
            "branch_count": len(plan.batches),
        }
    rows = active.query(MarketingCampaignV2ProviderCampaignORM).filter(
        MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == campaign_id,
        MarketingCampaignV2ProviderCampaignORM.status == "READY",
    ).all()
    by_branch = {row.sucursal_canon: int(row.id) for row in rows}
    pending = [by_branch[batch.sucursal_canon] for batch in plan.batches]
    snapshot, _ = enqueue_background_job(
        campaign_id=campaign_id,
        approval_id=approval_id,
        execution_id=execution_id,
        expected_manifest_digest=digest,
        expected_pending_child_ids=pending,
        request_key=secrets.token_hex(32),
        confirmation=f"ENVIAR PENDIENTES {len(pending)}",
        confirmed=True, actor_user_id=actor_user_id,
        allowed_sucursal_keys=allowed_sucursal_keys, session=active,
    )
    return {
        "campaign_id": campaign_id,
        "status": snapshot["status"],
        "job_id": snapshot["job_id"],
        "recipient_count": len(plan.sendable_phones),
        "branch_count": len(pending),
    }
