"""Cliente HTTP read-only para estadísticas de campañas iVentas."""

from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import quote

import requests


DEFAULT_BASE_URL = "https://rest.iventas.mx"
CAMPAIGN_STATS_PATH = "/v2/broadcast/stats/{campaign_id}"

DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_READ_TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 3
FALLBACK_RETRY_DELAYS_SECONDS = (2.0, 5.0)
MAX_SYNCHRONOUS_RETRY_AFTER_SECONDS = 60.0
RETRYABLE_STATUS_CODES = frozenset({
    429, 500, 502, 503, 504,
})


class IVentasCampaignsClientError(RuntimeError):
    """Error base del cliente de campañas iVentas."""


class IVentasCampaignsConfigurationError(
    IVentasCampaignsClientError
):
    """Configuración local inválida o incompleta."""


class IVentasCampaignsTransportError(
    IVentasCampaignsClientError
):
    """Fallo de red o timeout tras agotar retries."""


class IVentasCampaignsPayloadError(
    IVentasCampaignsClientError
):
    """Respuesta HTTP exitosa con JSON inválido."""


class IVentasCampaignsProviderError(
    IVentasCampaignsClientError
):
    """Respuesta HTTP de error emitida por iVentas."""

    def __init__(
        self,
        *,
        status_code: int,
        provider_code: str | None,
        support_ref: str | None,
        retryable: bool,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.status_code = status_code
        self.provider_code = provider_code
        self.support_ref = support_ref
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds

        super().__init__(
            f"iVentas campaigns HTTP {status_code}"
        )


class IVentasCampaignsClient:
    """Cliente GET-only para /v2/broadcast/stats/{campaign_id}."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
        connect_timeout_seconds: float = (
            DEFAULT_CONNECT_TIMEOUT_SECONDS
        ),
        read_timeout_seconds: float = (
            DEFAULT_READ_TIMEOUT_SECONDS
        ),
        sleeper: Callable[[float], None] = time.sleep,
        now_utc: Callable[[], datetime] | None = None,
        max_sync_retry_after_seconds: float = (
            MAX_SYNCHRONOUS_RETRY_AFTER_SECONDS
        ),
    ) -> None:
        resolved_api_key = (
            os.getenv("IVENTAS_CAMPAIGNS_API_KEY", "")
            if api_key is None
            else api_key
        ).strip()

        if not resolved_api_key:
            raise IVentasCampaignsConfigurationError(
                "IVENTAS_CAMPAIGNS_API_KEY no está configurada."
            )

        resolved_base_url = (
            os.getenv(
                "IVENTAS_CAMPAIGNS_API_BASE_URL",
                DEFAULT_BASE_URL,
            )
            if base_url is None
            else base_url
        ).strip().rstrip("/")

        if not resolved_base_url:
            raise IVentasCampaignsConfigurationError(
                "IVENTAS_CAMPAIGNS_API_BASE_URL está vacío."
            )

        if connect_timeout_seconds <= 0:
            raise IVentasCampaignsConfigurationError(
                "connect_timeout_seconds debe ser > 0."
            )

        if read_timeout_seconds <= 0:
            raise IVentasCampaignsConfigurationError(
                "read_timeout_seconds debe ser > 0."
            )

        if max_sync_retry_after_seconds < 0:
            raise IVentasCampaignsConfigurationError(
                "max_sync_retry_after_seconds debe ser >= 0."
            )

        self._api_key = resolved_api_key
        self._base_url = resolved_base_url
        self._session = session or requests.Session()
        self._timeout = (
            float(connect_timeout_seconds),
            float(read_timeout_seconds),
        )
        self._sleeper = sleeper
        self._now_utc = now_utc or (
            lambda: datetime.now(timezone.utc)
        )
        self._max_sync_retry_after_seconds = float(
            max_sync_retry_after_seconds
        )

    def get_campaign_stats(
        self,
        campaign_id: str,
    ) -> dict[str, Any]:
        campaign_value = str(campaign_id or "").strip()

        if not campaign_value:
            raise ValueError(
                "campaign_id no puede estar vacío."
            )

        escaped_campaign_id = quote(
            campaign_value,
            safe="",
        )
        url = (
            f"{self._base_url}"
            f"{CAMPAIGN_STATS_PATH.format(campaign_id=escaped_campaign_id)}"
        )

        response = self._get_with_retries(url=url)
        if response.status_code != 200:
            raise self._provider_error(response)

        try:
            payload = response.json()
        except ValueError:
            raise IVentasCampaignsPayloadError(
                "iVentas campaigns returned invalid JSON."
            ) from None

        if not isinstance(payload, dict):
            raise IVentasCampaignsPayloadError(
                "iVentas campaigns payload must be an object."
            )

        return payload

    def _get_with_retries(
        self,
        *,
        url: str,
    ) -> requests.Response:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._session.get(
                    url,
                    headers=headers,
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                if attempt < MAX_ATTEMPTS:
                    self._sleeper(
                        FALLBACK_RETRY_DELAYS_SECONDS[
                            attempt - 1
                        ]
                    )
                    continue

                raise IVentasCampaignsTransportError(
                    "Error de transporte al consultar "
                    "iVentas campaigns: "
                    f"{exc.__class__.__name__}."
                ) from None

            if (
                response.status_code
                not in RETRYABLE_STATUS_CODES
            ):
                return response

            retry_after = self._retry_after_seconds(
                response
            )

            if (
                retry_after is not None
                and retry_after
                > self._max_sync_retry_after_seconds
            ):
                raise self._provider_error(
                    response,
                    retry_after_seconds=retry_after,
                )

            if attempt >= MAX_ATTEMPTS:
                raise self._provider_error(
                    response,
                    retry_after_seconds=retry_after,
                )

            delay = (
                retry_after
                if retry_after is not None
                else FALLBACK_RETRY_DELAYS_SECONDS[
                    attempt - 1
                ]
            )
            self._sleeper(delay)

        raise AssertionError(
            "Flujo de retries iVentas campaigns inválido."
        )

    def _retry_after_seconds(
        self,
        response: requests.Response,
    ) -> float | None:
        raw = response.headers.get("Retry-After")

        if raw is None:
            return None

        value = str(raw).strip()

        if not value:
            return None

        try:
            delta_seconds = int(value)
        except ValueError:
            delta_seconds = None
        if (
            delta_seconds is not None
            and delta_seconds >= 0
        ):
            return float(delta_seconds)

        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None

        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(
                tzinfo=timezone.utc
            )

        now = self._now_utc()

        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        seconds = (
            retry_at.astimezone(timezone.utc)
            - now.astimezone(timezone.utc)
        ).total_seconds()

        return float(max(0, math.ceil(seconds)))

    def _provider_error(
        self,
        response: requests.Response,
        *,
        retry_after_seconds: float | None = None,
    ) -> IVentasCampaignsProviderError:
        provider_code, support_ref = (
            self._safe_error_metadata(response)
        )

        return IVentasCampaignsProviderError(
            status_code=response.status_code,
            provider_code=provider_code,
            support_ref=support_ref,
            retryable=(
                response.status_code
                in RETRYABLE_STATUS_CODES
            ),
            retry_after_seconds=retry_after_seconds,
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
            payload.get("error")
        )
        support_ref = self._safe_scalar(
            payload.get("supportRef")
        )

        return provider_code, support_ref
    def _safe_scalar(
        self,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(
            value,
            (str, int, float, bool),
        ):
            return None

        text = str(value)
        text = text.replace(
            self._api_key,
            "<redacted>",
        )

        return text[:200]
