"""Append-only fresh authorization for an expired, entirely unattempted V2 dispatch.

Creates a NEW immutable approval, scope reservations and execution in one
transaction. Prior approvals/executions/HELD children remain untouched.
Never calls the provider or enables outbound execution.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2DispatchApprovalORM as Approval,
    MarketingCampaignV2GovernedExecutionORM as Execution,
    MarketingCampaignV2ProviderCampaignORM as Child,
)
from app.services.marketing_campaign_v2_contact_gate_service import (
    acquire_campaign_v2_contact_gate,
    CampaignV2ContactGateConflict,
)
from app.services.marketing_campaign_v2_dispatch_approval_service import (
    _assess_scopes, _ready_plan_and_holds, _hold_sources, _reserve_locked,
    _database_date, CampaignV2ApprovalConflictError,
)
from app.services.marketing_campaign_v2_manifest_service import (
    _assert_manifest, _validate_existing, budget_for_existing_approval,
)
from app.services.marketing_campaign_v2_governed_dispatch_service import manifest_digest
from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
from app.services.marketing_campaign_v2_submit_service import _load_campaign_rows
from app.services.marketing_campaign_v2_query_service import get_campaign_v2


class CampaignV2ReauthorizationError(ValueError):
    pass


def _utc(value: datetime | None) -> datetime:
    current = value if value is not None else datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.utcoffset() is None:
        raise CampaignV2ReauthorizationError("Fecha con zona horaria requerida.")
    return current.astimezone(timezone.utc)


def reauthorize_unattempted_dispatch(
    *, campaign_id: int, previous_approval_id: int, expected_manifest_digest: str,
    actor_user_id: int, allowed_sucursal_keys: Any,
    session: Any | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    if any(type(value) is not int or value <= 0
           for value in (campaign_id, previous_approval_id, actor_user_id)):
        raise CampaignV2ReauthorizationError("Identidades inválidas.")
    if (not isinstance(expected_manifest_digest, str) or
            re.fullmatch(r"[0-9a-f]{64}", expected_manifest_digest) is None):
        raise CampaignV2ReauthorizationError("Digest íntegro obligatorio.")

    active = session if session is not None else db.session
    try:
        if active.get_bind().dialect.name != "postgresql":
            raise CampaignV2ReauthorizationError("Se requiere PostgreSQL real.")
        # Same global gate and lock order as ordinary dispatch.
        acquire_campaign_v2_contact_gate(active)
        get_campaign_v2(
            campaign_id=campaign_id, allowed_sucursal_keys=allowed_sucursal_keys,
            session=active,
        )
        campaign = active.query(Campaign).filter(
            Campaign.id == campaign_id
        ).with_for_update().one_or_none()
        old = active.query(Approval).filter(
            Approval.campaign_v2_id == campaign_id,
        ).order_by(Approval.revision_no.desc()).with_for_update().first()
        timestamp = _utc(now)
        if campaign is None or campaign.frozen_at is None or old is None:
            raise CampaignV2ReauthorizationError("Campaña sin aprobación congelada.")
        if old.id != previous_approval_id or manifest_digest(old.manifest_json) != expected_manifest_digest:
            raise CampaignV2ReauthorizationError("La autorización cambió; consulta el estado nuevamente.")
        original_exec = active.query(Execution).filter(
            Execution.approval_id == old.id
        ).with_for_update().one_or_none()
        if (original_exec is None or original_exec.status != "AUTHORIZED" or
                original_exec.last_child_id is not None or
                _database_date(old.expires_at) > timestamp or
                _database_date(original_exec.expires_at) > timestamp):
            raise CampaignV2ReauthorizationError(
                "Solo puede reautorizarse una ejecución vencida sin intentos."
            )
        children = active.query(Child).filter(
            Child.campaign_v2_id == campaign_id,
        ).order_by(Child.id).with_for_update().all()
        if not children or not any(row.status == "READY" for row in children):
            raise CampaignV2ReauthorizationError("No existen lotes READY íntegros.")
        if any(
            row.status not in {"READY", "HELD"} or
            row.provider_campaign_id is not None or
            row.submit_started_at is not None or
            row.submitted_at is not None or
            row.submitted_by_user_id is not None or
            row.error_code is not None or row.support_ref is not None or
            bool(row.provider_response_json or {}) or
            bool(row.retry_history_json or {}) or
            int(row.retry_attempt_count or 0) != 0
            for row in children
        ):
            raise CampaignV2ReauthorizationError(
                "Existe evidencia de intento o resultado; reautorización prohibida."
            )

        def review(t: datetime):
            plan = build_campaign_v2_preflight(
                campaign_id=campaign_id, template_id=int(old.template_id),
                allowed_sucursal_keys=allowed_sucursal_keys, session=active, now=t,
            )
            budget = budget_for_existing_approval(plan=plan, approval=old, session=active, now=t)
            definitions = _assert_manifest(plan, budget, old)
            _validate_existing(plan, definitions, children)
            held = sorted(name for name, row in definitions.items()
                          if row["planned_status"] == "HELD")
            ready_plan, held_set = _ready_plan_and_holds(plan, held)
            held_sources = _hold_sources(
                held_set, {name: definitions[name]["hold_evidence"]["source_reference"]
                           for name in held}
            )
            held_evidence = {name: definitions[name]["hold_evidence"] for name in held}
            quota, scopes, evidence_ids, quota_rows = _assess_scopes(
                ready_plan, session=active, timestamp=t,
                ignore_campaign_id=campaign_id,
                basis_preference=(old.manifest_json or {}).get("basis"),
            )
            return plan, budget, held_set, held_sources, held_evidence, quota, scopes, evidence_ids, quota_rows

        plan, budget, held, sources, held_evidence, quota, scopes, _, _ = review(timestamp)
        scope_keys = set(scopes)
        for kind, key in sorted(scope_keys):
            active.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                {"scope": "mkt_v2_quota:" + kind + ":" + key},
            )
        # A quota lock can wait. Never reuse the time from before acquisition.
        timestamp = _utc(now)
        if _database_date(old.expires_at) > timestamp:
            raise CampaignV2ReauthorizationError("La autorización anterior sigue vigente.")
        plan2, budget2, held2, sources2, evidence2, quota2, scopes2, ids2, rows2 = review(timestamp)
        if (plan2.dispatch_fingerprint != plan.dispatch_fingerprint or
                budget2["quote_fingerprint"] != budget["quote_fingerprint"] or
                quota2.get("basis") != quota.get("basis") or
                set(scopes2) != scope_keys or
                held2 != held or sources2 != sources or evidence2 != held_evidence):
            raise CampaignV2ReauthorizationError(
                "Preflight, cupo o retenciones cambiaron durante revisión."
            )

        currency = (old.manifest_json or {}).get("pricing_currency", "MXN")
        amount = (budget2.get("maximum_estimated_usd") if currency == "USD"
                  else budget2.get("total_estimated_mxn"))
        if currency not in {"USD", "MXN"} or amount is None:
            raise CampaignV2ReauthorizationError("Cotización no disponible.")
        result = _reserve_locked(
            plan=plan2, budget=budget2,
            confirmation=(
                old.dispatch_fingerprint,
                old.manifest_json["quote_fingerprint"],
                int(old.recipient_count), Decimal(amount), actor_user_id,
            ),
            session=active, timestamp=timestamp,
            quantities=scopes2, evidence_ids=ids2, quota_rows=rows2,
            held_names=frozenset(held), held_sources=sources,
            held_evidence_override=held_evidence,
            capacity_basis=quota2.get("basis"),
            revision_no=int(old.revision_no) + 1, commit=False,
        )
        revised = active.get(Approval, result["approval_id"])
        digest = manifest_digest(revised.manifest_json)
        execution = Execution(
            approval_id=revised.id, manifest_digest=digest,
            confirmed_by_user_id=actor_user_id, confirmed_at=timestamp,
            expires_at=revised.expires_at, status="AUTHORIZED",
            updated_at=timestamp,
        )
        active.add(execution)
        active.flush()
        active.commit()
        return {
            "campaign_id": campaign_id,
            "previous_approval_id": old.id,
            "new_approval_id": revised.id,
            "approval_revision": revised.revision_no,
            "new_execution_id": execution.id,
            "manifest_digest": digest,
            "expires_at": _database_date(revised.expires_at).isoformat(),
            "ready_batches": result["ready_batches"],
            "held_batches": result["held_batches"],
            "provider_calls": 0,
            "send_authorized": False,
        }
    except (CampaignV2ContactGateConflict, CampaignV2ApprovalConflictError,
            CampaignV2ReauthorizationError) as exc:
        active.rollback()
        if isinstance(exc, CampaignV2ReauthorizationError):
            raise
        raise CampaignV2ReauthorizationError(str(exc)) from exc
    except (IntegrityError, SQLAlchemyError):
        active.rollback()
        raise
