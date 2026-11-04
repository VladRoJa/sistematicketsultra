"""Audited, fail-closed continuation for the known Campaign #41 provider rejection.

Does not weaken the standard governed or legacy dispatch gates. The original
REVIEW_REQUIRED execution and its failed child remain unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from flask import current_app, has_app_context
from sqlalchemy import text

from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2DispatchApprovalORM as Approval,
    MarketingCampaignV2GovernedExecutionORM as Execution,
    MarketingCampaignV2ProviderCampaignORM as Child,
)
from app.models.marketing_campaign_v2_background_job import (
    MarketingCampaignV2BackgroundJobORM as BackgroundJob,
)
from app.models.user_model import UserORM
from app.services.marketing_access import resolve_marketing_access
from app.services.marketing_campaign_v2_contact_gate_service import (
    acquire_campaign_v2_contact_gate, verify_outbound_contact_admission,
)
from app.services.marketing_campaign_v2_dispatch_approval_service import _assess_scopes
from app.services.marketing_campaign_v2_governed_dispatch_service import manifest_digest
from app.services.marketing_campaign_v2_manifest_service import (
    _assert_manifest, budget_for_existing_approval,
)
from app.services.marketing_campaign_v2_preflight_service import (
    build_campaign_v2_preflight, build_provider_campaign_idempotency_key,
)
from app.services.marketing_campaign_v2_submit_service import (
    _persist_provider_failure, _persist_provider_success,
    build_campaign_v2_provider_dispatch_batch,
    serialize_campaign_v2_provider_request_snapshot,
)
from app.services.marketing_campaign_v2_provider import (
    CampaignProviderDeterministicError, CampaignProviderAmbiguousError,
    CampaignProviderConfigurationError,
)

logger = logging.getLogger(__name__)
CAMPAIGN_ID = 41
FAILED_ID = 255
FAILED_ERROR = "TEMPLATE_NOT_FOUND"
FAILED_REF = "bc-mw1c1why-phq041"
SECOND_FAILED_ID = 261
SECOND_FAILED_ERROR = "TEMPLATE_NOT_FOUND"
SECOND_FAILED_REF = "bc-mw2eakos-r7lxsj"


class GovernedRecoveryBlocked(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise GovernedRecoveryBlocked(message)


def verify_suffix(
    *, rows: list, accepted_original: tuple[tuple[int, str], ...],
    ready_ids: tuple[int, ...], completed: tuple[tuple[int, str], ...],
    next_id: int, actor_user_id: int,
) -> None:
    """Prove immutable original prefix, rejected #255 and ordered READY suffix."""
    by_id = {int(row.id): row for row in rows}
    require(len(by_id) == len(rows), "Children duplicados.")
    require(next_id in ready_ids and len(set(ready_ids)) == len(ready_ids),
            "Sufijo READY inválido.")
    require(len(completed) == ready_ids.index(next_id)
            and tuple(i for i, _ in completed) == ready_ids[:len(completed)],
            "La continuación tiene envíos fuera de orden.")
    for child_id, provider_id in accepted_original:
        row = by_id.get(child_id)
        require(row is not None and row.status == "SUBMITTED"
                and row.provider_campaign_id == provider_id
                and row.submitted_at is not None,
                "Un lote aceptado previamente cambió.")
    failed = by_id.get(FAILED_ID)
    require(failed is not None and failed.status == "PROVIDER_ERROR"
            and failed.error_code == FAILED_ERROR
            and failed.support_ref == FAILED_REF
            and failed.provider_campaign_id is None
            and failed.submitted_at is None,
            "El lote omitido #255 cambió.")
    second = by_id.get(SECOND_FAILED_ID)
    require(second is not None and second.status == "PROVIDER_ERROR"
            and second.error_code == SECOND_FAILED_ERROR
            and second.support_ref == SECOND_FAILED_REF
            and second.provider_campaign_id is None
            and second.submitted_at is None,
            "Sendero Culiacán #261 ya no conserva el rechazo original.")
    require(all(i > SECOND_FAILED_ID for i in ready_ids),
            "El nuevo sufijo incluye lotes aceptados o rechazados.")
    for position, child_id in enumerate(ready_ids):
        row = by_id.get(child_id)
        require(row is not None, "Falta un lote del manifiesto.")
        if position < len(completed):
            provider_id = completed[position][1]
            require(row.status == "SUBMITTED"
                    and row.provider_campaign_id == provider_id
                    and row.submitted_at is not None
                    and row.submitted_by_user_id == actor_user_id,
                    "El prefijo continuado cambió.")
        else:
            require(row.status == "READY"
                    and row.provider_campaign_id is None
                    and row.submit_started_at is None
                    and row.submitted_at is None,
                    "Un lote pendiente fue intentado o modificado.")


def claim_next(
    *, review: Any, child: Any, actor_user_id: int,
    completed: tuple[tuple[int, str], ...], session: Any,
) -> Any:
    """Commit READY->SUBMITTING only after governance and capacity checks."""
    require(
        has_app_context() and
        current_app.config.get("CAMPAIGN_V2_PROVIDER_SEND_ENABLED") is True and
        current_app.config.get("CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED") is True,
        "La recuperación gobernada no está habilitada en este proceso.",
    )
    require(session.get_bind().dialect.name == "postgresql", "Se requiere PostgreSQL.")
    try:
        # Same shared lock hierarchy as the governed dispatcher.
        acquire_campaign_v2_contact_gate(session)
        campaign = session.query(Campaign).filter(
            Campaign.id == CAMPAIGN_ID).with_for_update().one_or_none()
        approval = session.query(Approval).filter(
            Approval.id == review.approval_id,
            Approval.campaign_v2_id == CAMPAIGN_ID).with_for_update().one_or_none()
        execution = session.query(Execution).filter(
            Execution.id == review.execution_id,
            Execution.approval_id == review.approval_id).with_for_update().one_or_none()
        jobs = session.query(BackgroundJob).filter(
            BackgroundJob.campaign_v2_id == CAMPAIGN_ID
        ).with_for_update().all()
        rows = session.query(Child).filter(
            Child.campaign_v2_id == CAMPAIGN_ID
        ).order_by(Child.id).with_for_update().all()
        require(campaign is not None and approval is not None
                and execution is not None
                and execution.status == "REVIEW_REQUIRED"
                and execution.last_child_id == FAILED_ID
                and manifest_digest(approval.manifest_json) == review.digest
                and execution.manifest_digest == review.digest
                and approval.dispatch_fingerprint == review.plan_review.plan.dispatch_fingerprint,
                "La aprobación o ejecución original cambió.")
        require(len(jobs) <= 1, "Trabajos de background contradictorios.")
        if jobs:
            job = jobs[0]
            require(job.status == "REVIEW_REQUIRED"
                    and job.approval_id == approval.id
                    and job.execution_id == execution.id
                    and job.manifest_digest == review.digest
                    and job.current_child_id == FAILED_ID
                    and job.worker_lease_until is None,
                    "Mandato background activo o distinto.")
        newest = session.query(Approval.id).filter(
            Approval.campaign_v2_id == CAMPAIGN_ID
        ).order_by(Approval.revision_no.desc()).first()
        require(newest is not None and newest[0] == review.approval_id,
                "Existe una aprobación posterior.")
        actor = session.get(UserORM, actor_user_id)
        require(actor is not None, "Operador inexistente.")
        access = resolve_marketing_access(actor)
        require(access.is_global and access.can_send_campaigns
                and access.can_manage_dispatch_config,
                "Se perdió autorización global de despacho.")

        ready_ids = tuple(int(x.child_id) for x in review.plan_review.ready_children)
        verify_suffix(
            rows=rows, accepted_original=review.accepted_original,
            ready_ids=ready_ids, completed=completed,
            next_id=int(child.child_id), actor_user_id=actor_user_id,
        )
        now = datetime.now(timezone.utc)
        plan = build_campaign_v2_preflight(
            campaign_id=CAMPAIGN_ID, template_id=int(approval.template_id),
            allowed_sucursal_keys=None, session=session, now=now,
        )
        budget = budget_for_existing_approval(
            plan=plan, approval=approval, session=session, now=now,
        )
        manifest = _assert_manifest(plan, budget, approval)
        require(plan.ready and plan.mode == "IMMEDIATE"
                and plan.provider == "IVENTAS"
                and plan.dispatch_fingerprint == review.plan_review.plan.dispatch_fingerprint,
                "El preflight aprobado cambió.")
        by_branch = {row.sucursal_canon: row for row in rows}
        require(len(rows) == len(by_branch) == len(plan.batches),
                "El conjunto de lotes del manifiesto cambió.")
        target = None
        for batch in plan.batches:
            row = by_branch.get(batch.sucursal_canon)
            outbound = build_campaign_v2_provider_dispatch_batch(plan=plan, batch=batch)
            require(row is not None
                    and row.provider == plan.provider
                    and row.sucursal_id == batch.sucursal_id
                    and row.channel_binding_id == batch.channel_binding_id
                    and row.provider_channel_id == batch.provider_channel_id
                    and row.template_id == batch.template_id
                    and row.template_name == batch.template_name
                    and row.dispatch_fingerprint == plan.dispatch_fingerprint
                    and int(row.recipient_count) == len(batch.recipients)
                    and row.idempotency_key == build_provider_campaign_idempotency_key(
                        campaign_v2_id=CAMPAIGN_ID, batch=batch,
                        dispatch_fingerprint=plan.dispatch_fingerprint)
                    and dict(row.request_snapshot_json or {}) ==
                    serialize_campaign_v2_provider_request_snapshot(outbound),
                    "Identidad o snapshot de lote cambiado.")
            if manifest[batch.sucursal_canon]["planned_status"] == "HELD":
                require(row.status == "HELD" and row.submit_started_at is None
                        and row.provider_campaign_id is None,
                        "Un lote HELD cambió.")
            if int(row.id) == int(child.child_id):
                require(manifest[batch.sucursal_canon]["planned_status"] == "READY"
                        and batch.sucursal_canon == child.batch.sucursal_canon,
                        "El siguiente lote no está autorizado.")
                target = (batch, row, outbound)
        require(target is not None, "El lote pendiente no está en el plan.")
        batch, row, outbound = target

        # Reassess capacity after acquiring identical quota advisory locks.
        scoped = replace(plan, batches=(batch,))
        _, scopes, evidence, _ = _assess_scopes(
            scoped, session=session, timestamp=now,
            ignore_campaign_id=None, basis_preference=review.quota_basis,
        )
        for kind, key in sorted(scopes):
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
                {"scope": "mkt_v2_quota:" + kind + ":" + key},
            )
        claim_time = datetime.now(timezone.utc)
        _, current_scopes, current_evidence, _ = _assess_scopes(
            scoped, session=session, timestamp=claim_time,
            ignore_campaign_id=None, basis_preference=review.quota_basis,
        )
        require(scopes == current_scopes and evidence == current_evidence,
                "Cambió la capacidad o su evidencia durante el bloqueo.")
        verify_outbound_contact_admission(child=row, session=session)
        row.status = "SUBMITTING"
        row.submit_started_at = claim_time
        row.submitted_by_user_id = actor_user_id
        row.updated_at = claim_time
        row.error_code = None
        row.support_ref = None
        session.commit()
        logger.warning(
            "CAMPAIGN41_GOVERNED_RECOVERY_CLAIM campaign=41 skipped=255 child=%s "
            "approval=%s execution=%s actor=%s digest=%s",
            row.id, approval.id, execution.id, actor_user_id, review.digest,
        )
        return outbound
    except Exception:
        session.rollback()
        raise


def send_next(
    *, review: Any, child: Any, actor_user_id: int,
    completed: tuple[tuple[int, str], ...],
    provider: Any, session: Any,
) -> tuple[str, str, str | None]:
    """Exactly one provider HTTP after a committed governed claim.

    A crash after the claim leaves SUBMITTING for reconciliation, never replay.
    """
    dispatch = claim_next(
        review=review, child=child, actor_user_id=actor_user_id,
        completed=completed, session=session,
    )
    started = perf_counter()
    try:
        outcome = provider.create_campaign(dispatch)
    except CampaignProviderDeterministicError as exc:
        status, code, http, ref = (
            "PROVIDER_ERROR", exc.code, exc.http_status, exc.support_ref)
    except CampaignProviderAmbiguousError as exc:
        status, code, http, ref = (
            "RECONCILIATION_REQUIRED", exc.code, exc.http_status, exc.support_ref)
    except CampaignProviderConfigurationError:
        status, code, http, ref = (
            "PROVIDER_ERROR", "PROVIDER_CONFIGURATION", None, None)
    except Exception:
        status, code, http, ref = (
            "RECONCILIATION_REQUIRED", "UNEXPECTED_PROVIDER_RESULT", None, None)
    else:
        _persist_provider_success(
            row_id=child.child_id,
            provider_campaign_id=outcome.provider_campaign_id,
            deduplicated=outcome.deduplicated,
            response_metadata=outcome.response_metadata,
            accepted_status="SUBMITTED", actor_user_id=actor_user_id,
            session=session, now=datetime.now(timezone.utc),
        )
        logger.warning(
            "CAMPAIGN41_GOVERNED_RECOVERY_ACCEPTED child=%s provider_id=%s elapsed_ms=%.1f",
            child.child_id, outcome.provider_campaign_id,
            (perf_counter() - started) * 1000,
        )
        return child.batch.sucursal_canon, "SUBMITTED", outcome.provider_campaign_id

    _persist_provider_failure(
        row_id=child.child_id, status=status, error_code=code,
        support_ref=ref, http_status=http, actor_user_id=actor_user_id,
        session=session, now=datetime.now(timezone.utc),
    )
    logger.error(
        "CAMPAIGN41_GOVERNED_RECOVERY_STOP child=%s status=%s error=%s ref=%s elapsed_ms=%.1f",
        child.child_id, status, code, ref, (perf_counter() - started) * 1000,
    )
    return child.batch.sucursal_canon, status, code
