from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.extensions import db
from app.models.warehouse import (
    SociosActivosSnapshotORM,
)


SOCIOS_ACTIVOS_REPORT_TYPE_KEY = "socios_activos"
SOCIOS_ACTIVOS_SNAPSHOT_KIND = "daily"


class SociosActivosSnapshotResolverError(RuntimeError):
    """Error al resolver el snapshot canónico de Socios Activos."""


def resolve_latest_canonical_socios_activos_snapshot(
    *,
    minimum_cutoff_date: date | datetime | str,
    snapshot_kind: str = SOCIOS_ACTIVOS_SNAPSHOT_KIND,
    session: Any | None = None,
) -> SociosActivosSnapshotORM | None:
    """
    Devuelve el snapshot canónico de Socios Activos más reciente
    cuyo cutoff_date sea igual o posterior a minimum_cutoff_date.

    Orden de desempate:
    1) cutoff_date más reciente
    2) captured_at más reciente
    3) id más reciente

    No modifica canonicalidad ni persiste información.
    """
    normalized_minimum_cutoff_date = _ensure_date(
        minimum_cutoff_date,
        field_name="minimum_cutoff_date",
    )

    normalized_snapshot_kind = _normalize_required_text(
        snapshot_kind,
        field_name="snapshot_kind",
    )

    if (
        normalized_snapshot_kind
        != SOCIOS_ACTIVOS_SNAPSHOT_KIND
    ):
        raise SociosActivosSnapshotResolverError(
            "snapshot_kind no soportado para "
            "Socios Activos: "
            f"{normalized_snapshot_kind!r}."
        )

    active_session = (
        session
        if session is not None
        else db.session
    )

    return (
        active_session.query(
            SociosActivosSnapshotORM
        )
        .filter(
            SociosActivosSnapshotORM.report_type_key
            == SOCIOS_ACTIVOS_REPORT_TYPE_KEY,
            SociosActivosSnapshotORM.snapshot_kind
            == normalized_snapshot_kind,
            SociosActivosSnapshotORM.is_canonical.is_(
                True
            ),
            SociosActivosSnapshotORM.cutoff_date
            >= normalized_minimum_cutoff_date,
        )
        .order_by(
            SociosActivosSnapshotORM.cutoff_date.desc(),
            SociosActivosSnapshotORM.captured_at.desc(),
            SociosActivosSnapshotORM.id.desc(),
        )
        .first()
    )


def _ensure_date(
    value: Any,
    *,
    field_name: str,
) -> date:
    if (
        isinstance(value, date)
        and not isinstance(value, datetime)
    ):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        normalized = value.strip()

        try:
            return date.fromisoformat(
                normalized
            )
        except ValueError as exc:
            raise SociosActivosSnapshotResolverError(
                f"{field_name} debe tener formato "
                "YYYY-MM-DD."
            ) from exc

    raise SociosActivosSnapshotResolverError(
        f"{field_name} debe ser date, datetime "
        "o string ISO YYYY-MM-DD."
    )


def _normalize_required_text(
    value: Any,
    *,
    field_name: str,
) -> str:
    normalized = str(
        value or ""
    ).strip()

    if not normalized:
        raise SociosActivosSnapshotResolverError(
            f"{field_name} es obligatorio."
        )

    return normalized
