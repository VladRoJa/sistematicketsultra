"""Issue #856 D2a — operator cost/volume approval with atomic capacity ledger.

This endpoint NEVER calls iVentas, creates provider children or grants send
authority. PostgreSQL advisory locks serialize competing approvals for every
shared channel/portfolio; stale/missing evidence fails closed.
"""
from __future__ import annotations

import re
from dataclasses import replace
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2DispatchApprovalORM,
    MarketingCampaignV2CapacityReservationORM,
    MarketingCampaignV2QuotaCapacityAttestationORM,
)
from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
from app.services.marketing_campaign_v2_budget_service import estimate_preflight_cost
from app.services.marketing_campaign_v2_quota_service import (
    assess_preflight_capacity, _database_date,
)
from app.services.marketing_campaign_v2_operational_capacity_service import BASIS as OPERATIONAL_BASIS

APPROVAL_TTL = timedelta(minutes=15)


class CampaignV2ApprovalValidationError(ValueError):
    pass


class CampaignV2ApprovalConflictError(RuntimeError):
    pass


def _timestamp(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        raise CampaignV2ApprovalValidationError("Fecha con zona horaria requerida.")
    return current.astimezone(timezone.utc)


def _validate_confirmation(
    expected_dispatch_fingerprint: Any, expected_quote_fingerprint: Any,
    expected_recipients: Any, expected_total_mxn: Any, actor_user_id: Any,
) -> tuple[str, str, int, Decimal, int]:
    if (not isinstance(expected_dispatch_fingerprint, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_dispatch_fingerprint) is None):
        raise CampaignV2ApprovalValidationError("Fingerprint SHA256 exacto requerido.")
    if (not isinstance(expected_quote_fingerprint, str) or
            re.fullmatch(r"[0-9a-f]{64}", expected_quote_fingerprint) is None):
        raise CampaignV2ApprovalValidationError("Huella exacta de cotización requerida.")
    if type(expected_recipients) is not int or expected_recipients <= 0:
        raise CampaignV2ApprovalValidationError("Confirma un volumen entero positivo.")
    if (not isinstance(expected_total_mxn, str)
            or re.fullmatch(r"(0|[1-9][0-9]{0,11})\.[0-9]{2}", expected_total_mxn) is None):
        raise CampaignV2ApprovalValidationError("Confirma monto MXN con dos decimales.")
    if type(actor_user_id) is not int or actor_user_id <= 0:
        raise CampaignV2ApprovalValidationError("Actor inválido.")
    return (expected_dispatch_fingerprint, expected_quote_fingerprint,
            expected_recipients, Decimal(expected_total_mxn), actor_user_id)


def _ready_plan_and_holds(plan: Any, held_sucursal_canons: Any):
    """A held branch is an explicit choice, never an automatic quota bypass."""
    if held_sucursal_canons is None:
        held_sucursal_canons = []
    if not isinstance(held_sucursal_canons, list) or any(
        not isinstance(value, str) or not value.strip() or value != value.strip()
        for value in held_sucursal_canons
    ):
        raise CampaignV2ApprovalValidationError("HELD requiere lista explícita de sucursales.")
    names = [batch.sucursal_canon for batch in plan.batches]
    holds = set(held_sucursal_canons)
    if len(names) != len(set(names)) or len(holds) != len(held_sucursal_canons):
        raise CampaignV2ApprovalValidationError("Lotes HELD duplicados.")
    if not holds.issubset(names) or len(holds) >= len(names):
        raise CampaignV2ApprovalValidationError("HELD desconocido o sin lotes READY.")
    ready_batches = tuple(batch for batch in plan.batches
                          if batch.sucursal_canon not in holds)
    return replace(plan, batches=ready_batches), holds


def _hold_sources(held_names: set[str], supplied: Any) -> dict[str, str]:
    """Every HELD requires an operator-sourced reference, never inferred quota."""
    if not held_names and supplied is None:
        return {}
    if not isinstance(supplied, dict) or set(supplied) != held_names:
        raise CampaignV2ApprovalValidationError(
            "Indica evidencia de cuota por cada sucursal HELD."
        )
    normalized = {}
    for name, source in supplied.items():
        if (not isinstance(source, str) or
                not source.strip() or len(source.strip()) > 255):
            raise CampaignV2ApprovalValidationError(
                "Cada HELD requiere referencia documental/manual de cuota."
            )
        normalized[name] = source.strip()
    return normalized


def _assess_scopes(
    plan: Any, *, session: Any, timestamp: datetime,
    ignore_campaign_id: int | None = None,
    basis_preference: str | None = None,
):
    if not plan.ready or plan.mode != "IMMEDIATE" or not plan.batches:
        raise CampaignV2ApprovalConflictError(
            "Solo preflight IMMEDIATE totalmente conciliado puede aprobarse."
        )
    quota = assess_preflight_capacity(
        plan=plan, session=session, now=timestamp,
        ignore_campaign_id=ignore_campaign_id, basis_preference=basis_preference,
    )
    if (quota["status"] != "REVIEWABLE" or
            not all(x["recommendation"] == "CAPACITY_REVIEWED" for x in quota["batches"]) or
            len(quota["batches"]) != len(plan.batches)):
        raise CampaignV2ApprovalConflictError(
            "No hay evidencia de capacidad completa y vigente para todos los lotes."
        )

    operational = quota.get("basis") == OPERATIONAL_BASIS
    quantities = defaultdict(int)
    evidence_ids = {}
    by_branch = {}
    for batch, row in zip(plan.batches, quota["batches"], strict=True):
        count = len(batch.recipients)
        if (row["sucursal_canon"] != batch.sucursal_canon or
                row["provider_channel_id"] != str(batch.provider_channel_id or "") or
                not row["portfolio_key"] or
                (not operational and (not row["channel_evidence_id"] or
                                   not row["portfolio_evidence_id"])) or
             (operational and (row.get("policy_revision_id") is None or
                               not row.get("operator_channel_cap") or
                               not row.get("operator_portfolio_cap")))):
            raise CampaignV2ApprovalConflictError("Cambió la asignación de lotes/canales.")
        channel_scope = ("CHANNEL", row["provider_channel_id"])
        portfolio_scope = ("PORTFOLIO", row["portfolio_key"])
        for scope, evidence_id in (
            (channel_scope, row["channel_evidence_id"]),
            (portfolio_scope, row["portfolio_evidence_id"]),
        ):
            if scope in evidence_ids and evidence_ids[scope] != evidence_id:
                raise CampaignV2ApprovalConflictError("Evidencias contradictorias entre lotes.")
            evidence_ids[scope] = evidence_id
            quantities[scope] += count
        by_branch[batch.sucursal_canon] = row
    return quota, quantities, evidence_ids, by_branch


def _reserve_locked(
    *, plan: Any, budget: dict[str, Any], confirmation: tuple,
    session: Any, timestamp: datetime, quantities: dict,
    evidence_ids: dict, quota_rows: dict,
    held_names: frozenset[str] = frozenset(),
    held_sources: dict[str, str] | None = None,
) -> dict[str, Any]:
    expected_fingerprint, expected_quote, expected_count, expected_cost, actor = confirmation
    if plan.dispatch_fingerprint != expected_fingerprint:
        raise CampaignV2ApprovalConflictError("Fingerprint cambió; vuelve a revisar.")
    if len(plan.sendable_phones) != expected_count:
        raise CampaignV2ApprovalConflictError("Volumen cambió; vuelve a revisar.")
    if (budget["quote_fingerprint"] != expected_quote or
            budget["status"] != "COMPLETE" or budget["currency"] != "MXN" or
            budget["sendable_recipients"] != expected_count or
            budget["total_estimated_mxn"] is None or
            Decimal(budget["total_estimated_mxn"]) != expected_cost):
        raise CampaignV2ApprovalConflictError("Costo o revisión de tarifa cambió.")

    operational = (bool(quota_rows) and all(
        row.get("policy_revision_id") is not None for row in quota_rows.values()
    ))
    if operational and any(value is not None for value in evidence_ids.values()):
        raise CampaignV2ApprovalConflictError("Modos de cupo mezclados.")
    evidence = {}
    expiry = timestamp + APPROVAL_TTL
    for scope in sorted(quantities):
        kind, key = scope
        if operational:
            # Already assessed inside the same transaction AFTER obtaining scope locks.
            evidence[scope] = None
            continue
        row = session.get(MarketingCampaignV2QuotaCapacityAttestationORM, evidence_ids[scope])
        if (row is None or row.scope_kind != kind or row.scope_key != key or
                _database_date(row.observed_at) > timestamp or
                _database_date(row.expires_at) <= timestamp or
                _database_date(row.window_ends_at) <= timestamp):
            raise CampaignV2ApprovalConflictError("Evidencia de cupo revocada, vencida o incompatible.")
        expiry = min(expiry, _database_date(row.expires_at), _database_date(row.window_ends_at))
        already_reserved = session.query(
            func.coalesce(func.sum(MarketingCampaignV2CapacityReservationORM.reserved_messages), 0)
        ).filter(
            MarketingCampaignV2CapacityReservationORM.scope_kind == kind,
            MarketingCampaignV2CapacityReservationORM.scope_key == key,
            MarketingCampaignV2CapacityReservationORM.reserved_until > timestamp,
        ).scalar()
        if int(already_reserved or 0) + quantities[scope] > int(row.remaining_messages):
            raise CampaignV2ApprovalConflictError(
                "Reserva concurrente o remanente insuficiente en " + kind + ":" + key
            )
        evidence[scope] = row
    if expiry <= timestamp:
        raise CampaignV2ApprovalConflictError("La evidencia caducó antes de aprobar.")

    prices = {x["sucursal_canon"]: x for x in budget["batches"]}
    manifest_batches = []
    for batch in plan.batches:
        held = batch.sucursal_canon in held_names
        if held and not (held_sources or {}).get(batch.sucursal_canon):
            raise CampaignV2ApprovalConflictError("HELD sin fuente documentada.")
        item = None if held else quota_rows[batch.sucursal_canon]
        price = prices[batch.sucursal_canon]
        if price["recipients"] != len(batch.recipients):
            raise CampaignV2ApprovalConflictError("Detalle de presupuesto incompatible.")
        manifest_batches.append({
            "sucursal_canon": batch.sucursal_canon,
            "provider_channel_id": batch.provider_channel_id,
            "recipients": len(batch.recipients),
            "planned_status": "HELD" if held else "READY",
            "hold_reason": "CHANNEL_DAILY_QUOTA" if held else None,
            "hold_evidence": {
                "source": "EXPLICIT_OPERATOR_DECISION",
                "source_reference": (held_sources or {})[batch.sucursal_canon],
                "approved_by_user_id": actor,
                "approved_at": timestamp.isoformat(),
                "dispatch_fingerprint": expected_fingerprint,
                "quote_fingerprint": expected_quote,
            } if held else None,
            "channel_attestation_id": item["channel_evidence_id"] if item else None,
            "policy_revision_id": item.get("policy_revision_id") if item else None,
            "operator_channel_cap": item.get("operator_channel_cap") if item else None,
            "operator_portfolio_cap": item.get("operator_portfolio_cap") if item else None,
            "portfolio_key": item["portfolio_key"] if item else None,
            "portfolio_attestation_id": item["portfolio_evidence_id"] if item else None,
            "cost_rate_revision_id": price["revision_id"],
            "estimated_mxn": price["estimated_mxn"],
        })

    approval = MarketingCampaignV2DispatchApprovalORM(
        campaign_v2_id=plan.campaign_id,
        template_id=plan.batches[0].template_id,
        dispatch_fingerprint=plan.dispatch_fingerprint,
        recipient_count=expected_count,
        approved_estimated_mxn=expected_cost,
        manifest_json={
            "version": "D2B_READY_HELD_V1",
            "quote_fingerprint": expected_quote,
            "basis": OPERATIONAL_BASIS if operational else "OPERATOR_ATTESTED_NOT_META_VERIFIED",
            "send_authorized": False,
            "schedule_mode": plan.mode,
            "batches": manifest_batches,
        },
        approved_by_user_id=actor, approved_at=timestamp, expires_at=expiry,
    )
    session.add(approval)
    session.flush()
    for scope in sorted(quantities):
        kind, key = scope
        session.add(MarketingCampaignV2CapacityReservationORM(
            approval_id=approval.id,
            attestation_id=None if operational else evidence[scope].id,
            scope_kind=kind, scope_key=key,
            reserved_messages=quantities[scope],
            reserved_until=expiry, created_at=timestamp,
        ))
    session.commit()
    return {
        "approval_id": int(approval.id), "campaign_id": int(plan.campaign_id),
        "dispatch_fingerprint": plan.dispatch_fingerprint,
        "quote_fingerprint": expected_quote,
        "approved_recipients": expected_count,
        "approved_estimated_mxn": format(expected_cost, ".2f"),
        "currency": "MXN", "approved_at": timestamp.isoformat(),
        "expires_at": expiry.isoformat(),
        "reservation_scopes": len(quantities),
        "ready_batches": len(plan.batches) - len(held_names),
        "held_batches": len(held_names),
        "manifest": approval.manifest_json,
        "send_authorized": False,
        "status": "RESERVED_NOT_DISPATCHED",
    }


def approve_dispatch_reservation(
    *, campaign_id: int, template_id: int, expected_dispatch_fingerprint: Any,
    expected_quote_fingerprint: Any, expected_recipients: Any, expected_total_mxn: Any, actor_user_id: Any,
    allowed_sucursal_keys: Any, held_sucursal_canons: Any = None,
    held_source_references: Any = None, session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reserve only, with PostgreSQL transaction-scoped locks; never dispatch."""
    if type(campaign_id) is not int or campaign_id <= 0:
        raise CampaignV2ApprovalValidationError("campaign_id inválido.")
    if type(template_id) is not int or template_id <= 0:
        raise CampaignV2ApprovalValidationError("template_id inválido.")
    confirmation = _validate_confirmation(
        expected_dispatch_fingerprint, expected_quote_fingerprint,
        expected_recipients, expected_total_mxn, actor_user_id,
    )
    timestamp = _timestamp(now)
    active = session if session is not None else db.session
    try:
        # Only supported on PostgreSQL; SQLite simulation cannot claim atomicity.
        if active.get_bind().dialect.name != "postgresql":
            raise CampaignV2ApprovalConflictError("Reservas requieren PostgreSQL.")
        campaign = active.query(MarketingCampaignV2ORM).filter(
            MarketingCampaignV2ORM.id == campaign_id
        ).with_for_update().one_or_none()
        if campaign is None:
            raise CampaignV2ApprovalConflictError("Campaña no encontrada.")
        if active.query(MarketingCampaignV2DispatchApprovalORM.id).filter(
            MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == campaign_id
        ).first() is not None:
            raise CampaignV2ApprovalConflictError("Ya hay aprobación para esta campaña.")
        if active.query(MarketingCampaignV2ProviderCampaignORM.id).filter(
            MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == campaign_id
        ).first() is not None:
            raise CampaignV2ApprovalConflictError(
                "La campaña tiene provider children; no se aprueba retroactivamente."
            )

        def current_plan():
            return build_campaign_v2_preflight(
                campaign_id=campaign_id, template_id=template_id,
                allowed_sucursal_keys=allowed_sucursal_keys,
                session=active, now=timestamp,
            )

        plan = current_plan()
        if not plan.ready or plan.mode != "IMMEDIATE":
            raise CampaignV2ApprovalConflictError("Preflight bloqueado o no inmediato.")
        ready_plan, held_names = _ready_plan_and_holds(plan, held_sucursal_canons)
        held_sources = _hold_sources(held_names, held_source_references)
        initial_quota, scopes, _, _ = _assess_scopes(ready_plan, session=active, timestamp=timestamp)
        initial_scope_names = set(scopes)
        for kind, key in sorted(initial_scope_names):
            active.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                           {"scope": "mkt_v2_quota:" + kind + ":" + key})

        # Never reuse the pre-lock clock after waiting for another operator.
        # Keep injected test timestamps deterministic.
        if now is None:
            timestamp = _timestamp(None)
        # Recheck after waiting for other approvals and before reserving.
        plan = current_plan()
        if not plan.ready or plan.mode != "IMMEDIATE":
            raise CampaignV2ApprovalConflictError("Cambió el preflight.")
        ready_plan, current_held_names = _ready_plan_and_holds(plan, held_sucursal_canons)
        if current_held_names != held_names:
            raise CampaignV2ApprovalConflictError("Cambió el manifiesto HELD.")
        refreshed_quota, quantities, evidence_ids, quota_rows = _assess_scopes(
            ready_plan, session=active, timestamp=timestamp,
            basis_preference=initial_quota.get("basis"),
        )
        if refreshed_quota.get("basis") != initial_quota.get("basis"):
            raise CampaignV2ApprovalConflictError("Modalidad de cupo cambió durante aprobación.")
        if set(quantities) != initial_scope_names:
            raise CampaignV2ApprovalConflictError(
                "Cambió la membresía de portafolio; revisa y reintenta."
            )
        budget = estimate_preflight_cost(plan=plan, session=active, now=timestamp)
        return _reserve_locked(
            plan=plan, budget=budget, confirmation=confirmation,
            session=active, timestamp=timestamp, quantities=quantities,
            evidence_ids=evidence_ids, quota_rows=quota_rows,
            held_names=frozenset(held_names),
            held_sources=held_sources,
        )
    except (CampaignV2ApprovalValidationError, CampaignV2ApprovalConflictError):
        active.rollback()
        raise
    except IntegrityError as exc:
        active.rollback()
        raise CampaignV2ApprovalConflictError(
            "Conflicto concurrente de aprobación/cupo; no se reservó."
        ) from exc
    except SQLAlchemyError:
        active.rollback()
        raise


def get_dispatch_approval(*, campaign_id: int, session: Any | None = None) -> dict[str, Any]:
    active = session if session is not None else db.session
    approval = active.query(MarketingCampaignV2DispatchApprovalORM).filter(
        MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == campaign_id
    ).one_or_none()
    if approval is None:
        return {"approval": None, "send_authorized": False}
    return {
        "approval": {
            "approval_id": int(approval.id),
            "campaign_id": int(approval.campaign_v2_id),
            "dispatch_fingerprint": approval.dispatch_fingerprint,
            "approved_recipients": int(approval.recipient_count),
            "approved_estimated_mxn": format(approval.approved_estimated_mxn, ".2f"),
            "approved_at": _database_date(approval.approved_at).isoformat(),
            "expires_at": _database_date(approval.expires_at).isoformat(),
            "status": "EXPIRED" if _database_date(approval.expires_at)
            <= datetime.now(timezone.utc) else "RESERVED_NOT_DISPATCHED",
            "manifest": approval.manifest_json,
        },
        "send_authorized": False,
    }
