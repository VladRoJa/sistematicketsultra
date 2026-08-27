from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from sqlalchemy import tuple_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.warehouse import (
    SociosVencidosCarteraORM,
    SociosVencidosSnapshotORM,
    SociosVencidosSnapshotRowORM,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


SOCIOS_VENCIDOS_REPORT_TYPE_KEY = "socios_vencidos"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EDAD_STATUS_VALID = "VALID"
EDAD_STATUS_INVALID_OUT_OF_RANGE = "INVALID_OUT_OF_RANGE"
EDAD_STATUS_MISSING = "MISSING"
ROW_STORAGE_MODE_SNAPSHOT_ONLY = "SNAPSHOT_ONLY"
ROW_STORAGE_MODE_CARTERA_ONLY = "CARTERA_ONLY"
SUPPORTED_ROW_STORAGE_MODES = frozenset(
    {
        ROW_STORAGE_MODE_SNAPSHOT_ONLY,
        ROW_STORAGE_MODE_CARTERA_ONLY,
    }
)

_CARTERA_MUTABLE_FIELDS = (
    "sucursal_raw",
    "nombre",
    "genero",
    "edad_raw",
    "edad",
    "edad_status",
    "fecha_vencimiento_local",
    "fecha_ultimo_pago_local",
    "tarifa",
    "correo_raw",
    "telefono_raw",
    "telefono_digits",
    "adeudo",
    "row_hash",
)


class SociosVencidosRepositoryError(RuntimeError):
    """Error de persistencia de Socios Vencidos estructurado."""


def register_socios_vencidos_repository(app) -> None:
    app.config["WAREHOUSE_SOCIOS_VENCIDOS_REPOSITORY"] = (
        persist_socios_vencidos_snapshot
    )


def persist_socios_vencidos_snapshot(
    *,
    warehouse_upload_id: int,
    report_type_key: str,
    date_from: date | datetime | str,
    date_to: date | datetime | str,
    captured_at: datetime | str,
    parsed_snapshot: Any,
    row_storage_mode: str = ROW_STORAGE_MODE_SNAPSHOT_ONLY,
) -> dict[str, Any]:
    normalized_upload_id = _ensure_positive_int(
        warehouse_upload_id,
        field_name="warehouse_upload_id",
    )
    normalized_report_type = _normalize_required_text(
        report_type_key,
        field_name="report_type_key",
    )
    if normalized_report_type != SOCIOS_VENCIDOS_REPORT_TYPE_KEY:
        raise ValueError(
            "report_type_key no corresponde a socios_vencidos."
        )

    normalized_date_from = _ensure_date(date_from)
    normalized_date_to = _ensure_date(date_to)
    if normalized_date_from > normalized_date_to:
        raise ValueError("date_from no puede ser posterior a date_to.")

    normalized_captured_at = _ensure_aware_datetime(captured_at)
    normalized_storage_mode = _normalize_row_storage_mode(row_storage_mode)

    existing_snapshot = _find_snapshot_by_upload(
        warehouse_upload_id=normalized_upload_id
    )
    if existing_snapshot is not None:
        return _build_result(
            snapshot=existing_snapshot,
            status="already_ingested",
            was_idempotent=True,
            rows_inserted=0,
        )

    normalized_rows, counts = _normalize_parsed_snapshot(parsed_snapshot)
    now = _utc_now()

    try:
        snapshot = SociosVencidosSnapshotORM(
            warehouse_upload_id=normalized_upload_id,
            report_type_key=normalized_report_type,
            date_from=normalized_date_from,
            date_to=normalized_date_to,
            captured_at=normalized_captured_at,
            row_count_detected=counts["row_count_detected"],
            row_count_valid=counts["row_count_valid"],
            row_count_rejected=counts["row_count_rejected"],
            row_storage_mode=normalized_storage_mode,
            cartera_inserted_count=0,
            cartera_updated_count=0,
            cartera_existing_count=0,
            created_at=now,
            updated_at=now,
        )
        db.session.add(snapshot)
        db.session.flush()

        rows_inserted = 0
        cartera_counts = {
            "inserted": 0,
            "updated": 0,
            "existing": 0,
        }
        if normalized_storage_mode == ROW_STORAGE_MODE_SNAPSHOT_ONLY:
            rows_inserted = _insert_snapshot_rows(
                snapshot_id=int(snapshot.id),
                rows=normalized_rows,
                now=now,
            )
        else:
            cartera_counts = _upsert_cartera_rows(
                snapshot_id=int(snapshot.id),
                observed_at=normalized_captured_at,
                rows=normalized_rows,
            )
            snapshot.cartera_inserted_count = cartera_counts["inserted"]
            snapshot.cartera_updated_count = cartera_counts["updated"]
            snapshot.cartera_existing_count = cartera_counts["existing"]
            snapshot.updated_at = now
            db.session.flush()
        db.session.commit()

        return _build_result(
            snapshot=snapshot,
            status="ingested",
            was_idempotent=False,
            rows_inserted=rows_inserted,
            cartera_counts=cartera_counts,
        )
    except IntegrityError as exc:
        db.session.rollback()
        existing_snapshot = _find_snapshot_by_upload(
            warehouse_upload_id=normalized_upload_id
        )
        if existing_snapshot is not None:
            return _build_result(
                snapshot=existing_snapshot,
                status="already_ingested",
                was_idempotent=True,
                rows_inserted=0,
                cartera_counts=_snapshot_cartera_counts(existing_snapshot),
            )
        raise SociosVencidosRepositoryError(
            "Falló la persistencia por una restricción de integridad."
        ) from exc
    except Exception as exc:
        db.session.rollback()
        raise SociosVencidosRepositoryError(
            "Falló la persistencia transaccional de Socios Vencidos."
        ) from exc


def _find_snapshot_by_upload(
    *,
    warehouse_upload_id: int,
) -> SociosVencidosSnapshotORM | None:
    return SociosVencidosSnapshotORM.query.filter_by(
        warehouse_upload_id=warehouse_upload_id
    ).first()


def _normalize_parsed_snapshot(
    parsed_snapshot: Any,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    payload = _as_dict(parsed_snapshot)
    raw_rows = payload.get("rows") or []
    normalized_rows = [
        _normalize_row(_as_dict(raw_row))
        for raw_row in raw_rows
    ]

    row_count_valid = _ensure_nonnegative_int(
        payload.get("row_count_valid", len(normalized_rows)),
        field_name="row_count_valid",
    )
    row_count_rejected = _ensure_nonnegative_int(
        payload.get("row_count_rejected", 0),
        field_name="row_count_rejected",
    )
    row_count_detected = _ensure_nonnegative_int(
        payload.get(
            "row_count_detected",
            row_count_valid + row_count_rejected,
        ),
        field_name="row_count_detected",
    )

    if row_count_valid != len(normalized_rows):
        raise ValueError(
            "row_count_valid no coincide con la cantidad de filas parseadas."
        )
    if row_count_detected != row_count_valid + row_count_rejected:
        raise ValueError(
            "row_count_detected debe ser igual a valid + rejected."
        )

    return normalized_rows, {
        "row_count_detected": row_count_detected,
        "row_count_valid": row_count_valid,
        "row_count_rejected": row_count_rejected,
    }


def _normalize_row_storage_mode(value: Any) -> str:
    normalized = _normalize_required_text(
        value,
        field_name="row_storage_mode",
    ).upper()
    if normalized not in SUPPORTED_ROW_STORAGE_MODES:
        raise ValueError(
            "row_storage_mode no soportado. "
            f"Permitidos: {sorted(SUPPORTED_ROW_STORAGE_MODES)}."
        )
    return normalized


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    row_hash = _normalize_required_text(
        row.get("row_hash"),
        field_name="row_hash",
    ).lower()
    if not _SHA256_RE.fullmatch(row_hash):
        raise ValueError("row_hash debe ser un SHA-256 hexadecimal.")

    fecha_vencimiento_local = _ensure_local_datetime(
        row.get("fecha_vencimiento_local"),
        field_name="fecha_vencimiento_local",
    )
    fecha_vencimiento_date = _ensure_date(
        row.get("fecha_vencimiento_date")
    )
    if fecha_vencimiento_local.date() != fecha_vencimiento_date:
        raise ValueError(
            "fecha_vencimiento_date no coincide con fecha_vencimiento_local."
        )

    edad_raw, edad, edad_status = _normalize_age_fields(row)

    sucursal_raw = _normalize_required_text(
        row.get("sucursal_raw"),
        field_name="sucursal_raw",
    )
    sucursal_key = normalize_socios_vencidos_branch_key(sucursal_raw)
    if not sucursal_key:
        raise ValueError("sucursal_raw no produce una sucursal_key válida.")

    return {
        "row_index": _ensure_nonnegative_int(
            row.get("row_index"),
            field_name="row_index",
        ),
        "source_row_number": _ensure_optional_positive_int(
            row.get("source_row_number"),
            field_name="source_row_number",
        ),
        "pin": _normalize_required_text(
            row.get("pin"),
            field_name="pin",
        ),
        "nombre": _normalize_optional_text(row.get("nombre")),
        "genero": _normalize_optional_text(row.get("genero")),
        "edad_raw": edad_raw,
        "edad": edad,
        "edad_status": edad_status,
        "fecha_vencimiento_local": fecha_vencimiento_local,
        "fecha_vencimiento_date": fecha_vencimiento_date,
        "fecha_ultimo_pago_local": _ensure_optional_local_datetime(
            row.get("fecha_ultimo_pago_local"),
            field_name="fecha_ultimo_pago_local",
        ),
        "tarifa": _normalize_optional_text(row.get("tarifa")),
        "correo_raw": _normalize_optional_text(row.get("correo_raw")),
        "telefono_raw": _normalize_optional_text(row.get("telefono_raw")),
        "telefono_digits": _normalize_optional_text(
            row.get("telefono_digits")
        ),
        "sucursal_raw": sucursal_raw,
        "sucursal_key": sucursal_key,
        "adeudo": _ensure_optional_decimal(
            row.get("adeudo"),
            field_name="adeudo",
        ),
        "row_hash": row_hash,
    }


def _normalize_age_fields(
    row: dict[str, Any],
) -> tuple[int | None, int | None, str]:
    edad_raw = _ensure_optional_int(
        row.get("edad_raw"),
        field_name="edad_raw",
    )
    edad = _ensure_optional_int(
        row.get("edad"),
        field_name="edad",
    )
    edad_status = _normalize_required_text(
        row.get("edad_status"),
        field_name="edad_status",
    )

    if edad_status == EDAD_STATUS_VALID:
        if edad_raw is None or not 0 <= edad_raw <= 120 or edad != edad_raw:
            raise ValueError(
                "La edad VALID requiere edad_raw entre 0 y 120 y edad igual."
            )
    elif edad_status == EDAD_STATUS_INVALID_OUT_OF_RANGE:
        if (
            edad_raw is None
            or 0 <= edad_raw <= 120
            or edad is not None
        ):
            raise ValueError(
                "La edad INVALID_OUT_OF_RANGE requiere edad_raw fuera de rango "
                "y edad NULL."
            )
    elif edad_status == EDAD_STATUS_MISSING:
        if edad_raw is not None or edad is not None:
            raise ValueError(
                "La edad MISSING requiere edad_raw y edad NULL."
            )
    else:
        raise ValueError(f"edad_status no soportado: {edad_status!r}.")

    return edad_raw, edad, edad_status


def _insert_snapshot_rows(
    *,
    snapshot_id: int,
    rows: list[dict[str, Any]],
    now: datetime,
) -> int:
    orm_rows = [
        SociosVencidosSnapshotRowORM(
            snapshot_id=snapshot_id,
            created_at=now,
            updated_at=now,
            **{
                key: value
                for key, value in row.items()
                if key != "sucursal_key"
            },
        )
        for row in rows
    ]
    if orm_rows:
        db.session.add_all(orm_rows)
        db.session.flush()
    return len(orm_rows)


def _upsert_cartera_rows(
    *,
    snapshot_id: int,
    observed_at: datetime,
    rows: list[dict[str, Any]],
    session: Any | None = None,
) -> dict[str, int]:
    active_session = session if session is not None else db.session
    existing_by_key = _read_existing_cartera_rows(
        rows=rows,
        session=active_session,
    )
    counts = {"inserted": 0, "updated": 0, "existing": 0}

    for row in rows:
        episode_key = _cartera_episode_key(row)
        existing = existing_by_key.get(episode_key)

        if existing is None:
            cartera_row = SociosVencidosCarteraORM(
                sucursal_key=row["sucursal_key"],
                pin=row["pin"],
                fecha_vencimiento_date=row["fecha_vencimiento_date"],
                first_seen_at=observed_at,
                last_seen_at=observed_at,
                first_source_snapshot_id=snapshot_id,
                last_source_snapshot_id=snapshot_id,
                **{
                    field_name: row[field_name]
                    for field_name in _CARTERA_MUTABLE_FIELDS
                },
            )
            active_session.add(cartera_row)
            existing_by_key[episode_key] = cartera_row
            counts["inserted"] += 1
            continue

        is_latest_observation = observed_at >= existing.last_seen_at
        if str(existing.row_hash) == row["row_hash"]:
            counts["existing"] += 1
        elif is_latest_observation:
            for field_name in _CARTERA_MUTABLE_FIELDS:
                setattr(existing, field_name, row[field_name])
            counts["updated"] += 1
        else:
            counts["existing"] += 1

        if is_latest_observation:
            existing.last_seen_at = observed_at
            existing.last_source_snapshot_id = snapshot_id

    if rows:
        active_session.flush()
    return counts


def _read_existing_cartera_rows(
    *,
    rows: list[dict[str, Any]],
    session: Any,
) -> dict[tuple[str, str, date], SociosVencidosCarteraORM]:
    episode_keys = tuple(sorted({_cartera_episode_key(row) for row in rows}))
    if not episode_keys:
        return {}

    existing_rows = (
        session.query(SociosVencidosCarteraORM)
        .filter(
            tuple_(
                SociosVencidosCarteraORM.sucursal_key,
                SociosVencidosCarteraORM.pin,
                SociosVencidosCarteraORM.fecha_vencimiento_date,
            ).in_(episode_keys)
        )
        .all()
    )
    return {
        (
            str(row.sucursal_key),
            str(row.pin),
            row.fecha_vencimiento_date,
        ): row
        for row in existing_rows
    }


def _cartera_episode_key(row: dict[str, Any]) -> tuple[str, str, date]:
    return (
        str(row["sucursal_key"]),
        str(row["pin"]),
        row["fecha_vencimiento_date"],
    )


def seed_socios_vencidos_cartera_from_existing_snapshots(
    *,
    snapshot_id: int | None = None,
    session: Any | None = None,
) -> dict[str, int]:
    """Puebla cartera desde snapshots legacy sin ejecutarse al importar."""

    active_session = session if session is not None else db.session
    query = active_session.query(SociosVencidosSnapshotORM)
    if snapshot_id is not None:
        normalized_snapshot_id = _ensure_positive_int(
            snapshot_id,
            field_name="snapshot_id",
        )
        query = query.filter(SociosVencidosSnapshotORM.id == normalized_snapshot_id)

    snapshots = query.order_by(
        SociosVencidosSnapshotORM.captured_at.asc(),
        SociosVencidosSnapshotORM.id.asc(),
    ).all()
    if snapshot_id is not None and not snapshots:
        raise SociosVencidosRepositoryError(
            f"No existe el snapshot de Socios Vencidos id={snapshot_id}."
        )

    totals = {
        "snapshots_processed": 0,
        "rows_read": 0,
        "inserted": 0,
        "updated": 0,
        "existing": 0,
    }
    try:
        for snapshot in snapshots:
            snapshot_rows = (
                active_session.query(SociosVencidosSnapshotRowORM)
                .filter(
                    SociosVencidosSnapshotRowORM.snapshot_id
                    == int(snapshot.id)
                )
                .order_by(SociosVencidosSnapshotRowORM.row_index.asc())
                .all()
            )
            normalized_rows = [
                _normalize_row(_snapshot_row_to_payload(row))
                for row in snapshot_rows
            ]
            counts = _upsert_cartera_rows(
                snapshot_id=int(snapshot.id),
                observed_at=_ensure_aware_datetime(snapshot.captured_at),
                rows=normalized_rows,
                session=active_session,
            )
            totals["snapshots_processed"] += 1
            totals["rows_read"] += len(normalized_rows)
            for key in ("inserted", "updated", "existing"):
                totals[key] += counts[key]

        active_session.commit()
    except Exception as exc:
        active_session.rollback()
        raise SociosVencidosRepositoryError(
            "Falló el seed transaccional de cartera desde snapshots."
        ) from exc

    return totals


def _snapshot_row_to_payload(row: Any) -> dict[str, Any]:
    return {
        "row_index": row.row_index,
        "source_row_number": row.source_row_number,
        "pin": row.pin,
        "nombre": row.nombre,
        "genero": row.genero,
        "edad_raw": row.edad_raw,
        "edad": row.edad,
        "edad_status": row.edad_status,
        "fecha_vencimiento_local": row.fecha_vencimiento_local,
        "fecha_vencimiento_date": row.fecha_vencimiento_date,
        "fecha_ultimo_pago_local": row.fecha_ultimo_pago_local,
        "tarifa": row.tarifa,
        "correo_raw": row.correo_raw,
        "telefono_raw": row.telefono_raw,
        "telefono_digits": row.telefono_digits,
        "sucursal_raw": row.sucursal_raw,
        "adeudo": row.adeudo,
        "row_hash": row.row_hash,
    }


def _build_result(
    *,
    snapshot: SociosVencidosSnapshotORM,
    status: str,
    was_idempotent: bool,
    rows_inserted: int,
    cartera_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    normalized_cartera_counts = (
        cartera_counts
        if cartera_counts is not None
        else _snapshot_cartera_counts(snapshot)
    )
    return {
        "status": status,
        "was_idempotent": was_idempotent,
        "snapshot_id": int(snapshot.id),
        "warehouse_upload_id": int(snapshot.warehouse_upload_id),
        "report_type_key": str(snapshot.report_type_key),
        "date_from": snapshot.date_from.isoformat(),
        "date_to": snapshot.date_to.isoformat(),
        "captured_at": snapshot.captured_at.isoformat(),
        "row_count_detected": int(snapshot.row_count_detected),
        "row_count_valid": int(snapshot.row_count_valid),
        "row_count_rejected": int(snapshot.row_count_rejected),
        "row_storage_mode": str(
            getattr(snapshot, "row_storage_mode", ROW_STORAGE_MODE_SNAPSHOT_ONLY)
        ),
        "rows_inserted": rows_inserted,
        "cartera_inserted": normalized_cartera_counts["inserted"],
        "cartera_updated": normalized_cartera_counts["updated"],
        "cartera_existing": normalized_cartera_counts["existing"],
    }


def _snapshot_cartera_counts(
    snapshot: SociosVencidosSnapshotORM,
) -> dict[str, int]:
    return {
        "inserted": int(getattr(snapshot, "cartera_inserted_count", 0)),
        "updated": int(getattr(snapshot, "cartera_updated_count", 0)),
        "existing": int(getattr(snapshot, "cartera_existing_count", 0)),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    raise ValueError("Se esperaba dict o dataclass serializable.")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"No se pudo convertir a date: {value!r}")


def _ensure_aware_datetime(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise ValueError(f"No se pudo convertir a datetime: {value!r}")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _ensure_local_datetime(
    value: Any,
    *,
    field_name: str,
) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"No se pudo convertir {field_name} a datetime."
            ) from exc
    if not isinstance(value, datetime):
        raise ValueError(
            f"No se pudo convertir {field_name} a datetime."
        )
    return value.replace(tzinfo=None)


def _ensure_optional_local_datetime(
    value: Any,
    *,
    field_name: str,
) -> datetime | None:
    if value is None or value == "":
        return None
    return _ensure_local_datetime(value, field_name=field_name)


def _normalize_required_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"El campo {field_name!r} es obligatorio.")
    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _ensure_positive_int(value: Any, *, field_name: str) -> int:
    normalized = _ensure_nonnegative_int(value, field_name=field_name)
    if normalized <= 0:
        raise ValueError(f"{field_name} debe ser entero positivo.")
    return normalized


def _ensure_nonnegative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} no puede ser bool.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} debe ser entero.") from exc
    if normalized < 0:
        raise ValueError(f"{field_name} no puede ser negativo.")
    return normalized


def _ensure_optional_int(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} no puede ser bool.")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} debe ser entero.") from exc
    if decimal_value != decimal_value.to_integral_value():
        raise ValueError(f"{field_name} debe ser entero.")
    return int(decimal_value)


def _ensure_optional_positive_int(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None or value == "":
        return None
    return _ensure_positive_int(value, field_name=field_name)


def _ensure_optional_nonnegative_int(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None or value == "":
        return None
    return _ensure_nonnegative_int(value, field_name=field_name)


def _ensure_optional_decimal(
    value: Any,
    *,
    field_name: str,
) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} debe ser Decimal.") from exc
