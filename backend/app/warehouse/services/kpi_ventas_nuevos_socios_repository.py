# backend/app/warehouse/services/kpi_ventas_nuevos_socios_repository.py


from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.warehouse import (
    KpiVentasNuevosSociosSnapshotORM,
    KpiVentasNuevosSociosSnapshotRowORM,
)


KPI_VENTAS_NUEVOS_SOCIOS_REPORT_TYPE_KEY = "kpi_ventas_nuevos_socios"


class KpiVentasNuevosSociosRepositoryError(RuntimeError):
    """Error base del repository estructurado de KPI Ventas Nuevos Socios."""


def register_kpi_ventas_nuevos_socios_repository(app) -> None:
    app.config["WAREHOUSE_KPI_VENTAS_NUEVOS_SOCIOS_REPOSITORY"] = (
        persist_kpi_ventas_nuevos_socios_snapshot
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    raise ValueError("Se esperaba dict o dataclass serializable.")


def _ensure_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        return date.fromisoformat(value)

    raise ValueError(f"No se pudo convertir a date: {value!r}")


def _ensure_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    if value is None:
        return _utc_now()

    raise ValueError(f"No se pudo convertir a datetime: {value!r}")


def _ensure_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} no puede ser bool.")

    try:
        return int(value)
    except Exception as exc:
        raise ValueError(
            f"No se pudo convertir a int el campo {field_name!r}: {value!r}"
        ) from exc


def _ensure_decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError(
            f"No se pudo convertir a Decimal el campo {field_name!r}: {value!r}"
        ) from exc


def _rows_from_parsed_snapshot(parsed_snapshot: Any) -> list[dict[str, Any]]:
    parsed_dict = _as_dict(parsed_snapshot)
    raw_rows = parsed_dict.get("rows") or []

    normalized_rows: list[dict[str, Any]] = []
    for raw_row in raw_rows:
        row = _as_dict(raw_row)

        normalized_rows.append(
            {
                "row_index": _ensure_int(
                    row.get("row_index"),
                    field_name="row_index",
                ),
                "sucursal": str(row.get("sucursal") or "").strip(),
                "numero_cnm_meta": _ensure_int(
                    row.get("numero_cnm_meta"),
                    field_name="numero_cnm_meta",
                ),
                "ingreso_por_cnm_meta": _ensure_decimal(
                    row.get("ingreso_por_cnm_meta"),
                    field_name="ingreso_por_cnm_meta",
                ),
                "clientes_nuevos_real": _ensure_int(
                    row.get("clientes_nuevos_real"),
                    field_name="clientes_nuevos_real",
                ),
                "ingreso_clientes_nuevos_real": _ensure_decimal(
                    row.get("ingreso_clientes_nuevos_real"),
                    field_name="ingreso_clientes_nuevos_real",
                ),
                "cnreal_menos_meta_cnm": _ensure_int(
                    row.get("cnreal_menos_meta_cnm"),
                    field_name="cnreal_menos_meta_cnm",
                ),
                "porcentaje_meta": _ensure_decimal(
                    row.get("porcentaje_meta"),
                    field_name="porcentaje_meta",
                ),
                "cnreal_menos_meta_cnm_alt": _ensure_decimal(
                    row.get("cnreal_menos_meta_cnm_alt"),
                    field_name="cnreal_menos_meta_cnm_alt",
                ),
                "porcentaje_meta_alt": _ensure_decimal(
                    row.get("porcentaje_meta_alt"),
                    field_name="porcentaje_meta_alt",
                ),
            }
        )

    return normalized_rows


def _fetch_existing_snapshot_by_upload(
    *,
    warehouse_upload_id: int,
) -> KpiVentasNuevosSociosSnapshotORM | None:
    return (
        KpiVentasNuevosSociosSnapshotORM.query.filter_by(
            warehouse_upload_id=warehouse_upload_id
        )
        .first()
    )


def _fetch_existing_canonical_snapshot_for_day(
    *,
    business_date: date,
    snapshot_kind: str,
) -> KpiVentasNuevosSociosSnapshotORM | None:
    return (
        KpiVentasNuevosSociosSnapshotORM.query.filter_by(
            business_date=business_date,
            snapshot_kind=snapshot_kind,
            is_canonical=True,
        )
        .order_by(KpiVentasNuevosSociosSnapshotORM.id.desc())
        .first()
    )


def _insert_snapshot_header(
    *,
    warehouse_upload_id: int,
    report_type_key: str,
    business_date: date,
    captured_at: datetime,
    snapshot_kind: str,
    is_canonical: bool,
    row_count_detected: int,
    row_count_valid: int,
    row_count_rejected: int,
) -> KpiVentasNuevosSociosSnapshotORM:
    now = _utc_now()

    snapshot = KpiVentasNuevosSociosSnapshotORM(
        warehouse_upload_id=warehouse_upload_id,
        report_type_key=report_type_key,
        business_date=business_date,
        captured_at=captured_at,
        snapshot_kind=snapshot_kind,
        is_canonical=is_canonical,
        row_count_detected=row_count_detected,
        row_count_valid=row_count_valid,
        row_count_rejected=row_count_rejected,
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
        KpiVentasNuevosSociosSnapshotRowORM(
            snapshot_id=snapshot_id,
            row_index=row["row_index"],
            sucursal=row["sucursal"],
            numero_cnm_meta=row["numero_cnm_meta"],
            ingreso_por_cnm_meta=row["ingreso_por_cnm_meta"],
            clientes_nuevos_real=row["clientes_nuevos_real"],
            ingreso_clientes_nuevos_real=row["ingreso_clientes_nuevos_real"],
            cnreal_menos_meta_cnm=row["cnreal_menos_meta_cnm"],
            porcentaje_meta=row["porcentaje_meta"],
            cnreal_menos_meta_cnm_alt=row["cnreal_menos_meta_cnm_alt"],
            porcentaje_meta_alt=row["porcentaje_meta_alt"],
            created_at=now,
            updated_at=now,
        )
        for row in rows
    ]

    db.session.add_all(orm_rows)
    db.session.flush()

    return len(orm_rows)


def _set_snapshot_canonical_state(
    *,
    snapshot: KpiVentasNuevosSociosSnapshotORM,
    is_canonical: bool,
) -> None:
    snapshot.is_canonical = is_canonical
    snapshot.updated_at = _utc_now()
    db.session.flush()


def _clear_existing_canonical_snapshot(
    *,
    existing_snapshot: KpiVentasNuevosSociosSnapshotORM | None,
) -> None:
    if existing_snapshot is None:
        return

    existing_snapshot.is_canonical = False
    existing_snapshot.updated_at = _utc_now()
    db.session.flush()


def _build_already_ingested_result(
    *,
    snapshot: KpiVentasNuevosSociosSnapshotORM,
) -> dict[str, Any]:
    return {
        "status": "already_ingested",
        "was_idempotent": True,
        "snapshot_id": snapshot.id,
        "warehouse_upload_id": snapshot.warehouse_upload_id,
        "report_type_key": snapshot.report_type_key,
        "business_date": snapshot.business_date.isoformat(),
        "captured_at": snapshot.captured_at.isoformat(),
        "snapshot_kind": snapshot.snapshot_kind,
        "is_canonical": snapshot.is_canonical,
        "row_count_detected": snapshot.row_count_detected,
        "row_count_valid": snapshot.row_count_valid,
        "row_count_rejected": snapshot.row_count_rejected,
        "metadata": {
            "reason": "snapshot_already_exists_for_warehouse_upload_id",
        },
    }


def _apply_optional_advisory_lock(*, advisory_lock_key: int | None) -> None:
    if advisory_lock_key is None:
        return

    db.session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": int(advisory_lock_key)},
    )


def _resolve_canonicality_decision(
    *,
    business_date: date,
    snapshot_kind: str,
    canonicality_resolver: Callable[..., dict[str, Any] | None] | None,
) -> dict[str, Any]:
    existing_canonical = _fetch_existing_canonical_snapshot_for_day(
        business_date=business_date,
        snapshot_kind=snapshot_kind,
    )

    default_decision = {
        "is_canonical": False,
        "replace_existing_canonical": False,
        "existing_canonical_snapshot_id": (
            existing_canonical.id if existing_canonical else None
        ),
        "reason": "canonicality_not_configured",
    }

    if canonicality_resolver is None:
        return default_decision

    resolved = canonicality_resolver(
        business_date=business_date,
        snapshot_kind=snapshot_kind,
        existing_canonical_snapshot=existing_canonical,
        report_type_key=KPI_VENTAS_NUEVOS_SOCIOS_REPORT_TYPE_KEY,
    )

    if not resolved:
        return default_decision

    return {
        "is_canonical": bool(resolved.get("is_canonical", False)),
        "replace_existing_canonical": bool(
            resolved.get("replace_existing_canonical", False)
        ),
        "existing_canonical_snapshot_id": (
            existing_canonical.id if existing_canonical else None
        ),
        "reason": resolved.get("reason") or "resolver_provided_decision",
    }


def persist_kpi_ventas_nuevos_socios_snapshot(
    *,
    warehouse_upload_id: int,
    report_type_key: str,
    business_date: date | datetime | str,
    captured_at: datetime | str | None,
    snapshot_kind: str,
    parsed_snapshot: Any,
    canonicality_resolver: Callable[..., dict[str, Any] | None] | None = None,
    advisory_lock_key: int | None = None,
) -> dict[str, Any]:
    if report_type_key != KPI_VENTAS_NUEVOS_SOCIOS_REPORT_TYPE_KEY:
        raise KpiVentasNuevosSociosRepositoryError(
            f"report_type_key inválido para KPI Ventas Nuevos Socios: {report_type_key!r}"
        )

    business_date_value = _ensure_date(business_date)
    captured_at_value = _ensure_datetime(captured_at)
    parsed_snapshot_dict = _as_dict(parsed_snapshot)
    normalized_rows = _rows_from_parsed_snapshot(parsed_snapshot)

    row_count_detected = _ensure_int(
        parsed_snapshot_dict.get("row_count", len(normalized_rows)),
        field_name="row_count",
    )
    row_count_valid = _ensure_int(
        parsed_snapshot_dict.get("row_count_valid", len(normalized_rows)),
        field_name="row_count_valid",
    )
    row_count_rejected = _ensure_int(
        parsed_snapshot_dict.get("row_count_rejected", 0),
        field_name="row_count_rejected",
    )

    if not normalized_rows:
        raise KpiVentasNuevosSociosRepositoryError(
            "No se puede persistir un snapshot KPI Ventas Nuevos Socios sin rows válidas."
        )

    try:
        _apply_optional_advisory_lock(advisory_lock_key=advisory_lock_key)

        existing_snapshot = _fetch_existing_snapshot_by_upload(
            warehouse_upload_id=warehouse_upload_id
        )
        if existing_snapshot is not None:
            db.session.rollback()
            return _build_already_ingested_result(snapshot=existing_snapshot)

        canonicality_decision = _resolve_canonicality_decision(
            business_date=business_date_value,
            snapshot_kind=snapshot_kind,
            canonicality_resolver=canonicality_resolver,
        )

        snapshot = _insert_snapshot_header(
            warehouse_upload_id=warehouse_upload_id,
            report_type_key=report_type_key,
            business_date=business_date_value,
            captured_at=captured_at_value,
            snapshot_kind=snapshot_kind,
            is_canonical=bool(canonicality_decision["is_canonical"]),
            row_count_detected=row_count_detected,
            row_count_valid=row_count_valid,
            row_count_rejected=row_count_rejected,
        )

        rows_inserted = _insert_snapshot_rows(
            snapshot_id=snapshot.id,
            rows=normalized_rows,
        )

        if canonicality_decision["replace_existing_canonical"]:
            existing_canonical_snapshot = _fetch_existing_canonical_snapshot_for_day(
                business_date=business_date_value,
                snapshot_kind=snapshot_kind,
            )
            if (
                existing_canonical_snapshot is not None
                and existing_canonical_snapshot.id != snapshot.id
            ):
                _clear_existing_canonical_snapshot(
                    existing_snapshot=existing_canonical_snapshot
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
            "warehouse_upload_id": snapshot.warehouse_upload_id,
            "report_type_key": snapshot.report_type_key,
            "business_date": snapshot.business_date.isoformat(),
            "captured_at": snapshot.captured_at.isoformat(),
            "snapshot_kind": snapshot.snapshot_kind,
            "is_canonical": snapshot.is_canonical,
            "row_count_detected": snapshot.row_count_detected,
            "row_count_valid": snapshot.row_count_valid,
            "row_count_rejected": snapshot.row_count_rejected,
            "rows_inserted": rows_inserted,
            "metadata": {
                "canonicality_reason": canonicality_decision["reason"],
                "existing_canonical_snapshot_id": canonicality_decision[
                    "existing_canonical_snapshot_id"
                ],
            },
        }

    except IntegrityError as exc:
        db.session.rollback()

        existing_snapshot = _fetch_existing_snapshot_by_upload(
            warehouse_upload_id=warehouse_upload_id
        )
        if existing_snapshot is not None:
            return _build_already_ingested_result(snapshot=existing_snapshot)

        raise KpiVentasNuevosSociosRepositoryError(
            "Falló la persistencia estructurada de KPI Ventas Nuevos Socios por conflicto de integridad."
        ) from exc

    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, KpiVentasNuevosSociosRepositoryError):
            raise
        raise KpiVentasNuevosSociosRepositoryError(
            "Falló la persistencia estructurada de KPI Ventas Nuevos Socios."
        ) from exc