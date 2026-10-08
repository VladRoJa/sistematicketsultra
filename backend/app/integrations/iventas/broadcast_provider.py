"""Write-only iVentas adapter for Campaign V2 controlled submit.

Important: create calls are never retried automatically because a timeout/5xx may
mean the provider accepted the broadcast before the connection failed.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from app.services.marketing_campaign_v2_provider import (
    CampaignProviderAmbiguousError,
    CampaignProviderConfigurationError,
    CampaignProviderCreateResult,
    CampaignProviderDeterministicError,
    CampaignProviderDispatchBatch,
)


DEFAULT_BASE_URL = "https://rest.iventas.mx"
BROADCAST_PATH = "/v2/broadcast"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_READ_TIMEOUT_SECONDS = 30.0


class IVentasBroadcastProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS,
    ) -> None:
        resolved_api_key = (
            os.getenv("IVENTAS_CAMPAIGN_SEND_API_KEY", "")
            if api_key is None
            else api_key
        ).strip()
        if not resolved_api_key:
            raise CampaignProviderConfigurationError(
                "IVENTAS_CAMPAIGN_SEND_API_KEY no está configurada."
            )
        if not resolved_api_key.startswith("ivk_live_"):
            raise CampaignProviderConfigurationError(
                "Campaign V2 submit requiere una integration key iVentas."
            )

        resolved_base_url = (
            os.getenv(
                "IVENTAS_CAMPAIGN_SEND_API_BASE_URL",
                DEFAULT_BASE_URL,
            )
            if base_url is None
            else base_url
        ).strip().rstrip("/")
        if not resolved_base_url:
            raise CampaignProviderConfigurationError(
                "IVENTAS_CAMPAIGN_SEND_API_BASE_URL está vacío."
            )
        if connect_timeout_seconds <= 0 or read_timeout_seconds <= 0:
            raise CampaignProviderConfigurationError(
                "Los timeouts del provider deben ser > 0."
            )

        self._api_key = resolved_api_key
        self._base_url = resolved_base_url
        self._session = session or requests.Session()
        self._timeout = (
            float(connect_timeout_seconds),
            float(read_timeout_seconds),
        )

    def create_campaign(
        self,
        batch: CampaignProviderDispatchBatch,
    ) -> CampaignProviderCreateResult:
        payload = self._request_payload(batch)
        url = f"{self._base_url}{BROADCAST_PATH}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            response = self._session.post(
                url,
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise CampaignProviderAmbiguousError(
                code=f"TRANSPORT_{exc.__class__.__name__.upper()}",
                http_status=None,
                support_ref=None,
            ) from None

        if response.status_code == 200:
            return self._parse_success(response)

        provider_code, support_ref = self._safe_error_metadata(response)
        code = provider_code or f"HTTP_{response.status_code}"

        if response.status_code == 409 or response.status_code == 429:
            raise CampaignProviderAmbiguousError(
                code=code,
                http_status=response.status_code,
                support_ref=support_ref,
            )

        if response.status_code >= 500:
            raise CampaignProviderAmbiguousError(
                code=code,
                http_status=response.status_code,
                support_ref=support_ref,
            )

        if 400 <= response.status_code < 500:
            raise CampaignProviderDeterministicError(
                code=code,
                http_status=response.status_code,
                support_ref=support_ref,
            )

        raise CampaignProviderAmbiguousError(
            code=code,
            http_status=response.status_code,
            support_ref=support_ref,
        )

    def _request_payload(
        self,
        batch: CampaignProviderDispatchBatch,
    ) -> dict[str, Any]:
        provider = str(batch.provider or "").strip().upper()
        channel_id = str(batch.provider_channel_id or "").strip()
        template_name = str(batch.template_name or "").strip()
        campaign_name = str(batch.campaign_name or "").strip()

        if provider != "IVENTAS":
            raise CampaignProviderConfigurationError(
                "IVentasBroadcastProvider solo admite provider IVENTAS."
            )
        if not channel_id:
            raise CampaignProviderConfigurationError(
                "provider_channel_id es obligatorio."
            )
        if not template_name:
            raise CampaignProviderConfigurationError(
                "template_name es obligatorio."
            )
        if not campaign_name:
            raise CampaignProviderConfigurationError(
                "campaign_name es obligatorio."
            )
        if not batch.leads:
            raise CampaignProviderConfigurationError(
                "El batch no tiene leads."
            )

        leads: list[dict[str, Any]] = []
        for lead in batch.leads:
            phone = str(lead.phone or "").strip()
            if not phone or not phone.isdigit():
                raise CampaignProviderConfigurationError(
                    "Todos los leads deben tener teléfono internacional numérico."
                )
            leads.append(lead.to_payload())

        payload: dict[str, Any] = {
            "templateName": template_name,
            "leads": leads,
            "channelId": channel_id,
            "name": campaign_name,
        }
        if batch.send_at is not None:
            send_at = str(batch.send_at).strip()
            if not send_at:
                raise CampaignProviderConfigurationError(
                    "send_at no puede estar vacío cuando está configurado."
                )
            payload["sendAt"] = send_at
        if batch.file_url is not None:
            file_url = str(batch.file_url).strip()
            if not file_url:
                raise CampaignProviderConfigurationError(
                    "file_url no puede estar vacío cuando está configurado."
                )
            payload["fileUrl"] = file_url
        return payload

    def _parse_success(
        self,
        response: requests.Response,
    ) -> CampaignProviderCreateResult:
        try:
            payload = response.json()
        except ValueError:
            raise CampaignProviderAmbiguousError(
                code="INVALID_SUCCESS_JSON",
                http_status=response.status_code,
                support_ref=None,
            ) from None

        if not isinstance(payload, dict):
            raise CampaignProviderAmbiguousError(
                code="INVALID_SUCCESS_PAYLOAD",
                http_status=response.status_code,
                support_ref=None,
            )

        campaign_id = self._safe_scalar(payload.get("campaign"))
        if not campaign_id:
            raise CampaignProviderAmbiguousError(
                code="MISSING_CAMPAIGN_ID",
                http_status=response.status_code,
                support_ref=self._safe_scalar(payload.get("supportRef")),
            )

        raw_deduplicated = payload.get("deduplicated", False)
        if not isinstance(raw_deduplicated, bool):
            raise CampaignProviderAmbiguousError(
                code="INVALID_DEDUPLICATED_FLAG",
                http_status=response.status_code,
                support_ref=self._safe_scalar(payload.get("supportRef")),
            )

        metadata = {
            "campaign": campaign_id,
            "deduplicated": raw_deduplicated,
        }
        return CampaignProviderCreateResult(
            provider_campaign_id=campaign_id,
            deduplicated=raw_deduplicated,
            http_status=response.status_code,
            response_metadata=metadata,
        )

    def _safe_error_metadata(
        self,
        response: requests.Response,
    ) -> tuple[str | None, str | None]:
        try:
            payload = response.json()
        except ValueError:
            return None, None

        if not isinstance(payload, dict):
            return None, None

        provider_code = self._safe_scalar(
            payload.get("error") or payload.get("userMessage")
        )
        support_ref = self._safe_scalar(payload.get("supportRef"))
        return provider_code, support_ref

    def _safe_scalar(self, value: Any) -> str | None:
        if value is None or not isinstance(value, (str, int, float, bool)):
            return None
        text = str(value).replace(self._api_key, "<redacted>").strip()
        return text[:200] or None
