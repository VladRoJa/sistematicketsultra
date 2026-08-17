"""Cliente HTTP mínimo para Meta Ads Insights a nivel anuncio."""

from __future__ import annotations

from datetime import date
import json
import os
from typing import Any

import requests

from app.services.marketing_meta_service import (
    MarketingMetaRawPageResponse,
    normalize_meta_account_id,
)


META_INSIGHT_FIELDS = (
    "account_id",
    "account_name",
    "campaign_id",
    "campaign_name",
    "adset_id",
    "adset_name",
    "ad_id",
    "ad_name",
    "date_start",
    "date_stop",
    "spend",
    "reach",
    "impressions",
    "clicks",
    "actions",
)


class MetaInsightsClientError(RuntimeError):
    """No fue posible obtener una página Meta."""


class MetaInsightsClient:
    def __init__(
        self,
        *,
        api_version: str | None = None,
        http_session: Any | None = None,
    ) -> None:
        version = str(
            api_version
            if api_version is not None
            else os.getenv("META_GRAPH_API_VERSION", "")
        ).strip().lstrip("/")
        if not version:
            raise ValueError(
                "META_GRAPH_API_VERSION no está configurado."
            )

        self.api_version = version
        self.http_session = (
            http_session if http_session is not None else requests
        )

    def fetch_insights_page(
        self,
        *,
        account_id: str,
        access_token: str,
        date_from: date,
        date_to: date,
        after: str | None = None,
        limit: int = 500,
    ) -> MarketingMetaRawPageResponse:
        account_value = normalize_meta_account_id(account_id)
        token = str(access_token or "").strip()
        if not token:
            raise ValueError("access_token Meta no puede estar vacío.")
        if date_from > date_to:
            raise ValueError(
                "date_from no puede ser posterior a date_to."
            )
        if limit <= 0 or limit > 500:
            raise ValueError("limit Meta debe estar entre 1 y 500.")

        params: dict[str, Any] = {
            "fields": ",".join(META_INSIGHT_FIELDS),
            "level": "ad",
            "time_range": json.dumps(
                {
                    "since": date_from.isoformat(),
                    "until": date_to.isoformat(),
                },
                separators=(",", ":"),
            ),
            "limit": limit,
        }
        if after:
            params["after"] = after

        url = (
            "https://graph.facebook.com/"
            f"{self.api_version}/act_{account_value}/insights"
        )
        try:
            response = self.http_session.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                params=params,
                timeout=(10, 60),
            )
        except requests.RequestException as exc:
            raise MetaInsightsClientError(
                "Falló la solicitud HTTP a Meta Ads Insights."
            ) from exc

        return MarketingMetaRawPageResponse(
            http_status=int(response.status_code),
            request_cursor=after,
            raw_payload=response.text,
        )
