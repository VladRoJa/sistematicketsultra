"""Read-through Campaign V2 -> CampaignProvider stats, sin persistencia."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from app.extensions import db
from app.integrations.iventas.campaigns_client import (
    IVentasCampaignsClientError,
    IVentasCampaignsProviderError,
    IVentasCampaignsTransportError,
)
from app.services.marketing_campaign_iventas_stats_parser import (
    IVentasCampaignStatsPayloadError,
)
from app.services.marketing_campaign_provider import (
    CampaignProvider,
    CampaignProviderStats,
)
from app.services.marketing_campaign_provider_registry import (
    CampaignProviderResolutionError,
    resolve_campaign_provider,
)
from app.services.marketing_campaign_v2_query_service import (
    _load_visible_campaign_orm,
    _normalize_current_scope,
    _positive_int,
)


class MarketingCampaignV2ProviderStatsError(RuntimeError):
    """Base de errores read-through provider stats."""


class MarketingCampaignV2ProviderStatsUnboundError(
    MarketingCampaignV2ProviderStatsError
):
    """Campaign V2 sin binding provider completo."""


class MarketingCampaignV2ProviderStatsUnsupportedError(
    MarketingCampaignV2ProviderStatsError
):
    """Provider persistido no soportado por el registry."""


class MarketingCampaignV2ProviderStatsUpstreamError(
    MarketingCampaignV2ProviderStatsError
):
    """Fallo upstream sanitizado."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.retryable = bool(retryable)
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


ProviderResolver = Callable[[str], CampaignProvider]


@dataclass(frozen=True)
class CampaignV2ProviderStatsFetch:
    campaign_id: int
    provider: str
    provider_campaign_id: str
    stats: CampaignProviderStats


def get_campaign_v2_provider_stats(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
    provider_resolver: ProviderResolver = resolve_campaign_provider,
) -> dict[str, Any]:
    fetched = fetch_campaign_v2_provider_stats(
        campaign_id=campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=session,
        provider_resolver=provider_resolver,
    )
    return _serialize_provider_stats(
        campaign_id=fetched.campaign_id,
        provider=fetched.provider,
        provider_campaign_id=fetched.provider_campaign_id,
        stats=fetched.stats,
    )


def fetch_campaign_v2_provider_stats(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
    provider_resolver: ProviderResolver = resolve_campaign_provider,
) -> CampaignV2ProviderStatsFetch:
    active_session = session if session is not None else db.session
    normalized_campaign_id = _positive_int(
        campaign_id,
        field_name="campaign_id",
        maximum=None,
    )
    scope = _normalize_current_scope(allowed_sucursal_keys)
    with active_session.no_autoflush:
        campaign = _load_visible_campaign_orm(
            campaign_id=normalized_campaign_id,
            scope=scope,
            session=active_session,
        )

    provider_key = _clean_required(campaign.provider)
    provider_campaign_id = _clean_required(
        campaign.provider_campaign_id
    )

    if provider_key is None or provider_campaign_id is None:
        raise MarketingCampaignV2ProviderStatsUnboundError(
            "Campaign V2 no tiene provider binding completo."
        )

    try:
        provider = provider_resolver(provider_key)
    except CampaignProviderResolutionError as exc:
        raise MarketingCampaignV2ProviderStatsUnsupportedError(
            str(exc)
        ) from exc
    except IVentasCampaignsClientError as exc:
        raise MarketingCampaignV2ProviderStatsUpstreamError(
            "No fue posible inicializar el provider de campañas.",
            retryable=False,
        ) from exc

    try:
        stats = provider.get_campaign_stats(provider_campaign_id)
    except IVentasCampaignsProviderError as exc:
        raise MarketingCampaignV2ProviderStatsUpstreamError(
            "El provider de campañas respondió con error.",
            retryable=exc.retryable,
            retry_after_seconds=exc.retry_after_seconds,
        ) from exc
    except IVentasCampaignsTransportError as exc:
        raise MarketingCampaignV2ProviderStatsUpstreamError(
            "No fue posible conectar con el provider de campañas.",
            retryable=True,
        ) from exc
    except IVentasCampaignsClientError as exc:
        raise MarketingCampaignV2ProviderStatsUpstreamError(
            "El provider de campañas devolvió una respuesta inválida.",
            retryable=False,
        ) from exc
    except IVentasCampaignStatsPayloadError as exc:
        raise MarketingCampaignV2ProviderStatsUpstreamError(
            "El payload del provider no cumple el contrato Campaign V2.",
            retryable=False,
        ) from exc

    return CampaignV2ProviderStatsFetch(
        campaign_id=int(campaign.id),
        provider=provider_key,
        provider_campaign_id=provider_campaign_id,
        stats=stats,
    )


def _serialize_provider_stats(
    *,
    campaign_id: int,
    provider: str,
    provider_campaign_id: str,
    stats: CampaignProviderStats,
) -> dict[str, Any]:
    raw = stats.raw_counts

    return {
        "campaign_id": int(campaign_id),
        "provider": provider,
        "provider_campaign_id": provider_campaign_id,
        "analytics_status": stats.analytics_status,
        "raw_counts": {
            "successful": raw.successful,
            "failed": raw.failed,
            "sent": raw.sent,
            "delivered": raw.delivered,
            "viewed": raw.viewed,
            "answered": raw.answered,
            "interaction_groups": raw.interaction_groups,
            "interaction_items": raw.interaction_items,
        },
        "recipients": {
            "successful": sorted(stats.successful_phones),
            "failed": sorted(stats.failed_phones),
            "sent": sorted(stats.sent_phones),
            "delivered": sorted(stats.delivered_phones),
            "viewed": sorted(stats.viewed_phones),
        },
        "button_interactions": [
            {
                "label": interaction.label,
                "raw_item_count": interaction.raw_item_count,
                "recipient_phones": sorted(
                    interaction.unique_recipient_phones
                ),
            }
            for interaction in stats.button_interactions
        ],
        "analytics": (
            deepcopy(dict(stats.analytics))
            if stats.analytics is not None
            else None
        ),
    }


def _clean_required(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
