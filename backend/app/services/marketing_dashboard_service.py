from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable
import unicodedata
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.marketing import MarketingMonthlyInputORM
from app.models.warehouse import (
    TrackBranchAliasORM,
    TrackBranchCatalogORM,
    VentaTotalSnapshotORM,
    VentaTotalSnapshotRowORM,
    VentasNuevosSociosDetalleSnapshotORM,
    VentasNuevosSociosDetalleSnapshotRowORM,
)
from app.services.marketing_access import (
    MarketingAccess,
    MarketingAuthorizationError,
)
from app.services.marketing_attribution import (
    SaleRecord,
    VisitEvent,
    count_unique_visitors,
    deduplicate_visit_events,
    reconcile_visit_sales,
    safe_divide,
)
from app.services.marketing_inputs_service import (
    list_marketing_inputs,
    parse_month,
)
from app.services.marketing_iventas_dashboard_data_service import (
    read_iventas_dashboard_month_data,
)
from app.services.marketing_phone import (
    normalize_member_phone,
    normalize_phone,
)


TIJUANA_TIMEZONE = ZoneInfo("America/Tijuana")
ELIGIBLE_VISIT_DESCRIPTIONS = frozenset(
    {
        "PASE 2 DIAS GRATIS",
        "PASE RECORRIDO",
    }
)
CANCELLED_STATUS_TERMS = (
    "CANCELADO",
    "CANCELADA",
    "ANULADO",
    "ANULADA",
)

ATTRIBUTION_CLASS_STANDARD = "STANDARD_SALE"
ATTRIBUTION_CLASS_FAMILY_ADDITIONAL = (
    "FAMILY_PLAN_ADDITIONAL_MEMBER"
)
ATTRIBUTION_CLASS_REVIEW = (
    "NON_POSITIVE_AMOUNT_REVIEW"
)

FAMILY_PLAN_ADDITIONAL_MEMBER_TARIFFS = frozenset(
    {
        (
            "DOMICILIADO 12 MESES PLAN FAMILIAR "
            "$999 (ADULTO + ADULTO)"
        ),
    }
)

FIXED_LIMITATIONS = (
    (
        "Los leads requieren un snapshot canónico iVentas del periodo "
        "con firstMessageAt y al menos un tag META_AD."
    ),
    "No existe todavía atribución individual lead -> visita.",
    "Las ventas solo se atribuyen con teléfono exacto y misma sucursal.",
    "Una cohorte reciente puede seguir madurando durante 30 días.",
)


@dataclass(frozen=True)
class MarketingBranch:
    sucursal_id: int
    name: str
    display_order: int


@dataclass(frozen=True)
class _EligibleVisit:
    event_key: str
    branch_id: int
    visit_date: date
    phone: str | None
    description: str


@dataclass
class VisitLoadResult:
    events: list[VisitEvent] = field(default_factory=list)
    eligible_visit_events: int = 0
    visit_events_with_valid_phone: int = 0
    visit_events_without_valid_phone: int = 0
    snapshot_id: int | None = None
    limitations: list[str] = field(default_factory=list)


@dataclass
class SalesLoadResult:
    sales: list[SaleRecord] = field(default_factory=list)
    snapshot_ids: list[int] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def _normalize_text(value: Any) -> str:
    text_value = str(value or "").strip().upper()
    without_accents = "".join(
        character
        for character in unicodedata.normalize(
            "NFKD",
            text_value,
        )
        if not unicodedata.combining(character)
    )
    return " ".join(without_accents.split())


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(
            str(value).strip().replace("$", "").replace(",", "")
        )
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"No se pudo convertir a Decimal: {value!r}"
        ) from exc


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return _to_decimal(value)


def _join_member_name(row: Any) -> str | None:
    parts = [
        str(getattr(row, field_name, "") or "").strip()
        for field_name in (
            "nombre",
            "apellido_paterno",
            "apellido_materno",
        )
    ]
    full_name = " ".join(
        part
        for part in parts
        if part
    )
    return full_name or None


def _mask_phone(phone: str) -> str:
    return f"*** *** {phone[-4:]}"


def _classify_attributed_sale(
    sale: SaleRecord,
) -> str:
    if sale.revenue > 0:
        return ATTRIBUTION_CLASS_STANDARD

    normalized_tariff = _normalize_text(
        sale.tariff
    )

    is_family_additional_member = (
        sale.revenue == Decimal("0")
        and sale.listed_total == Decimal("0")
        and normalized_tariff
        in FAMILY_PLAN_ADDITIONAL_MEMBER_TARIFFS
    )

    if is_family_additional_member:
        return ATTRIBUTION_CLASS_FAMILY_ADDITIONAL

    return ATTRIBUTION_CLASS_REVIEW


def _month_end(month_start: date) -> date:
    return date(
        month_start.year,
        month_start.month,
        monthrange(
            month_start.year,
            month_start.month,
        )[1],
    )


def _calendar_month_starts(
    *,
    start_date: date,
    end_date: date,
) -> list[date]:
    current = start_date.replace(day=1)
    last_month = end_date.replace(day=1)
    result: list[date] = []

    while current <= last_month:
        result.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(
                current.year,
                current.month + 1,
                1,
            )

    return result


def _parse_visit_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(
        value,
        datetime,
    ):
        return value
    if isinstance(value, datetime):
        return value.date()

    raw_value = str(value or "").strip()
    for date_format in (
        "%Y-%m-%d",
        "%d-%m-%y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(
                raw_value,
                date_format,
            ).date()
        except ValueError:
            continue

    raise ValueError(
        f"No se pudo interpretar fecha de visita: {value!r}"
    )


def _payment_local_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(
        value,
        datetime,
    ):
        return value
    if not isinstance(value, datetime):
        raise ValueError(
            "fecha_pago_at debe ser datetime."
        )

    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(
            tzinfo=timezone.utc
        )

    return normalized.astimezone(
        TIJUANA_TIMEZONE
    ).date()


def _load_available_branches() -> list[MarketingBranch]:
    catalog_rows = (
        TrackBranchCatalogORM.query.filter(
            TrackBranchCatalogORM.is_track_active.is_(
                True
            ),
            TrackBranchCatalogORM.sucursal_id.isnot(
                None
            ),
        )
        .order_by(
            TrackBranchCatalogORM.display_order.asc(),
            TrackBranchCatalogORM.sucursal_id.asc(),
        )
        .all()
    )

    return [
        MarketingBranch(
            sucursal_id=int(row.sucursal_id),
            name=(
                str(row.sucursal.sucursal).strip()
                if row.sucursal is not None
                else str(row.track_label).strip()
            ),
            display_order=int(row.display_order),
        )
        for row in catalog_rows
    ]


def load_visible_marketing_branches(
    access: MarketingAccess,
) -> tuple[
    list[MarketingBranch],
    tuple[int, ...],
    dict[str, object],
]:
    available_branches = _load_available_branches()
    visible_branch_ids = access.visible_branch_ids(
        branch.sucursal_id
        for branch in available_branches
    )
    visible_id_set = set(visible_branch_ids)
    visible_branches = [
        branch
        for branch in available_branches
        if branch.sucursal_id in visible_id_set
    ]
    scope = access.to_scope_dict(
        branch.sucursal_id
        for branch in available_branches
    )
    return (
        visible_branches,
        visible_branch_ids,
        scope,
    )


def _load_branch_alias_map() -> dict[str, int]:
    rows = (
        db.session.query(
            TrackBranchAliasORM,
            TrackBranchCatalogORM,
        )
        .join(
            TrackBranchCatalogORM,
            TrackBranchCatalogORM.sucursal_canon
            == TrackBranchAliasORM.sucursal_canon,
        )
        .filter(
            TrackBranchAliasORM.source_family
            == "gasca_family",
            TrackBranchAliasORM.is_active.is_(True),
            TrackBranchCatalogORM.is_track_active.is_(
                True
            ),
            TrackBranchCatalogORM.sucursal_id.isnot(
                None
            ),
        )
        .all()
    )

    return {
        _normalize_text(alias.raw_branch_name): int(
            catalog.sucursal_id
        )
        for alias, catalog in rows
    }


def _select_venta_total_snapshot(
    *,
    month_start: date,
) -> VentaTotalSnapshotORM | None:
    return (
        VentaTotalSnapshotORM.query.filter(
            VentaTotalSnapshotORM.report_type_key
            == "venta_total",
            VentaTotalSnapshotORM.business_date
            >= month_start,
            VentaTotalSnapshotORM.business_date
            <= _month_end(month_start),
            VentaTotalSnapshotORM.snapshot_kind
            == "daily",
            VentaTotalSnapshotORM.is_canonical.is_(
                True
            ),
        )
        .order_by(
            VentaTotalSnapshotORM.business_date.desc(),
            VentaTotalSnapshotORM.id.desc(),
        )
        .first()
    )


def _visit_event_key(
    *,
    row: VentaTotalSnapshotRowORM,
    branch_id: int,
    visit_date: date,
    phone: str | None,
    description: str,
) -> str:
    id_orden = str(row.id_orden or "").strip()
    if id_orden:
        return f"id_orden:{id_orden}"

    folio = str(row.folio or "").strip()
    if folio:
        return f"folio:{folio}"

    raw_phone_key = (
        phone
        or _normalize_text(row.telefono)
        or "SIN_TELEFONO"
    )
    return (
        f"fallback:{branch_id}:"
        f"{visit_date.isoformat()}:"
        f"{raw_phone_key}:{description}"
    )


def _load_visit_events(
    *,
    month_start: date,
    branch_ids: tuple[int, ...],
) -> VisitLoadResult:
    snapshot = _select_venta_total_snapshot(
        month_start=month_start
    )
    if snapshot is None:
        return VisitLoadResult(
            limitations=[
                "No existe snapshot canónico de Venta Total para el mes."
            ]
        )

    allowed_branch_ids = set(branch_ids)
    alias_map = _load_branch_alias_map()
    rows = VentaTotalSnapshotRowORM.query.filter_by(
        snapshot_id=snapshot.id
    ).all()
    eligible_by_key: dict[str, _EligibleVisit] = {}

    for row in rows:
        try:
            visit_date = _parse_visit_date(row.fecha)
            total = _to_decimal(row.total)
        except ValueError:
            continue

        if visit_date.replace(day=1) != month_start:
            continue

        description = _normalize_text(
            row.descripcion
        )
        if description not in ELIGIBLE_VISIT_DESCRIPTIONS:
            continue

        if total != 0:
            continue

        normalized_status = _normalize_text(row.estatus)
        if any(
            term in normalized_status
            for term in CANCELLED_STATUS_TERMS
        ):
            continue

        branch_id = alias_map.get(
            _normalize_text(row.sucursal)
        )
        if (
            branch_id is None
            or branch_id not in allowed_branch_ids
        ):
            continue

        phone = normalize_phone(row.telefono)
        event_key = _visit_event_key(
            row=row,
            branch_id=branch_id,
            visit_date=visit_date,
            phone=phone,
            description=description,
        )
        eligible_by_key.setdefault(
            event_key,
            _EligibleVisit(
                event_key=event_key,
                branch_id=branch_id,
                visit_date=visit_date,
                phone=phone,
                description=description,
            ),
        )

    eligible_events = list(
        eligible_by_key.values()
    )
    valid_events = [
        VisitEvent(
            event_key=event.event_key,
            branch_id=event.branch_id,
            visit_date=event.visit_date,
            phone=event.phone,
            description=event.description,
        )
        for event in eligible_events
        if event.phone is not None
    ]

    return VisitLoadResult(
        events=deduplicate_visit_events(valid_events),
        eligible_visit_events=len(eligible_events),
        visit_events_with_valid_phone=len(valid_events),
        visit_events_without_valid_phone=(
            len(eligible_events) - len(valid_events)
        ),
        snapshot_id=int(snapshot.id),
    )


def _select_sales_snapshots(
    *,
    window_start: date,
    window_end: date,
) -> list[
    VentasNuevosSociosDetalleSnapshotORM
]:
    selected = []

    for calendar_month in _calendar_month_starts(
        start_date=window_start,
        end_date=window_end,
    ):
        snapshot = (
            VentasNuevosSociosDetalleSnapshotORM.query
            .filter(
                VentasNuevosSociosDetalleSnapshotORM.report_type_key
                == "ventas_nuevos_socios_detalle",
                VentasNuevosSociosDetalleSnapshotORM.business_date
                >= calendar_month,
                VentasNuevosSociosDetalleSnapshotORM.business_date
                <= _month_end(calendar_month),
                VentasNuevosSociosDetalleSnapshotORM.date_from
                == calendar_month,
                VentasNuevosSociosDetalleSnapshotORM.snapshot_kind
                == "month_to_date",
                VentasNuevosSociosDetalleSnapshotORM.is_canonical.is_(
                    True
                ),
            )
            .order_by(
                VentasNuevosSociosDetalleSnapshotORM.business_date.desc(),
                VentasNuevosSociosDetalleSnapshotORM.captured_at.desc(),
                VentasNuevosSociosDetalleSnapshotORM.id.desc(),
            )
            .first()
        )
        if snapshot is not None:
            selected.append(snapshot)

    return selected


def _load_sales(
    *,
    window_start: date,
    window_end: date,
    branch_ids: tuple[int, ...],
) -> SalesLoadResult:
    snapshots = _select_sales_snapshots(
        window_start=window_start,
        window_end=window_end,
    )
    snapshot_ids = [
        int(snapshot.id)
        for snapshot in snapshots
    ]
    if not snapshot_ids:
        return SalesLoadResult(
            limitations=[
                "No existen snapshots canónicos de ventas nuevas para la ventana."
            ]
        )

    allowed_branch_ids = set(branch_ids)
    rows = (
        VentasNuevosSociosDetalleSnapshotRowORM.query
        .filter(
            VentasNuevosSociosDetalleSnapshotRowORM.snapshot_id.in_(
                snapshot_ids
            )
        )
        .all()
    )
    sales: list[SaleRecord] = []

    for row in rows:
        if row.sucursal_id is None:
            continue

        branch_id = int(row.sucursal_id)
        if branch_id not in allowed_branch_ids:
            continue

        try:
            payment_date = _payment_local_date(
                row.fecha_pago_at
            )
        except ValueError:
            continue

        if not (
            window_start
            <= payment_date
            <= window_end
        ):
            continue

        phone = normalize_member_phone(
            lada=row.lada,
            telefono=row.telefono,
        )
        if phone is None:
            continue

        member_id = str(row.id_socio or "").strip()
        id_folio = str(row.id_folio or "").strip()
        if member_id:
            sale_key = f"id_socio:{member_id}"
        elif id_folio:
            sale_key = f"id_folio:{id_folio}"
        else:
            continue

        sales.append(
            SaleRecord(
                sale_key=sale_key,
                branch_id=branch_id,
                payment_date=payment_date,
                phone=phone,
                member_id=member_id or None,
                revenue=_to_decimal(
                    row.total_pagado
                ),
                snapshot_id=int(row.snapshot_id),
                source_row_id=int(row.id),
                folio=id_folio or None,
                member_name=_join_member_name(row),
                membership_type=(
                    str(row.tipo_membresia or "").strip()
                    or None
                ),
                tariff=(
                    str(row.tarifa or "").strip()
                    or None
                ),
                registration=(
                    str(row.inscripcion or "").strip()
                    or None
                ),
                pass_name=(
                    str(row.pase or "").strip()
                    or None
                ),
                payment_place=(
                    str(row.lugar_pago or "").strip()
                    or None
                ),
                listed_total=_optional_decimal(row.total),
            )
        )

    return SalesLoadResult(
        sales=sales,
        snapshot_ids=snapshot_ids,
    )


def _load_inputs_by_branch(
    *,
    month_start: date,
    branch_ids: tuple[int, ...],
) -> dict[int, MarketingMonthlyInputORM]:
    return {
        int(row.sucursal_id): row
        for row in list_marketing_inputs(
            month_start=month_start,
            branch_ids=branch_ids,
        )
    }


def _serialize_ratio(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _build_metrics(
    *,
    investment: Decimal,
    leads: int | None,
    visits: int,
    sales: int,
    sales_revenue: Decimal,
) -> dict[str, Any]:
    return {
        "investment": float(investment),
        "leads": leads,
        "visits": visits,
        "sales": sales,
        "sales_revenue": float(sales_revenue),
        "cost_per_lead": (
            _serialize_ratio(
                safe_divide(investment, leads)
            )
            if leads is not None
            else None
        ),
        "cost_per_visit": _serialize_ratio(
            safe_divide(investment, visits)
        ),
        "cost_per_sale": _serialize_ratio(
            safe_divide(investment, sales)
        ),
        "lead_to_visit_rate": (
            _serialize_ratio(
                safe_divide(visits, leads)
            )
            if leads is not None
            else None
        ),
        "visit_to_sale_rate": _serialize_ratio(
            safe_divide(sales, visits)
        ),
        "lead_to_sale_rate": (
            _serialize_ratio(
                safe_divide(sales, leads)
            )
            if leads is not None
            else None
        ),
    }


def build_marketing_dashboard(
    *,
    month: str,
    access: MarketingAccess,
    today: date | None = None,
) -> dict[str, Any]:
    month_start = parse_month(month)
    month_end = _month_end(month_start)
    attribution_window_end = month_end + timedelta(
        days=30
    )
    (
        branches,
        visible_branch_ids,
        scope,
    ) = load_visible_marketing_branches(access)

    normalized_today = (
        today
        if today is not None
        else datetime.now(
            TIJUANA_TIMEZONE
        ).date()
    )
    iventas_data = read_iventas_dashboard_month_data(
        month_date=month_start,
        today=normalized_today,
    )
    iventas_available = bool(
        iventas_data.available
        and iventas_data.metrics is not None
    )

    if iventas_available:
        iventas_by_branch = {
            int(row.sucursal_id): row
            for row in (iventas_data.branch_metrics or ())
        }
        visible_iventas_rows = [
            iventas_by_branch[branch_id]
            for branch_id in visible_branch_ids
            if branch_id in iventas_by_branch
        ]
        summary_iventas = {
            "available": True,
            "period_key": iventas_data.period_key,
            "sync_run_id": iventas_data.sync_run_id,
            "date_from": iventas_data.date_from.isoformat(),
            "date_to": iventas_data.date_to.isoformat(),
            "contacts": sum(
                row.iventas_contacts
                for row in visible_iventas_rows
            ),
            "contacts_with_first_message": sum(
                row.iventas_contacts_with_first_message
                for row in visible_iventas_rows
            ),
            "meta_observed_leads": sum(
                row.meta_observed_leads
                for row in visible_iventas_rows
            ),
        }
    else:
        iventas_by_branch = {}
        summary_iventas = {
            "available": False,
            "period_key": iventas_data.period_key,
            "sync_run_id": None,
            "date_from": iventas_data.date_from.isoformat(),
            "date_to": iventas_data.date_to.isoformat(),
            "contacts": None,
            "contacts_with_first_message": None,
            "meta_observed_leads": None,
        }

    inputs_by_branch = _load_inputs_by_branch(
        month_start=month_start,
        branch_ids=visible_branch_ids,
    )
    visit_result = _load_visit_events(
        month_start=month_start,
        branch_ids=visible_branch_ids,
    )
    sales_result = _load_sales(
        window_start=month_start,
        window_end=attribution_window_end,
        branch_ids=visible_branch_ids,
    )
    attributions = reconcile_visit_sales(
        visits=visit_result.events,
        sales=sales_result.sales,
    )

    visits_by_branch: dict[int, list[VisitEvent]] = {
        branch_id: []
        for branch_id in visible_branch_ids
    }
    for event in visit_result.events:
        visits_by_branch.setdefault(
            event.branch_id,
            [],
        ).append(event)

    attributions_by_branch = {
        branch_id: []
        for branch_id in visible_branch_ids
    }
    for attribution in attributions:
        attributions_by_branch.setdefault(
            attribution.visit.branch_id,
            [],
        ).append(attribution)

    branch_payloads: list[dict[str, Any]] = []
    summary_investment = Decimal("0")
    summary_leads: int | None = (
        0 if iventas_available else None
    )
    summary_visits = 0
    summary_sales = 0
    summary_revenue = Decimal("0")

    for branch in branches:
        monthly_input = inputs_by_branch.get(
            branch.sucursal_id
        )
        investment = (
            _to_decimal(monthly_input.investment)
            if monthly_input is not None
            else Decimal("0")
        )
        branch_iventas = iventas_by_branch.get(
            branch.sucursal_id
        )
        leads: int | None = (
            (
                int(branch_iventas.meta_observed_leads)
                if branch_iventas is not None
                else 0
            )
            if iventas_available
            else None
        )
        visits = count_unique_visitors(
            visits_by_branch.get(
                branch.sucursal_id,
                [],
            )
        )
        branch_attributions = (
            attributions_by_branch.get(
                branch.sucursal_id,
                [],
            )
        )
        sales = len(branch_attributions)
        revenue = sum(
            (
                attribution.sale.revenue
                for attribution in branch_attributions
            ),
            Decimal("0"),
        )
        metrics = _build_metrics(
            investment=investment,
            leads=leads,
            visits=visits,
            sales=sales,
            sales_revenue=revenue,
        )
        if iventas_available:
            branch_iventas_payload = {
                "available": True,
                "period_key": iventas_data.period_key,
                "sync_run_id": iventas_data.sync_run_id,
                "contacts": (
                    branch_iventas.iventas_contacts
                    if branch_iventas is not None
                    else 0
                ),
                "contacts_with_first_message": (
                    branch_iventas
                    .iventas_contacts_with_first_message
                    if branch_iventas is not None
                    else 0
                ),
                "meta_observed_leads": leads,
            }
        else:
            branch_iventas_payload = {
                "available": False,
                "period_key": iventas_data.period_key,
                "sync_run_id": None,
                "contacts": None,
                "contacts_with_first_message": None,
                "meta_observed_leads": None,
            }

        branch_payloads.append(
            {
                "sucursal_id": branch.sucursal_id,
                "sucursal": branch.name,
                **metrics,
                "iventas": branch_iventas_payload,
            }
        )

        summary_investment += investment
        if summary_leads is not None and leads is not None:
            summary_leads += leads
        summary_visits += visits
        summary_sales += sales
        summary_revenue += revenue

    summary_payload = _build_metrics(
        investment=summary_investment,
        leads=summary_leads,
        visits=summary_visits,
        sales=summary_sales,
        sales_revenue=summary_revenue,
    )
    summary_payload["iventas"] = summary_iventas

    quality_limitations = list(FIXED_LIMITATIONS)
    quality_limitations.extend(
        visit_result.limitations
    )
    quality_limitations.extend(
        sales_result.limitations
    )
    if not iventas_available:
        quality_limitations.append(
            "No existe un sync canónico iVentas para el periodo; "
            "los leads y métricas dependientes no están disponibles."
        )

    return {
        "month": month_start.strftime("%Y-%m"),
        "cohort_mode": "visit_month",
        "scope": scope,
        "permissions": {
            "can_edit_inputs": access.can_edit_inputs,
        },
        "summary": summary_payload,
        "branches": branch_payloads,
        "data_quality": {
            "lead_mode": (
                "iventas_canonical_first_message_meta_ad"
            ),
            "sales_attribution_mode": (
                "exact_phone_same_branch_30d"
            ),
            "individual_lead_attribution": False,
            "cohort_complete": (
                normalized_today
                >= attribution_window_end
            ),
            "eligible_visit_events": (
                visit_result.eligible_visit_events
            ),
            "unique_visitors": count_unique_visitors(
                visit_result.events
            ),
            "visit_events_with_valid_phone": (
                visit_result.visit_events_with_valid_phone
            ),
            "visit_events_without_valid_phone": (
                visit_result.visit_events_without_valid_phone
            ),
            "visit_phone_coverage_rate": _serialize_ratio(
                safe_divide(
                    visit_result.visit_events_with_valid_phone,
                    visit_result.eligible_visit_events,
                )
            ),
            "limitations": quality_limitations,
        },
    }


def build_marketing_attribution_detail(
    *,
    month: str,
    access: MarketingAccess,
    sucursal_id: int | None = None,
) -> dict[str, Any]:
    month_start = parse_month(month)
    month_end = _month_end(month_start)
    attribution_window_end = month_end + timedelta(days=30)

    (
        visible_branches,
        visible_branch_ids,
        scope,
    ) = load_visible_marketing_branches(access)

    selected_branch_ids = visible_branch_ids
    selected_branches = visible_branches

    if sucursal_id is not None:
        if sucursal_id not in set(visible_branch_ids):
            raise MarketingAuthorizationError(
                "La sucursal está fuera del alcance autorizado."
            )

        selected_branch_ids = (sucursal_id,)
        selected_branches = [
            branch
            for branch in visible_branches
            if branch.sucursal_id == sucursal_id
        ]

    visit_result = _load_visit_events(
        month_start=month_start,
        branch_ids=selected_branch_ids,
    )
    sales_result = _load_sales(
        window_start=month_start,
        window_end=attribution_window_end,
        branch_ids=selected_branch_ids,
    )
    attributions = reconcile_visit_sales(
        visits=visit_result.events,
        sales=sales_result.sales,
    )

    branch_names = {
        branch.sucursal_id: branch.name
        for branch in selected_branches
    }
    branch_order = {
        branch.sucursal_id: branch.display_order
        for branch in selected_branches
    }

    attributions.sort(
        key=lambda attribution: (
            branch_order.get(
                attribution.visit.branch_id,
                999999,
            ),
            attribution.visit.visit_date,
            attribution.sale.payment_date,
            attribution.sale.sale_key,
        )
    )

    classified_attributions = [
        (
            attribution,
            _classify_attributed_sale(
                attribution.sale
            ),
        )
        for attribution in attributions
    ]

    total_revenue = sum(
        (
            attribution.sale.revenue
            for attribution, _
            in classified_attributions
        ),
        Decimal("0"),
    )

    review_sales = sum(
        1
        for _, classification
        in classified_attributions
        if classification
        == ATTRIBUTION_CLASS_REVIEW
    )

    family_plan_additional_members = sum(
        1
        for _, classification
        in classified_attributions
        if classification
        == ATTRIBUTION_CLASS_FAMILY_ADDITIONAL
    )

    return {
        "month": month_start.strftime("%Y-%m"),
        "cohort_mode": "visit_month",
        "scope": scope,
        "filters": {
            "sucursal_id": sucursal_id,
        },
        "summary": {
            "sales": len(attributions),
            "sales_revenue": float(total_revenue),
            "review_sales": review_sales,
            "non_positive_sales": review_sales,
            "family_plan_additional_members": (
                family_plan_additional_members
            ),
        },
        "source": {
            "visit_snapshot_id": visit_result.snapshot_id,
            "sales_snapshot_ids": sales_result.snapshot_ids,
        },
        "rows": [
            {
                "sucursal_id": attribution.visit.branch_id,
                "sucursal": branch_names.get(
                    attribution.visit.branch_id,
                    str(attribution.visit.branch_id),
                ),
                "sale_key": attribution.sale.sale_key,
                "id_socio": attribution.sale.member_id,
                "id_folio": attribution.sale.folio,
                "socio": attribution.sale.member_name,
                "telefono": _mask_phone(
                    attribution.sale.phone
                ),
                "fecha_visita": (
                    attribution.visit.visit_date.isoformat()
                ),
                "fecha_pago": (
                    attribution.sale.payment_date.isoformat()
                ),
                "dias_a_venta": (
                    attribution.sale.payment_date
                    - attribution.visit.visit_date
                ).days,
                "tipo_visita": attribution.visit.description,
                "tipo_membresia": (
                    attribution.sale.membership_type
                ),
                "tarifa": attribution.sale.tariff,
                "inscripcion": attribution.sale.registration,
                "pase": attribution.sale.pass_name,
                "lugar_pago": attribution.sale.payment_place,
                "total": (
                    float(attribution.sale.listed_total)
                    if attribution.sale.listed_total is not None
                    else None
                ),
                "total_pagado": float(
                    attribution.sale.revenue
                ),
                "attribution_classification": (
                    classification
                ),
                "amount_assigned_to_primary_member": (
                    classification
                    == ATTRIBUTION_CLASS_FAMILY_ADDITIONAL
                ),
                "venta_sin_ingreso_positivo": (
                    classification
                    == ATTRIBUTION_CLASS_REVIEW
                ),
                "snapshot_id": attribution.sale.snapshot_id,
                "source_row_id": (
                    attribution.sale.source_row_id
                ),
            }
            for attribution, classification
            in classified_attributions
        ],
    }
