"""Resolver pequeño de CampaignProvider por provider key persistido."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from app.integrations.iventas.campaigns_client import IVentasCampaignsClient
from app.services.marketing_campaign_iventas_provider import (
    IVentasCampaignProvider,
)
from app.services.marketing_campaign_provider import CampaignProvider


CampaignProviderFactory = Callable[[], CampaignProvider]


class CampaignProviderResolutionError(RuntimeError):
    """Provider key vacío, desconocido o no soportado."""


def _build_iventas_provider() -> CampaignProvider:
    return IVentasCampaignProvider(
        client=IVentasCampaignsClient(),
    )


_DEFAULT_PROVIDER_FACTORIES: dict[str, CampaignProviderFactory] = {
    "IVENTAS": _build_iventas_provider,
}


def resolve_campaign_provider(
    provider_key: str,
    *,
    factories: Mapping[str, CampaignProviderFactory] | None = None,
) -> CampaignProvider:
    """Resuelve un provider sin conocer Flask ni acceder a DB."""

    normalized = _normalize_provider_key(provider_key)
    registry = (
        _DEFAULT_PROVIDER_FACTORIES
        if factories is None
        else factories
    )
    factory = registry.get(normalized)

    if factory is None:
        raise CampaignProviderResolutionError(
            f"Campaign provider no soportado: {normalized}."
        )

    return factory()


def _normalize_provider_key(provider_key: str) -> str:
    if not isinstance(provider_key, str):
        raise CampaignProviderResolutionError(
            "Campaign provider inválido."
        )

    normalized = provider_key.strip().upper()

    if not normalized:
        raise CampaignProviderResolutionError(
            "Campaign provider inválido."
        )

    return normalized
