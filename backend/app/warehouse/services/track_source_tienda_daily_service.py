# backend/app/warehouse/services/track_source_tienda_daily_service.py

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any
import unicodedata

from app.extensions import db
from app.models.warehouse import (
    TrackSourceTiendaDailyORM,
    VentaTotalSnapshotORM,
    VentaTotalSnapshotRowORM,
)
from app.warehouse.services.track_branch_alias_resolver_service import (
    resolve_track_branch_alias,
)


VENTA_TOTAL_REPORT_TYPE_KEY = "venta_total"


class TrackSourceTiendaDailyServiceError(RuntimeError):
    """Error construyendo fuente diaria de tienda para Track."""


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return " ".join(text.split())


def _month_start_for_date(value: date) -> date:
    return date(value.year, value.month, 1)


def _month_end_for_date(value: date) -> date:
    if value.month == 12:
        return date(value.year, 12, 31)

    next_month = date(value.year, value.month + 1, 1)
    return date.fromordinal(next_month.toordinal() - 1)


def _ensure_date(value: str | date | datetime) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        return date.fromisoformat(value)

    raise TrackSourceTiendaDailyServiceError(
        f"Fecha no soportada para tienda: {value!r}"
    )


def _parse_venta_total_row_date(value: Any, *, row_index: int | None = None) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    text = str(value or "").strip()

    for date_format in ("%Y-%m-%d", "%d-%m-%y", "%d/%m/%y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue

    raise TrackSourceTiendaDailyServiceError(
        "No se pudo parsear fecha de venta_total "
        f"row_index={row_index}: {value!r}"
    )


def _resolve_venta_total_snapshot_for_track_date(
    *,
    business_date: date,
) -> VentaTotalSnapshotORM:
    exact_snapshot = (
        VentaTotalSnapshotORM.query.filter_by(
            business_date=business_date,
            snapshot_kind="daily",
            is_canonical=True,
        )
        .order_by(VentaTotalSnapshotORM.id.desc())
        .first()
    )

    if exact_snapshot is not None:
        return exact_snapshot

    month_start = _month_start_for_date(business_date)
    month_end = _month_end_for_date(business_date)

    monthly_snapshot = (
        VentaTotalSnapshotORM.query.filter(
            VentaTotalSnapshotORM.business_date >= month_start,
            VentaTotalSnapshotORM.business_date <= month_end,
            VentaTotalSnapshotORM.snapshot_kind == "daily",
            VentaTotalSnapshotORM.is_canonical.is_(True),
        )
        .order_by(
            VentaTotalSnapshotORM.business_date.desc(),
            VentaTotalSnapshotORM.id.desc(),
        )
        .first()
    )

    if monthly_snapshot is not None:
        return monthly_snapshot

    raise TrackSourceTiendaDailyServiceError(
        "No existe snapshot canónico daily de venta_total "
        f"para el mes de business_date={business_date.isoformat()}."
    )


def _is_out_of_scope_track_branch(raw_branch_name: Any) -> bool:
    normalized = _normalize_text(raw_branch_name)

    if not normalized:
        return True

    if normalized in {"beca", "corporativo"}:
        return True

    if "prueba" in normalized:
        return True

    return False


def _is_active_status(value: Any) -> bool:
    return _normalize_text(value) == "activo"


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value

    if value is None:
        return Decimal("0")

    text = str(value).strip().replace("$", "").replace(",", "")

    if not text:
        return Decimal("0")

    try:
        return Decimal(text)
    except Exception as exc:
        raise TrackSourceTiendaDailyServiceError(
            f"No se pudo convertir total de tienda: {value!r}"
        ) from exc


def _is_tienda_candidate(row: VentaTotalSnapshotRowORM) -> bool:
    descripcion = _normalize_text(row.descripcion)
    clave_producto = _normalize_text(row.clave_producto)
    total = _to_decimal(row.total)

    if not _is_active_status(row.estatus):
        return False

    if total <= 0:
        return False

    if not descripcion:
        return False

    if clave_producto == "membresia":
        return False

    excluded_terms = (
        "membresia",
        "mensual",
        "mensualidad",
        "inscripcion",
        "domiciliado",
        "recurrente",
        "convenio",
        "diario",
        "semana",
        "trimestral",
        "trimestre",
        "semestral",
        "semestre",
        "anualidad",
        "penalizacion",
        "primer pago",
        "borron",
        "borrón",
        "cuenta nueva",
        "promo",
        "cobach",
        "atleta",
        "gympass",
        "total pass",
        "wellhub",
        "pase",
        "pases",
        "consulta",
        "fisioterapeuta",
        "nutriologo",
        "nutriólogo",
        "high end",
        "acceso a high end",
        "prueba",
        "pureba",
        "rws",
        "rewards",
    )

    return not any(term in descripcion for term in excluded_terms)


def build_track_source_tienda_daily_for_date(
    *,
    business_date: str | date | datetime,
) -> list[dict[str, Any]]:
    normalized_business_date = _ensure_date(business_date)

    snapshot = _resolve_venta_total_snapshot_for_track_date(
        business_date=normalized_business_date,
    )

    rows = VentaTotalSnapshotRowORM.query.filter_by(
        snapshot_id=snapshot.id,
    ).all()

    totals_by_branch: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for row in rows:
        row_date = _parse_venta_total_row_date(
            row.fecha,
            row_index=row.row_index,
        )

        if (
            row_date.year != normalized_business_date.year
            or row_date.month != normalized_business_date.month
        ):
            continue

        if row_date > normalized_business_date:
            continue

        if _is_out_of_scope_track_branch(row.sucursal):
            continue

        if not _is_tienda_candidate(row):
            continue

        sucursal_canon = resolve_track_branch_alias(
            source_family="gasca_family",
            raw_branch_name=str(row.sucursal or "").strip(),
        )

        if sucursal_canon is None:
            raise TrackSourceTiendaDailyServiceError(
                "No se pudo resolver alias de sucursal para venta_total tienda: "
                f"{row.sucursal!r}"
            )

        totals_by_branch[sucursal_canon] += _to_decimal(row.total)

    result_rows: list[dict[str, Any]] = []

    for sucursal_canon, venta_tienda_mtd in sorted(totals_by_branch.items()):
        result_rows.append(
            {
                "business_date": normalized_business_date,
                "sucursal_canon": sucursal_canon,
                "venta_tienda_mtd": venta_tienda_mtd,
                "source_snapshot_id": snapshot.id,
                "source_report_type_key": VENTA_TOTAL_REPORT_TYPE_KEY,
            }
        )

    return result_rows


def refresh_track_source_tienda_daily_for_date(
    *,
    business_date: str | date | datetime,
) -> dict[str, Any]:
    normalized_business_date = _ensure_date(business_date)

    rows = build_track_source_tienda_daily_for_date(
        business_date=normalized_business_date,
    )

    TrackSourceTiendaDailyORM.query.filter_by(
        business_date=normalized_business_date,
    ).delete(synchronize_session=False)

    for row in rows:
        db.session.add(
            TrackSourceTiendaDailyORM(
                business_date=row["business_date"],
                sucursal_canon=row["sucursal_canon"],
                venta_tienda_mtd=row["venta_tienda_mtd"],
                source_snapshot_id=row["source_snapshot_id"],
                source_report_type_key=row["source_report_type_key"],
            )
        )

    db.session.commit()

    total_tienda = sum(
        (Decimal(str(row["venta_tienda_mtd"])) for row in rows),
        Decimal("0"),
    )

    return {
        "business_date": normalized_business_date.isoformat(),
        "rows_count": len(rows),
        "venta_tienda_mtd_total": str(total_tienda),
    }