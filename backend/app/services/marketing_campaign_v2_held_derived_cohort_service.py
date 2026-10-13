"""D3c2 — atomically freeze a new campaign from one immutable HELD batch.

No Meta/iVentas client, no quotas reserved, no child materialization, no send.
D2a/D2b/D2c must be executed again on the NEW campaign. The original HELD
and approval remain immutable forever.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2RecipientORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2HeldReleaseIntentORM,
    MarketingCampaignV2DispatchApprovalORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.services.marketing_campaign_v2_held_release_intent_service import (
    HeldReleaseConflict, HeldReleaseNotFound, HeldReleaseValidation,
    _evaluate, _required_id, _utc,
)
from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
from app.services.marketing_campaign_v2_derived_contact_guard import (
    DERIVED_SOURCE, DerivedContactConflict, assert_no_prior_or_pending_contact,
)

DERIVED_PREVIEW_VERSION = "d3c2-held-frozen-v1"


def _copy_fields(row: Any, *, excluded: set[str]) -> dict:
    return {
        column.name: deepcopy(getattr(row, column.name))
        for column in row.__table__.columns
        if column.name not in excluded
    }


def _source_recipients(*, original_campaign_id: int, batch: Any,
                       session: Any) -> list:
    ids = [int(r.recipient_id) for r in batch.recipients]
    if not ids or len(set(ids)) != len(ids):
        raise HeldReleaseConflict("Identidad de destinatarios HELD duplicada o vacía.")
    rows = session.query(MarketingCampaignV2RecipientORM).filter(
        MarketingCampaignV2RecipientORM.campaign_id == original_campaign_id,
        MarketingCampaignV2RecipientORM.id.in_(ids),
    ).order_by(MarketingCampaignV2RecipientORM.id).all()
    by_id = {int(r.id): r for r in rows}
    if len(rows) != len(ids) or set(by_id) != set(ids):
        raise HeldReleaseConflict("Destinatarios originales HELD ya no coinciden.")
    for recipient in batch.recipients:
        if by_id[int(recipient.recipient_id)].phone_mx10 != recipient.phone_mx10:
            raise HeldReleaseConflict("La identidad telefónica de origen cambió.")
    return rows


def freeze_derived_held_cohort(
    *, source_campaign_id: int, source_child_id: int, intent_id: int,
    expected_candidate_fingerprint: Any, expected_recipient_count: int,
    actor_user_id: int, allowed_sucursal_keys: Any,
    session: Any | None = None, now: datetime | None = None,
) -> dict:
    source_campaign_id = _required_id(source_campaign_id, "source_campaign_id")
    source_child_id = _required_id(source_child_id, "source_child_id")
    intent_id = _required_id(intent_id, "intent_id")
    expected_recipient_count = _required_id(expected_recipient_count, "expected_recipient_count")
    actor_user_id = _required_id(actor_user_id, "actor_user_id")
    if (not isinstance(expected_candidate_fingerprint, str) or
            re.fullmatch(r"[0-9a-f]{64}", expected_candidate_fingerprint) is None):
        raise HeldReleaseValidation("Se necesita fingerprint SHA256 de D3c1.")
    active = session if session is not None else db.session
    if active.get_bind().dialect.name != "postgresql":
        raise HeldReleaseConflict("Congelamiento derivado exige PostgreSQL.")
    try:
        # Serialize other D3c2 derivations before checking global contact use.
        # Campaign locking follows the same campaign->approval->child order as D3c1.
        active.execute(text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"
        ), {"scope": "mkt_v2_d3c2:freeze_all_derived"})
        timestamp = _utc(now)
        fresh = _evaluate(
            campaign_id=source_campaign_id, child_id=source_child_id,
            allowed_sucursal_keys=allowed_sucursal_keys, session=active,
            timestamp=timestamp, lock=True, refresh_after_lock=now is None,
        )
        timestamp = _utc(now)
        if (fresh["candidate_fingerprint"] != expected_candidate_fingerprint or
                fresh["recipient_count"] != expected_recipient_count):
            raise HeldReleaseConflict("Cohorte/evidencia cambió; repetir preview e intención.")

        intent = active.query(MarketingCampaignV2HeldReleaseIntentORM).filter(
            MarketingCampaignV2HeldReleaseIntentORM.id == intent_id,
            MarketingCampaignV2HeldReleaseIntentORM.source_campaign_id == source_campaign_id,
            MarketingCampaignV2HeldReleaseIntentORM.source_child_id == source_child_id,
        ).with_for_update().one_or_none()
        if intent is None:
            raise HeldReleaseNotFound("Solicitud D3c1 inexistente o pertenece a otro child.")
        if (intent.status != "PENDING_FRESH_COHORT" or
                intent.derived_campaign_id is not None or
                intent.materialized_at is not None):
            raise HeldReleaseConflict("Solicitud ya materializada; no puede recrearse.")
        if (intent.candidate_fingerprint != fresh["candidate_fingerprint"] or
                int(intent.candidate_recipients) != fresh["recipient_count"] or
                intent.source_manifest_digest != fresh["source_manifest_digest"] or
                int(intent.source_approval_id) != fresh["source_approval_id"]):
            raise HeldReleaseConflict("Solicitud D3c1 cambió o está desactualizada.")

        original = active.get(MarketingCampaignV2ORM, source_campaign_id)
        if original is None:
            raise HeldReleaseNotFound("Campaña original no encontrada.")
        definition = original.audience_definition_json
        if (not isinstance(definition, dict) or
                not isinstance(definition.get("filters"), dict) or
                "allowed_sucursal_keys" not in definition["filters"]):
            raise HeldReleaseConflict("Scope congelado del origen no verificable.")

        approval = active.query(MarketingCampaignV2DispatchApprovalORM).filter(
            MarketingCampaignV2DispatchApprovalORM.id == int(intent.source_approval_id),
            MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == source_campaign_id,
        ).one_or_none()
        source_child = active.get(MarketingCampaignV2ProviderCampaignORM, source_child_id)
        if approval is None or source_child is None or source_child.status != "HELD":
            raise HeldReleaseConflict("Origen HELD o aprobación incompatible.")
        plan = build_campaign_v2_preflight(
            campaign_id=source_campaign_id,
            template_id=int(approval.template_id),
            allowed_sucursal_keys=allowed_sucursal_keys,
            session=active, now=timestamp,
        )
        batches = [b for b in plan.batches
                   if b.sucursal_canon == source_child.sucursal_canon]
        if len(batches) != 1 or len(batches[0].recipients) != expected_recipient_count:
            raise HeldReleaseConflict("Lote HELD no coincide con la fuente aprobada.")
        source_rows = _source_recipients(
            original_campaign_id=source_campaign_id,
            batch=batches[0], session=active,
        )
        # Recheck blacklist, other submitted/potential campaigns, and competing
        # derived cohorts just before inserting any destination rows.
        try:
            assert_no_prior_or_pending_contact(
                phones=(r.phone_mx10 for r in source_rows), session=active,
            )
        except DerivedContactConflict as exc:
            raise HeldReleaseConflict(str(exc)) from exc

        frozen_scope = deepcopy(definition["filters"])
        suffix = " · HELD " + str(source_child.sucursal_canon)
        base = str(original.name or "Campaign V2").strip()
        derived_name = base[:max(1, 255-len(suffix))] + suffix
        derived = MarketingCampaignV2ORM(
            name=derived_name,
            purpose=original.purpose,
            source=DERIVED_SOURCE,
            audience_definition_json={
                "schema_version": 2,
                "filters": frozen_scope,
                "source_metadata": {
                    "source": DERIVED_SOURCE,
                    "source_campaign_id": source_campaign_id,
                    "source_child_id": source_child_id,
                },
                "preview": {
                    "fingerprint_version": DERIVED_PREVIEW_VERSION,
                    "fingerprint": fresh["candidate_fingerprint"],
                    "summary": {"unique_recipient_count": len(source_rows)},
                },
                "derived_release": {
                    "version": DERIVED_PREVIEW_VERSION,
                    "intent_id": intent_id,
                    "source_campaign_id": source_campaign_id,
                    "source_child_id": source_child_id,
                    "source_approval_id": int(approval.id),
                    "source_manifest_digest": fresh["source_manifest_digest"],
                    "candidate_fingerprint": fresh["candidate_fingerprint"],
                    "source_recipient_count": len(source_rows),
                    "send_authorized": False,
                    "quota_reserved": False,
                },
            },
            created_by_user_id=actor_user_id,
            frozen_at=timestamp, created_at=timestamp, updated_at=timestamp,
        )
        for row in source_rows:
            copied = MarketingCampaignV2RecipientORM(
                **_copy_fields(row, excluded={"id", "campaign_id", "created_at"}),
                created_at=timestamp,
            )
            for evidence in sorted(row.evidence_rows, key=lambda e: e.evidence_order):
                copied.evidence_rows.append(MarketingCampaignV2RecipientEvidenceORM(
                    **_copy_fields(evidence, excluded={"id", "recipient_id", "created_at"}),
                    created_at=timestamp,
                ))
            derived.recipients.append(copied)

        active.add(derived)
        active.flush()
        # The intent link and every recipient/evidence row commit atomically.
        # No D2a approval, D2b children or D2c execution is created.
        intent.status = "FROZEN_DERIVED"
        intent.derived_campaign_id = int(derived.id)
        intent.materialized_at = timestamp
        active.commit()
        return {
            "derived_campaign_id": int(derived.id),
            "source_campaign_id": source_campaign_id,
            "source_child_id": source_child_id,
            "intent_id": intent_id,
            "recipient_count": len(source_rows),
            "status": "FROZEN_DERIVED",
            "send_authorized": False,
            "quota_reserved": False,
            "provider_calls": 0,
            "next_action": "FRESH_D2A_D2B_D2C_APPROVAL_REQUIRED",
        }
    except (HeldReleaseConflict, HeldReleaseNotFound, HeldReleaseValidation):
        active.rollback()
        raise
    except IntegrityError as exc:
        active.rollback()
        raise HeldReleaseConflict("Conflicto concurrente congelando cohorte derivada.") from exc
    except SQLAlchemyError:
        active.rollback()
        raise
