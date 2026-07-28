from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.warehouse import (
    VentasNuevosSociosDetalleSnapshotORM,
    VentasNuevosSociosDetalleSnapshotRowORM,
)


VENTAS_NUEVOS_SOCIOS_DETALLE_REPORT_TYPE_KEY = (
    "ventas_nuevos_socios_detalle"
)

SUPPORTED_SNAPSHOT_KINDS = frozenset(
    {
        "month_to_date",
    }
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class VentasNuevosSociosDetalleRepositoryError(
    RuntimeError
):
    """Error del repository estructurado de nuevos socios."""


def register_ventas_nuevos_socios_detalle_repository(
    app,
) -> None:
    app.config[
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_REPOSITORY"
    ] = persist_ventas_nuevos_socios_detalle_snapshot


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    if is_dataclass(value):
        return asdict(value)

    raise VentasNuevosSociosDetalleRepositoryError(
        "Se esperaba dict o dataclass serializable."
    )


def _ensure_positive_integer(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} no puede ser booleano."
        )

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} debe ser entero positivo."
        ) from exc

    if parsed <= 0:
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} debe ser entero positivo."
        )

    return parsed


def _ensure_nonnegative_integer(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} no puede ser booleano."
        )

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} debe ser entero no negativo."
        ) from exc

    if parsed < 0:
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} debe ser entero no negativo."
        )

    return parsed


def _ensure_optional_positive_integer(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None:
        return None

    return _ensure_positive_integer(
        value,
        field_name=field_name,
    )


def _ensure_required_text(
    value: Any,
    *,
    field_name: str,
) -> str:
    if value is None:
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} es obligatorio."
        )

    normalized = str(value).strip()

    if not normalized:
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} es obligatorio."
        )

    return normalized


def _ensure_optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    return normalized or None


def _ensure_date(
    value: Any,
    *,
    field_name: str,
) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise VentasNuevosSociosDetalleRepositoryError(
                f"{field_name} debe usar formato ISO YYYY-MM-DD."
            ) from exc

    raise VentasNuevosSociosDetalleRepositoryError(
        f"{field_name} no contiene una fecha válida."
    )


def _ensure_optional_date(
    value: Any,
    *,
    field_name: str,
) -> date | None:
    if value is None or value == "":
        return None

    return _ensure_date(
        value,
        field_name=field_name,
    )


def _ensure_datetime(
    value: Any,
    *,
    field_name: str,
) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()

        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"

        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise VentasNuevosSociosDetalleRepositoryError(
                f"{field_name} no contiene un datetime ISO válido."
            ) from exc
    else:
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} no contiene un datetime válido."
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _ensure_optional_datetime(
    value: Any,
    *,
    field_name: str,
) -> datetime | None:
    if value is None or value == "":
        return None

    return _ensure_datetime(
        value,
        field_name=field_name,
    )


def _ensure_optional_decimal(
    value: Any,
    *,
    field_name: str,
) -> Decimal | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} no puede ser booleano."
        )

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} no contiene un decimal válido."
        ) from exc


def _ensure_integer_code(
    value: Any,
    *,
    field_name: str,
    required: bool,
) -> int | None:
    if value is None or value == "":
        if required:
            raise VentasNuevosSociosDetalleRepositoryError(
                f"{field_name} es obligatorio."
            )

        return None

    if isinstance(value, bool):
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} no puede ser booleano."
        )

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise VentasNuevosSociosDetalleRepositoryError(
            f"{field_name} debe ser entero."
        ) from exc


def _normalize_quality_flags(
    value: Any,
) -> list[str]:
    if value is None:
        return []

    if not isinstance(value, (list, tuple, set)):
        raise VentasNuevosSociosDetalleRepositoryError(
            "quality_flags debe ser una colección."
        )

    normalized = sorted(
        {
            str(flag).strip()
            for flag in value
            if str(flag).strip()
        }
    )

    return normalized


def _normalize_row(
    raw_row: Any,
) -> dict[str, Any]:
    row = _as_dict(raw_row)

    row_hash = _ensure_required_text(
        row.get("row_hash"),
        field_name="row_hash",
    ).lower()

    if _SHA256_PATTERN.fullmatch(row_hash) is None:
        raise VentasNuevosSociosDetalleRepositoryError(
            "row_hash debe ser SHA-256 hexadecimal."
        )

    return {
        "row_index": _ensure_positive_integer(
            row.get("row_index"),
            field_name="row_index",
        ),
        "row_hash": row_hash,
        "id_socio": _ensure_required_text(
            row.get("id_socio"),
            field_name="id_socio",
        ),
        "pin": _ensure_required_text(
            row.get("pin"),
            field_name="pin",
        ),
        "sucursal_raw": _ensure_required_text(
            row.get("sucursal_raw"),
            field_name="sucursal_raw",
        ),
        "sucursal_id": _ensure_optional_positive_integer(
            row.get("sucursal_id"),
            field_name="sucursal_id",
        ),
        "nombre": _ensure_required_text(
            row.get("nombre"),
            field_name="nombre",
        ),
        "apellido_paterno": _ensure_required_text(
            row.get("apellido_paterno"),
            field_name="apellido_paterno",
        ),
        "apellido_materno": _ensure_required_text(
            row.get("apellido_materno"),
            field_name="apellido_materno",
        ),
        "lada": _ensure_required_text(
            row.get("lada"),
            field_name="lada",
        ),
        "telefono": _ensure_required_text(
            row.get("telefono"),
            field_name="telefono",
        ),
        "domicilio": _ensure_optional_text(
            row.get("domicilio")
        ),
        "genero": _ensure_optional_text(
            row.get("genero")
        ),
        "fecha_nacimiento": _ensure_optional_date(
            row.get("fecha_nacimiento"),
            field_name="fecha_nacimiento",
        ),
        "email": _ensure_optional_text(
            row.get("email")
        ),
        "fecha_creacion_at": _ensure_datetime(
            row.get("fecha_creacion_at"),
            field_name="fecha_creacion_at",
        ),
        "inscripcion": _ensure_optional_text(
            row.get("inscripcion")
        ),
        "tipo_membresia": _ensure_required_text(
            row.get("tipo_membresia"),
            field_name="tipo_membresia",
        ),
        "tarifa": _ensure_required_text(
            row.get("tarifa"),
            field_name="tarifa",
        ),
        "total": _ensure_optional_decimal(
            row.get("total"),
            field_name="total",
        ),
        "fecha_pago_at": _ensure_datetime(
            row.get("fecha_pago_at"),
            field_name="fecha_pago_at",
        ),
        "fecha_renovacion_at": _ensure_datetime(
            row.get("fecha_renovacion_at"),
            field_name="fecha_renovacion_at",
        ),
        "fecha_firma_contrato_at": (
            _ensure_optional_datetime(
                row.get("fecha_firma_contrato_at"),
                field_name="fecha_firma_contrato_at",
            )
        ),
        "tipo_pago_code": _ensure_integer_code(
            row.get("tipo_pago_code"),
            field_name="tipo_pago_code",
            required=True,
        ),
        "tipo_tarjeta_code": _ensure_integer_code(
            row.get("tipo_tarjeta_code"),
            field_name="tipo_tarjeta_code",
            required=False,
        ),
        "lugar_pago": _ensure_required_text(
            row.get("lugar_pago"),
            field_name="lugar_pago",
        ),
        "id_folio": _ensure_required_text(
            row.get("id_folio"),
            field_name="id_folio",
        ),
        "pase": _ensure_optional_text(
            row.get("pase")
        ),
        "anfitrion": _ensure_optional_text(
            row.get("anfitrion")
        ),
        "total_pagado": _ensure_optional_decimal(
            row.get("total_pagado"),
            field_name="total_pagado",
        ),
        "quality_flags": _normalize_quality_flags(
            row.get("quality_flags")
        ),
    }


def _normalize_rejected_rows(
    value: Any,
) -> list[dict[str, Any]]:
    if value is None:
        return []

    if not isinstance(value, (list, tuple)):
        raise VentasNuevosSociosDetalleRepositoryError(
            "rejected_rows debe ser una colección."
        )

    normalized: list[dict[str, Any]] = []

    for raw_rejected_row in value:
        rejected_row = _as_dict(raw_rejected_row)

        normalized.append(
            {
                "row_number": _ensure_positive_integer(
                    rejected_row.get("row_number"),
                    field_name="rejected_rows.row_number",
                ),
                "reason_code": _ensure_required_text(
                    rejected_row.get("reason_code"),
                    field_name="rejected_rows.reason_code",
                ),
                "reason_message": _ensure_required_text(
                    rejected_row.get("reason_message"),
                    field_name="rejected_rows.reason_message",
                ),
            }
        )

    return normalized


def _normalize_parsed_snapshot(
    parsed_snapshot: Any,
) -> dict[str, Any]:
    payload = _as_dict(parsed_snapshot)

    raw_rows = payload.get("rows")

    if not isinstance(raw_rows, (list, tuple)):
        raise VentasNuevosSociosDetalleRepositoryError(
            "El parser no devolvió rows como colección."
        )

    if not raw_rows:
        raise VentasNuevosSociosDetalleRepositoryError(
            "El parser no devolvió filas válidas."
        )

    rows = [
        _normalize_row(raw_row)
        for raw_row in raw_rows
    ]

    row_count_valid = _ensure_nonnegative_integer(
        payload.get(
            "row_count_valid",
            len(rows),
        ),
        field_name="row_count_valid",
    )

    row_count_rejected = _ensure_nonnegative_integer(
        payload.get(
            "row_count_rejected",
            0,
        ),
        field_name="row_count_rejected",
    )

    row_count_detected = _ensure_nonnegative_integer(
        payload.get(
            "row_count",
            row_count_valid + row_count_rejected,
        ),
        field_name="row_count",
    )

    if row_count_valid != len(rows):
        raise VentasNuevosSociosDetalleRepositoryError(
            "row_count_valid no coincide con el número de rows."
        )

    if (
        row_count_detected
        != row_count_valid + row_count_rejected
    ):
        raise VentasNuevosSociosDetalleRepositoryError(
            "row_count debe ser igual a valid + rejected."
        )

    raw_metadata = payload.get("metadata") or {}

    if not isinstance(raw_metadata, Mapping):
        raise VentasNuevosSociosDetalleRepositoryError(
            "metadata debe ser un objeto."
        )

    quality_flag_counts = payload.get(
        "quality_flag_counts"
    ) or {}

    if not isinstance(quality_flag_counts, Mapping):
        raise VentasNuevosSociosDetalleRepositoryError(
            "quality_flag_counts debe ser un objeto."
        )

    metadata = {
        **dict(raw_metadata),
        "quality_flag_counts": {
            str(key): _ensure_nonnegative_integer(
                value,
                field_name=(
                    f"quality_flag_counts.{key}"
                ),
            )
            for key, value in quality_flag_counts.items()
        },
        "rejected_rows": _normalize_rejected_rows(
            payload.get("rejected_rows")
        ),
    }

    return {
        "rows": rows,
        "row_count_detected": row_count_detected,
        "row_count_valid": row_count_valid,
        "row_count_rejected": row_count_rejected,
        "metadata": metadata,
    }


def _fetch_existing_snapshot_by_upload(
    *,
    warehouse_upload_id: int,
) -> VentasNuevosSociosDetalleSnapshotORM | None:
    return (
        VentasNuevosSociosDetalleSnapshotORM.query
        .filter_by(
            warehouse_upload_id=warehouse_upload_id
        )
        .first()
    )


def _fetch_existing_canonical_snapshot(
    *,
    business_date: date,
    snapshot_kind: str,
) -> VentasNuevosSociosDetalleSnapshotORM | None:
    return (
        VentasNuevosSociosDetalleSnapshotORM.query
        .filter_by(
            report_type_key=(
                VENTAS_NUEVOS_SOCIOS_DETALLE_REPORT_TYPE_KEY
            ),
            business_date=business_date,
            snapshot_kind=snapshot_kind,
            is_canonical=True,
        )
        .order_by(
            VentasNuevosSociosDetalleSnapshotORM.id.desc()
        )
        .first()
    )


def _insert_snapshot_header(
    *,
    warehouse_upload_id: int,
    report_type_key: str,
    business_date: date,
    date_from: date,
    date_to: date,
    captured_at: datetime,
    snapshot_kind: str,
    is_canonical: bool,
    row_count_detected: int,
    row_count_valid: int,
    row_count_rejected: int,
    metadata: dict[str, Any],
) -> VentasNuevosSociosDetalleSnapshotORM:
    now = _utc_now()

    snapshot = VentasNuevosSociosDetalleSnapshotORM(
        warehouse_upload_id=warehouse_upload_id,
        report_type_key=report_type_key,
        business_date=business_date,
        date_from=date_from,
        date_to=date_to,
        captured_at=captured_at,
        snapshot_kind=snapshot_kind,
        is_canonical=is_canonical,
        row_count_detected=row_count_detected,
        row_count_valid=row_count_valid,
        row_count_rejected=row_count_rejected,
        metadata_json=metadata,
        created_at=now,
        updated_at=now,
    )

    db.session.add(snapshot)
    db.session.flush()

    return snapshot


def _insert_snapshot_rows(
    *,
    snapshot_id: int,
    rows: list[dict[str, Any]],
) -> int:
    now = _utc_now()

    orm_rows = [
        VentasNuevosSociosDetalleSnapshotRowORM(
            snapshot_id=snapshot_id,
            created_at=now,
            updated_at=now,
            **row,
        )
        for row in rows
    ]

    db.session.add_all(orm_rows)
    db.session.flush()

    return len(orm_rows)


def _set_snapshot_canonical_state(
    *,
    snapshot: VentasNuevosSociosDetalleSnapshotORM,
    is_canonical: bool,
) -> None:
    snapshot.is_canonical = is_canonical
    snapshot.updated_at = _utc_now()
    db.session.flush()


def _build_already_ingested_result(
    *,
    snapshot: VentasNuevosSociosDetalleSnapshotORM,
) -> dict[str, Any]:
    return {
        "status": "already_ingested",
        "was_idempotent": True,
        "snapshot_id": snapshot.id,
        "warehouse_upload_id": (
            snapshot.warehouse_upload_id
        ),
        "report_type_key": snapshot.report_type_key,
        "business_date": snapshot.business_date.isoformat(),
        "date_from": snapshot.date_from.isoformat(),
        "date_to": snapshot.date_to.isoformat(),
        "captured_at": snapshot.captured_at.isoformat(),
        "snapshot_kind": snapshot.snapshot_kind,
        "is_canonical": bool(snapshot.is_canonical),
        "row_count_detected": (
            snapshot.row_count_detected
        ),
        "row_count_valid": snapshot.row_count_valid,
        "row_count_rejected": (
            snapshot.row_count_rejected
        ),
        "rows_inserted": None,
        "metadata": {
            **dict(snapshot.metadata_json or {}),
            "reason": (
                "snapshot_already_exists_for_"
                "warehouse_upload_id"
            ),
        },
    }


def _apply_optional_advisory_lock(
    *,
    advisory_lock_key: int | None,
) -> None:
    if advisory_lock_key is None:
        return

    db.session.execute(
        text(
            "SELECT pg_advisory_xact_lock(:lock_key)"
        ),
        {
            "lock_key": int(advisory_lock_key),
        },
    )


def _resolve_canonicality_decision(
    *,
    business_date: date,
    date_from: date,
    date_to: date,
    snapshot_kind: str,
    captured_at: datetime,
    row_count_valid: int,
    row_count_rejected: int,
    canonicality_resolver: (
        Callable[..., dict[str, Any] | None]
        | None
    ),
) -> dict[str, Any]:
    existing_canonical = (
        _fetch_existing_canonical_snapshot(
            business_date=business_date,
            snapshot_kind=snapshot_kind,
        )
    )

    default_decision = {
        "is_canonical": False,
        "replace_existing_canonical": False,
        "existing_canonical_snapshot": (
            existing_canonical
        ),
        "existing_canonical_snapshot_id": (
            existing_canonical.id
            if existing_canonical is not None
            else None
        ),
        "reason": "canonicality_not_configured",
    }

    if canonicality_resolver is None:
        return default_decision

    resolved = canonicality_resolver(
        report_type_key=(
            VENTAS_NUEVOS_SOCIOS_DETALLE_REPORT_TYPE_KEY
        ),
        business_date=business_date,
        date_from=date_from,
        date_to=date_to,
        snapshot_kind=snapshot_kind,
        existing_canonical_snapshot=(
            existing_canonical
        ),
        captured_at=captured_at,
        row_count_valid=row_count_valid,
        row_count_rejected=row_count_rejected,
    )

    if not resolved:
        return default_decision

    is_canonical = bool(
        resolved.get("is_canonical", False)
    )

    replace_existing = bool(
        resolved.get(
            "replace_existing_canonical",
            False,
        )
    )

    if replace_existing and not is_canonical:
        raise VentasNuevosSociosDetalleRepositoryError(
            "No se puede reemplazar el canónico con "
            "is_canonical=False."
        )

    if (
        existing_canonical is not None
        and is_canonical
        and not replace_existing
    ):
        raise VentasNuevosSociosDetalleRepositoryError(
            "Ya existe un snapshot canónico para la fecha; "
            "el resolver debe indicar reemplazo."
        )

    return {
        "is_canonical": is_canonical,
        "replace_existing_canonical": (
            replace_existing
        ),
        "existing_canonical_snapshot": (
            existing_canonical
        ),
        "existing_canonical_snapshot_id": (
            existing_canonical.id
            if existing_canonical is not None
            else None
        ),
        "reason": (
            resolved.get("reason")
            or "resolver_provided_decision"
        ),
    }


def persist_ventas_nuevos_socios_detalle_snapshot(
    *,
    warehouse_upload_id: int,
    report_type_key: str,
    business_date: date | datetime | str,
    date_from: date | datetime | str,
    date_to: date | datetime | str,
    captured_at: datetime | str,
    snapshot_kind: str,
    parsed_snapshot: Any,
    canonicality_resolver: (
        Callable[..., dict[str, Any] | None]
        | None
    ) = None,
    advisory_lock_key: int | None = None,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
) -> dict[str, Any]:
    normalized_upload_id = _ensure_positive_integer(
        warehouse_upload_id,
        field_name="warehouse_upload_id",
    )

    if (
        report_type_key
        != VENTAS_NUEVOS_SOCIOS_DETALLE_REPORT_TYPE_KEY
    ):
        raise VentasNuevosSociosDetalleRepositoryError(
            "report_type_key inválido para "
            "Ventas Nuevos Socios Detalle: "
            f"{report_type_key!r}"
        )

    normalized_snapshot_kind = (
        _ensure_required_text(
            snapshot_kind,
            field_name="snapshot_kind",
        )
    )

    if (
        normalized_snapshot_kind
        not in SUPPORTED_SNAPSHOT_KINDS
    ):
        raise VentasNuevosSociosDetalleRepositoryError(
            "snapshot_kind inválido para "
            "Ventas Nuevos Socios Detalle: "
            f"{normalized_snapshot_kind!r}"
        )

    business_date_value = _ensure_date(
        business_date,
        field_name="business_date",
    )

    date_from_value = _ensure_date(
        date_from,
        field_name="date_from",
    )

    date_to_value = _ensure_date(
        date_to,
        field_name="date_to",
    )

    captured_at_value = _ensure_datetime(
        captured_at,
        field_name="captured_at",
    )

    if date_from_value > date_to_value:
        raise VentasNuevosSociosDetalleRepositoryError(
            "date_from no puede ser posterior a date_to."
        )

    if business_date_value != date_to_value:
        raise VentasNuevosSociosDetalleRepositoryError(
            "business_date debe ser igual a date_to."
        )

    normalized_snapshot = (
        _normalize_parsed_snapshot(parsed_snapshot)
    )

    metadata = {
        **normalized_snapshot["metadata"],
        "requested_by": (
            _ensure_optional_text(requested_by)
        ),
        "ingestion_source": (
            _ensure_optional_text(ingestion_source)
        ),
    }

    try:
        _apply_optional_advisory_lock(
            advisory_lock_key=advisory_lock_key
        )

        existing_snapshot = (
            _fetch_existing_snapshot_by_upload(
                warehouse_upload_id=(
                    normalized_upload_id
                )
            )
        )

        if existing_snapshot is not None:
            return _build_already_ingested_result(
                snapshot=existing_snapshot
            )

        canonicality_decision = (
            _resolve_canonicality_decision(
                business_date=business_date_value,
                date_from=date_from_value,
                date_to=date_to_value,
                snapshot_kind=(
                    normalized_snapshot_kind
                ),
                captured_at=captured_at_value,
                row_count_valid=int(
                    normalized_snapshot[
                        "row_count_valid"
                    ]
                ),
                row_count_rejected=int(
                    normalized_snapshot[
                        "row_count_rejected"
                    ]
                ),
                canonicality_resolver=(
                    canonicality_resolver
                ),
            )
        )

        snapshot = _insert_snapshot_header(
            warehouse_upload_id=normalized_upload_id,
            report_type_key=report_type_key,
            business_date=business_date_value,
            date_from=date_from_value,
            date_to=date_to_value,
            captured_at=captured_at_value,
            snapshot_kind=normalized_snapshot_kind,
            is_canonical=bool(
                canonicality_decision["is_canonical"]
            ),
            row_count_detected=(
                normalized_snapshot[
                    "row_count_detected"
                ]
            ),
            row_count_valid=(
                normalized_snapshot[
                    "row_count_valid"
                ]
            ),
            row_count_rejected=(
                normalized_snapshot[
                    "row_count_rejected"
                ]
            ),
            metadata=metadata,
        )

        rows_inserted = _insert_snapshot_rows(
            snapshot_id=snapshot.id,
            rows=normalized_snapshot["rows"],
        )

        if canonicality_decision[
            "replace_existing_canonical"
        ]:
            previous_canonical = (
                canonicality_decision[
                    "existing_canonical_snapshot"
                ]
            )

            if (
                previous_canonical is not None
                and previous_canonical.id != snapshot.id
            ):
                _set_snapshot_canonical_state(
                    snapshot=previous_canonical,
                    is_canonical=False,
                )

                _set_snapshot_canonical_state(
                    snapshot=snapshot,
                    is_canonical=True,
                )

        db.session.commit()

        return {
            "status": "ingested",
            "was_idempotent": False,
            "snapshot_id": snapshot.id,
            "warehouse_upload_id": (
                snapshot.warehouse_upload_id
            ),
            "report_type_key": (
                snapshot.report_type_key
            ),
            "business_date": (
                snapshot.business_date.isoformat()
            ),
            "date_from": (
                snapshot.date_from.isoformat()
            ),
            "date_to": snapshot.date_to.isoformat(),
            "captured_at": (
                snapshot.captured_at.isoformat()
            ),
            "snapshot_kind": snapshot.snapshot_kind,
            "is_canonical": bool(
                snapshot.is_canonical
            ),
            "row_count_detected": (
                snapshot.row_count_detected
            ),
            "row_count_valid": (
                snapshot.row_count_valid
            ),
            "row_count_rejected": (
                snapshot.row_count_rejected
            ),
            "rows_inserted": rows_inserted,
            "metadata": {
                **dict(snapshot.metadata_json or {}),
                "canonicality_reason": (
                    canonicality_decision["reason"]
                ),
                "existing_canonical_snapshot_id": (
                    canonicality_decision[
                        "existing_canonical_snapshot_id"
                    ]
                ),
            },
        }

    except IntegrityError as exc:
        db.session.rollback()

        existing_snapshot = (
            _fetch_existing_snapshot_by_upload(
                warehouse_upload_id=(
                    normalized_upload_id
                )
            )
        )

        if existing_snapshot is not None:
            return _build_already_ingested_result(
                snapshot=existing_snapshot
            )

        raise VentasNuevosSociosDetalleRepositoryError(
            "Falló la persistencia por conflicto "
            "de integridad."
        ) from exc

    except Exception as exc:
        db.session.rollback()

        if isinstance(
            exc,
            VentasNuevosSociosDetalleRepositoryError,
        ):
            raise

        raise VentasNuevosSociosDetalleRepositoryError(
            "Falló la persistencia estructurada de "
            "Ventas Nuevos Socios Detalle."
        ) from exc
