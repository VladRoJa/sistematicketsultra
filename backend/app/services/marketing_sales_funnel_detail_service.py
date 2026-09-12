from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.models import MarketingIventasContactORM
from app.models.warehouse import (
    VentaTotalSnapshotRowORM,
    VentasNuevosSociosDetalleSnapshotRowORM,
)
from app.services.marketing_access import MarketingAccess
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.services.marketing_inputs_service import parse_month
from app.services.marketing_sales_funnel_service import (
    MATCH_WINDOW_DAYS,
    ORIGIN_IVENTAS_META,
    ORIGIN_IVENTAS_OTHER,
    ORIGIN_LABELS,
    _canonical_runs_for_window,
    _classify_survey,
    _load_branch_alias_map,
    _load_iventas_data,
    _load_new_sales,
    _load_visits,
    _match_iventas,
    _meta_contact_keys,
    _month_end,
    _payment_local_date,
    _select_new_sales_detail_snapshot,
    _select_venta_total_snapshot,
)


DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


class MarketingSalesFunnelDetailValidationError(ValueError):
    pass


SALES_METRICS = frozenset(
    {
        "sales_total",
        "sales_with_phone",
        "sales_iventas",
        "sales_iventas_meta",
        "sales_not_iventas",
        "revenue_total",
        "revenue_iventas_meta",
    }
)
VISIT_METRICS = frozenset(
    {
        "visits_total",
        "visits_iventas",
        "visits_iventas_meta",
        "visits_not_iventas",
    }
)
LEAD_METRICS = frozenset({"leads_meta"})

METRIC_TITLES = {
    "sales_total": "Venta nueva oficial",
    "sales_with_phone": "Venta nueva con teléfono utilizable",
    "sales_iventas": "Venta nueva con match iVentas",
    "sales_iventas_meta": "Venta nueva atribuida a Meta Ads",
    "sales_not_iventas": "Venta nueva sin match iVentas",
    "revenue_total": "Ingreso de Venta Nueva",
    "revenue_iventas_meta": "Ingreso de Venta Nueva Meta Ads",
    "visits_total": "Visitas comerciales detectadas",
    "visits_iventas": "Visitas con match iVentas",
    "visits_iventas_meta": "Visitas con match iVentas / Meta",
    "visits_not_iventas": "Visitas sin match iVentas",
    "leads_meta": "Leads Meta",
}


def _normalize_optional_int(value: Any, *, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingSalesFunnelDetailValidationError(
            f"{field_name} inválido."
        ) from exc


def _normalize_pagination(
    page: Any,
    page_size: Any,
) -> tuple[int, int]:
    normalized_page = _normalize_optional_int(page, field_name="page")
    normalized_page_size = _normalize_optional_int(
        page_size,
        field_name="page_size",
    )

    normalized_page = normalized_page or 1
    normalized_page_size = normalized_page_size or DEFAULT_PAGE_SIZE

    if normalized_page < 1:
        raise MarketingSalesFunnelDetailValidationError(
            "page debe ser mayor o igual a 1."
        )
    if normalized_page_size < 1 or normalized_page_size > MAX_PAGE_SIZE:
        raise MarketingSalesFunnelDetailValidationError(
            f"page_size debe estar entre 1 y {MAX_PAGE_SIZE}."
        )

    return normalized_page, normalized_page_size


def _page_bounds(page: int, page_size: int) -> tuple[int, int]:
    start = (page - 1) * page_size
    return start, start + page_size


def _normalize_metric(metric: str, origin: str | None) -> tuple[str, str | None]:
    normalized_metric = str(metric or "").strip()
    normalized_origin = str(origin or "").strip() or None

    if normalized_metric == "origin":
        if normalized_origin not in ORIGIN_LABELS:
            raise MarketingSalesFunnelDetailValidationError(
                "origin inválido para detalle de composición."
            )
        return normalized_metric, normalized_origin

    supported = SALES_METRICS | VISIT_METRICS | LEAD_METRICS
    if normalized_metric not in supported:
        raise MarketingSalesFunnelDetailValidationError(
            "metric no soportado para detalle del funnel."
        )

    return normalized_metric, normalized_origin


def _branch_name_map(branches: list[Any]) -> dict[int, str]:
    return {
        int(branch.sucursal_id): str(branch.name)
        for branch in branches
    }


def _full_name(row: Any) -> str:
    return " ".join(
        part
        for part in (
            str(getattr(row, "nombre", "") or "").strip(),
            str(getattr(row, "apellido_paterno", "") or "").strip(),
            str(getattr(row, "apellido_materno", "") or "").strip(),
        )
        if part
    )


def _sale_key_from_detail_row(row: Any) -> str:
    member_id = str(getattr(row, "id_socio", None) or "").strip()
    folio = str(getattr(row, "id_folio", None) or "").strip()
    if member_id:
        return f"id_socio:{member_id}"
    if folio:
        return f"id_folio:{folio}"
    return f"row:{int(row.id)}"


def _sale_matches_metric(
    metric: str,
    origin_filter: str | None,
    *,
    phone: str | None,
    origin: str,
) -> bool:
    if metric in {"sales_total", "revenue_total"}:
        return True
    if metric == "sales_with_phone":
        return phone is not None
    if metric == "sales_iventas":
        return origin in {ORIGIN_IVENTAS_META, ORIGIN_IVENTAS_OTHER}
    if metric in {"sales_iventas_meta", "revenue_iventas_meta"}:
        return origin == ORIGIN_IVENTAS_META
    if metric == "sales_not_iventas":
        return origin not in {ORIGIN_IVENTAS_META, ORIGIN_IVENTAS_OTHER}
    if metric == "origin":
        return origin == origin_filter
    return False


def _visit_matches_metric(metric: str, origin: str | None) -> bool:
    if metric == "visits_total":
        return True
    if metric == "visits_iventas":
        return origin in {ORIGIN_IVENTAS_META, ORIGIN_IVENTAS_OTHER}
    if metric == "visits_iventas_meta":
        return origin == ORIGIN_IVENTAS_META
    if metric == "visits_not_iventas":
        return origin is None
    return False


def _venta_total_transaction_lookup(
    rows: list[VentaTotalSnapshotRowORM],
    month_start: date,
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, date], dict[str, Any]]]:
    by_folio: dict[str, dict[str, Any]] = {}
    by_pin_date: dict[tuple[str, date], dict[str, Any]] = {}

    for row in rows:
        try:
            row_date = date.fromisoformat(str(row.fecha))
        except ValueError:
            from app.services.marketing_sales_funnel_service import _parse_row_date

            try:
                row_date = _parse_row_date(row.fecha)
            except ValueError:
                continue

        if row_date.replace(day=1) != month_start:
            continue

        payload = {
            "transaction_branch": str(row.sucursal or "").strip() or None,
            "survey": str(row.encuesta or "").strip() or None,
            "payment_method": str(row.forma_pago or "").strip() or None,
            "id_order": str(row.id_orden or "").strip() or None,
        }

        folio = str(row.folio or "").strip()
        if folio:
            current = by_folio.setdefault(folio, {})
            for key, value in payload.items():
                if value and not current.get(key):
                    current[key] = value

        pin = str(row.pin or "").strip()
        if pin:
            current = by_pin_date.setdefault((pin, row_date), {})
            for key, value in payload.items():
                if value and not current.get(key):
                    current[key] = value

    return by_folio, by_pin_date


def _sales_detail(
    *,
    month_start: date,
    metric: str,
    origin_filter: str | None,
    branch_ids: tuple[int, ...],
    branch_names: dict[int, str],
    branch_id_filter: int | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int, Decimal]:
    detail_snapshot = _select_new_sales_detail_snapshot(month_start)
    if detail_snapshot is None:
        return [], 0, Decimal("0")

    venta_total_snapshot = _select_venta_total_snapshot(month_start)
    venta_total_rows = (
        VentaTotalSnapshotRowORM.query.filter_by(
            snapshot_id=venta_total_snapshot.id
        ).all()
        if venta_total_snapshot is not None
        else []
    )

    sales_result = _load_new_sales(
        snapshot=detail_snapshot,
        venta_total_rows=venta_total_rows,
        month_start=month_start,
        branch_ids=branch_ids,
    )
    sales_by_key = {sale.sale_key: sale for sale in sales_result.sales}

    evidence, _, _ = _load_iventas_data(month_start, branch_ids)
    by_folio, by_pin_date = _venta_total_transaction_lookup(
        venta_total_rows,
        month_start,
    )

    raw_rows = (
        VentasNuevosSociosDetalleSnapshotRowORM.query.filter_by(
            snapshot_id=detail_snapshot.id
        )
        .order_by(VentasNuevosSociosDetalleSnapshotRowORM.id.asc())
        .all()
    )

    page_start, page_end = _page_bounds(page, page_size)
    page_rows: list[dict[str, Any]] = []
    matched_count = 0
    revenue_total = Decimal("0")
    seen_keys: set[str] = set()

    for row in raw_rows:
        sale_key = _sale_key_from_detail_row(row)
        if sale_key in seen_keys:
            continue
        sale = sales_by_key.get(sale_key)
        if sale is None:
            continue
        seen_keys.add(sale_key)

        if branch_id_filter is not None and sale.branch_id != branch_id_filter:
            continue

        origin = _match_iventas(
            evidence,
            sale.branch_id,
            sale.phone,
            sale.sale_date,
        )
        if origin is None:
            origin = _classify_survey(sale.survey_raw)

        if not _sale_matches_metric(
            metric,
            origin_filter,
            phone=sale.phone,
            origin=origin,
        ):
            continue

        row_position = matched_count
        matched_count += 1
        revenue_total += sale.revenue

        if row_position < page_start or row_position >= page_end:
            continue

        folio = str(row.id_folio or "").strip()
        pin = str(row.pin or "").strip()
        transaction = by_folio.get(folio)
        if transaction is None and pin:
            transaction = by_pin_date.get((pin, sale.sale_date))
        transaction = transaction or {}

        page_rows.append(
            {
                "branch_id": sale.branch_id,
                "branch": branch_names.get(sale.branch_id, str(row.sucursal_raw)),
                "date": sale.sale_date.isoformat(),
                "name": _full_name(row),
                "member_id": str(row.id_socio or "").strip() or None,
                "pin": pin or None,
                "phone": sale.phone,
                "folio": folio or None,
                "membership_type": str(row.tipo_membresia or "").strip() or None,
                "tariff": str(row.tarifa or "").strip() or None,
                "revenue": float(sale.revenue),
                "survey": sale.survey_raw,
                "origin_key": origin,
                "origin": ORIGIN_LABELS.get(origin, origin),
                "transaction_branch": transaction.get("transaction_branch"),
                "payment_method": transaction.get("payment_method"),
                "id_order": transaction.get("id_order"),
                "payment_place": str(row.lugar_pago or "").strip() or None,
            }
        )

    return page_rows, matched_count, revenue_total


def _visits_detail(
    *,
    month_start: date,
    metric: str,
    branch_ids: tuple[int, ...],
    branch_names: dict[int, str],
    branch_id_filter: int | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int, Decimal]:
    snapshot = _select_venta_total_snapshot(month_start)
    if snapshot is None:
        return [], 0, Decimal("0")

    rows = (
        VentaTotalSnapshotRowORM.query.filter_by(snapshot_id=snapshot.id)
        .order_by(VentaTotalSnapshotRowORM.row_index.asc())
        .all()
    )
    visits = _load_visits(
        rows,
        month_start,
        branch_ids,
        _load_branch_alias_map(),
    )
    evidence, _, _ = _load_iventas_data(month_start, branch_ids)

    page_start, page_end = _page_bounds(page, page_size)
    page_rows: list[dict[str, Any]] = []
    matched_count = 0

    for visit in visits:
        if branch_id_filter is not None and visit.branch_id != branch_id_filter:
            continue
        origin = _match_iventas(
            evidence,
            visit.branch_id,
            visit.phone,
            visit.visit_date,
        )
        if not _visit_matches_metric(metric, origin):
            continue

        row_position = matched_count
        matched_count += 1
        if row_position < page_start or row_position >= page_end:
            continue

        page_rows.append(
            {
                "branch_id": visit.branch_id,
                "branch": branch_names.get(visit.branch_id, ""),
                "date": visit.visit_date.isoformat(),
                "phone": visit.phone,
                "origin_key": origin,
                "origin": (
                    ORIGIN_LABELS.get(origin, origin)
                    if origin is not None
                    else "Sin match iVentas"
                ),
                "source": "Pase comercial en Venta Total",
            }
        )

    return page_rows, matched_count, Decimal("0")


def _leads_meta_detail(
    *,
    month_start: date,
    branch_ids: tuple[int, ...],
    branch_names: dict[int, str],
    branch_id_filter: int | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int, Decimal]:
    window_start = month_start - timedelta(days=MATCH_WINDOW_DAYS)
    runs = _canonical_runs_for_window(window_start, _month_end(month_start))
    current_period_key = f"IVENTAS-{month_start.strftime('%Y-%m')}"
    current_run_ids = tuple(
        int(run.id)
        for run in runs
        if str(run.period_key) == current_period_key
    )
    if not current_run_ids:
        return [], 0, Decimal("0")

    meta_keys = _meta_contact_keys(current_run_ids)
    allowed = set(branch_ids)
    contacts = (
        MarketingIventasContactORM.query.filter(
            MarketingIventasContactORM.sync_run_id.in_(current_run_ids),
            MarketingIventasContactORM.sucursal_id.in_(branch_ids),
            MarketingIventasContactORM.first_message_at_utc.isnot(None),
            MarketingIventasContactORM.phone_mx10.isnot(None),
        )
        .order_by(MarketingIventasContactORM.first_message_at_local.asc())
        .all()
    )

    page_start, page_end = _page_bounds(page, page_size)
    page_rows: list[dict[str, Any]] = []
    matched_count = 0

    for contact in contacts:
        branch_id = int(contact.sucursal_id)
        if branch_id not in allowed:
            continue
        if branch_id_filter is not None and branch_id != branch_id_filter:
            continue
        if (int(contact.sync_run_id), int(contact.id)) not in meta_keys:
            continue

        row_position = matched_count
        matched_count += 1
        if row_position < page_start or row_position >= page_end:
            continue

        page_rows.append(
            {
                "branch_id": branch_id,
                "branch": branch_names.get(branch_id, ""),
                "date": (
                    contact.first_message_date_local.isoformat()
                    if contact.first_message_date_local is not None
                    else None
                ),
                "name": str(contact.name or "").strip() or None,
                "phone": str(contact.phone_mx10 or "").strip() or None,
                "contact_id": str(contact.contact_id or "").strip() or None,
                "channel": str(contact.channel_name or "").strip() or None,
                "origin_key": ORIGIN_IVENTAS_META,
                "origin": ORIGIN_LABELS[ORIGIN_IVENTAS_META],
            }
        )

    return page_rows, matched_count, Decimal("0")


def build_marketing_sales_funnel_detail(
    *,
    month: str,
    access: MarketingAccess,
    metric: str,
    branch_id: Any = None,
    origin: str | None = None,
    page: Any = None,
    page_size: Any = None,
) -> dict[str, Any]:
    month_start = parse_month(month)
    metric, origin = _normalize_metric(metric, origin)
    branch_id_filter = _normalize_optional_int(
        branch_id,
        field_name="branch_id",
    )
    page, page_size = _normalize_pagination(page, page_size)

    branches, branch_ids, scope = load_visible_marketing_branches(access)
    allowed = set(branch_ids)
    if branch_id_filter is not None and branch_id_filter not in allowed:
        raise MarketingSalesFunnelDetailValidationError(
            "La sucursal solicitada no pertenece al alcance del usuario."
        )

    branch_names = _branch_name_map(branches)

    if metric in SALES_METRICS or metric == "origin":
        kind = "sales"
        rows, count, revenue_total = _sales_detail(
            month_start=month_start,
            metric=metric,
            origin_filter=origin,
            branch_ids=branch_ids,
            branch_names=branch_names,
            branch_id_filter=branch_id_filter,
            page=page,
            page_size=page_size,
        )
    elif metric in VISIT_METRICS:
        kind = "visits"
        rows, count, revenue_total = _visits_detail(
            month_start=month_start,
            metric=metric,
            branch_ids=branch_ids,
            branch_names=branch_names,
            branch_id_filter=branch_id_filter,
            page=page,
            page_size=page_size,
        )
    else:
        kind = "leads"
        rows, count, revenue_total = _leads_meta_detail(
            month_start=month_start,
            branch_ids=branch_ids,
            branch_names=branch_names,
            branch_id_filter=branch_id_filter,
            page=page,
            page_size=page_size,
        )

    title = (
        ORIGIN_LABELS[origin]
        if metric == "origin" and origin is not None
        else METRIC_TITLES[metric]
    )
    if branch_id_filter is not None:
        title = f"{title} · {branch_names.get(branch_id_filter, branch_id_filter)}"

    total_pages = (count + page_size - 1) // page_size if count else 0

    return {
        "month": month_start.strftime("%Y-%m"),
        "scope": scope,
        "metric": metric,
        "origin": origin,
        "kind": kind,
        "title": title,
        "branch_id": branch_id_filter,
        "count": count,
        "revenue_total": float(revenue_total),
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "rows": rows,
    }
