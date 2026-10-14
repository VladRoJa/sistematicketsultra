"""D2b — persist READY/HELD children atomically without provider activity.

Approvals are *not* dispatch permissions. This materialization has no external
provider dependency, never transitions a child to SUBMITTING, and fails closed.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2DispatchApprovalORM,
    MarketingCampaignV2CapacityReservationORM,
)
from app.services.marketing_campaign_v2_dispatch_approval_service import (
    CampaignV2ApprovalConflictError,
    _assess_scopes,
    _database_date,
)
from app.services.marketing_campaign_v2_budget_service import estimate_preflight_cost
from app.services.marketing_campaign_v2_preflight_service import (
    build_campaign_v2_preflight,
    build_provider_campaign_idempotency_key,
)
from app.services.marketing_campaign_v2_submit_service import (
    MarketingCampaignV2SubmitConflictError,
    MarketingCampaignV2SubmitPreconditionError,
    _prepare_provider_campaign_rows,
    _load_campaign_rows,
    build_campaign_v2_provider_dispatch_batch,
    serialize_campaign_v2_provider_request_snapshot,
)

MANIFEST_VERSION = "D2B_READY_HELD_V1"


def _assert_manifest(plan: Any, budget: dict, approval: Any):
    manifest = dict(approval.manifest_json or {})
    if manifest.get("version") != MANIFEST_VERSION or manifest.get("send_authorized") is not False:
        raise CampaignV2ApprovalConflictError("Manifiesto no habilitado para materialización D2b.")
    if (plan.dispatch_fingerprint != approval.dispatch_fingerprint or
            len(plan.sendable_phones) != int(approval.recipient_count) or
            plan.mode != "IMMEDIATE" or not plan.ready or
            budget["status"] != "COMPLETE" or
            budget["quote_fingerprint"] != manifest.get("quote_fingerprint") or
            Decimal(budget["total_estimated_mxn"]) != Decimal(approval.approved_estimated_mxn)):
        raise CampaignV2ApprovalConflictError("Preflight, presupuesto o revisión cambiaron.")
    batches = manifest.get("batches")
    if not isinstance(batches, list) or len(batches) != len(plan.batches):
        raise CampaignV2ApprovalConflictError("Manifiesto de lotes incompleto.")
    by_name = {}
    for row in batches:
        if not isinstance(row, dict) or not isinstance(row.get("sucursal_canon"), str):
            raise CampaignV2ApprovalConflictError("Entrada inválida en manifiesto.")
        key = row["sucursal_canon"]
        if key in by_name or row.get("planned_status") not in {"READY", "HELD"}:
            raise CampaignV2ApprovalConflictError("Duplicado o estado inválido en manifiesto.")
        by_name[key] = row
    if set(by_name) != {b.sucursal_canon for b in plan.batches}:
        raise CampaignV2ApprovalConflictError("Sucursales del manifiesto no coinciden.")
    costs = {b["sucursal_canon"]: b for b in budget["batches"]}
    for batch in plan.batches:
        row = by_name[batch.sucursal_canon]
        cost = costs[batch.sucursal_canon]
        if (row["provider_channel_id"] != batch.provider_channel_id or
                type(row["recipients"]) is not int or
                row["recipients"] != len(batch.recipients) or
                row["estimated_mxn"] != cost["estimated_mxn"] or
                row["cost_rate_revision_id"] != cost["revision_id"]):
            raise CampaignV2ApprovalConflictError("Lote, identidad o tarifa diferente.")
        held = row["planned_status"] == "HELD"
        if held and (
            row.get("hold_reason") != "CHANNEL_DAILY_QUOTA" or
            not isinstance(row.get("hold_evidence"), dict) or
            row["hold_evidence"].get("dispatch_fingerprint") != plan.dispatch_fingerprint or
            row["hold_evidence"].get("quote_fingerprint") != manifest["quote_fingerprint"] or
            not isinstance(row["hold_evidence"].get("source_reference"), str) or
            not row["hold_evidence"]["source_reference"].strip()
        ):
            raise CampaignV2ApprovalConflictError("HELD sin autorización y evidencia íntegra.")
        if not held and (row.get("hold_reason") or row.get("hold_evidence")):
            raise CampaignV2ApprovalConflictError("READY contiene retención incompatible.")
    if not any(row["planned_status"] == "READY" for row in batches):
        raise CampaignV2ApprovalConflictError("No se autoriza manifiesto completamente HELD.")
    return by_name


def _validate_existing(plan: Any, by_name: dict, rows: list):
    if len(rows) != len(by_name) or {r.sucursal_canon for r in rows} != set(by_name):
        raise CampaignV2ApprovalConflictError("Children incompletos o duplicados.")
    batch_by_name = {b.sucursal_canon: b for b in plan.batches}
    for row in rows:
        definition = by_name[row.sucursal_canon]
        batch = batch_by_name[row.sucursal_canon]
        expected_key = build_provider_campaign_idempotency_key(
            campaign_v2_id=plan.campaign_id, batch=batch,
            dispatch_fingerprint=plan.dispatch_fingerprint,
        )
        expected_snapshot = serialize_campaign_v2_provider_request_snapshot(
            build_campaign_v2_provider_dispatch_batch(plan=plan, batch=batch)
        )
        if (row.status != definition["planned_status"] or
                int(row.campaign_v2_id) != int(plan.campaign_id) or
                row.provider != plan.provider or
                int(row.sucursal_id) != int(batch.sucursal_id) or
                int(row.channel_binding_id) != int(batch.channel_binding_id or 0) or
                row.template_name != batch.template_name or
                row.dispatch_fingerprint != plan.dispatch_fingerprint or
                row.idempotency_key != expected_key or
                row.provider_channel_id != batch.provider_channel_id or
                int(row.recipient_count) != len(batch.recipients) or
                int(row.template_id) != int(batch.template_id) or
                dict(row.request_snapshot_json or {}) != expected_snapshot or
                row.provider_campaign_id is not None or
                row.submit_started_at is not None or row.submitted_at is not None or
                row.submitted_by_user_id is not None or
                row.error_code is not None):
            raise CampaignV2ApprovalConflictError("Child modificado; no se reescribe.")
        if definition["planned_status"] == "READY" and (
            row.hold_reason is not None or row.held_at is not None or
            row.held_by_user_id is not None or dict(row.hold_evidence_json or {})
        ):
            raise CampaignV2ApprovalConflictError("READY alterado con campos de retención.")
        if definition["planned_status"] == "HELD" and (
            row.hold_reason != "CHANNEL_DAILY_QUOTA" or
            dict(row.hold_evidence_json or {}) != definition["hold_evidence"] or
            row.held_at is None or row.held_by_user_id is None
        ):
            raise CampaignV2ApprovalConflictError("Retención histórica modificada.")


def materialize_approved_manifest(
    *, campaign_id: int, actor_user_id: int, allowed_sucursal_keys: Any,
    session: Any | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    """Create all provider children as READY/HELD. Never makes a network request."""
    if type(campaign_id) is not int or campaign_id <= 0 or (
        type(actor_user_id) is not int or actor_user_id <= 0
    ):
        raise CampaignV2ApprovalConflictError("Campaña o actor inválido.")
    active = session if session is not None else db.session
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise CampaignV2ApprovalConflictError("Fecha sin zona horaria.")
    timestamp = timestamp.astimezone(timezone.utc)
    try:
        if active.get_bind().dialect.name != "postgresql":
            raise CampaignV2ApprovalConflictError("Persistencia gobernada requiere PostgreSQL.")
        campaign = active.query(MarketingCampaignV2ORM).filter(
            MarketingCampaignV2ORM.id == campaign_id
        ).with_for_update().one_or_none()
        if campaign is None:
            raise CampaignV2ApprovalConflictError("Campaña inexistente.")
        approval = active.query(MarketingCampaignV2DispatchApprovalORM).filter(
            MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == campaign_id
        ).with_for_update().one_or_none()
        if approval is None or _database_date(approval.expires_at) <= timestamp:
            raise CampaignV2ApprovalConflictError("Aprobación inexistente o caducada.")
        plan = build_campaign_v2_preflight(
            campaign_id=campaign_id, template_id=int(approval.template_id),
            allowed_sucursal_keys=allowed_sucursal_keys, session=active, now=timestamp,
        )
        budget = estimate_preflight_cost(plan=plan, session=active, now=timestamp)
        by_name = _assert_manifest(plan, budget, approval)
        ready = tuple(b for b in plan.batches
                      if by_name[b.sucursal_canon]["planned_status"] == "READY")
        ready_plan = replace(plan, batches=ready)
        _, expected_scopes, expected_evidence_ids, current_quota = _assess_scopes(
            ready_plan, session=active, timestamp=timestamp,
            ignore_campaign_id=campaign_id,
            basis_preference=(approval.manifest_json or {}).get("basis"),
        )
        for kind, key in sorted(expected_scopes):
            active.execute(text(
                "SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"
            ), {"scope": "mkt_v2_quota:" + kind + ":" + key})
        # A lock may wait past expiry or a cost-rate change; recalculate.
        if now is None:
            timestamp = datetime.now(timezone.utc)
        if _database_date(approval.expires_at) <= timestamp:
            raise CampaignV2ApprovalConflictError("Aprobación vencida durante bloqueo.")
        plan = build_campaign_v2_preflight(
            campaign_id=campaign_id, template_id=int(approval.template_id),
            allowed_sucursal_keys=allowed_sucursal_keys, session=active, now=timestamp,
        )
        budget = estimate_preflight_cost(plan=plan, session=active, now=timestamp)
        by_name = _assert_manifest(plan, budget, approval)
        ready = tuple(b for b in plan.batches
                      if by_name[b.sucursal_canon]["planned_status"] == "READY")
        ready_plan = replace(plan, batches=ready)
        # Capacity and mapping must still be current after acquiring the locks.
        _, locked_scopes, locked_evidence, locked_quota = _assess_scopes(
            ready_plan, session=active, timestamp=timestamp,
            ignore_campaign_id=campaign_id,
            basis_preference=(approval.manifest_json or {}).get("basis"),
        )
        if locked_scopes != expected_scopes or locked_evidence != expected_evidence_ids:
            raise CampaignV2ApprovalConflictError("Evidencia de cupo cambió durante preparación.")
        reservations = active.query(MarketingCampaignV2CapacityReservationORM).filter(
            MarketingCampaignV2CapacityReservationORM.approval_id == approval.id,
        ).all()
        reserved = {(r.scope_kind, r.scope_key): r for r in reservations}
        if len(reservations) != len(reserved) or set(reserved) != set(locked_scopes):
            raise CampaignV2ApprovalConflictError("Reservas y manifiesto no concilian.")
        for scope, required in locked_scopes.items():
            reservation = reserved[scope]
            if (int(reservation.reserved_messages) != required or
                    reservation.attestation_id != locked_evidence[scope] or
                    _database_date(reservation.reserved_until) <= timestamp or
                    _database_date(reservation.reserved_until) > _database_date(approval.expires_at)):
                raise CampaignV2ApprovalConflictError("Reserva caducada o diferente.")
        for batch in ready:
            manifest_row = by_name[batch.sucursal_canon]
            quota_row = locked_quota[batch.sucursal_canon]
            if (quota_row["channel_evidence_id"] != manifest_row["channel_attestation_id"] or
                    quota_row["portfolio_evidence_id"] != manifest_row["portfolio_attestation_id"] or
                    quota_row["portfolio_key"] != manifest_row["portfolio_key"] or
                    quota_row.get("policy_revision_id") != manifest_row.get("policy_revision_id") or
                    quota_row.get("operator_channel_cap") != manifest_row.get("operator_channel_cap") or
                    quota_row.get("operator_portfolio_cap") != manifest_row.get("operator_portfolio_cap")):
                raise CampaignV2ApprovalConflictError("Política o atestación del lote cambió.")

        existing = _load_campaign_rows(campaign_id=campaign_id, session=active)
        if existing:
            _validate_existing(plan, by_name, existing)
            active.rollback()  # no change on idempotent repeat
            status = "ALREADY_PREPARED"
            count = len(existing)
        else:
            holds = {
                name: {"reason": "CHANNEL_DAILY_QUOTA", "evidence": row["hold_evidence"]}
                for name, row in by_name.items() if row["planned_status"] == "HELD"
            }
            rows = _prepare_provider_campaign_rows(
                plan=plan, actor_user_id=actor_user_id,
                session=active, now=timestamp, held_batches=holds,
                commit_rows=False,
            )
            _validate_existing(plan, by_name, rows)
            active.commit()  # all children commit only after full validation
            status = "PREPARED_NO_SEND"
            count = len(rows)
        return {
            "campaign_id": campaign_id, "approval_id": int(approval.id),
            "status": status, "provider_children": count,
            "ready_batches": len(ready),
            "held_batches": len(by_name) - len(ready),
            "send_authorized": False,
        }
    except (CampaignV2ApprovalConflictError,
            MarketingCampaignV2SubmitConflictError,
            MarketingCampaignV2SubmitPreconditionError):
        active.rollback()
        raise
    except IntegrityError as exc:
        active.rollback()
        raise CampaignV2ApprovalConflictError("Conflicto de children concurrentes.") from exc
    except SQLAlchemyError:
        active.rollback()
        raise
