# backend/app/warehouse/services/reporte_direccion_repository.py

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from contextlib import nullcontext

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db


REPORTE_DIRECCION_REPORT_TYPE_KEY = "reporte_direccion"
SNAPSHOTS_TABLE = "reporte_direccion_snapshots"
ROWS_TABLE = "reporte_direccion_snapshot_rows"


def register_reporte_direccion_repository(app) -> None:
    """
    Registra este repositorio como hook runtime.

    Uso esperado más adelante en init/app factory:
        register_reporte_direccion_repository(app)

    Esto deja resuelto:
        app.config["WAREHOUSE_REPORTE_DIRECCION_REPOSITORY"] = persist_reporte_direccion_snapshot
    """
    app.config["WAREHOUSE_REPORTE_DIRECCION_REPOSITORY"] = (
        persist_reporte_direccion_snapshot
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

    raise ValueError(f"No se pudo convertir a datetime: {value!r}")


def _to_db_numeric(value: Any) -> Decimal | None:
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float, str)):
        return Decimal(str(value))

    raise ValueError(f"No se pudo convertir a Decimal: {value!r}")


def _to_db_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _fetch_existing_snapshot_by_upload(
    *,
    warehouse_upload_id: int,
) -> dict[str, Any] | None:
    sql = text(
        f"""
        SELECT
            id AS snapshot_id,
            warehouse_upload_id,
            business_date,
            snapshot_kind,
            is_canonical,
            row_count_detected,
            row_count_valid,
            row_count_rejected,
            created_at,
            updated_at
        FROM {SNAPSHOTS_TABLE}
        WHERE warehouse_upload_id = :warehouse_upload_id
        LIMIT 1
        """
    )

    row = db.session.execute(
        sql,
        {"warehouse_upload_id": warehouse_upload_id},
    ).mappings().first()

    return dict(row) if row else None


def _fetch_existing_canonical_snapshot_for_day(
    *,
    business_date: date,
) -> dict[str, Any] | None:
    sql = text(
        f"""
        SELECT
            id AS snapshot_id,
            business_date,
            snapshot_kind,
            is_canonical
        FROM {SNAPSHOTS_TABLE}
        WHERE report_type_key = :report_type_key
          AND business_date = :business_date
          AND is_canonical = TRUE
        LIMIT 1
        """
    )

    row = db.session.execute(
        sql,
        {
            "report_type_key": REPORTE_DIRECCION_REPORT_TYPE_KEY,
            "business_date": business_date,
        },
    ).mappings().first()

    return dict(row) if row else None


def _insert_snapshot_header(
    *,
    parsed_snapshot: dict[str, Any],
    snapshot_kind: str,
) -> int:
    sql = text(
        f"""
        INSERT INTO {SNAPSHOTS_TABLE} (
            warehouse_upload_id,
            report_type_key,
            business_date,
            captured_at,
            snapshot_kind,
            is_canonical,
            row_count_detected,
            row_count_valid,
            row_count_rejected,
            created_at,
            updated_at
        )
        VALUES (
            :warehouse_upload_id,
            :report_type_key,
            :business_date,
            :captured_at,
            :snapshot_kind,
            FALSE,
            :row_count_detected,
            :row_count_valid,
            :row_count_rejected,
            NOW(),
            NOW()
        )
        RETURNING id
        """
    )

    row = db.session.execute(
        sql,
        {
            "warehouse_upload_id": int(parsed_snapshot["warehouse_upload_id"]),
            "report_type_key": REPORTE_DIRECCION_REPORT_TYPE_KEY,
            "business_date": _ensure_date(parsed_snapshot["business_date"]),
            "captured_at": _ensure_datetime(parsed_snapshot["captured_at"]),
            "snapshot_kind": snapshot_kind,
            "row_count_detected": int(parsed_snapshot["row_count_detected"]),
            "row_count_valid": int(parsed_snapshot["row_count_valid"]),
            "row_count_rejected": int(parsed_snapshot["row_count_rejected"]),
        },
    ).first()

    if not row:
        raise RuntimeError("No se pudo obtener el id del snapshot insertado.")

    return int(row[0])


def _insert_snapshot_rows(
    *,
    snapshot_id: int,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    sql = text(
        f"""
        INSERT INTO {ROWS_TABLE} (
            snapshot_id,
            sucursal,
            socios_activos_totales,
            socios_activos_kpi,
            socios_kpi_m2,
            asistencia_hoy,
            diarios_hoy,
            gympass,
            totalpass,
            pases_cortesia,
            ingreso_hoy,
            ingreso_acumulado_semana_en_curso,
            ingreso_acumulado_mes_en_curso,
            membresia_domiciliada_mes_en_curso,
            pago_posterior_domiciliado_mes_en_curso,
            producto_pct_venta,
            ingreso_acumulado_mismo_mes_anio_anterior,
            hora_apertura_raw,
            hora_clausura_raw,
            created_at,
            updated_at
        )
        VALUES (
            :snapshot_id,
            :sucursal,
            :socios_activos_totales,
            :socios_activos_kpi,
            :socios_kpi_m2,
            :asistencia_hoy,
            :diarios_hoy,
            :gympass,
            :totalpass,
            :pases_cortesia,
            :ingreso_hoy,
            :ingreso_acumulado_semana_en_curso,
            :ingreso_acumulado_mes_en_curso,
            :membresia_domiciliada_mes_en_curso,
            :pago_posterior_domiciliado_mes_en_curso,
            :producto_pct_venta,
            :ingreso_acumulado_mismo_mes_anio_anterior,
            :hora_apertura_raw,
            :hora_clausura_raw,
            NOW(),
            NOW()
        )
        """
    )

    params: list[dict[str, Any]] = []
    for raw_row in rows:
        row = _as_dict(raw_row)
        params.append(
            {
                "snapshot_id": snapshot_id,
                "sucursal": str(row["sucursal"]).strip(),
                "socios_activos_totales": _to_db_int(
                    row.get("socios_activos_totales")
                ),
                "socios_activos_kpi": _to_db_int(row.get("socios_activos_kpi")),
                "socios_kpi_m2": _to_db_numeric(row.get("socios_kpi_m2")),
                "asistencia_hoy": _to_db_int(row.get("asistencia_hoy")),
                "diarios_hoy": _to_db_int(row.get("diarios_hoy")),
                "gympass": _to_db_int(row.get("gympass")),
                "totalpass": _to_db_int(row.get("totalpass")),
                "pases_cortesia": _to_db_int(row.get("pases_cortesia")),
                "ingreso_hoy": _to_db_numeric(row.get("ingreso_hoy")),
                "ingreso_acumulado_semana_en_curso": _to_db_numeric(
                    row.get("ingreso_acumulado_semana_en_curso")
                ),
                "ingreso_acumulado_mes_en_curso": _to_db_numeric(
                    row.get("ingreso_acumulado_mes_en_curso")
                ),
                "membresia_domiciliada_mes_en_curso": _to_db_numeric(
                    row.get("membresia_domiciliada_mes_en_curso")
                ),
                "pago_posterior_domiciliado_mes_en_curso": _to_db_numeric(
                    row.get("pago_posterior_domiciliado_mes_en_curso")
                ),
                "producto_pct_venta": _to_db_numeric(
                    row.get("producto_pct_venta")
                ),
                "ingreso_acumulado_mismo_mes_anio_anterior": _to_db_numeric(
                    row.get("ingreso_acumulado_mismo_mes_anio_anterior")
                ),
                "hora_apertura_raw": row.get("hora_apertura_raw"),
                "hora_clausura_raw": row.get("hora_clausura_raw"),
            }
        )

    db.session.execute(sql, params)


def _set_snapshot_canonical_state(
    *,
    snapshot_id: int,
    is_canonical: bool,
) -> None:
    sql = text(
        f"""
        UPDATE {SNAPSHOTS_TABLE}
        SET
            is_canonical = :is_canonical,
            updated_at = NOW()
        WHERE id = :snapshot_id
        """
    )

    db.session.execute(
        sql,
        {
            "snapshot_id": snapshot_id,
            "is_canonical": is_canonical,
        },
    )


def _build_already_ingested_result(existing_snapshot: dict[str, Any]) -> dict[str, Any]:
    business_date = existing_snapshot.get("business_date")
    if isinstance(business_date, datetime):
        business_date = business_date.date()

    return {
        "snapshot_id": existing_snapshot["snapshot_id"],
        "business_date": business_date.isoformat() if business_date else None,
        "snapshot_kind": existing_snapshot.get("snapshot_kind"),
        "is_canonical": bool(existing_snapshot.get("is_canonical")),
        "status": "already_ingested",
        "was_idempotent": True,
        "row_count_detected": int(existing_snapshot.get("row_count_detected") or 0),
        "row_count_valid": int(existing_snapshot.get("row_count_valid") or 0),
        "row_count_rejected": int(existing_snapshot.get("row_count_rejected") or 0),
        "issues_count": 0,
        "metadata": {
            "reason": "warehouse_upload_already_ingested",
        },
    }


def persist_reporte_direccion_snapshot(
    *,
    parsed_snapshot: Any,
    snapshot_kind: str,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
    advisory_lock_callback: Callable[..., Any] | None = None,
    canonicality_resolver: Callable[..., tuple[bool, int | None]] | None = None,
) -> dict[str, Any]:
    """
    Persistencia transaccional de reporte_direccion.

    Responsabilidades:
    - idempotencia por warehouse_upload_id
    - insert de cabecera
    - insert de rows
    - resolución de canonicalidad
    - commit / rollback en una sola transacción
    """
    parsed = _as_dict(parsed_snapshot)

    if snapshot_kind not in {"daily", "month_end_close"}:
        raise ValueError(
            "El 'snapshot_kind' no es válido para reporte_direccion."
        )

    business_date = _ensure_date(parsed["business_date"])
    warehouse_upload_id = int(parsed["warehouse_upload_id"])
    rows = parsed.get("rows") or []

    if not isinstance(rows, list) or not rows:
        raise ValueError("El parsed_snapshot debe traer rows válidas.")

    if canonicality_resolver is None:
        raise ValueError("Se requiere 'canonicality_resolver'.")

    session = db.session()

    owns_transaction = not session.in_transaction()
    transaction_ctx = session.begin() if owns_transaction else nullcontext()

    try:
        with transaction_ctx:
            existing_snapshot = _fetch_existing_snapshot_by_upload(
                warehouse_upload_id=warehouse_upload_id
            )
            if existing_snapshot is not None:
                return _build_already_ingested_result(existing_snapshot)

            if advisory_lock_callback is not None:
                advisory_lock_callback(
                    report_type_key=REPORTE_DIRECCION_REPORT_TYPE_KEY,
                    business_date=business_date,
                )

            existing_canonical = _fetch_existing_canonical_snapshot_for_day(
                business_date=business_date
            )

            snapshot_id = _insert_snapshot_header(
                parsed_snapshot=parsed,
                snapshot_kind=snapshot_kind,
            )

            _insert_snapshot_rows(
                snapshot_id=snapshot_id,
                rows=rows,
            )

            new_is_canonical, previous_canonical_snapshot_id = canonicality_resolver(
                existing_canonical_snapshot=existing_canonical,
                snapshot_kind=snapshot_kind,
            )

            if previous_canonical_snapshot_id is not None:
                _set_snapshot_canonical_state(
                    snapshot_id=previous_canonical_snapshot_id,
                    is_canonical=False,
                )

            if new_is_canonical:
                _set_snapshot_canonical_state(
                    snapshot_id=snapshot_id,
                    is_canonical=True,
                )

            result = {
                "snapshot_id": snapshot_id,
                "business_date": business_date.isoformat(),
                "snapshot_kind": snapshot_kind,
                "is_canonical": bool(new_is_canonical),
                "status": "ingested",
                "was_idempotent": False,
                "row_count_detected": int(parsed["row_count_detected"]),
                "row_count_valid": int(parsed["row_count_valid"]),
                "row_count_rejected": int(parsed["row_count_rejected"]),
                "issues_count": len(parsed.get("issues") or []),
                "metadata": {
                    "requested_by": requested_by,
                    "ingestion_source": ingestion_source,
                    "previous_canonical_snapshot_id": previous_canonical_snapshot_id,
                    "existing_canonical_snapshot_id": (
                        existing_canonical.get("snapshot_id")
                        if existing_canonical
                        else None
                    ),
                },
            }

        # Si ya veníamos dentro de una transacción activa (abierta por lecturas previas
        # en la misma scoped_session), hay que confirmar explícitamente para que el
        # snapshot quede persistido de forma durable.
        if not owns_transaction and session.in_transaction():
            session.commit()

        return result

    except IntegrityError as exc:
        session.rollback()
        raise RuntimeError(
            "Falló la persistencia por conflicto de integridad. "
            "Revisa constraints/índices de reporte_direccion."
        ) from exc
    except Exception:
        session.rollback()
        raise