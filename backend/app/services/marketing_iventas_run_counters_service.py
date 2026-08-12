"""Lectura de contadores persistidos de un run iVentas.

Este módulo reconstruye únicamente métricas derivables de
PostgreSQL.

No decide:
- branches_completed;
- branches_failed;
- aliases_resolved;
- aliases_unresolved;
- status final;
- canonicalidad.

Esas decisiones pertenecen al orquestador/lifecycle del run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import distinct, func, select

from app.extensions import db
from app.models import (
    MarketingIventasContactORM,
    MarketingIventasContactTagORM,
    MarketingIventasRawPageORM,
    MarketingIventasSyncRunORM,
)
from app.services.marketing_iventas_service import (
    PHONE_STATUS_MISSING,
    PHONE_STATUS_MX10_MATCHABLE,
    PHONE_STATUS_NON_MX_OR_UNRESOLVED,
    TAG_KIND_META_AD,
)


class MarketingIventasRunCountersReadError(
    RuntimeError
):
    """Inconsistencia al reconstruir counters persistidos."""


@dataclass(frozen=True)
class MarketingIventasStoredRunCounters:
    contacts_received: int
    contacts_unique: int

    contacts_with_phone: int
    contacts_mx10_matchable: int
    contacts_non_mx_or_unresolved: int

    contacts_with_first_message: int

    contacts_with_any_tag: int
    contacts_with_meta_ad_tag: int
    contacts_with_multiple_meta_ad_tags: int


def _session_or_default(
    session: Any | None,
):
    return (
        session
        if session is not None
        else db.session
    )


def _build_stored_run_counters_statement(
    sync_run_id: int,
):
    raw_received = (
        select(
            func.coalesce(
                func.sum(
                    MarketingIventasRawPageORM
                    .contacts_count
                ),
                0,
            )
        )
        .where(
            MarketingIventasRawPageORM
            .sync_run_id
            == sync_run_id
        )
        .scalar_subquery()
    )

    contacts_unique = (
        select(
            func.count(
                MarketingIventasContactORM.id
            )
        )
        .where(
            MarketingIventasContactORM
            .sync_run_id
            == sync_run_id
        )
        .scalar_subquery()
    )

    contacts_with_phone = (
        select(
            func.count(
                MarketingIventasContactORM.id
            )
        )
        .where(
            MarketingIventasContactORM
            .sync_run_id
            == sync_run_id,
            MarketingIventasContactORM
            .phone_match_status
            != PHONE_STATUS_MISSING,
        )
        .scalar_subquery()
    )

    contacts_mx10_matchable = (
        select(
            func.count(
                MarketingIventasContactORM.id
            )
        )
        .where(
            MarketingIventasContactORM
            .sync_run_id
            == sync_run_id,
            MarketingIventasContactORM
            .phone_match_status
            == PHONE_STATUS_MX10_MATCHABLE,
        )
        .scalar_subquery()
    )

    contacts_non_mx_or_unresolved = (
        select(
            func.count(
                MarketingIventasContactORM.id
            )
        )
        .where(
            MarketingIventasContactORM
            .sync_run_id
            == sync_run_id,
            MarketingIventasContactORM
            .phone_match_status
            == PHONE_STATUS_NON_MX_OR_UNRESOLVED,
        )
        .scalar_subquery()
    )

    contacts_with_first_message = (
        select(
            func.count(
                MarketingIventasContactORM.id
            )
        )
        .where(
            MarketingIventasContactORM
            .sync_run_id
            == sync_run_id,
            MarketingIventasContactORM
            .first_message_at_utc
            .is_not(None),
        )
        .scalar_subquery()
    )

    contacts_with_any_tag = (
        select(
            func.count(
                distinct(
                    MarketingIventasContactTagORM
                    .iventas_contact_row_id
                )
            )
        )
        .where(
            MarketingIventasContactTagORM
            .sync_run_id
            == sync_run_id
        )
        .scalar_subquery()
    )

    contacts_with_meta_ad_tag = (
        select(
            func.count(
                distinct(
                    MarketingIventasContactTagORM
                    .iventas_contact_row_id
                )
            )
        )
        .where(
            MarketingIventasContactTagORM
            .sync_run_id
            == sync_run_id,
            MarketingIventasContactTagORM
            .tag_kind
            == TAG_KIND_META_AD,
        )
        .scalar_subquery()
    )

    multi_meta_contacts = (
        select(
            MarketingIventasContactTagORM
            .iventas_contact_row_id
            .label(
                "iventas_contact_row_id"
            )
        )
        .where(
            MarketingIventasContactTagORM
            .sync_run_id
            == sync_run_id,
            MarketingIventasContactTagORM
            .tag_kind
            == TAG_KIND_META_AD,
        )
        .group_by(
            MarketingIventasContactTagORM
            .iventas_contact_row_id
        )
        .having(
            func.count(
                MarketingIventasContactTagORM.id
            )
            >= 2
        )
        .subquery()
    )

    contacts_with_multiple_meta_ad_tags = (
        select(
            func.count()
        )
        .select_from(
            multi_meta_contacts
        )
        .scalar_subquery()
    )

    return select(
        raw_received.label(
            "contacts_received"
        ),
        contacts_unique.label(
            "contacts_unique"
        ),
        contacts_with_phone.label(
            "contacts_with_phone"
        ),
        contacts_mx10_matchable.label(
            "contacts_mx10_matchable"
        ),
        contacts_non_mx_or_unresolved.label(
            "contacts_non_mx_or_unresolved"
        ),
        contacts_with_first_message.label(
            "contacts_with_first_message"
        ),
        contacts_with_any_tag.label(
            "contacts_with_any_tag"
        ),
        contacts_with_meta_ad_tag.label(
            "contacts_with_meta_ad_tag"
        ),
        contacts_with_multiple_meta_ad_tags.label(
            "contacts_with_multiple_meta_ad_tags"
        ),
    )


def read_iventas_stored_run_counters(
    *,
    sync_run_id: int,
    session: Any | None = None,
) -> MarketingIventasStoredRunCounters:
    """Reconstruye counters derivados del snapshot persistido."""

    if (
        isinstance(sync_run_id, bool)
        or not isinstance(sync_run_id, int)
        or sync_run_id <= 0
    ):
        raise ValueError(
            "sync_run_id debe ser "
            "un entero positivo."
        )

    session_value = _session_or_default(
        session
    )

    run = session_value.get(
        MarketingIventasSyncRunORM,
        sync_run_id,
    )

    if run is None:
        raise MarketingIventasRunCountersReadError(
            "No existe el sync_run indicado."
        )

    statement = (
        _build_stored_run_counters_statement(
            sync_run_id
        )
    )

    row = (
        session_value
        .execute(statement)
        .mappings()
        .one()
    )

    values = {
        key: int(
            row[key] or 0
        )
        for key in (
            "contacts_received",
            "contacts_unique",
            "contacts_with_phone",
            "contacts_mx10_matchable",
            "contacts_non_mx_or_unresolved",
            "contacts_with_first_message",
            "contacts_with_any_tag",
            "contacts_with_meta_ad_tag",
            "contacts_with_multiple_meta_ad_tags",
        )
    }

    if any(
        value < 0
        for value in values.values()
    ):
        raise MarketingIventasRunCountersReadError(
            "PostgreSQL devolvió un contador negativo."
        )

    if (
        values[
            "contacts_with_phone"
        ]
        > values[
            "contacts_unique"
        ]
        or values[
            "contacts_mx10_matchable"
        ]
        > values[
            "contacts_unique"
        ]
        or values[
            "contacts_non_mx_or_unresolved"
        ]
        > values[
            "contacts_unique"
        ]
        or values[
            "contacts_with_first_message"
        ]
        > values[
            "contacts_unique"
        ]
        or values[
            "contacts_with_any_tag"
        ]
        > values[
            "contacts_unique"
        ]
        or values[
            "contacts_with_meta_ad_tag"
        ]
        > values[
            "contacts_unique"
        ]
        or values[
            "contacts_with_multiple_meta_ad_tags"
        ]
        > values[
            "contacts_unique"
        ]
    ):
        raise MarketingIventasRunCountersReadError(
            "Los counters persistidos violan "
            "la cardinalidad de contacts_unique."
        )

    if (
        values[
            "contacts_with_meta_ad_tag"
        ]
        > values[
            "contacts_with_any_tag"
        ]
    ):
        raise MarketingIventasRunCountersReadError(
            "contacts_with_meta_ad_tag no puede "
            "superar contacts_with_any_tag."
        )

    if (
        values[
            "contacts_with_multiple_meta_ad_tags"
        ]
        > values[
            "contacts_with_meta_ad_tag"
        ]
    ):
        raise MarketingIventasRunCountersReadError(
            "contacts_with_multiple_meta_ad_tags "
            "no puede superar contacts_with_meta_ad_tag."
        )

    if (
        values[
            "contacts_unique"
        ]
        > values[
            "contacts_received"
        ]
    ):
        raise MarketingIventasRunCountersReadError(
            "contacts_unique no puede superar "
            "contacts_received."
        )

    return MarketingIventasStoredRunCounters(
        **values
    )
