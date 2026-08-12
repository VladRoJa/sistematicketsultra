"""Persistencia raw-first para sincronizaciones iVentas.

Este módulo define exclusivamente las fronteras de escritura:

1. crear sync_run RUNNING y confirmar COMMIT;
2. persistir respuesta HTTP raw y confirmar COMMIT;
3. después del parse, completar metadata de paginación.

No realiza HTTP.
No normaliza contactos.
No persiste contactos ni tags.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.extensions import db
from app.integrations.iventas import (
    IventasPage,
    IventasRawPageResponse,
)
from app.models import (
    MarketingIventasRawPageORM,
    MarketingIventasSyncRunORM,
)


SYNC_STATUS_RUNNING = "RUNNING"


class MarketingIventasPersistenceError(
    RuntimeError
):
    """Inconsistencia en una frontera de persistencia iVentas."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _session_or_default(session: Any | None):
    return (
        session
        if session is not None
        else db.session
    )


def create_iventas_sync_run_running(
    *,
    period_key: str,
    date_from: date,
    date_to: date,
    branches_requested: int,
    started_at: datetime | None = None,
    session: Any | None = None,
) -> MarketingIventasSyncRunORM:
    """Crea y confirma un sync_run RUNNING.

    El COMMIT es deliberado: el run debe existir antes de
    iniciar cualquier request HTTP.
    """

    period_key_value = str(
        period_key or ""
    ).strip()

    if not period_key_value:
        raise ValueError(
            "period_key no puede estar vacío."
        )

    if len(period_key_value) > 64:
        raise ValueError(
            "period_key excede 64 caracteres."
        )

    if date_from > date_to:
        raise ValueError(
            "date_from no puede ser posterior a date_to."
        )

    if (
        isinstance(branches_requested, bool)
        or not isinstance(
            branches_requested,
            int,
        )
        or branches_requested <= 0
    ):
        raise ValueError(
            "branches_requested debe ser "
            "un entero positivo."
        )

    started = (
        started_at
        if started_at is not None
        else _utc_now()
    )

    if (
        started.tzinfo is None
        or started.utcoffset() is None
    ):
        raise ValueError(
            "started_at debe tener timezone."
        )

    session_value = _session_or_default(
        session
    )

    sync_run = MarketingIventasSyncRunORM(
        period_key=period_key_value,
        date_from=date_from,
        date_to=date_to,
        started_at=started,
        finished_at=None,
        status=SYNC_STATUS_RUNNING,
        branches_requested=branches_requested,
        branches_completed=0,
        branches_failed=0,
        contacts_received=0,
        contacts_unique=0,
        contacts_with_phone=0,
        contacts_mx10_matchable=0,
        contacts_non_mx_or_unresolved=0,
        contacts_with_first_message=0,
        contacts_with_any_tag=0,
        contacts_with_meta_ad_tag=0,
        contacts_with_multiple_meta_ad_tags=0,
        aliases_resolved=0,
        aliases_unresolved=0,
        is_canonical=False,
    )

    session_value.add(sync_run)
    session_value.commit()

    return sync_run


def persist_iventas_raw_page_pre_parse(
    *,
    sync_run_id: int,
    branch_code: str,
    page_number: int,
    raw_response: IventasRawPageResponse,
    received_at: datetime | None = None,
    session: Any | None = None,
) -> MarketingIventasRawPageORM:
    """Persiste exactamente el raw antes de parsearlo.

    `has_more`, `next_cursor` y `contacts_count`
    permanecen NULL hasta que el raw sea parseado.

    Si la misma clave run/branch/page ya existe con el mismo
    raw, la operación es idempotente y devuelve la fila.

    Si la misma clave ya existe con contenido distinto,
    falla para impedir sobrescribir historia dentro del run.
    """

    if (
        isinstance(sync_run_id, bool)
        or not isinstance(sync_run_id, int)
        or sync_run_id <= 0
    ):
        raise ValueError(
            "sync_run_id debe ser "
            "un entero positivo."
        )

    branch_value = str(
        branch_code or ""
    ).strip()

    if not branch_value:
        raise ValueError(
            "branch_code no puede estar vacío."
        )

    if (
        isinstance(page_number, bool)
        or not isinstance(page_number, int)
        or page_number < 1
    ):
        raise ValueError(
            "page_number debe ser >= 1."
        )

    if not isinstance(
        raw_response,
        IventasRawPageResponse,
    ):
        raise TypeError(
            "raw_response debe ser "
            "IventasRawPageResponse."
        )

    if not (
        100
        <= raw_response.http_status
        <= 599
    ):
        raise ValueError(
            "http_status fuera del rango HTTP."
        )

    if not isinstance(
        raw_response.raw_payload,
        str,
    ):
        raise TypeError(
            "raw_payload debe ser string."
        )

    received = (
        received_at
        if received_at is not None
        else _utc_now()
    )

    if (
        received.tzinfo is None
        or received.utcoffset() is None
    ):
        raise ValueError(
            "received_at debe tener timezone."
        )

    session_value = _session_or_default(
        session
    )

    existing = (
        session_value.query(
            MarketingIventasRawPageORM
        )
        .filter_by(
            sync_run_id=sync_run_id,
            branch_code=branch_value,
            page_number=page_number,
        )
        .first()
    )

    if existing is not None:
        same_raw_identity = (
            existing.request_cursor
            == raw_response.request_cursor
            and existing.http_status
            == raw_response.http_status
            and existing.payload_json
            == raw_response.raw_payload
        )

        if not same_raw_identity:
            raise MarketingIventasPersistenceError(
                "La página ya existe dentro del run "
                "con contenido HTTP diferente."
            )

        return existing

    raw_page = MarketingIventasRawPageORM(
        sync_run_id=sync_run_id,
        branch_code=branch_value,
        page_number=page_number,
        request_cursor=(
            raw_response.request_cursor
        ),
        next_cursor=None,
        has_more=None,
        contacts_count=None,
        http_status=(
            raw_response.http_status
        ),
        payload_json=(
            raw_response.raw_payload
        ),
        received_at=received,
    )

    session_value.add(raw_page)
    session_value.commit()

    return raw_page


def apply_iventas_raw_page_parse_metadata(
    *,
    raw_page_id: int,
    page: IventasPage,
    session: Any | None = None,
) -> MarketingIventasRawPageORM:
    """Completa metadata derivada solamente después del parse.

    El raw HTTP nunca se reemplaza ni se reserializa.
    """

    if (
        isinstance(raw_page_id, bool)
        or not isinstance(raw_page_id, int)
        or raw_page_id <= 0
    ):
        raise ValueError(
            "raw_page_id debe ser "
            "un entero positivo."
        )

    if not isinstance(
        page,
        IventasPage,
    ):
        raise TypeError(
            "page debe ser IventasPage."
        )

    session_value = _session_or_default(
        session
    )

    raw_page = session_value.get(
        MarketingIventasRawPageORM,
        raw_page_id,
    )

    if raw_page is None:
        raise MarketingIventasPersistenceError(
            "No existe la raw page indicada."
        )

    if (
        raw_page.request_cursor
        != page.request_cursor
        or raw_page.http_status
        != page.http_status
        or raw_page.payload_json
        != page.raw_payload
    ):
        raise MarketingIventasPersistenceError(
            "La página parseada no corresponde "
            "al raw persistido."
        )

    parsed_contacts_count = len(
        page.contacts
    )

    if raw_page.has_more is not None:
        same_existing_metadata = (
            raw_page.has_more
            == page.has_more
            and raw_page.next_cursor
            == page.next_cursor
        )

        if not same_existing_metadata:
            raise MarketingIventasPersistenceError(
                "La metadata de parseo ya existe "
                "con valores diferentes."
            )

        if raw_page.contacts_count is None:
            raw_page.contacts_count = (
                parsed_contacts_count
            )

            session_value.commit()

            return raw_page

        if (
            raw_page.contacts_count
            == parsed_contacts_count
        ):
            return raw_page

        raise MarketingIventasPersistenceError(
            "La metadata de parseo ya existe "
            "con contacts_count diferente."
        )

    if (
        raw_page.next_cursor is not None
        or raw_page.contacts_count is not None
    ):
        raise MarketingIventasPersistenceError(
            "La raw page contiene metadata "
            "de parseo parcial inconsistente."
        )

    raw_page.has_more = page.has_more
    raw_page.next_cursor = page.next_cursor
    raw_page.contacts_count = (
        parsed_contacts_count
    )

    session_value.commit()

    return raw_page
