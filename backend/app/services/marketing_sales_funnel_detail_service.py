from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy import and_, case, func

from app.models import MarketingIventasContactORM
from app.models.warehouse import (
    TrackBranchCatalogORM,
    VentaTotalSnapshotRowORM,
    VentasNuevosSociosDetalleSnapshotRowORM,
)
from app.services.marketing_access import MarketingAccess
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.services.marketing_inputs_service import parse_month
from app.services.marketing_phone import normalize_member_phone, normalize_phone
from app.services.marketing_sales_funnel_service import (
    MATCH_WINDOW_DAYS,
    ORIGIN_IVENTAS_META,
    ORIGIN_IVENTAS_OTHER,
    ORIGIN_LABELS,
    SALE_CATEGORY_BTL,
    SALE_CATEGORY_DIGITAL,
    SALE_CATEGORY_DIGITAL_ORGANIC,
    SALE_CATEGORY_WEB,
    _build_venta_total_enrichment,
    _canonical_runs_for_window,
    _classify_sale_category,
    _classify_survey,
    _load_branch_alias_map,
    _load_iventas_data,
    _load_new_sales,
    _find_venta_total_enrichment,
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
LEAD_GLOBAL_PURCHASE_WINDOW_DAYS = 60


class MarketingSalesFunnelDetailValidationError(ValueError):
    pass


SALES_METRICS = frozenset(
    {
        "sales_total",
        "sales_with_phone",
        "sales_iventas",
        "sales_iventas_meta",
        "sales_not_iventas",
        "sales_digital_total",
        "sales_digital",
        "sales_digital_organic",
        "sales_web",
        "sales_btl",
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
    "sales_digital_total": "Venta nueva · Digital",
    "sales_digital": "Venta nueva · Digital trazado",
    "sales_digital_organic": "Venta nueva · Orgánica digital",
    "sales_web": "Venta nueva · Web",
    "sales_btl": "Venta nueva · BTL",
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

    if normalized_page is None:
        normalized_page = 1
    if normalized_page_size is None:
        normalized_page_size = DEFAULT_PAGE_SIZE

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

    if normalized_metric in {"origin", "btl_origin"}:
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
    sale_category: str | None = None,
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

    if metric == "sales_digital_total":
        return sale_category in {
            SALE_CATEGORY_DIGITAL,
            SALE_CATEGORY_DIGITAL_ORGANIC,
        }
    if metric == "sales_digital":
        return sale_category == SALE_CATEGORY_DIGITAL
    if metric == "sales_digital_organic":
        return sale_category == SALE_CATEGORY_DIGITAL_ORGANIC
    if metric == "sales_web":
        return sale_category == SALE_CATEGORY_WEB
    if metric == "sales_btl":
        return sale_category == SALE_CATEGORY_BTL

    if metric == "btl_origin":
        return (
            sale_category == SALE_CATEGORY_BTL
            and origin == origin_filter
        )

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
    result: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    matched_count = 0
    revenue_total = Decimal("0")

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

        iventas_origin = _match_iventas(
            evidence,
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
        current_index = matched_count
        matched_count += 1
        if current_index < page_start or current_index >= page_end:
            continue

        folio = str(row.id_folio or "").strip()
        pin = str(row.pin or "").strip()
        transaction = by_folio.get(folio)
        if transaction is None and pin:
            transaction = by_pin_date.get((pin, sale.sale_date))
        transaction = transaction or {}

        result.append(
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

    return result, matched_count, revenue_total


def _visits_detail(
    *,
    month_start: date,
    metric: str,
    branch_ids: tuple[int, ...],
    branch_names: dict[int, str],
    branch_id_filter: int | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    snapshot = _select_venta_total_snapshot(month_start)
    if snapshot is None:
        return [], 0

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
    result: list[dict[str, Any]] = []
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

        current_index = matched_count
        matched_count += 1
        if current_index < page_start or current_index >= page_end:
            continue

        result.append(
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
    return result, matched_count


def _lead_followup_label(*, visited: bool, bought: bool) -> str:
    if bought:
        return "Ya compró"
    if visited:
        return "Visita sin compra"
    return "Sin visita / sin compra"


def _iter_month_starts(start_date: date, end_date: date) -> tuple[date, ...]:
    current = date(start_date.year, start_date.month, 1)
    final = date(end_date.year, end_date.month, 1)
    result: list[date] = []

    while current <= final:
        result.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    return tuple(result)


def _load_global_marketing_branches() -> tuple[tuple[int, ...], dict[int, str]]:
    rows = (
        TrackBranchCatalogORM.query.filter(
            TrackBranchCatalogORM.is_track_active.is_(True),
            TrackBranchCatalogORM.sucursal_id.isnot(None),
        )
        .order_by(
            TrackBranchCatalogORM.display_order.asc(),
            TrackBranchCatalogORM.sucursal_id.asc(),
        )
        .all()
    )

    branch_ids: list[int] = []
    branch_names: dict[int, str] = {}
    seen: set[int] = set()

    for row in rows:
        branch_id = int(row.sucursal_id)
        if branch_id not in seen:
            seen.add(branch_id)
            branch_ids.append(branch_id)

        branch_names.setdefault(
            branch_id,
            (
                str(row.sucursal.sucursal).strip()
                if row.sucursal is not None
                else str(row.track_label).strip()
            ),
        )

    return tuple(branch_ids), branch_names


def _enrich_lead_followup_rows(
    rows: list[dict[str, Any]],
    *,
    visits: Any,
    sales: Any,
    global_branch_names: dict[int, str] | None = None,
    visible_branch_ids: tuple[int, ...] | None = None,
    cutoff_date: date | None = None,
) -> list[dict[str, Any]]:
    visit_dates_by_identity: dict[tuple[int, str], list[date]] = {}
    sales_by_phone: dict[str, list[tuple[date, int]]] = {}

    for visit in visits or ():
        phone = str(getattr(visit, "phone", "") or "").strip()
        if not phone:
            continue
        identity = (int(visit.branch_id), phone)
        visit_dates_by_identity.setdefault(identity, []).append(visit.visit_date)

    for sale in sales or ():
        phone = str(getattr(sale, "phone", "") or "").strip()
        if not phone:
            continue
        sales_by_phone.setdefault(phone, []).append(
            (sale.sale_date, int(sale.branch_id))
        )

    for values in visit_dates_by_identity.values():
        values.sort()
    for values in sales_by_phone.values():
        values.sort(key=lambda item: (item[0], item[1]))

    visible_ids = (
        set(visible_branch_ids)
        if visible_branch_ids is not None
        else None
    )
    branch_names = global_branch_names or {}

    enriched: list[dict[str, Any]] = []
    for row in rows:
        current = dict(row)
        phone = str(current.get("phone") or "").strip()
        raw_date = str(current.get("date") or "").strip()

        try:
            lead_date = date.fromisoformat(raw_date)
        except ValueError:
            lead_date = None

        visit_date: date | None = None
        global_sale_date: date | None = None
        global_sale_branch_id: int | None = None

        if lead_date is not None and phone:
            branch_id = int(current["branch_id"])
            identity = (branch_id, phone)

            visit_window_end = lead_date + timedelta(days=MATCH_WINDOW_DAYS)
            purchase_window_end = lead_date + timedelta(
                days=LEAD_GLOBAL_PURCHASE_WINDOW_DAYS
            )
            if cutoff_date is not None:
                visit_window_end = min(visit_window_end, cutoff_date)
                purchase_window_end = min(purchase_window_end, cutoff_date)

            visit_date = next(
                (
                    event_date
                    for event_date in visit_dates_by_identity.get(identity, ())
                    if lead_date <= event_date <= visit_window_end
                ),
                None,
            )

            global_sale = next(
                (
                    (event_date, sale_branch_id)
                    for event_date, sale_branch_id in sales_by_phone.get(
                        phone,
                        (),
                    )
                    if lead_date <= event_date <= purchase_window_end
                ),
                None,
            )
            if global_sale is not None:
                global_sale_date, global_sale_branch_id = global_sale

        visited = visit_date is not None
        bought = global_sale_date is not None

        purchase_branch: str | None = None
        if global_sale_branch_id is not None:
            if (
                visible_ids is not None
                and global_sale_branch_id not in visible_ids
            ):
                purchase_branch = "Otra sucursal Ultra"
            else:
                purchase_branch = branch_names.get(
                    global_sale_branch_id,
                    f"Sucursal #{global_sale_branch_id}",
                )

        current.update(
            {
                "visit_status": "Sí" if visited else "No",
                "visit_date": visit_date.isoformat() if visit_date else None,
                "purchase_status": "Sí" if bought else "No",
                "sale_date": (
                    global_sale_date.isoformat()
                    if global_sale_date is not None
                    else None
                ),
                "purchase_branch": purchase_branch,
                "followup_status": _lead_followup_label(
                    visited=visited,
                    bought=bought,
                ),
            }
        )
        enriched.append(current)

    return enriched


def _sql_normalized_phone(telefono_column: Any, lada_column: Any = None) -> Any:
    phone_digits = func.regexp_replace(
        func.coalesce(telefono_column, ""),
        r"\D",
        "",
        "g",
    )
    direct_phone = case(
        (func.length(phone_digits) == 10, phone_digits),
        (
            and_(
                func.length(phone_digits) == 12,
                func.left(phone_digits, 2) == "52",
            ),
            func.right(phone_digits, 10),
        ),
        (
            and_(
                func.length(phone_digits) == 13,
                func.left(phone_digits, 3) == "521",
            ),
            func.right(phone_digits, 10),
        ),
        else_=None,
    )

    if lada_column is None:
        return direct_phone

    combined_digits = func.regexp_replace(
        func.concat(
            func.coalesce(lada_column, ""),
            func.coalesce(telefono_column, ""),
        ),
        r"\D",
        "",
        "g",
    )
    combined_phone = case(
        (func.length(combined_digits) == 10, combined_digits),
        (
            and_(
                func.length(combined_digits) == 12,
                func.left(combined_digits, 2) == "52",
            ),
            func.right(combined_digits, 10),
        ),
        (
            and_(
                func.length(combined_digits) == 13,
                func.left(combined_digits, 3) == "521",
            ),
            func.right(combined_digits, 10),
        ),
        else_=None,
    )
    return func.coalesce(direct_phone, combined_phone)


def _lead_candidate_phones(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(row.get("phone") or "").strip()
                for row in rows
                if str(row.get("phone") or "").strip()
            }
        )
    )


def _load_targeted_venta_total_rows(
    *,
    month_start: date,
    candidate_phones: tuple[str, ...],
) -> list[VentaTotalSnapshotRowORM]:
    if not candidate_phones:
        return []

    snapshot = _select_venta_total_snapshot(month_start)
    if snapshot is None:
        return []

    base_query = VentaTotalSnapshotRowORM.query.filter(
        VentaTotalSnapshotRowORM.snapshot_id == snapshot.id,
    )

    exact_rows = base_query.filter(
        VentaTotalSnapshotRowORM.telefono.in_(candidate_phones),
    ).all()

    matched_phones = {
        phone
        for row in exact_rows
        if (phone := normalize_phone(row.telefono)) is not None
    }
    remaining = tuple(
        phone for phone in candidate_phones if phone not in matched_phones
    )

    if not remaining:
        return exact_rows

    normalized_phone = _sql_normalized_phone(
        VentaTotalSnapshotRowORM.telefono,
    )
    normalized_rows = base_query.filter(
        normalized_phone.in_(remaining),
    ).all()

    by_id = {int(row.id): row for row in exact_rows}
    for row in normalized_rows:
        by_id.setdefault(int(row.id), row)
    return list(by_id.values())


def _load_targeted_purchase_events(
    *,
    month_start: date,
    candidate_phones: tuple[str, ...],
    branch_ids: tuple[int, ...],
    venta_total_rows: list[VentaTotalSnapshotRowORM],
) -> list[Any]:
    if not candidate_phones or not branch_ids:
        return []

    snapshot = _select_new_sales_detail_snapshot(month_start)
    if snapshot is None:
        return []

    base_query = VentasNuevosSociosDetalleSnapshotRowORM.query.filter(
        VentasNuevosSociosDetalleSnapshotRowORM.snapshot_id == snapshot.id,
        VentasNuevosSociosDetalleSnapshotRowORM.sucursal_id.in_(branch_ids),
    )

    exact_rows = base_query.filter(
        VentasNuevosSociosDetalleSnapshotRowORM.telefono.in_(
            candidate_phones
        ),
    ).all()

    matched_phones = {
        phone
        for row in exact_rows
        if (
            phone := normalize_member_phone(
                lada=row.lada,
                telefono=row.telefono,
            )
        )
        is not None
    }
    remaining = tuple(
        phone for phone in candidate_phones if phone not in matched_phones
    )

    normalized_rows: list[Any] = []
    if remaining:
        normalized_phone = _sql_normalized_phone(
            VentasNuevosSociosDetalleSnapshotRowORM.telefono,
            VentasNuevosSociosDetalleSnapshotRowORM.lada,
        )
        normalized_rows = base_query.filter(
            normalized_phone.in_(remaining),
        ).all()

    by_folio, by_pin_date = _build_venta_total_enrichment(
        venta_total_rows,
        month_start,
    )

    enrichment_rows: list[Any] = []
    folios = tuple(by_folio.keys())
    pins = tuple({pin for pin, _ in by_pin_date.keys()})
    if folios:
        enrichment_rows.extend(
            base_query.filter(
                VentasNuevosSociosDetalleSnapshotRowORM.id_folio.in_(folios),
            ).all()
        )
    if pins:
        enrichment_rows.extend(
            base_query.filter(
                VentasNuevosSociosDetalleSnapshotRowORM.pin.in_(pins),
            ).all()
        )

    candidates: dict[int, Any] = {}
    for row in [*exact_rows, *normalized_rows, *enrichment_rows]:
        candidates.setdefault(int(row.id), row)

    allowed_phones = set(candidate_phones)
    events: dict[tuple[str, date, int], Any] = {}

    for row in candidates.values():
        try:
            payment_date = _payment_local_date(row.fecha_pago_at)
        except ValueError:
            continue
        if payment_date.replace(day=1) != month_start:
            continue

        phone = normalize_member_phone(
            lada=row.lada,
            telefono=row.telefono,
        )
        if phone is None:
            enrichment = _find_venta_total_enrichment(
                by_folio=by_folio,
                by_pin_date=by_pin_date,
                folio=row.id_folio,
                pin=row.pin,
                payment_date=payment_date,
            )
            phone = enrichment.phone if enrichment is not None else None

        if phone is None or phone not in allowed_phones:
            continue

        branch_id = int(row.sucursal_id)
        key = (phone, payment_date, branch_id)
        events.setdefault(
            key,
            SimpleNamespace(
                phone=phone,
                sale_date=payment_date,
                branch_id=branch_id,
            ),
        )

    return list(events.values())


def _load_month_lead_followup_sources(
    *,
    month_start: date,
    branch_ids: tuple[int, ...],
    lead_rows: list[dict[str, Any]],
) -> tuple[Any, Any, dict[int, str]]:
    candidate_phones = _lead_candidate_phones(lead_rows)
    global_branch_ids, global_branch_names = _load_global_marketing_branches()

    if not candidate_phones:
        return [], [], global_branch_names

    alias_map = _load_branch_alias_map()
    month_end = _month_end(month_start)
    venta_total_cache: dict[date, list[VentaTotalSnapshotRowORM]] = {}

    def targeted_venta_total(period_start: date) -> list[VentaTotalSnapshotRowORM]:
        rows = venta_total_cache.get(period_start)
        if rows is None:
            rows = _load_targeted_venta_total_rows(
                month_start=period_start,
                candidate_phones=candidate_phones,
            )
            venta_total_cache[period_start] = rows
        return rows

    visits: list[Any] = []
    visit_horizon = month_end + timedelta(days=MATCH_WINDOW_DAYS)
    for period_start in _iter_month_starts(month_start, visit_horizon):
        visits.extend(
            _load_visits(
                targeted_venta_total(period_start),
                period_start,
                branch_ids,
                alias_map,
            )
        )

    sales: list[Any] = []
    purchase_horizon = month_end + timedelta(
        days=LEAD_GLOBAL_PURCHASE_WINDOW_DAYS
    )
    for period_start in _iter_month_starts(month_start, purchase_horizon):
        sales.extend(
            _load_targeted_purchase_events(
                month_start=period_start,
                candidate_phones=candidate_phones,
                branch_ids=global_branch_ids,
                venta_total_rows=targeted_venta_total(period_start),
            )
        )

    return visits, sales, global_branch_names


def _leads_meta_detail(
    *,
    month_start: date,
    branch_ids: tuple[int, ...],
    branch_names: dict[int, str],
    branch_id_filter: int | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    window_start = month_start - timedelta(days=MATCH_WINDOW_DAYS)
    runs = _canonical_runs_for_window(window_start, _month_end(month_start))
    current_period_key = f"IVENTAS-{month_start.strftime('%Y-%m')}"
    current_run_ids = tuple(
        int(run.id)
        for run in runs
        if str(run.period_key) == current_period_key
    )
    if not current_run_ids:
        return [], 0

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
    result: list[dict[str, Any]] = []
    matched_count = 0
    for contact in contacts:
        branch_id = int(contact.sucursal_id)
        if branch_id not in allowed:
            continue
        if branch_id_filter is not None and branch_id != branch_id_filter:
            continue
        if (int(contact.sync_run_id), int(contact.id)) not in meta_keys:
            continue

        current_index = matched_count
        matched_count += 1
        if current_index < page_start or current_index >= page_end:
            continue

        result.append(
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

    visits, sales, global_branch_names = _load_month_lead_followup_sources(
        month_start=month_start,
        branch_ids=branch_ids,
        lead_rows=result,
    )
    return (
        _enrich_lead_followup_rows(
            result,
            visits=visits,
            sales=sales,
            global_branch_names=global_branch_names,
            visible_branch_ids=branch_ids,
        ),
        matched_count,
    )


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
    normalized_page, normalized_page_size = _normalize_pagination(
        page,
        page_size,
    )
    branch_id_filter = _normalize_optional_int(
        branch_id,
        field_name="branch_id",
    )

    branches, branch_ids, scope = load_visible_marketing_branches(access)
    allowed = set(branch_ids)
    if branch_id_filter is not None and branch_id_filter not in allowed:
        raise MarketingSalesFunnelDetailValidationError(
            "La sucursal solicitada no pertenece al alcance del usuario."
        )

    branch_names = _branch_name_map(branches)

    if metric in SALES_METRICS or metric in {"origin", "btl_origin"}:
        kind = "sales"
        rows, count, revenue_total = _sales_detail(
            month_start=month_start,
            metric=metric,
            origin_filter=origin,
            branch_ids=branch_ids,
            branch_names=branch_names,
            branch_id_filter=branch_id_filter,
            page=normalized_page,
            page_size=normalized_page_size,
        )
    elif metric in VISIT_METRICS:
        kind = "visits"
        rows, count = _visits_detail(
            month_start=month_start,
            metric=metric,
            branch_ids=branch_ids,
            branch_names=branch_names,
            branch_id_filter=branch_id_filter,
            page=normalized_page,
            page_size=normalized_page_size,
        )
        revenue_total = Decimal("0")
    else:
        kind = "leads"
        rows, count = _leads_meta_detail(
            month_start=month_start,
            branch_ids=branch_ids,
            branch_names=branch_names,
            branch_id_filter=branch_id_filter,
            page=normalized_page,
            page_size=normalized_page_size,
        )
        revenue_total = Decimal("0")

    title = (
        (
            f"BTL · {ORIGIN_LABELS[origin]}"
            if metric == "btl_origin" and origin is not None
            else ORIGIN_LABELS[origin]
        )
        if metric in {"origin", "btl_origin"} and origin is not None
        else METRIC_TITLES[metric]
    )
    if branch_id_filter is not None:
        title = f"{title} · {branch_names.get(branch_id_filter, branch_id_filter)}"

    total_pages = max(
        1,
        (count + normalized_page_size - 1) // normalized_page_size,
    )

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
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total_pages": total_pages,
        "rows": rows,
    }
