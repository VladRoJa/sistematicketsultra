from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.warehouse import (
    SociosActivosSnapshotORM,
    SociosActivosSnapshotRowORM,
)


SOCIOS_ACTIVOS_REPORT_TYPE_KEY = "socios_activos"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SociosActivosRepositoryError(RuntimeError):
    """Error de persistencia de Socios Activos estructurado."""


def register_socios_activos_repository(app) -> None:
    app.config["WAREHOUSE_SOCIOS_ACTIVOS_REPOSITORY"] = (
        persist_socios_activos_snapshot
    )


def persist_socios_activos_snapshot(
    *,
    warehouse_upload_id: int,
    report_type_key: str,
    cutoff_date: date | datetime | str,
    captured_at: datetime | str,
    snapshot_kind: str,
    is_canonical: bool,
    parsed_snapshot: Any,
) -> dict[str, Any]:
    normalized_upload_id = _ensure_positive_int(
        warehouse_upload_id,
        field_name="warehouse_upload_id",
    )

    normalized_report_type = _normalize_required_text(
        report_type_key,
        field_name="report_type_key",
    )

    if normalized_report_type != SOCIOS_ACTIVOS_REPORT_TYPE_KEY:
        raise ValueError(
            "report_type_key no corresponde a socios_activos."
        )

    normalized_cutoff_date = _ensure_date(
        cutoff_date
    )

    normalized_captured_at = _ensure_aware_datetime(
        captured_at
    )

    normalized_snapshot_kind = _normalize_required_text(
        snapshot_kind,
        field_name="snapshot_kind",
    )

    normalized_is_canonical = _ensure_bool(
        is_canonical,
        field_name="is_canonical",
    )

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

    normalized_rows, counts = _normalize_parsed_snapshot(
        parsed_snapshot
    )

    now = _utc_now()

    try:
        snapshot = SociosActivosSnapshotORM(
            warehouse_upload_id=normalized_upload_id,
            report_type_key=normalized_report_type,
            cutoff_date=normalized_cutoff_date,
            captured_at=normalized_captured_at,
            snapshot_kind=normalized_snapshot_kind,
            is_canonical=normalized_is_canonical,
            row_count_detected=counts[
                "row_count_detected"
            ],
            row_count_valid=counts[
                "row_count_valid"
            ],
            row_count_rejected=counts[
                "row_count_rejected"
            ],
            created_at=now,
            updated_at=now,
        )

        db.session.add(snapshot)
        db.session.flush()

        rows_inserted = _insert_snapshot_rows(
            snapshot_id=int(snapshot.id),
            rows=normalized_rows,
            now=now,
        )

        db.session.commit()

        return _build_result(
            snapshot=snapshot,
            status="ingested",
            was_idempotent=False,
            rows_inserted=rows_inserted,
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
            )

        raise SociosActivosRepositoryError(
            "Falló la persistencia por una "
            "restricción de integridad."
        ) from exc

    except Exception as exc:
        db.session.rollback()

        raise SociosActivosRepositoryError(
            "Falló la persistencia transaccional "
            "de Socios Activos."
        ) from exc


def _find_snapshot_by_upload(
    *,
    warehouse_upload_id: int,
) -> SociosActivosSnapshotORM | None:
    return SociosActivosSnapshotORM.query.filter_by(
        warehouse_upload_id=warehouse_upload_id
    ).first()


def _normalize_parsed_snapshot(
    parsed_snapshot: Any,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    payload = _as_dict(parsed_snapshot)

    raw_rows = payload.get("rows") or []

    normalized_rows = [
        _normalize_row(
            _as_dict(raw_row)
        )
        for raw_row in raw_rows
    ]

    row_count_valid = _ensure_nonnegative_int(
        payload.get(
            "row_count_valid",
            len(normalized_rows),
        ),
        field_name="row_count_valid",
    )

    row_count_rejected = _ensure_nonnegative_int(
        payload.get(
            "row_count_rejected",
            0,
        ),
        field_name="row_count_rejected",
    )

    row_count_detected = _ensure_nonnegative_int(
        payload.get(
            "row_count_detected",
            row_count_valid
            + row_count_rejected,
        ),
        field_name="row_count_detected",
    )

    if row_count_valid != len(normalized_rows):
        raise ValueError(
            "row_count_valid no coincide con la "
            "cantidad de filas parseadas."
        )

    if (
        row_count_detected
        != row_count_valid
        + row_count_rejected
    ):
        raise ValueError(
            "row_count_detected debe ser igual "
            "a valid + rejected."
        )

    return normalized_rows, {
        "row_count_detected": row_count_detected,
        "row_count_valid": row_count_valid,
        "row_count_rejected": row_count_rejected,
    }


def _normalize_row(
    row: dict[str, Any],
) -> dict[str, Any]:
    row_hash = _normalize_required_text(
        row.get("row_hash"),
        field_name="row_hash",
    ).lower()

    if not _SHA256_RE.fullmatch(row_hash):
        raise ValueError(
            "row_hash debe ser un SHA-256 hexadecimal."
        )

    fecha_vencimiento_local = _ensure_local_datetime(
        row.get("fecha_vencimiento_local"),
        field_name="fecha_vencimiento_local",
    )

    fecha_vencimiento_date = _ensure_date(
        row.get("fecha_vencimiento_date")
    )

    if (
        fecha_vencimiento_local.date()
        != fecha_vencimiento_date
    ):
        raise ValueError(
            "fecha_vencimiento_date no coincide "
            "con fecha_vencimiento_local."
        )

    aplica_kpi_raw = _normalize_required_text(
        row.get("aplica_kpi_raw"),
        field_name="aplica_kpi_raw",
    )

    aplica_kpi = _ensure_bool(
        row.get("aplica_kpi"),
        field_name="aplica_kpi",
    )

    _validate_aplica_kpi_pair(
        aplica_kpi_raw=aplica_kpi_raw,
        aplica_kpi=aplica_kpi,
    )

    return {
        "row_index": _ensure_nonnegative_int(
            row.get("row_index"),
            field_name="row_index",
        ),
        "source_row_number": (
            _ensure_optional_positive_int(
                row.get("source_row_number"),
                field_name="source_row_number",
            )
        ),
        "id_socio": _normalize_required_text(
            row.get("id_socio"),
            field_name="id_socio",
        ),
        "pin": _normalize_required_text(
            row.get("pin"),
            field_name="pin",
        ),
        "nombre": _normalize_optional_text(
            row.get("nombre")
        ),
        "sucursal_raw": _normalize_required_text(
            row.get("sucursal_raw"),
            field_name="sucursal_raw",
        ),
        "fecha_ultimo_pago_local": (
            _ensure_optional_local_datetime(
                row.get(
                    "fecha_ultimo_pago_local"
                ),
                field_name=(
                    "fecha_ultimo_pago_local"
                ),
            )
        ),
        "fecha_vencimiento_local": (
            fecha_vencimiento_local
        ),
        "fecha_vencimiento_date": (
            fecha_vencimiento_date
        ),
        "fecha_ingreso_local": (
            _ensure_optional_local_datetime(
                row.get(
                    "fecha_ingreso_local"
                ),
                field_name="fecha_ingreso_local",
            )
        ),
        "fecha_firma_local": (
            _ensure_optional_local_datetime(
                row.get(
                    "fecha_firma_local"
                ),
                field_name="fecha_firma_local",
            )
        ),
        "tarifa": _normalize_optional_text(
            row.get("tarifa")
        ),
        "importe_tarifa": _ensure_optional_decimal(
            row.get("importe_tarifa"),
            field_name="importe_tarifa",
        ),
        "lada_raw": _normalize_optional_text(
            row.get("lada_raw")
        ),
        "telefono_raw": _normalize_optional_text(
            row.get("telefono_raw")
        ),
        "telefono_digits": _normalize_optional_text(
            row.get("telefono_digits")
        ),
        "aplica_kpi_raw": aplica_kpi_raw,
        "aplica_kpi": aplica_kpi,
        "email_raw": _normalize_optional_text(
            row.get("email_raw")
        ),
        "row_hash": row_hash,
    }


def _validate_aplica_kpi_pair(
    *,
    aplica_kpi_raw: str,
    aplica_kpi: bool,
) -> None:
    token = "".join(
        character
        for character in unicodedata.normalize(
            "NFKD",
            aplica_kpi_raw,
        )
        if not unicodedata.combining(character)
    ).casefold()

    if token == "si":
        expected = True
    elif token == "no":
        expected = False
    else:
        raise ValueError(
            "aplica_kpi_raw no contiene un valor "
            "soportado de Gasca."
        )

    if aplica_kpi is not expected:
        raise ValueError(
            "aplica_kpi no coincide con aplica_kpi_raw."
        )


def _insert_snapshot_rows(
    *,
    snapshot_id: int,
    rows: list[dict[str, Any]],
    now: datetime,
) -> int:
    orm_rows = [
        SociosActivosSnapshotRowORM(
            snapshot_id=snapshot_id,
            created_at=now,
            updated_at=now,
            **row,
        )
        for row in rows
    ]

    if orm_rows:
        db.session.add_all(orm_rows)
        db.session.flush()

    return len(orm_rows)


def _build_result(
    *,
    snapshot: SociosActivosSnapshotORM,
    status: str,
    was_idempotent: bool,
    rows_inserted: int,
) -> dict[str, Any]:
    return {
        "status": status,
        "was_idempotent": was_idempotent,
        "snapshot_id": int(snapshot.id),
        "warehouse_upload_id": int(
            snapshot.warehouse_upload_id
        ),
        "report_type_key": str(
            snapshot.report_type_key
        ),
        "cutoff_date": (
            snapshot.cutoff_date.isoformat()
        ),
        "captured_at": (
            snapshot.captured_at.isoformat()
        ),
        "snapshot_kind": str(
            snapshot.snapshot_kind
        ),
        "is_canonical": bool(
            snapshot.is_canonical
        ),
        "row_count_detected": int(
            snapshot.row_count_detected
        ),
        "row_count_valid": int(
            snapshot.row_count_valid
        ),
        "row_count_rejected": int(
            snapshot.row_count_rejected
        ),
        "rows_inserted": rows_inserted,
    }


def _as_dict(
    value: Any,
) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if is_dataclass(value):
        return asdict(value)

    raise ValueError(
        "Se esperaba dict o dataclass serializable."
    )


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _ensure_date(
    value: Any,
) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return date.fromisoformat(
            value
        )

    raise ValueError(
        f"No se pudo convertir a date: {value!r}"
    )


def _ensure_aware_datetime(
    value: Any,
) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(
            value
        )

    if not isinstance(value, datetime):
        raise ValueError(
            "No se pudo convertir a datetime: "
            f"{value!r}"
        )

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value


def _ensure_local_datetime(
    value: Any,
    *,
    field_name: str,
) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(
                value
            )
        except ValueError as exc:
            raise ValueError(
                f"No se pudo convertir "
                f"{field_name} a datetime."
            ) from exc

    if not isinstance(value, datetime):
        raise ValueError(
            f"No se pudo convertir "
            f"{field_name} a datetime."
        )

    return value.replace(
        tzinfo=None
    )


def _ensure_optional_local_datetime(
    value: Any,
    *,
    field_name: str,
) -> datetime | None:
    if value is None or value == "":
        return None

    return _ensure_local_datetime(
        value,
        field_name=field_name,
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
        raise ValueError(
            f"El campo {field_name!r} "
            "es obligatorio."
        )

    return normalized


def _normalize_optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(
        value
    ).strip()

    return normalized or None


def _ensure_bool(
    value: Any,
    *,
    field_name: str,
) -> bool:
    if not isinstance(value, bool):
        raise ValueError(
            f"{field_name} debe ser bool."
        )

    return value


def _ensure_positive_int(
    value: Any,
    *,
    field_name: str,
) -> int:
    normalized = _ensure_nonnegative_int(
        value,
        field_name=field_name,
    )

    if normalized <= 0:
        raise ValueError(
            f"{field_name} debe ser "
            "entero positivo."
        )

    return normalized


def _ensure_nonnegative_int(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} no puede ser bool."
        )

    try:
        normalized = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{field_name} debe ser entero."
        ) from exc

    if normalized < 0:
        raise ValueError(
            f"{field_name} no puede ser negativo."
        )

    return normalized


def _ensure_optional_positive_int(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None or value == "":
        return None

    return _ensure_positive_int(
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

    try:
        return Decimal(
            str(value)
        )
    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{field_name} debe ser Decimal."
        ) from exc


def promote_socios_activos_snapshot_canonical(
    *,
    snapshot_id: int,
    expected_cutoff_date: date | datetime | str | None = None,
    expected_snapshot_kind: str | None = "daily",
    auto_commit: bool = False,
) -> dict[str, Any]:
    """
    Promueve explícitamente un snapshot de Socios Activos como canónico.

    La canonicalidad representa una decisión explícita sobre qué universo
    de socios activos debe usarse como referencia para un cutoff_date.

    Todos los snapshots del mismo cutoff_date + snapshot_kind se bloquean
    FOR UPDATE antes de cambiar canonicalidad.
    """
    try:
        normalized_snapshot_id = int(snapshot_id)
    except Exception as exc:
        raise SociosActivosRepositoryError(
            f"snapshot_id inválido: {snapshot_id!r}"
        ) from exc

    if normalized_snapshot_id <= 0:
        raise SociosActivosRepositoryError(
            "snapshot_id debe ser un entero positivo."
        )

    snapshot_probe = (
        SociosActivosSnapshotORM.query
        .filter_by(id=normalized_snapshot_id)
        .one_or_none()
    )

    if snapshot_probe is None:
        raise SociosActivosRepositoryError(
            "No existe snapshot Socios Activos con "
            f"id={normalized_snapshot_id}."
        )

    if (
        snapshot_probe.report_type_key
        != SOCIOS_ACTIVOS_REPORT_TYPE_KEY
    ):
        raise SociosActivosRepositoryError(
            "El snapshot solicitado no corresponde a "
            "socios_activos. "
            f"snapshot_id={normalized_snapshot_id} "
            f"report_type_key="
            f"{snapshot_probe.report_type_key!r}."
        )

    if expected_cutoff_date is not None:
        normalized_expected_cutoff_date = _ensure_date(
            expected_cutoff_date
        )

        if (
            snapshot_probe.cutoff_date
            != normalized_expected_cutoff_date
        ):
            raise SociosActivosRepositoryError(
                "cutoff_date inesperado para promoción "
                "canónica. "
                f"snapshot_id={normalized_snapshot_id} "
                f"esperado="
                f"{normalized_expected_cutoff_date.isoformat()} "
                f"real={snapshot_probe.cutoff_date.isoformat()}."
            )

    if expected_snapshot_kind is not None:
        normalized_expected_snapshot_kind = str(
            expected_snapshot_kind
        ).strip()

        if (
            snapshot_probe.snapshot_kind
            != normalized_expected_snapshot_kind
        ):
            raise SociosActivosRepositoryError(
                "snapshot_kind inesperado para promoción "
                "canónica. "
                f"snapshot_id={normalized_snapshot_id} "
                f"esperado="
                f"{normalized_expected_snapshot_kind!r} "
                f"real={snapshot_probe.snapshot_kind!r}."
            )

    snapshots_for_scope = (
        SociosActivosSnapshotORM.query
        .filter_by(
            cutoff_date=snapshot_probe.cutoff_date,
            snapshot_kind=snapshot_probe.snapshot_kind,
        )
        .order_by(
            SociosActivosSnapshotORM.id.asc()
        )
        .with_for_update()
        .all()
    )

    snapshot = next(
        (
            candidate
            for candidate in snapshots_for_scope
            if candidate.id == normalized_snapshot_id
        ),
        None,
    )

    if snapshot is None:
        raise SociosActivosRepositoryError(
            "El snapshot desapareció durante la promoción "
            "canónica. "
            f"snapshot_id={normalized_snapshot_id}."
        )

    replaced_snapshot_ids: list[int] = []

    now = _utc_now()

    for candidate in snapshots_for_scope:
        if candidate.id == snapshot.id:
            continue

        if candidate.is_canonical:
            candidate.is_canonical = False
            candidate.updated_at = now
            replaced_snapshot_ids.append(
                int(candidate.id)
            )

    # Primero quitamos canonicalidad a snapshots anteriores.
    # Este flush intermedio conserva compatibilidad con un posible
    # índice único parcial de canonicalidad.
    db.session.flush()

    snapshot.is_canonical = True
    snapshot.updated_at = now

    db.session.flush()

    if auto_commit:
        db.session.commit()

    return {
        "status": "promoted",
        "snapshot_id": int(snapshot.id),
        "cutoff_date": snapshot.cutoff_date.isoformat(),
        "snapshot_kind": snapshot.snapshot_kind,
        "is_canonical": True,
        "replaced_snapshot_ids": replaced_snapshot_ids,
    }
