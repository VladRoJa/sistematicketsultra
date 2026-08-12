"""Persistencia estructurada de páginas iVentas.

Responsabilidad:

contactos normalizados
    -> marketing_iventas_contacts
    -> marketing_iventas_contact_tags

La respuesta raw debe haber sido persistida y confirmada antes
de invocar este módulo.

Este módulo:
- no hace HTTP;
- no resuelve sucursales;
- no escribe raw pages;
- no actualiza estado/counters del sync run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from app.extensions import db
from app.models import (
    MarketingIventasContactORM,
    MarketingIventasContactTagORM,
)
from app.services.marketing_iventas_service import (
    MarketingIventasNormalizedContact,
)


class MarketingIventasStructuredPersistenceError(
    RuntimeError
):
    """Inconsistencia al persistir snapshot estructurado."""


@dataclass(frozen=True)
class MarketingIventasStructuredPageResult:
    """Resultado de persistencia de una página estructurada."""

    contacts_received: int
    contacts_created: int
    contacts_existing: int
    tags_created: int
    contact_row_ids: tuple[int, ...]


def _session_or_default(session: Any | None):
    return (
        session
        if session is not None
        else db.session
    )


def persist_iventas_normalized_page(
    *,
    sync_run_id: int,
    contacts: Iterable[
        MarketingIventasNormalizedContact
    ],
    observed_at: datetime,
    session: Any | None = None,
) -> MarketingIventasStructuredPageResult:
    """Persiste una página de contactos como snapshot inmutable.

    La página estructurada completa se confirma en una sola
    transacción.

    Si un contacto ya existe dentro del mismo run:
    - mismo row_hash + mismos tags: idempotente;
    - cualquier diferencia: error.

    Nunca realiza UPDATE destructivo de contactos o tags.
    """

    if (
        isinstance(sync_run_id, bool)
        or not isinstance(sync_run_id, int)
        or sync_run_id <= 0
    ):
        raise ValueError(
            "sync_run_id debe ser un entero positivo."
        )

    if (
        observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise ValueError(
            "observed_at debe tener timezone."
        )

    observed_at_utc = observed_at.astimezone(
        timezone.utc
    )

    normalized_contacts = tuple(
        contacts
    )

    for contact in normalized_contacts:
        if not isinstance(
            contact,
            MarketingIventasNormalizedContact,
        ):
            raise TypeError(
                "contacts debe contener únicamente "
                "MarketingIventasNormalizedContact."
            )

    branch_codes = {
        contact.branch_code
        for contact in normalized_contacts
    }

    if len(branch_codes) > 1:
        raise ValueError(
            "Una página estructurada no puede "
            "mezclar branch_code."
        )

    identities = [
        (
            contact.branch_code,
            contact.contact_id,
        )
        for contact in normalized_contacts
    ]

    if len(identities) != len(
        set(identities)
    ):
        raise MarketingIventasStructuredPersistenceError(
            "La página contiene contact_id duplicado "
            "para la misma sucursal."
        )

    session_value = _session_or_default(
        session
    )

    contacts_created = 0
    contacts_existing = 0
    tags_created = 0
    contact_row_ids: list[int] = []

    try:
        for normalized in normalized_contacts:
            existing = (
                session_value.query(
                    MarketingIventasContactORM
                )
                .filter_by(
                    sync_run_id=sync_run_id,
                    branch_code=(
                        normalized.branch_code
                    ),
                    contact_id=(
                        normalized.contact_id
                    ),
                )
                .first()
            )

            if existing is not None:
                _validate_existing_contact_snapshot(
                    session=session_value,
                    sync_run_id=sync_run_id,
                    existing=existing,
                    normalized=normalized,
                )

                if existing.id is None:
                    raise (
                        MarketingIventasStructuredPersistenceError(
                            "Contacto existente sin id."
                        )
                    )

                contacts_existing += 1
                contact_row_ids.append(
                    int(existing.id)
                )
                continue

            contact_row = (
                _build_contact_row(
                    sync_run_id=sync_run_id,
                    normalized=normalized,
                )
            )

            session_value.add(
                contact_row
            )

            # Necesitamos id antes de construir FK compuesta
            # de marketing_iventas_contact_tags.
            session_value.flush()

            if contact_row.id is None:
                raise (
                    MarketingIventasStructuredPersistenceError(
                        "El contacto no obtuvo id "
                        "después de flush."
                    )
                )

            contact_row_id = int(
                contact_row.id
            )

            tag_rows = [
                MarketingIventasContactTagORM(
                    sync_run_id=sync_run_id,
                    iventas_contact_row_id=(
                        contact_row_id
                    ),
                    branch_code=(
                        normalized.branch_code
                    ),
                    contact_id=(
                        normalized.contact_id
                    ),
                    tag_raw=tag.tag_raw,
                    tag_kind=tag.tag_kind,
                    meta_ad_id=(
                        tag.meta_ad_id
                    ),
                    observed_at=(
                        observed_at_utc
                    ),
                )
                for tag in normalized.tags
            ]

            if tag_rows:
                session_value.add_all(
                    tag_rows
                )

            contacts_created += 1
            tags_created += len(
                tag_rows
            )

            contact_row_ids.append(
                contact_row_id
            )

        if contacts_created > 0:
            session_value.commit()

        return MarketingIventasStructuredPageResult(
            contacts_received=len(
                normalized_contacts
            ),
            contacts_created=(
                contacts_created
            ),
            contacts_existing=(
                contacts_existing
            ),
            tags_created=tags_created,
            contact_row_ids=tuple(
                contact_row_ids
            ),
        )

    except Exception:
        session_value.rollback()
        raise


def _build_contact_row(
    *,
    sync_run_id: int,
    normalized: MarketingIventasNormalizedContact,
) -> MarketingIventasContactORM:
    return MarketingIventasContactORM(
        sync_run_id=sync_run_id,
        sucursal_id=normalized.sucursal_id,
        branch_code=normalized.branch_code,
        contact_id=normalized.contact_id,
        name=normalized.name,
        phone_raw=normalized.phone_raw,
        phone_digits=normalized.phone_digits,
        phone_mx10=normalized.phone_mx10,
        phone_match_status=(
            normalized.phone_match_status
        ),
        created_at_utc=(
            normalized.created_at_utc
        ),
        created_at_local=(
            normalized.created_at_local
        ),
        created_date_local=(
            normalized.created_date_local
        ),
        first_message_at_utc=(
            normalized.first_message_at_utc
        ),
        first_message_at_local=(
            normalized.first_message_at_local
        ),
        first_message_date_local=(
            normalized.first_message_date_local
        ),
        channel_id=normalized.channel_id,
        channel_name=normalized.channel_name,
        channel_phone=normalized.channel_phone,
        channel_platform=(
            normalized.channel_platform
        ),
        agent_json=(
            dict(normalized.agent_json)
            if normalized.agent_json
            is not None
            else None
        ),
        last_message_status=(
            normalized.last_message_status
        ),
        last_outbound_message_at_utc=(
            normalized
            .last_outbound_message_at_utc
        ),
        row_hash=normalized.row_hash,
    )


def _validate_existing_contact_snapshot(
    *,
    session: Any,
    sync_run_id: int,
    existing: MarketingIventasContactORM,
    normalized: MarketingIventasNormalizedContact,
) -> None:
    """Valida idempotencia sin mutar una foto existente."""

    if (
        existing.sucursal_id
        != normalized.sucursal_id
        or existing.row_hash
        != normalized.row_hash
    ):
        raise MarketingIventasStructuredPersistenceError(
            "El contacto ya existe dentro del run "
            "con contenido estructurado diferente."
        )

    existing_tags = (
        session.query(
            MarketingIventasContactTagORM
        )
        .filter_by(
            sync_run_id=sync_run_id,
            iventas_contact_row_id=existing.id,
        )
        .all()
    )

    existing_tag_set = {
        (
            tag.tag_raw,
            tag.tag_kind,
            tag.meta_ad_id,
        )
        for tag in existing_tags
    }

    normalized_tag_set = {
        (
            tag.tag_raw,
            tag.tag_kind,
            tag.meta_ad_id,
        )
        for tag in normalized.tags
    }

    if existing_tag_set != normalized_tag_set:
        raise MarketingIventasStructuredPersistenceError(
            "El contacto ya existe dentro del run "
            "con observaciones de tags diferentes."
        )
