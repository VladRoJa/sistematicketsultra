"""Atomic freeze of a snapshot-selected Campaign V2 follow-up (NO dispatch).

The frozen cohort preserves the full original recipient/evidence and a
verifiable source snapshot + preview fingerprint.  No provider, approval,
child, execution, quota reservation or outbound preflight is created here.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any, Iterable

from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2RecipientORM as Recipient,
    MarketingCampaignV2RecipientEvidenceORM as Evidence,
    MarketingCampaignV2ProviderRecipientObservationORM as Observation,
)
from app.services.marketing_campaign_v2_blacklist_service import get_blacklisted_phones
from app.services.marketing_campaign_v2_contact_gate_service import acquire_campaign_v2_contact_gate
from app.services.marketing_campaign_v2_followup_preview_service import (
    FOLLOWUP_DERIVED_SOURCE,
    FOLLOWUP_PREVIEW_VERSION,
    FollowupPreviewConflictError,
    FollowupPreviewUnavailableError,
    FollowupPreviewValidationError,
    _normalize_statuses,
    _status,
    build_followup_preview,
)
from app.services.marketing_campaign_v2_query_service import (
    _positive_int,
    _load_visible_campaign_orm,
    _normalize_current_scope,
)
from app.services.marketing_phone import normalize_phone

FOLLOWUP_FREEZE_VERSION = "campaign-v2-followup-frozen-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class FollowupFreezeValidationError(ValueError):
    pass


class FollowupFreezeConflictError(RuntimeError):
    pass


def _require_postgresql(session: Any) -> None:
    if session.get_bind().dialect.name != "postgresql":
        raise FollowupFreezeConflictError("El congelamiento de seguimiento exige PostgreSQL.")


def _fields(row: Any, excluded: set[str]) -> dict:
    return {
        column.name: deepcopy(getattr(row, column.name))
        for column in row.__table__.columns
        if column.name not in excluded
    }


def freeze_followup_campaign(
    *,
    source_campaign_id: Any,
    name: Any,
    selected_statuses: Any,
    source_snapshot_id: Any,
    expected_preview_fingerprint: Any,
    expected_recipient_count: Any,
    actor_user_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict:
    source_id = _positive_int(source_campaign_id, field_name="source_campaign_id", maximum=None)
    snapshot_id = _positive_int(source_snapshot_id, field_name="source_snapshot_id", maximum=None)
    actor_id = _positive_int(actor_user_id, field_name="actor_user_id", maximum=None)
    # A zero count must be rejected rather than materializing an empty cohort.
    count = _positive_int(
        expected_recipient_count, field_name="expected_recipient_count", maximum=None,
    )
    statuses = _normalize_statuses(selected_statuses)
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 255:
        raise FollowupFreezeValidationError("El nombre de la nueva campaña debe tener entre 1 y 255 caracteres.")
    campaign_name = name.strip()
    if (not isinstance(expected_preview_fingerprint, str) or
            _SHA256.fullmatch(expected_preview_fingerprint) is None):
        raise FollowupFreezeValidationError("Se requiere el fingerprint SHA256 exacto del preview.")

    active = session if session is not None else db.session
    _require_postgresql(active)
    scope = _normalize_current_scope(allowed_sucursal_keys)
    timestamp = now if now is not None else datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise FollowupFreezeValidationError("La fecha de congelamiento debe contener zona horaria.")
    timestamp = timestamp.astimezone(timezone.utc)

    try:
        # Serializes freeze-to-freeze collisions; shared with send admission.
        acquire_campaign_v2_contact_gate(active)
        source = _load_visible_campaign_orm(
            campaign_id=source_id, scope=scope, session=active,
        )
        if source.source == FOLLOWUP_DERIVED_SOURCE:
            raise FollowupFreezeConflictError(
                "El seguimiento de una campaña derivada requiere autorización posterior."
            )
        definition = source.audience_definition_json
        if (not isinstance(definition, dict) or
                not isinstance(definition.get("filters"), dict) or
                "allowed_sucursal_keys" not in definition["filters"]):
            raise FollowupFreezeConflictError("Alcance congelado del origen no verificable.")

        try:
            fresh = build_followup_preview(
                source_campaign_id=source_id,
                selected_statuses=statuses,
                expected_snapshot_id=snapshot_id,
                allowed_sucursal_keys=scope,
                session=active,
            )
        except (FollowupPreviewConflictError, FollowupPreviewUnavailableError) as exc:
            raise FollowupFreezeConflictError(str(exc)) from exc
        if (fresh["candidate_count"] != count or
                fresh["preview_fingerprint"] != expected_preview_fingerprint or
                fresh["preview_fingerprint_version"] != FOLLOWUP_PREVIEW_VERSION):
            raise FollowupFreezeConflictError(
                "La audiencia cambió; vuelve a calcular la vista previa antes de congelar."
            )

        # Snapshots and frozen recipients come only from the database, never
        # from request-supplied identities or pages of the Angular table.
        all_rows = (
            active.query(Recipient)
            .options(selectinload(Recipient.evidence_rows))
            .filter(Recipient.campaign_id == source_id)
            .order_by(Recipient.id.asc())
            .all()
        )
        observations = (
            active.query(Observation)
            .filter(Observation.snapshot_id == snapshot_id)
            .all()
        )
        by_recipient: dict[int, Any] = {}
        for obs in observations:
            if obs.campaign_recipient_id is None:
                continue
            rid = int(obs.campaign_recipient_id)
            if rid in by_recipient:
                raise FollowupFreezeConflictError("Observaciones duplicadas en el corte original.")
            by_recipient[rid] = obs

        selected = []
        for row in all_rows:
            obs = by_recipient.get(int(row.id))
            if obs is not None and obs.normalized_phone != f"mx10:{row.phone_mx10}":
                raise FollowupFreezeConflictError("La observación no coincide con la identidad congelada.")
            bucket = _status(obs.outcome if obs else None, obs.delivery_bucket if obs else None)
            if bucket in statuses:
                selected.append(row)
        if len(selected) != count:
            raise FollowupFreezeConflictError("La selección ya no coincide con el preview aprobado.")

        phones = [str(r.phone_mx10) for r in selected]
        if (len(set(phones)) != len(phones) or any(
            normalize_phone(phone) != phone for phone in phones
        )):
            raise FollowupFreezeConflictError("La cohorte contiene teléfonos duplicados o inválidos.")
        if get_blacklisted_phones(phones=phones, session=active):
            raise FollowupFreezeConflictError(
                "Hay destinatarios en lista negra. No se congeló una cohorte parcial; requiere revisión."
            )

        # Prevent duplicate/overlapping derived cohorts (including a second
        # click with a different label) before insert, under the shared lock.
        existing_ids = [
            int(item[0]) for item in active.query(Campaign.id).filter(
                Campaign.source == FOLLOWUP_DERIVED_SOURCE
            ).all()
        ]
        if existing_ids:
            collision = (
                active.query(Recipient.id)
                .filter(
                    Recipient.campaign_id.in_(existing_ids),
                    Recipient.phone_mx10.in_(phones),
                )
                .first()
            )
            if collision is not None:
                raise FollowupFreezeConflictError(
                    "Los contactos ya pertenecen a otra cohorte de seguimiento congelada."
                )

        derived = Campaign(
            name=campaign_name,
            purpose=source.purpose,
            source=FOLLOWUP_DERIVED_SOURCE,
            audience_definition_json={
                "schema_version": 2,
                "filters": deepcopy(definition["filters"]),
                "source_metadata": {
                    "source": FOLLOWUP_DERIVED_SOURCE,
                    "source_campaign_id": source_id,
                    "source_snapshot_id": snapshot_id,
                },
                "preview": {
                    "fingerprint_version": FOLLOWUP_PREVIEW_VERSION,
                    "fingerprint": fresh["preview_fingerprint"],
                    "summary": {"unique_recipient_count": count},
                },
                "followup": {
                    "version": FOLLOWUP_FREEZE_VERSION,
                    "source_campaign_id": source_id,
                    "source_snapshot_id": snapshot_id,
                    "source_snapshot_fingerprint": fresh["source_snapshot_fingerprint"],
                    "source_snapshot_fetched_at": fresh["source_snapshot_fetched_at"],
                    "selected_statuses": list(statuses),
                    "match_mode": "ANY",
                    "source_preview_fingerprint": fresh["preview_fingerprint"],
                    "source_recipient_count": count,
                    "send_authorized": False,
                    "quota_reserved": False,
                    "dispatch_locked": True,
                },
            },
            created_by_user_id=actor_id,
            frozen_at=timestamp, created_at=timestamp, updated_at=timestamp,
        )
        for row in selected:
            new_recipient = Recipient(
                **_fields(row, {"id", "campaign_id", "created_at"}),
                created_at=timestamp,
            )
            for evidence in sorted(row.evidence_rows, key=lambda e: e.evidence_order):
                new_recipient.evidence_rows.append(Evidence(
                    **_fields(evidence, {"id", "recipient_id", "created_at"}),
                    created_at=timestamp,
                ))
            derived.recipients.append(new_recipient)
        active.add(derived)
        active.flush()
        result = {
            "derived_campaign_id": int(derived.id),
            "source_campaign_id": source_id,
            "source_snapshot_id": snapshot_id,
            "source_preview_fingerprint": fresh["preview_fingerprint"],
            "selected_statuses": list(statuses),
            "recipient_count": count,
            "status": "FROZEN_FOLLOWUP",
            "send_authorized": False,
            "quota_reserved": False,
            "dispatch_locked": True,
            "provider_calls": 0,
            "next_action": "FOLLOWUP_RECONTACT_POLICY_AND_FRESH_APPROVAL_REQUIRED",
        }
        active.commit()
        return result
    except (
        FollowupFreezeValidationError, FollowupFreezeConflictError,
        FollowupPreviewValidationError,
    ):
        active.rollback()
        raise
    except IntegrityError as exc:
        active.rollback()
        raise FollowupFreezeConflictError("Conflicto de integridad al congelar seguimiento.") from exc
    except SQLAlchemyError:
        active.rollback()
        raise
    except Exception:
        active.rollback()
        raise
