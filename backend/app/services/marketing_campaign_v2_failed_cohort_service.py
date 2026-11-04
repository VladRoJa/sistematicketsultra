"""Freeze a *new* campaign only from definitively rejected provider batches.

Uses the original frozen provider-request phones and recipient evidence, not a
fresh audience query. All operations are non-sending and PostgreSQL-serialized.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2ProviderCampaignORM as Child,
    MarketingCampaignV2RecipientORM as Recipient,
    MarketingCampaignV2RecipientEvidenceORM as Evidence,
    MarketingCampaignV2FailedRecoveryORM as FailedRecovery,
)
from app.services.marketing_campaign_v2_confirmed_rejection import (
    confirmed_rejected_child,
)
from app.services.marketing_campaign_v2_contact_gate_service import (
    acquire_campaign_v2_contact_gate,
)
from app.services.marketing_campaign_v2_dispatch_branch_service import (
    CampaignV2DispatchBranchResolver, resolve_frozen_recipient_branch,
)
from app.services.marketing_phone import normalize_phone

FAILED_RECOVERY_SOURCE = "PROVIDER_FAILED_DERIVED"
FAILED_RECOVERY_VERSION = "provider-failed-frozen-v1"


class FailedCohortConflict(RuntimeError):
    pass


class FailedCohortNotFound(LookupError):
    pass


class FailedCohortValidation(ValueError):
    pass


def _hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _copy_fields(row: Any, *, excluded: set[str]) -> dict:
    return {
        column.name: deepcopy(getattr(row, column.name))
        for column in row.__table__.columns
        if column.name not in excluded
    }


def _request_phones(child: Any) -> tuple[str, ...]:
    payload = child.request_snapshot_json
    leads = payload.get("leads") if isinstance(payload, dict) else None
    if (not isinstance(leads, list) or
            len(leads) != int(child.recipient_count) or not leads):
        raise FailedCohortConflict("El snapshot del lote está incompleto.")
    phones = []
    for lead in leads:
        if not isinstance(lead, dict):
            raise FailedCohortConflict("Un destinatario no tiene identidad verificable.")
        phone = normalize_phone(lead.get("phone"))
        if phone is None:
            raise FailedCohortConflict("Teléfono de provider no normalizable.")
        phones.append(phone)
    if len(set(phones)) != len(phones):
        raise FailedCohortConflict("El lote incluye teléfonos duplicados.")
    return tuple(sorted(phones))


def _evaluate(*, source_campaign_id: int, session: Any, lock: bool) -> dict:
    campaign_q = session.query(Campaign).filter(Campaign.id == source_campaign_id)
    original = (campaign_q.with_for_update() if lock else campaign_q).one_or_none()
    if original is None:
        raise FailedCohortNotFound("Campaña de origen inexistente.")
    if original.source == FAILED_RECOVERY_SOURCE:
        raise FailedCohortConflict("No se permite derivar una campaña de recuperación.")
    children_q = session.query(Child).filter(
        Child.campaign_v2_id == source_campaign_id,
    ).order_by(Child.id)
    children = (children_q.with_for_update() if lock else children_q).all()
    if not children:
        raise FailedCohortConflict("La campaña aún no tiene intentos de iVentas.")
    if any(child.status in {"READY", "SUBMITTING", "PREPARED"} for child in children):
        raise FailedCohortConflict("Primero finaliza o concilia los lotes sin resolver.")
    failed = [child for child in children if confirmed_rejected_child(child)]
    if not failed:
        raise FailedCohortConflict("No hay rechazos definitivos verificables.")
    if any(child.status == "PROVIDER_ERROR" and child not in failed
           for child in children):
        raise FailedCohortConflict("Hay rechazos sin evidencia definitiva; revisar.")
    all_source = session.query(Recipient).filter(
        Recipient.campaign_id == source_campaign_id,
    ).all()
    by_phone = {str(row.phone_mx10): row for row in all_source}
    if len(by_phone) != len(all_source):
        raise FailedCohortConflict("Destinatarios congelados duplicados.")
    selected = {}
    selected_by_child = {}
    resolver = CampaignV2DispatchBranchResolver(session=session)
    for child in failed:
        phones = _request_phones(child)
        members = []
        for phone in phones:
            row = by_phone.get(phone)
            if row is None or phone in selected:
                raise FailedCohortConflict("Destinatario fallido no corresponde a origen único.")
            branch = resolve_frozen_recipient_branch(
                row, resolver=resolver, session=session,
            )
            if (branch is None or branch.sucursal_canon != child.sucursal_canon or
                    branch.sucursal_id != child.sucursal_id):
                raise FailedCohortConflict("La sucursal comercial del destinatario cambió.")
            selected[phone] = row
            members.append(phone)
        selected_by_child[int(child.id)] = members
    # No contact in the new cohort may have reached or possibly reached iVentas
    # in another child of its original campaign.
    forbidden = {"SUBMITTED", "SCHEDULED", "RECONCILIATION_REQUIRED", "SUBMITTING"}
    for child in children:
        if child.status not in forbidden:
            continue
        if set(_request_phones(child)) & set(selected):
            raise FailedCohortConflict("Un destinatario fallido aparece en otro envío posible.")
    source_child_ids = [int(row.id) for row in failed]
    payload = [
        {
            "child_id": int(child.id),
            "branch": str(child.sucursal_canon),
            "channel": str(child.provider_channel_id),
            "template": str(child.template_name),
            "error": str(child.error_code),
            "support_ref": str(child.support_ref),
            "phones": selected_by_child[int(child.id)],
        } for child in failed
    ]
    fingerprint = _hash({
        "source_campaign_id": source_campaign_id,
        "version": FAILED_RECOVERY_VERSION,
        "batches": payload,
    })
    return {
        "original": original,
        "failed": failed,
        "recipients": tuple(selected[p] for p in sorted(selected)),
        "source_child_ids": source_child_ids,
        "fingerprint": fingerprint,
        "payload": payload,
        "recipient_count": len(selected),
    }


def preview_failed_cohort(*, source_campaign_id: int,
                          session: Any | None = None) -> dict:
    if type(source_campaign_id) is not int or source_campaign_id <= 0:
        raise FailedCohortValidation("source_campaign_id inválido.")
    active = session if session is not None else db.session
    review = _evaluate(source_campaign_id=source_campaign_id,
                       session=active, lock=False)
    return {
        "source_campaign_id": source_campaign_id,
        "source_child_ids": review["source_child_ids"],
        "candidate_fingerprint": review["fingerprint"],
        "recipient_count": review["recipient_count"],
        "branches": [
            {
                "child_id": item["child_id"], "sucursal_canon": item["branch"],
                "provider_channel_id": item["channel"], "template_name": item["template"],
                "recipient_count": len(item["phones"]), "error_code": item["error"],
                "support_ref": item["support_ref"],
            } for item in review["payload"]
        ],
        "template_provider_verification": "UNVERIFIED",
        "provider_requests": 0,
        "send_authorized": False,
    }


def freeze_failed_cohort(*, source_campaign_id: int,
                         expected_candidate_fingerprint: str,
                         expected_recipient_count: int,
                         actor_user_id: int, session: Any | None = None,
                         now: datetime | None = None) -> dict:
    if (type(source_campaign_id) is not int or source_campaign_id <= 0 or
            type(expected_recipient_count) is not int or expected_recipient_count <= 0 or
            type(actor_user_id) is not int or actor_user_id <= 0 or
            not isinstance(expected_candidate_fingerprint, str) or
            len(expected_candidate_fingerprint) != 64):
        raise FailedCohortValidation("Confirmación de origen, conteo o fingerprint inválida.")
    active = session if session is not None else db.session
    if active.get_bind().dialect.name != "postgresql":
        raise FailedCohortConflict("El congelamiento exige PostgreSQL.")
    timestamp = now or datetime.now(timezone.utc)
    try:
        acquire_campaign_v2_contact_gate(active)
        review = _evaluate(source_campaign_id=source_campaign_id,
                           session=active, lock=True)
        if (review["fingerprint"] != expected_candidate_fingerprint or
                review["recipient_count"] != expected_recipient_count):
            raise FailedCohortConflict("Cohorte/cantidad cambió; repetir vista previa.")
        existing = active.query(FailedRecovery).filter(
            FailedRecovery.source_campaign_id == source_campaign_id,
            FailedRecovery.failed_fingerprint == review["fingerprint"],
        ).with_for_update().one_or_none()
        if existing is not None:
            if (existing.recipient_count != expected_recipient_count or
                    existing.source_child_ids_json != review["source_child_ids"] or
                    active.get(Campaign, existing.derived_campaign_id) is None):
                raise FailedCohortConflict("Registro de recuperación existente inconsistente.")
            derived_id = int(existing.derived_campaign_id)
            active.rollback()
            return {
                "derived_campaign_id": derived_id, "source_campaign_id": source_campaign_id,
                "source_child_ids": review["source_child_ids"],
                "recipient_count": expected_recipient_count,
                "status": "FROZEN", "created": False,
                "provider_requests": 0, "send_authorized": False,
            }
        original = review["original"]
        definition = original.audience_definition_json or {}
        filters = deepcopy(definition.get("filters") or {})
        suffix = " · Recuperación fallidas"
        campaign_name = str(original.name or "Campaign V2")[:255-len(suffix)] + suffix
        derived = Campaign(
            name=campaign_name, purpose=original.purpose,
            source=FAILED_RECOVERY_SOURCE,
            audience_definition_json={
                "schema_version": 2,
                "filters": filters,
                "source_metadata": {
                    "source": FAILED_RECOVERY_SOURCE,
                    "source_campaign_id": source_campaign_id,
                    "source_child_ids": review["source_child_ids"],
                    "source_fingerprint": review["fingerprint"],
                },
                "preview": {
                    "fingerprint_version": FAILED_RECOVERY_VERSION,
                    "fingerprint": review["fingerprint"],
                    "summary": {"unique_recipient_count": expected_recipient_count},
                },
                "failed_recovery": {
                    "version": FAILED_RECOVERY_VERSION,
                    "source_campaign_id": source_campaign_id,
                    "source_child_ids": review["source_child_ids"],
                    "candidate_fingerprint": review["fingerprint"],
                    "recipient_count": expected_recipient_count,
                    "template_provider_verification": "UNVERIFIED",
                    "send_authorized": False,
                },
            },
            created_by_user_id=actor_user_id,
            frozen_at=timestamp, created_at=timestamp, updated_at=timestamp,
        )
        for source_row in review["recipients"]:
            copied = Recipient(
                **_copy_fields(source_row, excluded={"id", "campaign_id", "created_at"}),
                created_at=timestamp,
            )
            for evidence in sorted(source_row.evidence_rows,
                                   key=lambda row: row.evidence_order):
                copied.evidence_rows.append(Evidence(
                    **_copy_fields(evidence, excluded={"id", "recipient_id", "created_at"}),
                    created_at=timestamp,
                ))
            derived.recipients.append(copied)
        active.add(derived)
        active.flush()
        active.add(FailedRecovery(
            source_campaign_id=source_campaign_id,
            derived_campaign_id=int(derived.id),
            failed_fingerprint=review["fingerprint"],
            source_child_ids_json=review["source_child_ids"],
            recipient_count=expected_recipient_count,
            created_by_user_id=actor_user_id, created_at=timestamp,
        ))
        active.commit()
        return {
            "derived_campaign_id": int(derived.id),
            "source_campaign_id": source_campaign_id,
            "source_child_ids": review["source_child_ids"],
            "recipient_count": expected_recipient_count,
            "status": "FROZEN", "created": True,
            "provider_requests": 0, "send_authorized": False,
        }
    except (FailedCohortValidation, FailedCohortNotFound, FailedCohortConflict):
        active.rollback()
        raise
    except (IntegrityError, SQLAlchemyError) as exc:
        active.rollback()
        raise FailedCohortConflict("Conflicto persistiendo recuperación fallida.") from exc


def validate_failed_recovery_preflight(
    *, campaign_id: int, campaign: Any, frozen_recipients: list,
    sendable_recipients: list, session: Any,
) -> None:
    """Recheck immutable source provenance whenever authorization builds a plan.

    Does not claim that the template exists in iVentas. That is a separate
    provider-verification gate, deliberately not inferred from local JSON.
    """
    if campaign.source != FAILED_RECOVERY_SOURCE:
        return
    definition = campaign.audience_definition_json or {}
    recovery = definition.get("failed_recovery")
    if not isinstance(recovery, dict) or recovery.get("version") != FAILED_RECOVERY_VERSION:
        raise FailedCohortConflict("Campaña derivada sin contrato de recuperación.")
    source_id = recovery.get("source_campaign_id")
    if type(source_id) is not int or source_id <= 0:
        raise FailedCohortConflict("Origen de recuperación inválido.")
    link = session.query(FailedRecovery).filter(
        FailedRecovery.derived_campaign_id == campaign_id,
        FailedRecovery.source_campaign_id == source_id,
    ).one_or_none()
    if link is None:
        raise FailedCohortConflict("Origen de recuperación sin vínculo auditado.")
    original = _evaluate(source_campaign_id=source_id, session=session, lock=False)
    if (link.failed_fingerprint != original["fingerprint"] or
            recovery.get("candidate_fingerprint") != original["fingerprint"] or
            recovery.get("source_child_ids") != original["source_child_ids"] or
            link.source_child_ids_json != original["source_child_ids"] or
            link.recipient_count != original["recipient_count"] or
            recovery.get("recipient_count") != original["recipient_count"]):
        raise FailedCohortConflict("Cambió la evidencia definitiva de rechazo.")
    frozen_phones = {r.phone_mx10 for r in frozen_recipients}
    source_phones = {r.phone_mx10 for r in original["recipients"]}
    if (frozen_phones != source_phones or
            len(frozen_phones) != len(frozen_recipients) or
            len(sendable_recipients) != len(frozen_recipients)):
        raise FailedCohortConflict("La cohorte congelada perdió o ganó destinatarios.")
