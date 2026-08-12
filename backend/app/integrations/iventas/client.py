"""Cliente HTTP aislado para la API de contactos de iVentas.

Responsabilidades:
- autenticación;
- GET de contactos;
- timeout explícito;
- rate limiting;
- retries controlados;
- paginación HTTP;
- errores del proveedor.

Este módulo NO conoce SQLAlchemy, Track, MarketingAccess,
timezone comercial, normalización ni reglas de negocio.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

import requests


DEFAULT_BASE_URL = "https://rest.iventas.mx"
CONTACTS_PATH = "/v1/integrations/contacts"

DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_READ_TIMEOUT_SECONDS = 30.0

DEFAULT_MAX_REQUESTS_PER_MINUTE = 40

RETRYABLE_STATUS_CODES = frozenset({
    429,
    500,
    503,
})

RETRY_DELAYS_SECONDS = (
    2.0,
    5.0,
    10.0,
)


class IventasClientError(RuntimeError):
    """Error base del cliente iVentas."""


class IventasConfigurationError(IventasClientError):
    """Configuración local inválida o incompleta."""


class IventasTransportError(IventasClientError):
    """Fallo de red o timeout antes de obtener respuesta válida."""


class IventasPayloadError(IventasClientError):
    """Respuesta HTTP 200 con estructura incompatible."""


class IventasProviderError(IventasClientError):
    """Respuesta de error emitida por iVentas."""

    def __init__(
        self,
        *,
        status_code: int,
        provider_code: str | None,
        retryable: bool,
    ) -> None:
        self.status_code = status_code
        self.provider_code = provider_code
        self.retryable = retryable

        safe_code = provider_code or "(sin código)"

        super().__init__(
            f"iVentas HTTP {status_code}: {safe_code}"
        )


@dataclass(frozen=True)
class IventasRawPageResponse:
    """Respuesta HTTP capturada antes de estructurar.

    raw_payload conserva exactamente response.text.

    _response se mantiene únicamente en memoria para que
    parse_page() pueda ejecutarse DESPUÉS de persistir raw.
    No participa en repr para evitar exposición accidental.
    """

    request_cursor: str | None
    http_status: int
    raw_payload: str

    _response: requests.Response = field(
        repr=False,
        compare=False,
    )


@dataclass(frozen=True)
class IventasPage:
    """Una página recibida del endpoint de contactos."""

    request_cursor: str | None
    http_status: int

    # Texto recibido, destinado posteriormente al raw storage.
    # Nunca debe imprimirse en logs.
    raw_payload: str

    # Parseo del mismo payload para consumo estructurado.
    payload: dict[str, Any]

    contacts: list[Any]

    has_more: bool
    next_cursor: str | None

    provider_branch_code: str | None
    provider_branch_label: str | None


class IventasClient:
    """Cliente HTTP secuencial para /v1/integrations/contacts."""

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
        connect_timeout_seconds: float = (
            DEFAULT_CONNECT_TIMEOUT_SECONDS
        ),
        read_timeout_seconds: float = (
            DEFAULT_READ_TIMEOUT_SECONDS
        ),
        max_requests_per_minute: int = (
            DEFAULT_MAX_REQUESTS_PER_MINUTE
        ),
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        resolved_token = (
            os.getenv("IVENTAS_API_TOKEN", "")
            if token is None
            else token
        ).strip()

        if not resolved_token:
            raise IventasConfigurationError(
                "IVENTAS_API_TOKEN no está configurado."
            )

        resolved_base_url = (
            os.getenv(
                "IVENTAS_API_BASE_URL",
                DEFAULT_BASE_URL,
            )
            if base_url is None
            else base_url
        ).strip().rstrip("/")

        if not resolved_base_url:
            raise IventasConfigurationError(
                "IVENTAS_API_BASE_URL está vacío."
            )

        if connect_timeout_seconds <= 0:
            raise IventasConfigurationError(
                "connect_timeout_seconds debe ser > 0."
            )

        if read_timeout_seconds <= 0:
            raise IventasConfigurationError(
                "read_timeout_seconds debe ser > 0."
            )

        if not 1 <= max_requests_per_minute <= 40:
            raise IventasConfigurationError(
                "max_requests_per_minute debe estar entre 1 y 40."
            )

        self._token = resolved_token
        self._base_url = resolved_base_url
        self._session = session or requests.Session()

        self._timeout = (
            float(connect_timeout_seconds),
            float(read_timeout_seconds),
        )

        self._minimum_request_interval_seconds = (
            60.0 / float(max_requests_per_minute)
        )

        self._sleeper = sleeper
        self._monotonic = monotonic

        self._rate_lock = threading.Lock()
        self._last_request_started_at: float | None = None

    @property
    def contacts_url(self) -> str:
        return (
            f"{self._base_url}"
            f"{CONTACTS_PATH}"
        )

    def request_page_raw(
        self,
        *,
        branch: str,
        from_utc: str,
        to_utc: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> IventasRawPageResponse:
        """Solicita una página sin estructurar el payload.

        Frontera raw-first prevista:

        request_page_raw()
            -> persistir raw_payload
            -> parse_page()
        """

        branch_value = branch.strip()
        from_value = from_utc.strip()
        to_value = to_utc.strip()

        if not branch_value:
            raise ValueError(
                "branch no puede estar vacío."
            )

        if not from_value:
            raise ValueError(
                "from_utc no puede estar vacío."
            )

        if not to_value:
            raise ValueError(
                "to_utc no puede estar vacío."
            )

        if not 1 <= limit <= 100:
            raise ValueError(
                "limit debe estar entre 1 y 100."
            )

        cursor_value = (
            cursor.strip()
            if isinstance(cursor, str)
            else None
        )

        if (
            cursor is not None
            and not cursor_value
        ):
            raise ValueError(
                "cursor no puede ser una cadena vacía."
            )

        params: dict[str, Any] = {
            "branch": branch_value,
            "from": from_value,
            "to": to_value,
            "limit": limit,
        }

        if cursor_value is not None:
            params["cursor"] = cursor_value

        response = self._get_with_retries(
            params=params,
        )

        return IventasRawPageResponse(
            request_cursor=cursor_value,
            http_status=response.status_code,
            raw_payload=response.text,
            _response=response,
        )

    def parse_page(
        self,
        raw_response: IventasRawPageResponse,
    ) -> IventasPage:
        """Estructura una respuesta previamente capturada.

        Este método no realiza ninguna llamada HTTP.
        """

        if not isinstance(
            raw_response,
            IventasRawPageResponse,
        ):
            raise TypeError(
                "raw_response debe ser "
                "IventasRawPageResponse."
            )

        response = raw_response._response

        if raw_response.http_status != 200:
            raise IventasProviderError(
                status_code=(
                    raw_response.http_status
                ),
                provider_code=(
                    self._safe_error_code(
                        response
                    )
                ),
                retryable=(
                    raw_response.http_status
                    in RETRYABLE_STATUS_CODES
                ),
            )

        try:
            payload = response.json()
        except ValueError:
            raise IventasPayloadError(
                "iVentas respondió HTTP 200 "
                "con JSON inválido."
            ) from None

        if not isinstance(payload, dict):
            raise IventasPayloadError(
                "La respuesta iVentas no es "
                "un objeto JSON."
            )

        contacts = payload.get("contacts")
        pagination = payload.get("pagination")
        provider_branch = payload.get("branch")

        if not isinstance(contacts, list):
            raise IventasPayloadError(
                "'contacts' no es una lista."
            )

        if not isinstance(pagination, dict):
            raise IventasPayloadError(
                "Falta objeto 'pagination'."
            )

        has_more = bool(
            pagination.get("hasMore")
        )

        raw_next_cursor = pagination.get(
            "nextCursor"
        )

        next_cursor = (
            str(raw_next_cursor).strip()
            if raw_next_cursor is not None
            else None
        )

        if next_cursor == "":
            next_cursor = None

        if has_more and next_cursor is None:
            raise IventasPayloadError(
                "hasMore=true pero nextCursor "
                "está vacío."
            )

        provider_branch_code: str | None = None
        provider_branch_label: str | None = None

        if isinstance(provider_branch, dict):
            raw_code = provider_branch.get("code")
            raw_label = provider_branch.get(
                "label"
            )

            if raw_code is not None:
                provider_branch_code = str(
                    raw_code
                )

            if raw_label is not None:
                provider_branch_label = str(
                    raw_label
                )

        return IventasPage(
            request_cursor=(
                raw_response.request_cursor
            ),
            http_status=(
                raw_response.http_status
            ),
            raw_payload=(
                raw_response.raw_payload
            ),
            payload=payload,
            contacts=contacts,
            has_more=has_more,
            next_cursor=next_cursor,
            provider_branch_code=(
                provider_branch_code
            ),
            provider_branch_label=(
                provider_branch_label
            ),
        )

    def fetch_page(
        self,
        *,
        branch: str,
        from_utc: str,
        to_utc: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> IventasPage:
        """Conveniencia: captura raw y después estructura.

        Los sincronizadores raw-first deben llamar
        request_page_raw() y parse_page() explícitamente
        para persistir entre ambos pasos.
        """

        raw_response = self.request_page_raw(
            branch=branch,
            from_utc=from_utc,
            to_utc=to_utc,
            limit=limit,
            cursor=cursor,
        )

        return self.parse_page(
            raw_response
        )


    def iter_pages(
        self,
        *,
        branch: str,
        from_utc: str,
        to_utc: str,
        limit: int = 100,
    ) -> Iterator[IventasPage]:
        """Recorre la paginación completa de una sucursal."""

        cursor: str | None = None
        seen_cursors: set[str] = set()

        while True:
            page = self.fetch_page(
                branch=branch,
                from_utc=from_utc,
                to_utc=to_utc,
                limit=limit,
                cursor=cursor,
            )

            yield page

            if not page.has_more:
                return

            next_cursor = page.next_cursor

            if next_cursor is None:
                raise IventasPayloadError(
                    "Paginación incompleta: "
                    "nextCursor ausente."
                )

            if next_cursor in seen_cursors:
                raise IventasPayloadError(
                    "iVentas devolvió un cursor "
                    "de paginación repetido."
                )

            seen_cursors.add(next_cursor)
            cursor = next_cursor

    def _get_with_retries(
        self,
        *,
        params: dict[str, Any],
    ) -> requests.Response:
        """Devuelve la respuesta HTTP final.

        429/500/503 se reintentan con 2s, 5s y 10s.

        Una respuesta final non-200 también se devuelve,
        en vez de lanzar aquí, para permitir que su
        response.text pueda persistirse antes de parsearla.
        """

        headers = {
            "Authorization": (
                f"Bearer {self._token}"
            ),
            "Accept": "application/json",
        }

        total_attempts = (
            1 + len(RETRY_DELAYS_SECONDS)
        )

        for attempt in range(
            1,
            total_attempts + 1,
        ):
            self._wait_for_rate_limit()

            try:
                response = self._session.get(
                    self.contacts_url,
                    headers=headers,
                    params=params,
                    timeout=self._timeout,
                )
            except requests.Timeout:
                raise IventasTransportError(
                    "Timeout al consultar iVentas."
                ) from None
            except requests.RequestException as exc:
                raise IventasTransportError(
                    "Error de transporte al consultar "
                    f"iVentas: "
                    f"{exc.__class__.__name__}."
                ) from None

            retryable = (
                response.status_code
                in RETRYABLE_STATUS_CODES
            )

            if (
                retryable
                and attempt < total_attempts
            ):
                delay = RETRY_DELAYS_SECONDS[
                    attempt - 1
                ]

                self._sleeper(delay)
                continue

            return response

        raise AssertionError(
            "Flujo de retries iVentas inválido."
        )


    def _wait_for_rate_limit(self) -> None:
        with self._rate_lock:
            now = self._monotonic()

            if (
                self._last_request_started_at
                is not None
            ):
                elapsed = (
                    now
                    - self._last_request_started_at
                )

                remaining = (
                    self._minimum_request_interval_seconds
                    - elapsed
                )

                if remaining > 0:
                    self._sleeper(remaining)
                    now = self._monotonic()

            self._last_request_started_at = now

    @staticmethod
    def _safe_error_code(
        response: requests.Response,
    ) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None

        if not isinstance(payload, dict):
            return None

        error = payload.get("error")

        if error is None:
            return None

        return str(error)
