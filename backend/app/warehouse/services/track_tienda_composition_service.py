from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.models.warehouse import TrackDailyMartORM, VentaTotalSnapshotRowORM
from app.warehouse.services.track_branch_alias_resolver_service import (
    resolve_track_branch_alias,
)
from app.warehouse.services.track_daily_query_version_service import (
    resolve_effective_track_daily_version,
)
from app.warehouse.services.track_source_tienda_daily_service import (
    _is_out_of_scope_track_branch,
    _is_tienda_candidate,
    _normalize_text,
    _parse_venta_total_row_date,
    _to_decimal,
)


DEFAULT_OPERATION_LIMIT = 250
MAX_OPERATION_LIMIT = 500


class TrackTiendaCompositionServiceError(RuntimeError):
    """Error construyendo la composición de venta Tienda del Track."""


def _ensure_date(value: str | date | datetime) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except Exception as exc:
            raise TrackTiendaCompositionServiceError(
                f"track_date inválido: {value!r}"
            ) from exc

    raise TrackTiendaCompositionServiceError(
        f"track_date inválido: {value!r}"
    )


def _ensure_generation_mode(value: Any) -> str:
    normalized = str(value or "manual_preview").strip()

    if normalized not in {"manual_preview", "official_closed_day"}:
        raise TrackTiendaCompositionServiceError(
            f"generation_mode inválido: {value!r}"
        )

    return normalized


def _ensure_operation_limit(value: Any) -> int:
    if value in (None, ""):
        return DEFAULT_OPERATION_LIMIT

    try:
        normalized = int(value)
    except Exception as exc:
        raise TrackTiendaCompositionServiceError(
            f"operation_limit inválido: {value!r}"
        ) from exc

    return max(1, min(normalized, MAX_OPERATION_LIMIT))


def _serialize_decimal(value: Decimal | None) -> float:
    return float(value or Decimal("0"))


def _serialize_quantity(value: Any) -> float:
    return _serialize_decimal(_to_decimal(value))


def _share_percent(value: Decimal, total: Decimal) -> float:
    if total <= 0:
        return 0.0
    return float((value / total) * Decimal("100"))


def _average(value: Decimal, count: int) -> Decimal:
    if count <= 0:
        return Decimal("0")
    return value / Decimal(count)


def _product_key_label(value: Any) -> str:
    raw = str(value or "").strip()
    return raw.upper() if raw else "SIN_CLAVE"


def _description_label(value: Any) -> str:
    raw = str(value or "").strip()
    return raw or "SIN_DESCRIPCION"


def _operation_sort_key(operation: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(operation.get("fecha") or ""),
        str(operation.get("hora") or ""),
        int(operation.get("row_index") or 0),
    )


def _matches_operation_filter(
    operation: dict[str, Any],
    *,
    clave_producto: str,
    descripcion: str,
    sucursal_canon: str,
) -> bool:
    if clave_producto:
        if _normalize_text(operation.get("clave_producto")) != clave_producto:
            return False

    if descripcion:
        if _normalize_text(operation.get("descripcion")) != descripcion:
            return False

    if sucursal_canon:
        if str(operation.get("sucursal_canon") or "").strip().upper() != sucursal_canon:
            return False

    return True


def build_track_tienda_composition(
    *,
    track_date: str | date | datetime,
    generation_mode: str = "manual_preview",
    include_operations: bool = False,
    clave_producto: Any = None,
    descripcion: Any = None,
    sucursal_canon: Any = None,
    operation_limit: Any = DEFAULT_OPERATION_LIMIT,
) -> dict[str, Any]:
    normalized_track_date = _ensure_date(track_date)
    normalized_generation_mode = _ensure_generation_mode(generation_mode)
    normalized_operation_limit = _ensure_operation_limit(operation_limit)

    resolved_version = resolve_effective_track_daily_version(
        track_date=normalized_track_date,
        generation_mode=normalized_generation_mode,
    )

    if resolved_version is None:
        raise TrackTiendaCompositionServiceError(
            "No existe una versión consultable del Track para "
            f"{normalized_track_date.isoformat()}."
        )

    mart_rows = TrackDailyMartORM.query.filter_by(
        track_daily_version_id=resolved_version.id,
    ).all()

    if not mart_rows:
        raise TrackTiendaCompositionServiceError(
            "La versión resuelta del Track no contiene filas de mart."
        )

    source_snapshot_ids = {
        int(row.source_snapshot_id_tienda)
        for row in mart_rows
        if row.source_snapshot_id_tienda is not None
    }

    if not source_snapshot_ids:
        raise TrackTiendaCompositionServiceError(
            "La versión resuelta no tiene lineage de snapshot Tienda."
        )

    if len(source_snapshot_ids) != 1:
        raise TrackTiendaCompositionServiceError(
            "La versión resuelta contiene múltiples snapshots Tienda: "
            f"{sorted(source_snapshot_ids)}."
        )

    source_snapshot_id = next(iter(source_snapshot_ids))

    track_total = sum(
        (
            _to_decimal(row.venta_tienda_real_mtd)
            for row in mart_rows
        ),
        Decimal("0"),
    )
    target_total = sum(
        (
            _to_decimal(row.meta_venta_tienda_mes)
            for row in mart_rows
        ),
        Decimal("0"),
    )

    source_rows = VentaTotalSnapshotRowORM.query.filter_by(
        snapshot_id=source_snapshot_id,
    ).all()

    totals_by_key: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "clave_producto": "SIN_CLAVE",
            "total": Decimal("0"),
            "cantidad": Decimal("0"),
            "operaciones": 0,
        }
    )
    totals_by_product: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "clave_producto": "SIN_CLAVE",
            "descripcion": "SIN_DESCRIPCION",
            "total": Decimal("0"),
            "cantidad": Decimal("0"),
            "operaciones": 0,
        }
    )
    totals_by_branch: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "sucursal_canon": "",
            "total": Decimal("0"),
            "cantidad": Decimal("0"),
            "operaciones": 0,
        }
    )
    totals_by_day: dict[date, dict[str, Any]] = defaultdict(
        lambda: {
            "total": Decimal("0"),
            "cantidad": Decimal("0"),
            "operaciones": 0,
        }
    )

    operations: list[dict[str, Any]] = []
    composition_total = Decimal("0")
    composition_quantity = Decimal("0")
    operation_count = 0

    for row in source_rows:
        row_date = _parse_venta_total_row_date(
            row.fecha,
            row_index=row.row_index,
        )

        if (
            row_date.year != normalized_track_date.year
            or row_date.month != normalized_track_date.month
            or row_date > normalized_track_date
        ):
            continue

        if _is_out_of_scope_track_branch(row.sucursal):
            continue

        if not _is_tienda_candidate(row):
            continue

        resolved_branch = resolve_track_branch_alias(
            source_family="gasca_family",
            raw_branch_name=str(row.sucursal or "").strip(),
        )

        if resolved_branch is None:
            raise TrackTiendaCompositionServiceError(
                "No se pudo resolver alias de sucursal para composición Tienda: "
                f"{row.sucursal!r}"
            )

        total = _to_decimal(row.total)
        quantity = _to_decimal(row.cantidad)
        product_key = _product_key_label(row.clave_producto)
        product_key_normalized = _normalize_text(product_key)
        description = _description_label(row.descripcion)
        description_normalized = _normalize_text(description)

        composition_total += total
        composition_quantity += quantity
        operation_count += 1

        key_bucket = totals_by_key[product_key_normalized]
        key_bucket["clave_producto"] = product_key
        key_bucket["total"] += total
        key_bucket["cantidad"] += quantity
        key_bucket["operaciones"] += 1

        product_bucket = totals_by_product[
            (product_key_normalized, description_normalized)
        ]
        product_bucket["clave_producto"] = product_key
        product_bucket["descripcion"] = description
        product_bucket["total"] += total
        product_bucket["cantidad"] += quantity
        product_bucket["operaciones"] += 1

        branch_bucket = totals_by_branch[resolved_branch]
        branch_bucket["sucursal_canon"] = resolved_branch
        branch_bucket["total"] += total
        branch_bucket["cantidad"] += quantity
        branch_bucket["operaciones"] += 1

        day_bucket = totals_by_day[row_date]
        day_bucket["total"] += total
        day_bucket["cantidad"] += quantity
        day_bucket["operaciones"] += 1

        operations.append(
            {
                "row_index": row.row_index,
                "fecha": row_date.isoformat(),
                "hora": str(row.hora or "").strip(),
                "sucursal_canon": resolved_branch,
                "sucursal_origen": str(row.sucursal or "").strip(),
                "folio": str(row.folio or "").strip(),
                "clave": str(row.clave or "").strip(),
                "clave_producto": product_key,
                "descripcion": description,
                "cantidad": _serialize_quantity(row.cantidad),
                "precio_unitario": _serialize_decimal(
                    _to_decimal(row.precio_unitario)
                ),
                "total": _serialize_decimal(total),
                "forma_pago": str(row.forma_pago or "").strip(),
                "estatus": str(row.estatus or "").strip(),
                "realizo_venta": str(row.realizo_venta or "").strip(),
                "capturista": str(row.capturista or "").strip(),
                "socio": str(row.socio or "").strip(),
            }
        )

    composition_rows = sorted(
        totals_by_key.values(),
        key=lambda item: (item["total"], item["clave_producto"]),
        reverse=True,
    )
    product_rows = sorted(
        totals_by_product.values(),
        key=lambda item: (item["total"], item["descripcion"]),
        reverse=True,
    )
    branch_rows = sorted(
        totals_by_branch.values(),
        key=lambda item: (item["total"], item["sucursal_canon"]),
        reverse=True,
    )

    composition = [
        {
            "clave_producto": item["clave_producto"],
            "total": _serialize_decimal(item["total"]),
            "cantidad": _serialize_decimal(item["cantidad"]),
            "operaciones": item["operaciones"],
            "participacion_pct": _share_percent(
                item["total"],
                composition_total,
            ),
            "ticket_promedio": _serialize_decimal(
                _average(item["total"], item["operaciones"])
            ),
        }
        for item in composition_rows
    ]

    products = [
        {
            "clave_producto": item["clave_producto"],
            "descripcion": item["descripcion"],
            "total": _serialize_decimal(item["total"]),
            "cantidad": _serialize_decimal(item["cantidad"]),
            "operaciones": item["operaciones"],
            "participacion_pct": _share_percent(
                item["total"],
                composition_total,
            ),
            "ticket_promedio": _serialize_decimal(
                _average(item["total"], item["operaciones"])
            ),
        }
        for item in product_rows
    ]

    branches = [
        {
            "sucursal_canon": item["sucursal_canon"],
            "total": _serialize_decimal(item["total"]),
            "cantidad": _serialize_decimal(item["cantidad"]),
            "operaciones": item["operaciones"],
            "participacion_pct": _share_percent(
                item["total"],
                composition_total,
            ),
            "ticket_promedio": _serialize_decimal(
                _average(item["total"], item["operaciones"])
            ),
        }
        for item in branch_rows
    ]

    daily = [
        {
            "fecha": business_date.isoformat(),
            "total": _serialize_decimal(item["total"]),
            "cantidad": _serialize_decimal(item["cantidad"]),
            "operaciones": item["operaciones"],
        }
        for business_date, item in sorted(totals_by_day.items())
    ]

    normalized_key_filter = _normalize_text(clave_producto)
    normalized_description_filter = _normalize_text(descripcion)
    normalized_branch_filter = str(sucursal_canon or "").strip().upper()

    filtered_operations = [
        operation
        for operation in operations
        if _matches_operation_filter(
            operation,
            clave_producto=normalized_key_filter,
            descripcion=normalized_description_filter,
            sucursal_canon=normalized_branch_filter,
        )
    ]
    filtered_operations.sort(key=_operation_sort_key, reverse=True)

    detail_filter = {
        "clave_producto": (
            _product_key_label(clave_producto)
            if normalized_key_filter
            else None
        ),
        "descripcion": (
            str(descripcion or "").strip()
            if normalized_description_filter
            else None
        ),
        "sucursal_canon": normalized_branch_filter or None,
    }

    difference = composition_total - track_total
    reconciliation_tolerance = Decimal("0.01")

    top_product = products[0] if products else None
    top_branch = branches[0] if branches else None
    top_key = composition[0] if composition else None

    return {
        "track_date": normalized_track_date.isoformat(),
        "generation_mode": normalized_generation_mode,
        "resolved_version": {
            "id": int(resolved_version.id),
            "version_type": str(resolved_version.version_type),
            "status": str(resolved_version.status),
            "generated_at_utc": (
                resolved_version.generated_at_utc.isoformat()
                if resolved_version.generated_at_utc
                else None
            ),
            "finished_at_utc": (
                resolved_version.finished_at_utc.isoformat()
                if resolved_version.finished_at_utc
                else None
            ),
        },
        "source_snapshot_id": source_snapshot_id,
        "summary": {
            "track_total": _serialize_decimal(track_total),
            "composition_total": _serialize_decimal(composition_total),
            "difference": _serialize_decimal(difference),
            "is_reconciled": abs(difference) <= reconciliation_tolerance,
            "target_total": _serialize_decimal(target_total),
            "progress_pct": _share_percent(track_total, target_total),
            "cantidad_total": _serialize_decimal(composition_quantity),
            "operaciones": operation_count,
            "ticket_promedio": _serialize_decimal(
                _average(composition_total, operation_count)
            ),
            "top_clave_producto": (
                top_key["clave_producto"] if top_key else None
            ),
            "top_producto": (
                top_product["descripcion"] if top_product else None
            ),
            "top_sucursal": (
                top_branch["sucursal_canon"] if top_branch else None
            ),
        },
        "composition": composition,
        "products": products,
        "branches": branches,
        "daily": daily,
        "detail_filter": detail_filter,
        "operation_count": len(filtered_operations),
        "operation_limit": normalized_operation_limit,
        "operations": (
            filtered_operations[:normalized_operation_limit]
            if include_operations
            else []
        ),
    }
