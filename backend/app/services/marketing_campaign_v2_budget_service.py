"""Read-only Campaign V2 MXN budgeting from operator-entered rate revisions.

Costs are estimates, NEVER iVentas/Meta invoices or binding delivery quotes.
No inferred fallback: every channel needs a current, explicit revision.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ChannelBindingORM,
    MarketingCampaignV2CostRateRevisionORM,
    MarketingCampaignV2TemplateORM,
)
from app.services.marketing_campaign_v2_preflight_service import CampaignV2PreflightPlan

CENT = Decimal("0.01")
MAX_RATE = Decimal("1000")


class CampaignV2BudgetValidationError(ValueError):
    pass


class CampaignV2BudgetConflictError(RuntimeError):
    pass


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise CampaignV2BudgetValidationError("Se requiere fecha UTC con zona horaria.")
    return current.astimezone(timezone.utc)


def _money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def _serialize_rate(row: MarketingCampaignV2CostRateRevisionORM) -> dict[str, Any]:
    return {
        "revision_id": int(row.id),
        "template_id": int(row.template_id),
        "provider_channel_id": str(row.provider_channel_id),
        "unit_cost_mxn": format(row.unit_cost_mxn, ".6f"),
        "valid_from": _utc(row.valid_from).isoformat(),
        "source_reference": str(row.source_reference),
        "created_at": _utc(row.created_at).isoformat(),
    }


def list_cost_rate_revisions(
    *,
    session: Any | None = None,
    template_id: int | None = None,
) -> list[dict[str, Any]]:
    active = session if session is not None else db.session
    query = active.query(MarketingCampaignV2CostRateRevisionORM)
    if template_id is not None:
        if type(template_id) is not int or template_id <= 0:
            raise CampaignV2BudgetValidationError("template_id inválido.")
        query = query.filter(
            MarketingCampaignV2CostRateRevisionORM.template_id == template_id,
        )
    return [
        _serialize_rate(row)
        for row in query.order_by(
            MarketingCampaignV2CostRateRevisionORM.template_id,
            MarketingCampaignV2CostRateRevisionORM.provider_channel_id,
            MarketingCampaignV2CostRateRevisionORM.valid_from.desc(),
            MarketingCampaignV2CostRateRevisionORM.id.desc(),
        ).all()
    ]


def register_cost_rate_revision(
    *,
    template_id: Any,
    provider_channel_id: Any,
    unit_cost_mxn: Any,
    source_reference: Any,
    actor_user_id: int,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active = session if session is not None else db.session
    timestamp = _utc(now)
    if type(template_id) is not int or template_id <= 0:
        raise CampaignV2BudgetValidationError("template_id debe ser positivo.")
    if type(actor_user_id) is not int or actor_user_id <= 0:
        raise CampaignV2BudgetValidationError("Actor inválido.")
    if not isinstance(provider_channel_id, str) or not provider_channel_id.strip():
        raise CampaignV2BudgetValidationError("Canal exacto requerido.")
    channel = provider_channel_id.strip()
    if not isinstance(source_reference, str) or not source_reference.strip():
        raise CampaignV2BudgetValidationError(
            "Indica origen de la tarifa (cotización, contrato o aprobación)."
        )
    reference = source_reference.strip()
    if len(channel) > 255 or len(reference) > 255:
        raise CampaignV2BudgetValidationError("Identificador demasiado largo.")
    if isinstance(unit_cost_mxn, bool) or not isinstance(
        unit_cost_mxn, (str, int, Decimal),
    ):
        raise CampaignV2BudgetValidationError("Costo debe ser decimal en MXN.")
    try:
        cost = Decimal(str(unit_cost_mxn))
    except (InvalidOperation, ValueError) as exc:
        raise CampaignV2BudgetValidationError("Costo inválido.") from exc
    if not cost.is_finite() or cost <= 0 or cost > MAX_RATE:
        raise CampaignV2BudgetValidationError("Costo fuera de rango permitido.")
    if cost.as_tuple().exponent < -6:
        raise CampaignV2BudgetValidationError("Máximo 6 decimales para la tarifa.")
    template = active.get(MarketingCampaignV2TemplateORM, template_id)
    if template is None or template.provider != "IVENTAS" or not template.is_active:
        raise CampaignV2BudgetValidationError("Plantilla iVentas inexistente o inactiva.")
    binding = active.query(MarketingCampaignV2ChannelBindingORM.id).filter(
        MarketingCampaignV2ChannelBindingORM.provider == "IVENTAS",
        MarketingCampaignV2ChannelBindingORM.provider_channel_id == channel,
        MarketingCampaignV2ChannelBindingORM.is_active.is_(True),
    ).one_or_none()
    if binding is None:
        raise CampaignV2BudgetValidationError("Canal inexistente o inactivo.")
    template_channels = list(template.compatible_channel_ids_json or [])
    if template_channels and channel not in template_channels:
        raise CampaignV2BudgetValidationError("Canal incompatible con la plantilla.")

    revision = MarketingCampaignV2CostRateRevisionORM(
        template_id=template_id,
        provider_channel_id=channel,
        unit_cost_mxn=cost,
        source_reference=reference,
        valid_from=timestamp,
        created_by_user_id=actor_user_id,
        created_at=timestamp,
    )
    active.add(revision)
    try:
        active.commit()
    except IntegrityError as exc:
        active.rollback()
        raise CampaignV2BudgetConflictError("Revisión duplicada; no se reemplazó.") from exc
    except SQLAlchemyError:
        active.rollback()
        raise
    return _serialize_rate(revision)


def current_cost_rates(
    *,
    template_id: int,
    channel_ids: set[str] | None = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """One latest revision per exact channel, respecting valid_from."""
    timestamp = _utc(now)
    active = session if session is not None else db.session
    q = active.query(MarketingCampaignV2CostRateRevisionORM).filter(
        MarketingCampaignV2CostRateRevisionORM.template_id == template_id,
        MarketingCampaignV2CostRateRevisionORM.valid_from <= timestamp,
    )
    if channel_ids is not None:
        if not channel_ids:
            return {}
        q = q.filter(
            MarketingCampaignV2CostRateRevisionORM.provider_channel_id.in_(sorted(channel_ids))
        )
    rows = q.order_by(
        MarketingCampaignV2CostRateRevisionORM.valid_from.desc(),
        MarketingCampaignV2CostRateRevisionORM.id.desc(),
    ).all()
    latest = {}
    for row in rows:
        channel = str(row.provider_channel_id)
        if channel not in latest:
            latest[channel] = _serialize_rate(row)
    return latest


def estimate_preflight_cost(
    *,
    plan: CampaignV2PreflightPlan,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Exact batch counts, manually priced; incomplete != zero/approved cost."""
    timestamp = _utc(now)
    batches = plan.batches
    channels = {
        str(batch.provider_channel_id)
        for batch in batches if batch.provider_channel_id
    }
    template_ids = {int(batch.template_id) for batch in batches}
    if len(template_ids) > 1:
        raise CampaignV2BudgetValidationError("Preflight contiene múltiples plantillas.")
    rates = current_cost_rates(
        template_id=next(iter(template_ids)) if template_ids else -1,
        channel_ids=channels, session=session, now=timestamp,
    )
    breakdown = []
    subtotal = Decimal("0")
    missing = []
    priced = 0
    for batch in batches:
        count = len(batch.recipients)
        channel = str(batch.provider_channel_id or "")
        revision = rates.get(channel)
        amount = None
        if revision is not None:
            amount = Decimal(revision["unit_cost_mxn"]) * count
            subtotal += amount
            priced += count
        else:
            missing.append({"sucursal_canon": batch.sucursal_canon, "recipient_count": count})
        breakdown.append({
            "sucursal_canon": batch.sucursal_canon,
            "channel_id": channel or None,
            "recipients": count,
            "revision_id": revision["revision_id"] if revision else None,
            "unit_cost_mxn": revision["unit_cost_mxn"] if revision else None,
            "source_reference": revision["source_reference"] if revision else None,
            "estimated_mxn": _money(amount) if amount is not None else None,
        })
    count = len(plan.sendable_phones)
    unassigned = max(0, count - sum(len(b.recipients) for b in batches))
    complete = (
        plan.ready and not missing and unassigned == 0
        and bool(batches) and sum(len(b.recipients) for b in batches) == count
    )
    return {
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "currency": "MXN",
        "basis": "MANUAL_OPERATOR_RATE_NOT_PROVIDER_QUOTE",
        "as_of": timestamp.isoformat(),
        "sendable_recipients": count,
        "priced_recipients": priced,
        "unassigned_recipients": unassigned,
        "missing_rate_channels": missing,
        "priced_subtotal_mxn": _money(subtotal),
        "total_estimated_mxn": _money(subtotal) if complete else None,
        "batches": breakdown,
    }
