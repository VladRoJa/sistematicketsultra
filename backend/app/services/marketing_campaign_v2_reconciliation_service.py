"""Manual, audited reconciliation for ambiguous Campaign V2 provider creates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import MarketingCampaignV2ProviderCampaignORM
from app.services.marketing_campaign_v2_retry_policy import (
    next_retry_allowed_at,
    retry_is_exhausted,
)


RESOLUTION_PROVIDER_CAMPAIGN_FOUND = "PROVIDER_CAMPAIGN_FOUND"
RESOLUTION_NOT_CREATED_CONFIRMED = "NOT_CREATED_CONFIRMED"
ALLOWED_RESOLUTIONS = frozenset(
    {
        RESOLUTION_PROVIDER_CAMPAIGN_FOUND,
        RESOLUTION_NOT_CREATED_CONFIRMED,
    }
)


class MarketingCampaignV2ReconciliationError(RuntimeError):
    pass


class MarketingCampaignV2ReconciliationValidationError(
    MarketingCampaignV2ReconciliationError,
    ValueError,
):
    pass


class MarketingCampaignV2ReconciliationNotFoundError(
    MarketingCampaignV2ReconciliationError
):
    pass


class MarketingCampaignV2ReconciliationConflictError(
    MarketingCampaignV2ReconciliationError
):
    pass


class MarketingCampaignV2ReconciliationPersistenceError(
    MarketingCampaignV2ReconciliationError
):
    pass


def reconcile_campaign_v2_provider_child(
    *,
    child_id: Any,
    resolution: Any,
    actor_user_id: Any,
    provider_campaign_id: Any = None,
    note: Any = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_child_id = _positive_int(child_id, "child_id")
    normalized_actor = _positive_int(actor_user_id, "actor_user_id")
    normalized_resolution = _resolution(resolution)
    normalized_note = _required_note(note)
    normalized_provider_id = _optional_text(
        provider_campaign_id,
        "provider_campaign_id",
        max_length=255,
    )
    timestamp = _normalize_now(now)

    if (
        normalized_resolution == RESOLUTION_PROVIDER_CAMPAIGN_FOUND
        and normalized_provider_id is None
    ):
        raise MarketingCampaignV2ReconciliationValidationError(
            "provider_campaign_id es obligatorio cuando la campaña fue encontrada."
        )
    if (
        normalized_resolution == RESOLUTION_NOT_CREATED_CONFIRMED
        and normalized_provider_id is not None
    ):
        raise MarketingCampaignV2ReconciliationValidationError(
            "provider_campaign_id debe omitirse cuando se confirmó que no fue creada."
        )

    row = (
        active_session.query(MarketingCampaignV2ProviderCampaignORM)
        .filter(
            MarketingCampaignV2ProviderCampaignORM.id
            == normalized_child_id
        )
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise MarketingCampaignV2ReconciliationNotFoundError(
            "Provider campaign child no encontrado."
        )

    if row.status != "RECONCILIATION_REQUIRED":
        raise MarketingCampaignV2ReconciliationConflictError(
            "El child ya no requiere reconciliación."
        )
    if row.reconciliation_resolution is not None:
        raise MarketingCampaignV2ReconciliationConflictError(
            "El child ya tiene una resolución de reconciliación registrada."
        )
    if row.provider_campaign_id is not None:
        raise MarketingCampaignV2ReconciliationConflictError(
            "El child ambiguo ya tiene provider_campaign_id; requiere revisión manual."
        )

    previous = {
        "status": str(row.status),
        "error_code": row.error_code,
        "support_ref": row.support_ref,
        "provider_campaign_id": row.provider_campaign_id,
    }

    if normalized_resolution == RESOLUTION_PROVIDER_CAMPAIGN_FOUND:
        duplicate = (
            active_session.query(MarketingCampaignV2ProviderCampaignORM.id)
            .filter(
                MarketingCampaignV2ProviderCampaignORM.provider
                == row.provider,
                MarketingCampaignV2ProviderCampaignORM.provider_campaign_id
                == normalized_provider_id,
                MarketingCampaignV2ProviderCampaignORM.id
                != normalized_child_id,
            )
            .first()
        )
        if duplicate is not None:
            raise MarketingCampaignV2ReconciliationConflictError(
                "provider_campaign_id ya está ligado a otro child."
            )

        target_status = (
            "SCHEDULED"
            if row.provider_send_at is not None
            else "SUBMITTED"
        )
        row.provider_campaign_id = normalized_provider_id
        row.status = target_status
        row.retry_next_allowed_at = None
        row.error_code = None
        row.support_ref = None
    else:
        attempts = int(row.retry_attempt_count or 0)
        if retry_is_exhausted(attempts):
            target_status = "RETRY_EXHAUSTED"
            retry_next_at = None
            error_code = "RETRY_LIMIT_REACHED"
        else:
            target_status = "RETRY_ELIGIBLE"
            retry_next_at = next_retry_allowed_at(
                completed_attempts=attempts,
                resolved_at=timestamp,
            )
            error_code = "RECONCILED_NOT_CREATED"

        row.status = target_status
        row.retry_next_allowed_at = retry_next_at
        row.error_code = error_code
        row.support_ref = None

    row.reconciliation_resolution = normalized_resolution
    row.reconciliation_note = normalized_note
    row.reconciliation_snapshot_json = {
        "schema_version": 1,
        "source": "MANUAL_OPERATOR",
        "previous": deepcopy(previous),
        "resolution": normalized_resolution,
        "target_status": target_status,
        "retry_attempt_count": int(row.retry_attempt_count or 0),
        "retry_next_allowed_at": _iso_datetime(
            row.retry_next_allowed_at
        ),
        "resolved_provider_campaign_id": (
            normalized_provider_id
            if normalized_resolution == RESOLUTION_PROVIDER_CAMPAIGN_FOUND
            else None
        ),
    }
    row.reconciled_by_user_id = normalized_actor
    row.reconciled_at = timestamp
    row.updated_at = timestamp

    try:
        active_session.commit()
    except IntegrityError as exc:
        active_session.rollback()
        raise MarketingCampaignV2ReconciliationConflictError(
            "La resolución entra en conflicto con evidencia provider ya persistida."
        ) from exc
    except SQLAlchemyError as exc:
        active_session.rollback()
        raise MarketingCampaignV2ReconciliationPersistenceError(
            "No fue posible persistir la reconciliación."
        ) from exc

    persisted = active_session.get(
        MarketingCampaignV2ProviderCampaignORM,
        normalized_child_id,
    )
    if persisted is None:
        raise MarketingCampaignV2ReconciliationPersistenceError(
            "No fue posible recuperar la reconciliación persistida."
        )
    return serialize_campaign_v2_reconciliation(persisted)


def serialize_campaign_v2_reconciliation(
    row: MarketingCampaignV2ProviderCampaignORM,
) -> dict[str, Any]:
    return {
        "child_id": int(row.id),
        "campaign_id": int(row.campaign_v2_id),
        "sucursal_id": int(row.sucursal_id),
        "sucursal_canon": str(row.sucursal_canon),
        "provider": str(row.provider),
        "status": str(row.status),
        "provider_campaign_id": (
            str(row.provider_campaign_id)
            if row.provider_campaign_id is not None
            else None
        ),
        "retry": {
            "attempt_count": int(row.retry_attempt_count or 0),
            "next_allowed_at": _iso_datetime(
                row.retry_next_allowed_at
            ),
            "exhausted": str(row.status) == "RETRY_EXHAUSTED",
        },
        "reconciliation": {
            "resolution": row.reconciliation_resolution,
            "note": row.reconciliation_note,
            "reconciled_by_user_id": row.reconciled_by_user_id,
            "reconciled_at": _iso_datetime(row.reconciled_at),
            "snapshot": deepcopy(
                dict(row.reconciliation_snapshot_json or {})
            ),
        },
    }


def _resolution(value: Any) -> str:
    if not isinstance(value, str):
        raise MarketingCampaignV2ReconciliationValidationError(
            "resolution debe ser texto."
        )
    normalized = value.strip().upper()
    if normalized not in ALLOWED_RESOLUTIONS:
        raise MarketingCampaignV2ReconciliationValidationError(
            "resolution no soportada."
        )
    return normalized


def _required_note(value: Any) -> str:
    if not isinstance(value, str):
        raise MarketingCampaignV2ReconciliationValidationError(
            "note debe ser texto."
        )
    normalized = " ".join(value.split())
    if not normalized:
        raise MarketingCampaignV2ReconciliationValidationError(
            "note es obligatorio para documentar la evidencia de reconciliación."
        )
    if len(normalized) > 2000:
        raise MarketingCampaignV2ReconciliationValidationError(
            "note excede 2000 caracteres."
        )
    return normalized


def _optional_text(
    value: Any,
    field_name: str,
    *,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MarketingCampaignV2ReconciliationValidationError(
            f"{field_name} debe ser texto."
        )
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise MarketingCampaignV2ReconciliationValidationError(
            f"{field_name} excede {max_length} caracteres."
        )
    return normalized


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise MarketingCampaignV2ReconciliationValidationError(
            f"{field_name} debe ser entero positivo."
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2ReconciliationValidationError(
            f"{field_name} debe ser entero positivo."
        ) from exc
    if normalized <= 0:
        raise MarketingCampaignV2ReconciliationValidationError(
            f"{field_name} debe ser entero positivo."
        )
    return normalized


def _normalize_now(value: datetime | None) -> datetime:
    current = value if value is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _iso_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    formatter = getattr(value, "isoformat", None)
    return formatter() if callable(formatter) else str(value)
