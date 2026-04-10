#  backend\app\warehouse\services\track_monthly_targets_service.py


from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models.warehouse import TrackMonthlyTargetORM, TrackBranchCatalogORM


class TrackMonthlyTargetsServiceError(RuntimeError):
    """Error base del servicio de targets mensuales del Track."""


@dataclass(slots=True)
class UpsertTrackMonthlyTargetCommand:
    target_month: date
    sucursal_canon: str
    m2_sin_circulaciones: Decimal
    usuarios_inicio_mes: int
    proyeccion_usuarios_cierre_mes: int
    meta_faycgo_mes: Decimal
    meta_clientes_nuevos_mes: int
    meta_reactivaciones_mes: int
    meta_bajas_mes: int
    meta_nuevos_domiciliados_mes: int
    meta_arpu_mes: Decimal
    meta_venta_tienda_mes: Decimal
    notes: str | None = None


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as exc:
            raise TrackMonthlyTargetsServiceError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise TrackMonthlyTargetsServiceError(
        f"Valor inválido para {field_name!r}: {value!r}"
    )


def _normalize_target_month(value: Any) -> date:
    month_date = _ensure_date(value, field_name="target_month")
    return month_date.replace(day=1)


def _ensure_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise TrackMonthlyTargetsServiceError(
            f"El campo {field_name!r} es obligatorio."
        )
    return normalized


def _ensure_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise TrackMonthlyTargetsServiceError(
            f"El campo {field_name!r} no puede ser bool."
        )

    try:
        return int(value)
    except Exception as exc:
        raise TrackMonthlyTargetsServiceError(
            f"No se pudo convertir a int el campo {field_name!r}: {value!r}"
        ) from exc


def _ensure_decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise TrackMonthlyTargetsServiceError(
            f"No se pudo convertir a Decimal el campo {field_name!r}: {value!r}"
        ) from exc


def _ensure_branch_exists(sucursal_canon: str) -> None:
    exists = TrackBranchCatalogORM.query.filter_by(
        sucursal_canon=sucursal_canon
    ).first()

    if exists is None:
        raise TrackMonthlyTargetsServiceError(
            f"La sucursal_canon no existe en track_branch_catalog: {sucursal_canon!r}"
        )

def _upsert_track_monthly_target_row(
    *,
    target_month: Any,
    sucursal_canon: Any,
    m2_sin_circulaciones: Any,
    usuarios_inicio_mes: Any,
    proyeccion_usuarios_cierre_mes: Any,
    meta_faycgo_mes: Any,
    meta_clientes_nuevos_mes: Any,
    meta_reactivaciones_mes: Any,
    meta_bajas_mes: Any,
    meta_nuevos_domiciliados_mes: Any,
    meta_arpu_mes: Any,
    meta_venta_tienda_mes: Any,
    notes: Any = None,
) -> tuple[TrackMonthlyTargetORM, bool]:
    normalized_target_month = _normalize_target_month(target_month)
    normalized_sucursal_canon = _ensure_text(
        sucursal_canon,
        field_name="sucursal_canon",
    )

    _ensure_branch_exists(normalized_sucursal_canon)

    normalized_notes = None if notes is None else str(notes).strip() or None

    existing_active = TrackMonthlyTargetORM.query.filter_by(
        target_month=normalized_target_month,
        sucursal_canon=normalized_sucursal_canon,
        is_active=True,
    ).first()

    if existing_active is not None:
        existing_active.is_active = False

    row = TrackMonthlyTargetORM(
        target_month=normalized_target_month,
        sucursal_canon=normalized_sucursal_canon,
        m2_sin_circulaciones=_ensure_decimal(
            m2_sin_circulaciones,
            field_name="m2_sin_circulaciones",
        ),
        usuarios_inicio_mes=_ensure_int(
            usuarios_inicio_mes,
            field_name="usuarios_inicio_mes",
        ),
        proyeccion_usuarios_cierre_mes=_ensure_int(
            proyeccion_usuarios_cierre_mes,
            field_name="proyeccion_usuarios_cierre_mes",
        ),
        meta_faycgo_mes=_ensure_decimal(
            meta_faycgo_mes,
            field_name="meta_faycgo_mes",
        ),
        meta_clientes_nuevos_mes=_ensure_int(
            meta_clientes_nuevos_mes,
            field_name="meta_clientes_nuevos_mes",
        ),
        meta_reactivaciones_mes=_ensure_int(
            meta_reactivaciones_mes,
            field_name="meta_reactivaciones_mes",
        ),
        meta_bajas_mes=_ensure_int(
            meta_bajas_mes,
            field_name="meta_bajas_mes",
        ),
        meta_nuevos_domiciliados_mes=_ensure_int(
            meta_nuevos_domiciliados_mes,
            field_name="meta_nuevos_domiciliados_mes",
        ),
        meta_arpu_mes=_ensure_decimal(
            meta_arpu_mes,
            field_name="meta_arpu_mes",
        ),
        meta_venta_tienda_mes=_ensure_decimal(
            meta_venta_tienda_mes,
            field_name="meta_venta_tienda_mes",
        ),
        is_active=True,
        notes=normalized_notes,
    )

    db.session.add(row)
    db.session.flush()

    return row, (existing_active is not None)


def upsert_track_monthly_target(
    *,
    target_month: Any,
    sucursal_canon: Any,
    m2_sin_circulaciones: Any,
    usuarios_inicio_mes: Any,
    proyeccion_usuarios_cierre_mes: Any,
    meta_faycgo_mes: Any,
    meta_clientes_nuevos_mes: Any,
    meta_reactivaciones_mes: Any,
    meta_bajas_mes: Any,
    meta_nuevos_domiciliados_mes: Any,
    meta_arpu_mes: Any,
    meta_venta_tienda_mes: Any,
    notes: Any = None,
) -> dict[str, Any]:
    row, previous_active_replaced = _upsert_track_monthly_target_row(
        target_month=target_month,
        sucursal_canon=sucursal_canon,
        m2_sin_circulaciones=m2_sin_circulaciones,
        usuarios_inicio_mes=usuarios_inicio_mes,
        proyeccion_usuarios_cierre_mes=proyeccion_usuarios_cierre_mes,
        meta_faycgo_mes=meta_faycgo_mes,
        meta_clientes_nuevos_mes=meta_clientes_nuevos_mes,
        meta_reactivaciones_mes=meta_reactivaciones_mes,
        meta_bajas_mes=meta_bajas_mes,
        meta_nuevos_domiciliados_mes=meta_nuevos_domiciliados_mes,
        meta_arpu_mes=meta_arpu_mes,
        meta_venta_tienda_mes=meta_venta_tienda_mes,
        notes=notes,
    )

    db.session.commit()

    return {
        "status": "upserted",
        "id": row.id,
        "target_month": row.target_month.isoformat(),
        "sucursal_canon": row.sucursal_canon,
        "is_active": row.is_active,
        "previous_active_replaced": previous_active_replaced,
    }  
def bulk_upsert_track_monthly_targets(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(rows, list) or not rows:
        raise TrackMonthlyTargetsServiceError(
            "rows debe ser una lista no vacía."
        )

    results: list[dict[str, Any]] = []

    try:
        for row in rows:
            if not isinstance(row, dict):
                raise TrackMonthlyTargetsServiceError(
                    f"Cada elemento de rows debe ser dict. Recibido: {type(row).__name__}"
                )

            created_row, previous_active_replaced = _upsert_track_monthly_target_row(
                target_month=row.get("target_month"),
                sucursal_canon=row.get("sucursal_canon"),
                m2_sin_circulaciones=row.get("m2_sin_circulaciones"),
                usuarios_inicio_mes=row.get("usuarios_inicio_mes"),
                proyeccion_usuarios_cierre_mes=row.get("proyeccion_usuarios_cierre_mes"),
                meta_faycgo_mes=row.get("meta_faycgo_mes"),
                meta_clientes_nuevos_mes=row.get("meta_clientes_nuevos_mes"),
                meta_reactivaciones_mes=row.get("meta_reactivaciones_mes"),
                meta_bajas_mes=row.get("meta_bajas_mes"),
                meta_nuevos_domiciliados_mes=row.get("meta_nuevos_domiciliados_mes"),
                meta_arpu_mes=row.get("meta_arpu_mes"),
                meta_venta_tienda_mes=row.get("meta_venta_tienda_mes"),
                notes=row.get("notes"),
            )

            results.append(
                {
                    "status": "upserted",
                    "id": created_row.id,
                    "target_month": created_row.target_month.isoformat(),
                    "sucursal_canon": created_row.sucursal_canon,
                    "is_active": created_row.is_active,
                    "previous_active_replaced": previous_active_replaced,
                }
            )

        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "bulk_upserted",
        "rows_processed": len(results),
        "results": results,
    }