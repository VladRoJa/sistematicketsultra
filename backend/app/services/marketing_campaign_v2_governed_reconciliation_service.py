"""Issue #856 D3b — manual, atomic governed-execution reconciliation.

Two explicit human actions:
1. Escalate stale IN_FLIGHT into REVIEW_REQUIRED without claiming an outcome.
2. Record externally confirmed provider outcome, leaving execution blocked.
No provider calls, retries, automatic HELD releases or quota renewal.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2DispatchApprovalORM,
    MarketingCampaignV2GovernedExecutionORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2GovernedReconciliationEventORM,
)
from app.services.marketing_campaign_v2_dispatch_approval_service import _database_date
from app.services.marketing_campaign_v2_governed_dispatch_service import manifest_digest

STALE_MIN_AGE = timedelta(minutes=10)
RESOLUTION_FOUND = "PROVIDER_CAMPAIGN_FOUND"
RESOLUTION_NOT_CREATED = "NOT_CREATED_CONFIRMED"


class GovernedReconciliationConflict(RuntimeError):
    pass


class GovernedReconciliationValidation(ValueError):
    pass


def _required_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise GovernedReconciliationValidation(label + " inválido.")
    return value


def _required_reference(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise GovernedReconciliationValidation(label + " obligatorio (longitud válida).")
    return value.strip()


def _utc(now: datetime | None) -> datetime:
    value = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise GovernedReconciliationValidation("Fecha con zona horaria requerida.")
    return value.astimezone(timezone.utc)


def _lock_pair(*, campaign_id: int, execution_id: int, child_id: int, session: Any):
    if session.get_bind().dialect.name != "postgresql":
        raise GovernedReconciliationConflict("Se requiere PostgreSQL real.")
    # Resolve IDs without locking; then acquire locks in the same
    # campaign -> approval -> execution -> child order as D2c.
    candidate = session.get(MarketingCampaignV2GovernedExecutionORM, execution_id)
    if candidate is None:
        raise GovernedReconciliationConflict("Ejecución no encontrada.")
    approval_id = int(candidate.approval_id)
    preliminary_approval = session.get(MarketingCampaignV2DispatchApprovalORM, approval_id)
    if preliminary_approval is None:
        raise GovernedReconciliationConflict("Aprobación no encontrada.")
    actual_campaign_id = int(preliminary_approval.campaign_v2_id)
    if actual_campaign_id != campaign_id:
        raise GovernedReconciliationConflict("Campaña de ruta y ejecución no coinciden.")

    campaign = session.query(MarketingCampaignV2ORM).filter(
        MarketingCampaignV2ORM.id == campaign_id,
    ).with_for_update().one_or_none()
    approval = session.query(MarketingCampaignV2DispatchApprovalORM).filter(
        MarketingCampaignV2DispatchApprovalORM.id == approval_id,
        MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == campaign_id,
    ).with_for_update().one_or_none()
    execution = session.query(MarketingCampaignV2GovernedExecutionORM).filter(
        MarketingCampaignV2GovernedExecutionORM.id == execution_id,
        MarketingCampaignV2GovernedExecutionORM.approval_id == approval_id,
    ).with_for_update().one_or_none()
    child = session.query(MarketingCampaignV2ProviderCampaignORM).filter(
        MarketingCampaignV2ProviderCampaignORM.id == child_id,
        MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == campaign_id,
    ).with_for_update().one_or_none()
    if (campaign is None or approval is None or execution is None or child is None or
            int(execution.last_child_id or 0) != child_id or
            manifest_digest(approval.manifest_json) != execution.manifest_digest):
        raise GovernedReconciliationConflict("Identidad de ejecución/child incongruente.")
    # No longer rely on a timestamp captured before waiting for row locks.
    return campaign, approval, execution, child


def _append_event(*, session: Any, execution: Any, child: Any,
                  event_kind: str, actor_user_id: int, source_reference: str,
                  evidence_note: str, timestamp: datetime,
                  previous_child_status: str, previous_execution_status: str,
                  provider_campaign_id: str | None = None,
                  details: dict | None = None):
    session.add(MarketingCampaignV2GovernedReconciliationEventORM(
        execution_id=execution.id, child_id=child.id,
        event_kind=event_kind, source_reference=source_reference,
        evidence_note=evidence_note, provider_campaign_id=provider_campaign_id,
        previous_child_status=previous_child_status,
        next_child_status=child.status,
        previous_execution_status=previous_execution_status,
        next_execution_status=execution.status,
        actor_user_id=actor_user_id, recorded_at=timestamp,
        evidence_json=details or {},
    ))


def _commit(session: Any):
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise GovernedReconciliationConflict(
            "Evento de reconciliación duplicado o identidad externa repetida."
        ) from exc
    except SQLAlchemyError:
        session.rollback()
        raise


def escalate_stale_governed_claim(
    *, campaign_id: int, execution_id: int, child_id: int, expected_manifest_digest: str,
    source_reference: str, evidence_note: str, actor_user_id: int,
    session: Any | None = None, now: datetime | None = None,
) -> dict:
    campaign_id = _required_int(campaign_id, "campaign_id")
    execution_id = _required_int(execution_id, "execution_id")
    child_id = _required_int(child_id, "child_id")
    actor = _required_int(actor_user_id, "actor_user_id")
    digest = _required_reference(expected_manifest_digest, "manifest_digest", 64)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise GovernedReconciliationValidation("Digest SHA256 requerido.")
    reference = _required_reference(source_reference, "source_reference", 255)
    note = _required_reference(evidence_note, "evidence_note", 2000)
    session = session if session is not None else db.session
    try:
        _, _, execution, child = _lock_pair(
            campaign_id=campaign_id, execution_id=execution_id,
            child_id=child_id, session=session,
        )
        timestamp = _utc(now) if now is not None else _utc(None)
        if execution.manifest_digest != digest:
            raise GovernedReconciliationConflict("Fingerprint cambió.")
        if (execution.status != "IN_FLIGHT" or
                child.status not in {"SUBMITTING", "RECONCILIATION_REQUIRED", "SUBMITTED"}):
            raise GovernedReconciliationConflict("No hay reclamo IN_FLIGHT elegible.")
        if timestamp - _database_date(execution.updated_at) < STALE_MIN_AGE:
            raise GovernedReconciliationConflict(
                "Reclamo aún no es elegible para revisión manual."
            )
        previous_child, previous_exec = str(child.status), str(execution.status)
        # A crash after child outcome persisted may already leave SUBMITTED;
        # do not overwrite that known acceptance.
        if child.status == "SUBMITTING":
            child.status = "RECONCILIATION_REQUIRED"
            child.error_code = "GOVERNED_UNCERTAIN_OUTCOME"
            child.updated_at = timestamp
        execution.status = "REVIEW_REQUIRED"
        execution.updated_at = timestamp
        _append_event(
            session=session, execution=execution, child=child,
            event_kind="STALE_CLAIM_REVIEW", actor_user_id=actor,
            source_reference=reference, evidence_note=note, timestamp=timestamp,
            previous_child_status=previous_child, previous_execution_status=previous_exec,
            details={"provider_outcome": "UNKNOWN", "auto_retry": False,
                     "previous_child_status": previous_child},
        )
        _commit(session)
        return {
            "execution_id": execution_id, "child_id": child_id,
            "execution_status": execution.status, "child_status": child.status,
            "provider_outcome": "UNKNOWN", "send_authorized": False,
            "may_auto_retry": False,
        }
    except (GovernedReconciliationConflict, SQLAlchemyError):
        session.rollback()
        raise


def record_governed_provider_resolution(
    *, campaign_id: int, execution_id: int, child_id: int, expected_manifest_digest: str,
    resolution: str, source_reference: str, evidence_note: str,
    actor_user_id: int, provider_campaign_id: str | None = None,
    session: Any | None = None, now: datetime | None = None,
) -> dict:
    campaign_id = _required_int(campaign_id, "campaign_id")
    execution_id = _required_int(execution_id, "execution_id")
    child_id = _required_int(child_id, "child_id")
    actor = _required_int(actor_user_id, "actor_user_id")
    digest = _required_reference(expected_manifest_digest, "manifest_digest", 64)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise GovernedReconciliationValidation("Digest SHA256 requerido.")
    if resolution not in {RESOLUTION_FOUND, RESOLUTION_NOT_CREATED}:
        raise GovernedReconciliationValidation("Resolución fuera de catálogo.")
    reference = _required_reference(source_reference, "source_reference", 255)
    note = _required_reference(evidence_note, "evidence_note", 2000)
    provider_id = None
    if resolution == RESOLUTION_FOUND:
        provider_id = _required_reference(provider_campaign_id, "provider_campaign_id", 255)
    elif provider_campaign_id is not None:
        raise GovernedReconciliationValidation(
            "No se acepta provider_campaign_id en NOT_CREATED_CONFIRMED."
        )
    session = session if session is not None else db.session
    try:
        _, _, execution, child = _lock_pair(
            campaign_id=campaign_id, execution_id=execution_id,
            child_id=child_id, session=session,
        )
        timestamp = _utc(now) if now is not None else _utc(None)
        if execution.manifest_digest != digest:
            raise GovernedReconciliationConflict("Fingerprint cambió.")
        if (execution.status != "REVIEW_REQUIRED" or
                child.status != "RECONCILIATION_REQUIRED" or
                child.reconciliation_resolution is not None or
                child.provider_campaign_id is not None):
            raise GovernedReconciliationConflict("Ejecución no permite resolver ese child.")
        if resolution == RESOLUTION_FOUND:
            duplicate = session.query(MarketingCampaignV2ProviderCampaignORM.id).filter(
                MarketingCampaignV2ProviderCampaignORM.provider == child.provider,
                MarketingCampaignV2ProviderCampaignORM.provider_campaign_id == provider_id,
                MarketingCampaignV2ProviderCampaignORM.id != child.id,
            ).first()
            if duplicate is not None:
                raise GovernedReconciliationConflict(
                    "Identidad del proveedor ya pertenece a otro child."
                )
        previous_child, previous_exec = child.status, execution.status
        if resolution == RESOLUTION_FOUND:
            child.status = "SUBMITTED"
            child.provider_campaign_id = provider_id
            # submitted_at is the time the verified outcome was recorded,
            # not claimed to be Meta's actual delivery/acceptance timestamp.
            child.submitted_at = timestamp
            child.error_code = None
        else:
            # No retry eligibility or automatic continuation is granted.
            child.status = "PROVIDER_ERROR"
            child.error_code = "GOVERNED_NOT_CREATED_CONFIRMED"
            child.retry_next_allowed_at = None
        child.support_ref = None
        child.reconciliation_resolution = resolution
        child.reconciliation_note = note
        child.reconciled_by_user_id = actor
        child.reconciled_at = timestamp
        child.reconciliation_snapshot_json = {
            "schema_version": 2, "source": "MANUAL_OPERATOR",
            "source_reference": reference, "resolution": resolution,
            "outcome_recorded_at": timestamp.isoformat(),
            "provider_actual_acceptance_time": "UNVERIFIED",
            "auto_retry": False,
        }
        child.updated_at = timestamp
        _append_event(
            session=session, execution=execution, child=child,
            event_kind=resolution, actor_user_id=actor,
            source_reference=reference, evidence_note=note, timestamp=timestamp,
            previous_child_status=previous_child, previous_execution_status=previous_exec,
            provider_campaign_id=provider_id,
            details=deepcopy(child.reconciliation_snapshot_json),
        )
        _commit(session)
        return {
            "execution_id": execution_id, "child_id": child_id,
            "execution_status": execution.status, "child_status": child.status,
            "resolution": resolution, "provider_campaign_id": provider_id,
            "send_authorized": False, "may_auto_retry": False,
        }
    except (GovernedReconciliationConflict, SQLAlchemyError):
        session.rollback()
        raise
