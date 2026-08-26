"""Métricas derivadas de contactos iVentas para Marketing.

Esta capa separa explícitamente:

- iventas_contacts:
  población operativa completa observada en iVentas;

- iventas_contacts_with_first_message:
  contactos con evidencia de interacción;

- meta_observed_leads:
  contactos con firstMessageAt y al menos una relación
  META_AD observada.

Es la fuente operativa de leads del dashboard de Marketing.
No realiza atribución causal a Meta.
No lee runs no canónicos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import NoResultFound

from app.extensions import db
from app.models import (
    MarketingIventasContactORM,
    MarketingIventasContactTagORM,
    MarketingIventasSyncRunORM,
)
from app.services.marketing_iventas_service import (
    TAG_KIND_META_AD,
)


class MarketingIventasCanonicalRunRequiredError(
    RuntimeError
):
    """No existe snapshot iVentas canónico para el periodo."""


@dataclass(frozen=True)
class MarketingIventasLeadMetrics:
    sync_run_id: int
    period_key: str

    iventas_contacts: int
    iventas_contacts_with_first_message: int
    meta_observed_leads: int




@dataclass(frozen=True)
class MarketingIventasLeadMetricsByBranchDate:
    sync_run_id: int
    period_key: str
    lead_date: date
    sucursal_id: int

    iventas_contacts: int
    iventas_contacts_with_first_message: int
    meta_observed_leads: int


def _session_or_default(
    session: Any | None,
):
    return (
        session
        if session is not None
        else db.session
    )


def _validate_period_key(
    period_key: str,
) -> str:
    if not isinstance(
        period_key,
        str,
    ):
        raise ValueError(
            "period_key debe ser texto no vacío."
        )

    value = period_key.strip()

    if not value:
        raise ValueError(
            "period_key debe ser texto no vacío."
        )

    return value


def _build_canonical_run_statement(
    period_key: str,
):
    return (
        select(
            MarketingIventasSyncRunORM.id.label(
                "sync_run_id"
            ),
            MarketingIventasSyncRunORM.period_key,
            MarketingIventasSyncRunORM.date_from,
            MarketingIventasSyncRunORM.date_to,
            MarketingIventasSyncRunORM.status,
            MarketingIventasSyncRunORM.is_canonical,
        )
        .where(
            MarketingIventasSyncRunORM.period_key
            == period_key,
            MarketingIventasSyncRunORM.status
            == "COMPLETED",
            MarketingIventasSyncRunORM.is_canonical
            .is_(True),
        )
    )


def _build_lead_metrics_statement(
    sync_run_id: int,
):
    iventas_contacts = (
        select(
            func.count(
                MarketingIventasContactORM.id
            )
        )
        .where(
            MarketingIventasContactORM.sync_run_id
            == sync_run_id
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
            MarketingIventasContactORM.sync_run_id
            == sync_run_id,
            MarketingIventasContactORM
            .first_message_at_utc
            .is_not(None),
        )
        .scalar_subquery()
    )

    meta_observed_leads = (
        select(
            func.count(
                distinct(
                    MarketingIventasContactORM.id
                )
            )
        )
        .select_from(
            MarketingIventasContactORM
        )
        .join(
            MarketingIventasContactTagORM,
            (
                MarketingIventasContactTagORM
                .iventas_contact_row_id
                == MarketingIventasContactORM.id
            )
            & (
                MarketingIventasContactTagORM
                .sync_run_id
                == MarketingIventasContactORM
                .sync_run_id
            ),
        )
        .where(
            MarketingIventasContactORM.sync_run_id
            == sync_run_id,
            MarketingIventasContactORM
            .first_message_at_utc
            .is_not(None),
            MarketingIventasContactTagORM.tag_kind
            == TAG_KIND_META_AD,
        )
        .scalar_subquery()
    )

    return select(
        iventas_contacts.label(
            "iventas_contacts"
        ),
        contacts_with_first_message.label(
            "iventas_contacts_with_first_message"
        ),
        meta_observed_leads.label(
            "meta_observed_leads"
        ),
    )


def read_canonical_iventas_run(
    *,
    period_key: str,
    session: Any,
):
    period_key_value = _validate_period_key(
        period_key
    )

    statement = (
        _build_canonical_run_statement(
            period_key_value
        )
    )

    try:
        row = (
            session
            .execute(statement)
            .mappings()
            .one()
        )
    except NoResultFound:
        row = None

    if row is None:
        raise (
            MarketingIventasCanonicalRunRequiredError(
                "No existe snapshot iVentas canónico "
                f"para period_key={period_key_value!r}."
            )
        )

    return row


def _validate_metrics(
    *,
    iventas_contacts: int,
    iventas_contacts_with_first_message: int,
    meta_observed_leads: int,
) -> None:
    values = {
        "iventas_contacts": iventas_contacts,
        "iventas_contacts_with_first_message": (
            iventas_contacts_with_first_message
        ),
        "meta_observed_leads": (
            meta_observed_leads
        ),
    }

    if any(
        value < 0
        for value in values.values()
    ):
        raise ValueError(
            "Las métricas iVentas no pueden "
            "ser negativas."
        )

    if (
        iventas_contacts_with_first_message
        > iventas_contacts
    ):
        raise ValueError(
            "iventas_contacts_with_first_message "
            "no puede superar iventas_contacts."
        )

    if (
        meta_observed_leads
        > iventas_contacts
        or meta_observed_leads
        > iventas_contacts_with_first_message
    ):
        raise ValueError(
            "meta_observed_leads no puede superar "
            "la población de contactos ni los "
            "contactos con firstMessageAt."
        )


def read_canonical_iventas_lead_metrics(
    *,
    period_key: str,
    session: Any | None = None,
) -> MarketingIventasLeadMetrics:
    """Lee las poblaciones derivadas de un snapshot canónico."""

    period_key_value = (
        _validate_period_key(
            period_key
        )
    )

    session_value = (
        _session_or_default(
            session
        )
    )

    canonical_run = (
        read_canonical_iventas_run(
            period_key=period_key_value,
            session=session_value,
        )
    )

    sync_run_id = int(
        canonical_run["sync_run_id"]
    )

    metrics_row = (
        session_value
        .execute(
            _build_lead_metrics_statement(
                sync_run_id
            )
        )
        .mappings()
        .one()
    )

    iventas_contacts = int(
        metrics_row[
            "iventas_contacts"
        ]
        or 0
    )

    iventas_contacts_with_first_message = int(
        metrics_row[
            "iventas_contacts_with_first_message"
        ]
        or 0
    )

    meta_observed_leads = int(
        metrics_row[
            "meta_observed_leads"
        ]
        or 0
    )

    _validate_metrics(
        iventas_contacts=iventas_contacts,
        iventas_contacts_with_first_message=(
            iventas_contacts_with_first_message
        ),
        meta_observed_leads=meta_observed_leads,
    )

    return MarketingIventasLeadMetrics(
        sync_run_id=sync_run_id,
        period_key=str(
            canonical_run["period_key"]
        ),
        iventas_contacts=iventas_contacts,
        iventas_contacts_with_first_message=(
            iventas_contacts_with_first_message
        ),
        meta_observed_leads=meta_observed_leads,
    )


def _build_lead_metrics_by_branch_date_statement(
    sync_run_id: int,
):
    """Agrupa poblaciones iVentas por fecha comercial y sucursal.

    No hace JOIN multiplicativo contra tags.

    La existencia de META_AD se resuelve mediante EXISTS para que:

        1 contacto + N META_AD = 1 meta_observed_lead
    """

    meta_tag_exists = (
        select(
            MarketingIventasContactTagORM.id
        )
        .where(
            MarketingIventasContactTagORM
            .iventas_contact_row_id
            == MarketingIventasContactORM.id,

            MarketingIventasContactTagORM
            .sync_run_id
            == MarketingIventasContactORM
            .sync_run_id,

            MarketingIventasContactTagORM
            .tag_kind
            == TAG_KIND_META_AD,
        )
        .exists()
    )

    return (
        select(
            MarketingIventasContactORM
            .created_date_local
            .label("lead_date"),

            MarketingIventasContactORM
            .sucursal_id
            .label("sucursal_id"),

            func.count(
                MarketingIventasContactORM.id
            ).label(
                "iventas_contacts"
            ),

            func.count(
                MarketingIventasContactORM.id
            )
            .filter(
                MarketingIventasContactORM
                .first_message_at_utc
                .is_not(None)
            )
            .label(
                "iventas_contacts_with_first_message"
            ),

            func.count(
                MarketingIventasContactORM.id
            )
            .filter(
                MarketingIventasContactORM
                .first_message_at_utc
                .is_not(None),

                meta_tag_exists,
            )
            .label(
                "meta_observed_leads"
            ),
        )
        .where(
            MarketingIventasContactORM
            .sync_run_id
            == sync_run_id
        )
        .group_by(
            MarketingIventasContactORM
            .created_date_local,

            MarketingIventasContactORM
            .sucursal_id,
        )
        .order_by(
            MarketingIventasContactORM
            .created_date_local
            .asc(),

            MarketingIventasContactORM
            .sucursal_id
            .asc(),
        )
    )


def list_canonical_iventas_lead_metrics_by_branch_date(
    *,
    period_key: str,
    session: Any | None = None,
) -> tuple[
    MarketingIventasLeadMetricsByBranchDate,
    ...,
]:
    """Lista poblaciones por fecha comercial y sucursal.

    Solo acepta como fuente un snapshot iVentas canónico.
    """

    period_key_value = (
        _validate_period_key(
            period_key
        )
    )

    session_value = (
        _session_or_default(
            session
        )
    )

    canonical_run = (
        read_canonical_iventas_run(
            period_key=period_key_value,
            session=session_value,
        )
    )

    sync_run_id = int(
        canonical_run["sync_run_id"]
    )

    rows = (
        session_value
        .execute(
            _build_lead_metrics_by_branch_date_statement(
                sync_run_id
            )
        )
        .mappings()
        .all()
    )

    result: list[
        MarketingIventasLeadMetricsByBranchDate
    ] = []

    for row in rows:
        iventas_contacts = int(
            row["iventas_contacts"]
            or 0
        )

        iventas_contacts_with_first_message = int(
            row[
                "iventas_contacts_with_first_message"
            ]
            or 0
        )

        meta_observed_leads = int(
            row["meta_observed_leads"]
            or 0
        )

        _validate_metrics(
            iventas_contacts=iventas_contacts,
            iventas_contacts_with_first_message=(
                iventas_contacts_with_first_message
            ),
            meta_observed_leads=(
                meta_observed_leads
            ),
        )

        result.append(
            MarketingIventasLeadMetricsByBranchDate(
                sync_run_id=sync_run_id,
                period_key=str(
                    canonical_run["period_key"]
                ),
                lead_date=row["lead_date"],
                sucursal_id=int(
                    row["sucursal_id"]
                ),
                iventas_contacts=(
                    iventas_contacts
                ),
                iventas_contacts_with_first_message=(
                    iventas_contacts_with_first_message
                ),
                meta_observed_leads=(
                    meta_observed_leads
                ),
            )
        )

    return tuple(result)


@dataclass(frozen=True)
class MarketingIventasLeadMetricsByBranchMonth:
    sync_run_id: int
    period_key: str
    month_start: date
    sucursal_id: int

    iventas_contacts: int
    iventas_contacts_with_first_message: int
    meta_observed_leads: int


def _build_lead_metrics_by_branch_month_statement(
    sync_run_id: int,
):
    """Agrupa poblaciones iVentas por mes comercial y sucursal.

    Un contacto permanece como una sola fila lógica.
    La relación META_AD se valida mediante EXISTS para evitar
    multiplicación cuando un contacto tiene varios tags Meta.
    """

    month_start = (
        func.date_trunc(
            "month",
            MarketingIventasContactORM.created_date_local,
        )
        .cast(db.Date)
    )

    meta_tag_exists = (
        select(
            MarketingIventasContactTagORM.id
        )
        .where(
            MarketingIventasContactTagORM
            .iventas_contact_row_id
            == MarketingIventasContactORM.id,

            MarketingIventasContactTagORM
            .sync_run_id
            == MarketingIventasContactORM
            .sync_run_id,

            MarketingIventasContactTagORM
            .tag_kind
            == TAG_KIND_META_AD,
        )
        .exists()
    )

    return (
        select(
            month_start.label(
                "month_start"
            ),

            MarketingIventasContactORM
            .sucursal_id
            .label(
                "sucursal_id"
            ),

            func.count(
                MarketingIventasContactORM.id
            )
            .label(
                "iventas_contacts"
            ),

            func.count(
                MarketingIventasContactORM.id
            )
            .filter(
                MarketingIventasContactORM
                .first_message_at_utc
                .is_not(None)
            )
            .label(
                "iventas_contacts_with_first_message"
            ),

            func.count(
                MarketingIventasContactORM.id
            )
            .filter(
                MarketingIventasContactORM
                .first_message_at_utc
                .is_not(None),

                meta_tag_exists,
            )
            .label(
                "meta_observed_leads"
            ),
        )
        .where(
            MarketingIventasContactORM
            .sync_run_id
            == sync_run_id
        )
        .group_by(
            month_start,

            MarketingIventasContactORM
            .sucursal_id,
        )
        .order_by(
            month_start.asc(),

            MarketingIventasContactORM
            .sucursal_id
            .asc(),
        )
    )


def list_iventas_lead_metrics_by_branch_month_for_run(
    *,
    sync_run_id: int,
    period_key: str,
    session: Any | None = None,
) -> tuple[
    MarketingIventasLeadMetricsByBranchMonth,
    ...,
]:
    """Lee métricas mensuales de un run iVentas exacto."""

    if (
        isinstance(sync_run_id, bool)
        or not isinstance(sync_run_id, int)
        or sync_run_id <= 0
    ):
        raise ValueError(
            "sync_run_id debe ser entero positivo."
        )

    period_key_value = _validate_period_key(
        period_key
    )

    session_value = _session_or_default(
        session
    )

    rows = (
        session_value
        .execute(
            _build_lead_metrics_by_branch_month_statement(
                sync_run_id
            )
        )
        .mappings()
        .all()
    )

    result: list[
        MarketingIventasLeadMetricsByBranchMonth
    ] = []

    for row in rows:
        iventas_contacts = int(
            row["iventas_contacts"]
            or 0
        )

        iventas_contacts_with_first_message = int(
            row[
                "iventas_contacts_with_first_message"
            ]
            or 0
        )

        meta_observed_leads = int(
            row["meta_observed_leads"]
            or 0
        )

        _validate_metrics(
            iventas_contacts=iventas_contacts,
            iventas_contacts_with_first_message=(
                iventas_contacts_with_first_message
            ),
            meta_observed_leads=(
                meta_observed_leads
            ),
        )

        result.append(
            MarketingIventasLeadMetricsByBranchMonth(
                sync_run_id=sync_run_id,
                period_key=period_key_value,
                month_start=row["month_start"],
                sucursal_id=int(
                    row["sucursal_id"]
                ),
                iventas_contacts=(
                    iventas_contacts
                ),
                iventas_contacts_with_first_message=(
                    iventas_contacts_with_first_message
                ),
                meta_observed_leads=(
                    meta_observed_leads
                ),
            )
        )

    return tuple(result)


def list_canonical_iventas_lead_metrics_by_branch_month(
    *,
    period_key: str,
    session: Any | None = None,
) -> tuple[
    MarketingIventasLeadMetricsByBranchMonth,
    ...,
]:
    """Lista métricas mensuales desde el canónico vigente."""

    period_key_value = _validate_period_key(
        period_key
    )

    session_value = _session_or_default(
        session
    )

    canonical_run = read_canonical_iventas_run(
        period_key=period_key_value,
        session=session_value,
    )

    return list_iventas_lead_metrics_by_branch_month_for_run(
        sync_run_id=int(
            canonical_run["sync_run_id"]
        ),
        period_key=str(
            canonical_run["period_key"]
        ),
        session=session_value,
    )
