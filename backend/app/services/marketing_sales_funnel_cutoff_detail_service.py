from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any

from app.models import MarketingIventasContactORM
from app.models.warehouse import (
    VentasNuevosSociosDetalleSnapshotORM,
    VentasNuevosSociosDetalleSnapshotRowORM,
)
from app.services.marketing_access import MarketingAccess
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.services.marketing_inputs_service import parse_month
from app.services.marketing_sales_funnel_cutoff_service import (
    build_marketing_sales_funnel_at_cutoff,
)
from app.services.marketing_sales_funnel_detail_service import (
    LEAD_METRICS,
    METRIC_TITLES,
    SALES_METRICS,
    VISIT_METRICS,
    MarketingSalesFunnelDetailValidationError,
    _branch_name_map,
    _full_name,
    _normalize_metric,
    _normalize_optional_int,
    _normalize_pagination,
    _sale_key_from_detail_row,
    _sale_matches_metric,
    _venta_total_transaction_lookup,
    _visit_matches_metric,
)
from app.services.marketing_sales_funnel_drilldown_service import (
    EXPORT_COLUMNS_BY_KIND,
    _build_excel_workbook,
    _normalize_sort,
    _safe_filename_segment,
    _sort_rows,
)
from app.services.marketing_sales_funnel_service import (
    ORIGIN_IVENTAS_META,
    ORIGIN_LABELS,
    _classify_sale_category,
    _classify_survey,
    _load_new_sales,
    _match_iventas,
    _meta_contact_keys,
)
from app.services.marketing_visit_conversion_service import (
    VISIT_CONVERSION_METRICS,
    VISIT_CONVERSION_TITLES,
    VisitConversionBundle,
    _build_bundle_from_loaded_data,
    _metric_matches as _visit_conversion_metric_matches,
    _normalize_sort as _normalize_visit_conversion_sort,
    _serialize_detail_row as _serialize_visit_conversion_row,
    _serialize_summary as _serialize_visit_conversion_summary,
)


def _selected_snapshot(
    *,
    source: dict[str, Any],
) -> VentasNuevosSociosDetalleSnapshotORM | None:
    snapshot_id = source.get("ventas_nuevos_socios_detalle_snapshot_id")
    if snapshot_id is None:
        return None
    return VentasNuevosSociosDetalleSnapshotORM.query.filter_by(
        id=int(snapshot_id)
    ).first()


def _selected_iventas_run_id(source: dict[str, Any]) -> int | None:
    value = source.get("iventas_sync_run_id")
    return int(value) if value is not None else None


def _normalize_detail_sort(
    *,
    metric: str,
    kind: str,
    sort_by: Any,
    sort_dir: Any,
) -> tuple[str | None, str]:
    if metric in VISIT_CONVERSION_METRICS:
        return _normalize_visit_conversion_sort(sort_by, sort_dir)
    return _normalize_sort(sort_by, sort_dir, kind)


def _sales_rows(
    *,
    month_start: date,
    cutoff_date: date,
    metric: str,
    origin_filter: str | None,
    branch_ids: tuple[int, ...],
    branch_names: dict[int, str],
    branch_id_filter: int | None,
    loaded: Any,
    source: dict[str, Any],
) -> tuple[list[dict[str, Any]], Decimal]:
    detail_snapshot = _selected_snapshot(source=source)
    if detail_snapshot is None:
        return [], Decimal("0")

    venta_total_rows = list(loaded.venta_total_rows or ())
    sales_result = _load_new_sales(
        snapshot=detail_snapshot,
        venta_total_rows=venta_total_rows,
        month_start=month_start,
        branch_ids=branch_ids,
    )
    sales_by_key = {sale.sale_key: sale for sale in sales_result.sales}
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

    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    revenue_total = Decimal("0")

    for row in raw_rows:
        sale_key = _sale_key_from_detail_row(row)
        if sale_key in seen_keys:
            continue
        sale = sales_by_key.get(sale_key)
        if sale is None or sale.sale_date > cutoff_date:
            continue
        seen_keys.add(sale_key)

        if branch_id_filter is not None and sale.branch_id != branch_id_filter:
            continue

        iventas_origin = _match_iventas(
            loaded.evidence,
            sale.branch_id,
            sale.phone,
            sale.sale_date,
        )
        origin = (
            iventas_origin
            if iventas_origin is not None
            else _classify_survey(sale.survey_raw)
        )
        sale_category = _classify_sale_category(
            iventas_origin=iventas_origin,
            api_raw=sale.api_raw,
            survey_raw=sale.survey_raw,
        )

        if not _sale_matches_metric(
            metric,
            origin_filter,
            phone=sale.phone,
            origin=origin,
            sale_category=sale_category,
        ):
            continue

        revenue_total += sale.revenue
        folio = str(row.id_folio or "").strip()
        pin = str(row.pin or "").strip()
        transaction = by_folio.get(folio)
        if transaction is None and pin:
            transaction = by_pin_date.get((pin, sale.sale_date))
        transaction = transaction or {}

        rows.append(
            {
                "branch_id": sale.branch_id,
                "branch": branch_names.get(
                    sale.branch_id,
                    str(row.sucursal_raw),
                ),
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

    return rows, revenue_total


def _visit_rows(
    *,
    cutoff_date: date,
    metric: str,
    branch_names: dict[int, str],
    branch_id_filter: int | None,
    loaded: Any,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for visit in loaded.visits:
        if visit.visit_date > cutoff_date:
            continue
        if branch_id_filter is not None and visit.branch_id != branch_id_filter:
            continue

        origin = _match_iventas(
            loaded.evidence,
            visit.branch_id,
            visit.phone,
            visit.visit_date,
        )
        if not _visit_matches_metric(metric, origin):
            continue

        rows.append(
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
    return rows


def _lead_rows(
    *,
    month_start: date,
    cutoff_date: date,
    branch_ids: tuple[int, ...],
    branch_names: dict[int, str],
    branch_id_filter: int | None,
    iventas_run_id: int | None,
    meta_only: bool,
) -> list[dict[str, Any]]:
    if iventas_run_id is None:
        return []

    meta_keys = _meta_contact_keys((iventas_run_id,)) if meta_only else set()
    contacts = (
        MarketingIventasContactORM.query.filter(
            MarketingIventasContactORM.sync_run_id == iventas_run_id,
            MarketingIventasContactORM.sucursal_id.in_(branch_ids),
            MarketingIventasContactORM.first_message_at_utc.isnot(None),
        )
        .order_by(
            MarketingIventasContactORM.first_message_at_local.asc(),
            MarketingIventasContactORM.id.asc(),
        )
        .all()
    )

    rows: list[dict[str, Any]] = []
    for contact in contacts:
        branch_id = int(contact.sucursal_id)
        if branch_id_filter is not None and branch_id != branch_id_filter:
            continue
        if meta_only and (iventas_run_id, int(contact.id)) not in meta_keys:
            continue

        contact_date = contact.first_message_date_local
        if contact_date is None:
            continue
        if contact_date < month_start or contact_date > cutoff_date:
            continue

        rows.append(
            {
                "branch_id": branch_id,
                "branch": branch_names.get(branch_id, ""),
                "date": contact_date.isoformat(),
                "name": str(contact.name or "").strip() or None,
                "phone": str(contact.phone_mx10 or "").strip() or None,
                "contact_id": str(contact.contact_id or "").strip() or None,
                "channel": str(contact.channel_name or "").strip() or None,
                "origin_key": ORIGIN_IVENTAS_META if meta_only else "IVENTAS",
                "origin": (
                    ORIGIN_LABELS[ORIGIN_IVENTAS_META]
                    if meta_only
                    else "iVentas"
                ),
            }
        )
    return rows


def _normalized_visit_conversion_bundle(
    *,
    loaded: Any,
    cutoff_date: date,
) -> VisitConversionBundle:
    bundle = _build_bundle_from_loaded_data(loaded=loaded, today=cutoff_date)
    return VisitConversionBundle(
        rows=tuple(
            replace(row, sale=None)
            if row.sale is not None and row.sale.payment_date > cutoff_date
            else row
            for row in bundle.rows
        ),
        sales_snapshot_ids=bundle.sales_snapshot_ids,
        cohort_complete=bundle.cohort_complete,
    )


def build_visit_conversion_summary_at_cutoff(
    *,
    loaded: Any,
    cutoff_date: str,
) -> dict[str, Any]:
    selected_cutoff = date.fromisoformat(cutoff_date)
    bundle = _normalized_visit_conversion_bundle(
        loaded=loaded,
        cutoff_date=selected_cutoff,
    )
    return _serialize_visit_conversion_summary(
        bundle=bundle,
        branch_ids=loaded.branch_ids,
    )


def _visit_conversion_rows(
    *,
    cutoff_date: date,
    metric: str,
    branch_names: dict[int, str],
    branch_id_filter: int | None,
    loaded: Any,
) -> list[dict[str, Any]]:
    bundle = _normalized_visit_conversion_bundle(
        loaded=loaded,
        cutoff_date=cutoff_date,
    )
    rows: list[dict[str, Any]] = []
    for row in bundle.rows:
        if not _visit_conversion_metric_matches(row, metric):
            continue
        if branch_id_filter is not None and row.branch_id != branch_id_filter:
            continue
        rows.append(_serialize_visit_conversion_row(row, branch_names))
    return rows


def _resolve_detail_rows(
    *,
    month: str,
    cutoff_date: Any,
    access: MarketingAccess,
    metric: str,
    branch_id: Any,
    origin: str | None,
) -> dict[str, Any]:
    month_start = parse_month(month)
    normalized_metric = str(metric or "").strip()
    normalized_origin = str(origin or "").strip() or None
    if (
        normalized_metric not in VISIT_CONVERSION_METRICS
        and normalized_metric != "leads_iventas"
    ):
        normalized_metric, normalized_origin = _normalize_metric(
            normalized_metric,
            normalized_origin,
        )

    branches, branch_ids, scope = load_visible_marketing_branches(access)
    branch_id_filter = _normalize_optional_int(
        branch_id,
        field_name="branch_id",
    )
    if branch_id_filter is not None and branch_id_filter not in set(branch_ids):
        raise MarketingSalesFunnelDetailValidationError(
            "La sucursal solicitada no pertenece al alcance del usuario."
        )
    branch_names = _branch_name_map(branches)

    funnel_build = build_marketing_sales_funnel_at_cutoff(
        month=month,
        access=access,
        cutoff_date=cutoff_date,
    )
    selected_cutoff = date.fromisoformat(
        funnel_build.payload["selected_cutoff_date"]
    )
    source = funnel_build.payload["source"]

    if normalized_metric in SALES_METRICS or normalized_metric in {"origin", "btl_origin"}:
        kind = "sales"
        rows, revenue_total = _sales_rows(
            month_start=month_start,
            cutoff_date=selected_cutoff,
            metric=normalized_metric,
            origin_filter=normalized_origin,
            branch_ids=branch_ids,
            branch_names=branch_names,
            branch_id_filter=branch_id_filter,
            loaded=funnel_build.loaded,
            source=source,
        )
        title = (
            (
                f"BTL · {ORIGIN_LABELS[normalized_origin]}"
                if normalized_metric == "btl_origin"
                and normalized_origin is not None
                else ORIGIN_LABELS[normalized_origin]
            )
            if normalized_metric in {"origin", "btl_origin"}
            and normalized_origin is not None
            else METRIC_TITLES[normalized_metric]
        )
    elif normalized_metric in VISIT_METRICS:
        kind = "visits"
        rows = _visit_rows(
            cutoff_date=selected_cutoff,
            metric=normalized_metric,
            branch_names=branch_names,
            branch_id_filter=branch_id_filter,
            loaded=funnel_build.loaded,
        )
        revenue_total = Decimal("0")
        title = METRIC_TITLES[normalized_metric]
    elif normalized_metric in LEAD_METRICS or normalized_metric == "leads_iventas":
        kind = "leads"
        rows = _lead_rows(
            month_start=month_start,
            cutoff_date=selected_cutoff,
            branch_ids=branch_ids,
            branch_names=branch_names,
            branch_id_filter=branch_id_filter,
            iventas_run_id=_selected_iventas_run_id(source),
            meta_only=normalized_metric in LEAD_METRICS,
        )
        revenue_total = Decimal("0")
        title = (
            METRIC_TITLES[normalized_metric]
            if normalized_metric in METRIC_TITLES
            else "Leads iVentas"
        )
    elif normalized_metric in VISIT_CONVERSION_METRICS:
        kind = "visits"
        rows = _visit_conversion_rows(
            cutoff_date=selected_cutoff,
            metric=normalized_metric,
            branch_names=branch_names,
            branch_id_filter=branch_id_filter,
            loaded=funnel_build.loaded,
        )
        revenue_total = Decimal("0")
        title = VISIT_CONVERSION_TITLES[normalized_metric]
    else:
        raise MarketingSalesFunnelDetailValidationError(
            "metric no soportado para detalle del funnel."
        )

    if branch_id_filter is not None:
        title = f"{title} · {branch_names.get(branch_id_filter, branch_id_filter)}"

    return {
        "month": month_start.strftime("%Y-%m"),
        "cutoff_date": selected_cutoff.isoformat(),
        "scope": scope,
        "metric": normalized_metric,
        "origin": normalized_origin,
        "kind": kind,
        "title": title,
        "branch_id": branch_id_filter,
        "count": len(rows),
        "revenue_total": revenue_total,
        "rows": rows,
    }


def build_marketing_sales_funnel_cutoff_detail(
    *,
    month: str,
    cutoff_date: Any,
    access: MarketingAccess,
    metric: str,
    branch_id: Any = None,
    origin: str | None = None,
    page: Any = None,
    page_size: Any = None,
    sort_by: Any = None,
    sort_dir: Any = None,
) -> dict[str, Any]:
    normalized_page, normalized_page_size = _normalize_pagination(page, page_size)
    detail = _resolve_detail_rows(
        month=month,
        cutoff_date=cutoff_date,
        access=access,
        metric=metric,
        branch_id=branch_id,
        origin=origin,
    )
    normalized_sort_by, normalized_sort_dir = _normalize_detail_sort(
        metric=detail["metric"],
        kind=detail["kind"],
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    rows = _sort_rows(
        detail["rows"],
        normalized_sort_by,
        normalized_sort_dir,
    )
    count = len(rows)
    start = (normalized_page - 1) * normalized_page_size
    end = start + normalized_page_size
    total_pages = max(1, (count + normalized_page_size - 1) // normalized_page_size)

    return {
        **detail,
        "revenue_total": float(detail["revenue_total"]),
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total_pages": total_pages,
        "sort_by": normalized_sort_by,
        "sort_dir": normalized_sort_dir,
        "rows": rows[start:end],
    }


def build_marketing_sales_funnel_cutoff_export(
    *,
    month: str,
    cutoff_date: Any,
    access: MarketingAccess,
    metric: str,
    branch_id: Any = None,
    origin: str | None = None,
    sort_by: Any = None,
    sort_dir: Any = None,
) -> tuple[BytesIO, str]:
    detail = _resolve_detail_rows(
        month=month,
        cutoff_date=cutoff_date,
        access=access,
        metric=metric,
        branch_id=branch_id,
        origin=origin,
    )
    normalized_sort_by, normalized_sort_dir = _normalize_detail_sort(
        metric=detail["metric"],
        kind=detail["kind"],
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    rows = _sort_rows(
        detail["rows"],
        normalized_sort_by,
        normalized_sort_dir,
    )

    if detail["kind"] not in EXPORT_COLUMNS_BY_KIND:
        raise MarketingSalesFunnelDetailValidationError(
            "No existe contrato de exportación para el detalle solicitado."
        )

    output = _build_excel_workbook(
        title=detail["title"],
        kind=detail["kind"],
        rows=rows,
    )
    parts = [
        "funnel_venta_nueva",
        _safe_filename_segment(detail["month"]),
        f"corte_{_safe_filename_segment(detail['cutoff_date'])}",
        _safe_filename_segment(detail["metric"]),
    ]
    if detail["origin"]:
        parts.append(_safe_filename_segment(detail["origin"]))
    if detail["branch_id"] is not None:
        parts.append(f"sucursal_{detail['branch_id']}")
    return output, "_".join(parts) + ".xlsx"
