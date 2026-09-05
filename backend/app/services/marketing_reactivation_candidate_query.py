"""Consulta SQL componible de la cartera operativa de Reactivación."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, false, func, or_

from app.models import MarketingReactivationTariffORM
from app.models.warehouse import SociosVencidosCarteraORM


DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
DEFAULT_SORT = "fecha_vencimiento"
DEFAULT_DIRECTION = "desc"

_SORT_COLUMNS = {
    "nombre": SociosVencidosCarteraORM.nombre,
    "pin": SociosVencidosCarteraORM.pin,
    "sucursal": SociosVencidosCarteraORM.sucursal_raw,
    "fecha_vencimiento": SociosVencidosCarteraORM.fecha_vencimiento_date,
    "fecha_ultimo_pago": SociosVencidosCarteraORM.fecha_ultimo_pago_local,
    "tarifa": SociosVencidosCarteraORM.tarifa,
    "telefono": SociosVencidosCarteraORM.telefono_raw,
}
ALLOWED_SORTS = frozenset(_SORT_COLUMNS)
ALLOWED_DIRECTIONS = frozenset({"asc", "desc"})


@dataclass(frozen=True, slots=True)
class ReactivationCandidateQuery:
    date_from: date
    date_to: date
    page: int = DEFAULT_PAGE
    page_size: int = DEFAULT_PAGE_SIZE
    sucursal: str | None = None
    tarifa: str | None = None
    tariff_group: str | None = None
    operational_status: str | None = None
    search: str | None = None
    sort: str = DEFAULT_SORT
    direction: str = DEFAULT_DIRECTION
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class ReactivationCandidateCursor:
    sort_value: str | date | datetime | Decimal | None
    row_id: int


def build_latest_operational_episode_query(
    *,
    session: Any,
    date_from: date,
    date_to: date,
    sucursal: str | None = None,
    tarifa: str | None = None,
    tariff_group: str | None = None,
    search: str | None = None,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    sort: str = DEFAULT_SORT,
    direction: str = DEFAULT_DIRECTION,
):
    """Selecciona primero el último episodio global y después filtra."""

    ranked = session.query(
        SociosVencidosCarteraORM.id.label("episode_id"),
        func.row_number().over(
            partition_by=(
                SociosVencidosCarteraORM.sucursal_key,
                SociosVencidosCarteraORM.pin,
            ),
            order_by=(
                SociosVencidosCarteraORM.fecha_vencimiento_date.desc(),
                SociosVencidosCarteraORM.id.desc(),
            ),
        ).label("episode_rank"),
    ).subquery("reactivation_ranked_episodes")

    query = (
        session.query(SociosVencidosCarteraORM)
        .join(
            ranked,
            SociosVencidosCarteraORM.id == ranked.c.episode_id,
        )
        .filter(
            ranked.c.episode_rank == 1,
            SociosVencidosCarteraORM.fecha_vencimiento_date.between(
                date_from,
                date_to,
            ),
        )
    )
    if allowed_sucursal_keys is not None:
        query = query.filter(
            SociosVencidosCarteraORM.sucursal_key.in_(
                allowed_sucursal_keys
            )
            if allowed_sucursal_keys
            else false()
        )
    if sucursal:
        query = query.filter(
            or_(
                SociosVencidosCarteraORM.sucursal_key == sucursal,
                SociosVencidosCarteraORM.sucursal_raw == sucursal,
            )
        )
    if tarifa:
        query = query.filter(SociosVencidosCarteraORM.tarifa == tarifa)
    if tariff_group:
        tariff_key = func.upper(
            func.regexp_replace(
                func.trim(SociosVencidosCarteraORM.tarifa),
                r"\s+",
                " ",
                "g",
            )
        )
        query = query.join(
            MarketingReactivationTariffORM,
            and_(
                MarketingReactivationTariffORM.is_active.is_(True),
                MarketingReactivationTariffORM.tarifa_key == tariff_key,
                MarketingReactivationTariffORM.reactivation_group
                == tariff_group,
            ),
        )
    if search:
        pattern = f"%{_escape_like(search)}%"
        query = query.filter(
            or_(
                SociosVencidosCarteraORM.nombre.ilike(pattern, escape="\\"),
                SociosVencidosCarteraORM.pin.ilike(pattern, escape="\\"),
                SociosVencidosCarteraORM.telefono_raw.ilike(
                    pattern,
                    escape="\\",
                ),
            )
        )

    sort_column = _SORT_COLUMNS[sort]
    primary_order = (
        sort_column.asc().nullslast()
        if direction == "asc"
        else sort_column.desc().nullslast()
    )
    return query.order_by(
        primary_order,
        SociosVencidosCarteraORM.id.desc(),
    )


def apply_candidate_cursor(
    query: Any,
    *,
    cursor: ReactivationCandidateCursor,
    sort: str,
    direction: str,
):
    """Continúa el orden estable ``sort, id DESC`` después del cursor."""

    sort_column = _SORT_COLUMNS[sort]
    if cursor.sort_value is None:
        return query.filter(
            sort_column.is_(None),
            SociosVencidosCarteraORM.id < cursor.row_id,
        )
    comparison = (
        sort_column > cursor.sort_value
        if direction == "asc"
        else sort_column < cursor.sort_value
    )
    return query.filter(
        or_(
            comparison,
            sort_column.is_(None),
            and_(
                sort_column == cursor.sort_value,
                SociosVencidosCarteraORM.id < cursor.row_id,
            ),
        )
    )


def candidate_sort_value(row: Any, sort: str) -> Any:
    return getattr(row, _SORT_COLUMNS[sort].key)


def build_phone_variant_filter(phone_mx10_values: set[str]):
    """Reduce posibles duplicados usando las tres formas MX compatibles."""

    variants = {
        variant
        for phone in phone_mx10_values
        for variant in (phone, f"52{phone}", f"521{phone}")
    }
    return SociosVencidosCarteraORM.telefono_digits.in_(tuple(sorted(variants)))


def normalize_candidate_query(
    *,
    date_from: date | datetime | str,
    date_to: date | datetime | str,
    page: Any = DEFAULT_PAGE,
    page_size: Any = DEFAULT_PAGE_SIZE,
    sucursal: Any = None,
    tarifa: Any = None,
    tariff_group: Any = None,
    operational_status: Any = None,
    search: Any = None,
    sort: Any = DEFAULT_SORT,
    direction: Any = DEFAULT_DIRECTION,
    cursor: Any = None,
) -> ReactivationCandidateQuery:
    normalized_from = _ensure_date(date_from, "date_from")
    normalized_to = _ensure_date(date_to, "date_to")
    if normalized_from > normalized_to:
        raise ValueError("date_from no puede ser posterior a date_to.")
    normalized_page = _ensure_positive_int(page, "page")
    normalized_page_size = _ensure_positive_int(page_size, "page_size")
    if normalized_page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size no puede ser mayor a {MAX_PAGE_SIZE}.")
    normalized_sort = str(sort or DEFAULT_SORT).strip()
    if normalized_sort not in ALLOWED_SORTS:
        raise ValueError("sort no es válido.")
    normalized_direction = str(direction or DEFAULT_DIRECTION).strip().lower()
    if normalized_direction not in ALLOWED_DIRECTIONS:
        raise ValueError("direction debe ser asc o desc.")
    return ReactivationCandidateQuery(
        date_from=normalized_from,
        date_to=normalized_to,
        page=normalized_page,
        page_size=normalized_page_size,
        sucursal=_optional_text(sucursal, "sucursal"),
        tarifa=_optional_text(tarifa, "tarifa"),
        tariff_group=_optional_text(tariff_group, "tariff_group"),
        operational_status=_optional_text(
            operational_status,
            "operational_status",
        ),
        search=_optional_text(search, "search"),
        sort=normalized_sort,
        direction=normalized_direction,
        cursor=_optional_text(cursor, "cursor", max_length=4096),
    )


def _ensure_date(value: date | datetime | str, field_name: str) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"{field_name} debe ser una fecha sin hora.")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} debe ser una fecha ISO válida.") from exc


def _ensure_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} debe ser un entero positivo.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} debe ser un entero positivo.") from exc
    if str(value).strip() != str(normalized) or normalized <= 0:
        raise ValueError(f"{field_name} debe ser un entero positivo.")
    return normalized


def _optional_text(
    value: Any,
    field_name: str,
    *,
    max_length: int = 255,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} debe ser texto.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} excede {max_length} caracteres.")
    return normalized


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
