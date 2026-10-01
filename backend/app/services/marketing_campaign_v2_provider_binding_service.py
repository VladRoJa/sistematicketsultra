"""Vinculación persistente Campaign V2 ↔ identidad externa de provider."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import MarketingCampaignV2ORM
from app.services.marketing_campaign_v2_query_service import (
    _normalize_current_scope,
    _require_visible_campaign,
)


class MarketingCampaignV2ProviderBindingError(RuntimeError):
    """Base para errores de provider binding Campaign V2."""


class MarketingCampaignV2ProviderBindingValidationError(
    MarketingCampaignV2ProviderBindingError,
    ValueError,
):
    """Provider o provider_campaign_id inválidos."""


class MarketingCampaignV2ProviderBindingConflictError(
    MarketingCampaignV2ProviderBindingError
):
    """El binding solicitado entra en conflicto con identidad existente."""


class MarketingCampaignV2ProviderBindingPersistenceError(
    MarketingCampaignV2ProviderBindingError
):
    """Falló la persistencia del binding."""


def bind_campaign_v2_provider(
    *,
    campaign_id: Any,
    provider: Any,
    provider_campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_campaign_id = _positive_int(campaign_id)
    normalized_provider = _normalize_provider(provider)
    normalized_provider_campaign_id = _normalize_provider_campaign_id(
        provider_campaign_id
    )
    scope = _normalize_current_scope(allowed_sucursal_keys)
    campaign = (
        active_session.query(MarketingCampaignV2ORM)
        .filter(MarketingCampaignV2ORM.id == normalized_campaign_id)
        .with_for_update()
        .first()
    )
    campaign = _require_visible_campaign(campaign, scope)

    current_provider = _clean_optional(campaign.provider)
    current_external_id = _clean_optional(campaign.provider_campaign_id)

    if current_provider is not None or current_external_id is not None:
        if (
            current_provider == normalized_provider
            and current_external_id == normalized_provider_campaign_id
        ):
            return _serialize_binding(campaign, created=False)
        raise MarketingCampaignV2ProviderBindingConflictError(
            "Campaign V2 ya está vinculada a otra identidad provider."
        )

    existing = (
        active_session.query(MarketingCampaignV2ORM.id)
        .filter(
            MarketingCampaignV2ORM.provider == normalized_provider,
            MarketingCampaignV2ORM.provider_campaign_id
            == normalized_provider_campaign_id,
            MarketingCampaignV2ORM.id != normalized_campaign_id,
        )
        .first()
    )
    if existing is not None:
        raise MarketingCampaignV2ProviderBindingConflictError(
            "La identidad provider ya está vinculada a otra Campaign V2."
        )

    campaign.provider = normalized_provider
    campaign.provider_campaign_id = normalized_provider_campaign_id
    campaign.updated_at = _normalize_now(now)

    try:
        active_session.commit()
    except IntegrityError as exc:
        active_session.rollback()
        raise MarketingCampaignV2ProviderBindingConflictError(
            "La identidad provider ya está vinculada a otra Campaign V2."
        ) from exc
    except SQLAlchemyError as exc:
        active_session.rollback()
        raise MarketingCampaignV2ProviderBindingPersistenceError(
            "No fue posible persistir el provider binding."
        ) from exc

    return _serialize_binding(campaign, created=True)


def _serialize_binding(
    campaign: MarketingCampaignV2ORM,
    *,
    created: bool,
) -> dict[str, Any]:
    return {
        "campaign_id": int(campaign.id),
        "provider": campaign.provider,
        "provider_campaign_id": campaign.provider_campaign_id,
        "created": bool(created),
    }


def _normalize_provider(value: Any) -> str:
    if not isinstance(value, str):
        raise MarketingCampaignV2ProviderBindingValidationError(
            "provider debe ser texto."
        )
    normalized = value.strip().upper()
    if not normalized:
        raise MarketingCampaignV2ProviderBindingValidationError(
            "provider es obligatorio."
        )
    if len(normalized) > 50:
        raise MarketingCampaignV2ProviderBindingValidationError(
            "provider excede 50 caracteres."
        )
    return normalized


def _normalize_provider_campaign_id(value: Any) -> str:
    if not isinstance(value, str):
        raise MarketingCampaignV2ProviderBindingValidationError(
            "provider_campaign_id debe ser texto."
        )
    normalized = value.strip()
    if not normalized:
        raise MarketingCampaignV2ProviderBindingValidationError(
            "provider_campaign_id es obligatorio."
        )
    if len(normalized) > 255:
        raise MarketingCampaignV2ProviderBindingValidationError(
            "provider_campaign_id excede 255 caracteres."
        )
    return normalized


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        raise MarketingCampaignV2ProviderBindingValidationError(
            "campaign_id inválido."
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2ProviderBindingValidationError(
            "campaign_id inválido."
        ) from exc
    if parsed <= 0:
        raise MarketingCampaignV2ProviderBindingValidationError(
            "campaign_id inválido."
        )
    return parsed


def _normalize_now(value: datetime | None) -> datetime:
    now = value if value is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)
