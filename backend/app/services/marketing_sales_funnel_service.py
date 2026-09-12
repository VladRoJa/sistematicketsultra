from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
import unicodedata

from app.extensions import db
from app.models import (
    MarketingIventasContactORM,
    MarketingIventasContactTagORM,
    MarketingIventasSyncRunORM,
)
from app.models.warehouse import (
    TrackBranchAliasORM,
    TrackBranchCatalogORM,
    VentaTotalSnapshotORM,
    VentaTotalSnapshotRowORM,
)
from app.services.marketing_access import MarketingAccess
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.services.marketing_inputs_service import parse_month
from app.services.marketing_phone import normalize_phone


MATCH_WINDOW_DAYS = 30
VALID_VENTA_TOTAL_STATUSES = frozenset({"ACTIVO", "FACTURADO"})
ELIGIBLE_VISIT_DESCRIPTIONS = frozenset(
    {"PASE 2 DIAS GRATIS", "PASE RECORRIDO"}
)

ORIGIN_IVENTAS_META = "IVENTAS_META"
ORIGIN_IVENTAS_OTHER = "IVENTAS_OTHER"
ORIGIN_SOCIAL_UNTRACED = "SOCIAL_UNTRACED"
ORIGIN_REFERRAL = "REFERRAL"
ORIGIN_PROXIMITY = "PROXIMITY"
ORIGIN_PLAZA = "PLAZA"
ORIGIN_OFFLINE = "OFFLINE"
ORIGIN_OTHER_SURVEY = "OTHER_SURVEY"
ORIGIN_UNKNOWN = "UNKNOWN"

ORIGIN_LABELS = {
    ORIGIN_IVENTAS_META: "iVentas / Meta Ads",
    ORIGIN_IVENTAS_OTHER: "iVentas / Otro",
    ORIGIN_SOCIAL_UNTRACED: "Redes sociales no trazadas",
    ORIGIN_REFERRAL: "Familiares o amigos",
    ORIGIN_PROXIMITY: "Cerca de domicilio/trabajo",
    ORIGIN_PLAZA: "Visita a plaza comercial",
    ORIGIN_OFFLINE: "Volantes / offline",
    ORIGIN_OTHER_SURVEY: "Encuesta: otro",
    ORIGIN_UNKNOWN: "Sin identificar",
}

ORIGIN_DISPLAY_ORDER = tuple(ORIGIN_LABELS.keys())


@dataclass(frozen=True)
class _IventasEvidence:
    branch_id: int
    phone: str
    interaction_date: date
    has_meta_ad: bool


@dataclass(frozen=True)
class _CommercialVisit:
    event_key: str
    branch_id: int
    visit_date: date
    phone: str | None


@dataclass(frozen=True)
class _CommercialSale:
    sale_key: str
    branch_id: int
    sale_date: date
    phone: str | None
    revenue: Decimal
    survey_raw: str | None


@dataclass
class _BranchStats:
    iventas_contacts: int = 0
    leads_meta: int = 0

    visits_total: int = 0
    visits_iventas: int = 0
    visits_iventas_meta: int = 0
    visits_iventas_other: int = 0
    visits_not_iventas: int = 0
    visits_unmatchable: int = 0

    sales_total: int = 0
    sales_iventas: int = 0
    sales_iventas_meta: int = 0
    sales_iventas_other: int = 0
    sales_not_iventas: int = 0
    sales_without_valid_phone: int = 0

    revenue_total: Decimal = Decimal("0")
    revenue_iventas: Decimal = Decimal("0")
    revenue_iventas_meta: Decimal = Decimal("0")
    revenue_iventas_other: Decimal = Decimal("0")
    revenue_not_iventas: Decimal = Decimal("0")

    origin_counts: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    origin_revenue: dict[str, Decimal] = field(
        default_factory=lambda: defaultdict(lambda: Decimal("0"))
    )


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().upper()
    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
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


def _month_end(month_start: date) -> date:
    return date(
        month_start.year,
        month_start.month,
        monthrange(month_start.year, month_start.month)[1],
    )


def _parse_row_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
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
            return datetime.strptime(raw_value, date_format).date()
        except ValueError:
            continue

    raise ValueError(
        f"No se pudo interpretar fecha Venta Total: {value!r}"
    )


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return float(Decimal(numerator) / Decimal(denominator))


def _is_valid_status(value: Any) -> bool:
    return _normalize_text(value) in VALID_VENTA_TOTAL_STATUSES


def _is_new_flag(value: Any) -> bool:
    return _normalize_text(value) in {"SI", "TRUE", "1", "YES"}


def _is_membership_row(row: Any) -> bool:
    return _normalize_text(getattr(row, "clave_producto", None)) == "MEMBRESIA"


def _classify_survey(value: Any) -> str:
    normalized = _normalize_text(value)

    if not normalized:
        return ORIGIN_UNKNOWN
    if normalized == "REDES SOCIALES":
        return ORIGIN_SOCIAL_UNTRACED
    if normalized == "FAMILIARES O AMIGOS":
        return ORIGIN_REFERRAL
    if normalized == "CERCA DE DOMICILIO/TRABAJO":
        return ORIGIN_PROXIMITY
    if normalized == "VISITA A PLAZA COMERCIAL":
        return ORIGIN_PLAZA
    if normalized == "VOLANTES":
        return ORIGIN_OFFLINE
    return ORIGIN_OTHER_SURVEY


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
            TrackBranchAliasORM.source_family == "gasca_family",
            TrackBranchAliasORM.is_active.is_(True),
            TrackBranchCatalogORM.is_track_active.is_(True),
            TrackBranchCatalogORM.sucursal_id.isnot(None),
        )
        .all()
    )

    return {
        _normalize_text(alias.raw_branch_name): int(catalog.sucursal_id)
        for alias, catalog in rows
    }


def _select_venta_total_snapshot(
    month_start: date,
) -> VentaTotalSnapshotORM | None:
    return (
        VentaTotalSnapshotORM.query.filter(
            VentaTotalSnapshotORM.report_type_key == "venta_total",
            VentaTotalSnapshotORM.business_date >= month_start,
            VentaTotalSnapshotORM.business_date <= _month_end(month_start),
            VentaTotalSnapshotORM.snapshot_kind == "daily",
            VentaTotalSnapshotORM.is_canonical.is_(True),
        )
        .order_by(
            VentaTotalSnapshotORM.business_date.desc(),
            VentaTotalSnapshotORM.id.desc(),
        )
        .first()
    )


def _visit_key(
    row: VentaTotalSnapshotRowORM,
    branch_id: int,
    visit_date: date,
    phone: str | None,
) -> str:
    id_orden = str(row.id_orden or "").strip()
    if id_orden:
        return f"id_orden:{branch_id}:{id_orden}"

    folio = str(row.folio or "").strip()
    if folio:
        return f"folio:{branch_id}:{folio}"

    return (
        f"fallback:{branch_id}:{visit_date.isoformat()}:"
        f"{phone or _normalize_text(row.telefono) or 'SIN_TELEFONO'}:"
        f"{_normalize_text(row.descripcion)}"
    )


def _load_visits(
    rows: list[VentaTotalSnapshotRowORM],
    month_start: date,
    branch_ids: tuple[int, ...],
    alias_map: dict[str, int],
) -> list[_CommercialVisit]:
    allowed = set(branch_ids)
    events: dict[str, _CommercialVisit] = {}

    for row in rows:
        if not _is_valid_status(row.estatus):
            continue
        if _normalize_text(row.descripcion) not in ELIGIBLE_VISIT_DESCRIPTIONS:
            continue

        try:
            visit_date = _parse_row_date(row.fecha)
            total = _to_decimal(row.total)
        except ValueError:
            continue

        if visit_date.replace(day=1) != month_start or total != 0:
            continue

        branch_id = alias_map.get(_normalize_text(row.sucursal))
        if branch_id is None or branch_id not in allowed:
            continue

        phone = normalize_phone(row.telefono)
        key = _visit_key(row, branch_id, visit_date, phone)
        events.setdefault(
            key,
            _CommercialVisit(key, branch_id, visit_date, phone),
        )

    with_phone: dict[tuple[int, str], _CommercialVisit] = {}
    without_phone: dict[str, _CommercialVisit] = {}

    for event in sorted(
        events.values(),
        key=lambda item: (
            item.visit_date,
            item.branch_id,
            item.phone or "",
            item.event_key,
        ),
    ):
        if event.phone is None:
            without_phone.setdefault(event.event_key, event)
        else:
            with_phone.setdefault((event.branch_id, event.phone), event)

    return [*with_phone.values(), *without_phone.values()]


def _sale_key(
    row: VentaTotalSnapshotRowORM,
    branch_id: int,
) -> str:
    id_orden = str(row.id_orden or "").strip()
    if id_orden:
        return f"id_orden:{branch_id}:{id_orden}"

    folio = str(row.folio or "").strip()
    if folio:
        return f"folio:{branch_id}:{folio}"

    pin = str(row.pin or "").strip()
    if pin:
        return f"pin:{branch_id}:{pin}"

    return f"row:{branch_id}:{row.id}"


def _load_new_sales(
    rows: list[VentaTotalSnapshotRowORM],
    month_start: date,
    branch_ids: tuple[int, ...],
    alias_map: dict[str, int],
) -> list[_CommercialSale]:
    allowed = set(branch_ids)
    grouped: dict[
        str,
        list[tuple[VentaTotalSnapshotRowORM, date, int]],
    ] = defaultdict(list)
    candidate_keys: set[str] = set()

    for row in rows:
        if not _is_valid_status(row.estatus):
            continue

        try:
            row_date = _parse_row_date(row.fecha)
        except ValueError:
            continue
        if row_date.replace(day=1) != month_start:
            continue

        branch_id = alias_map.get(_normalize_text(row.sucursal))
        if branch_id is None or branch_id not in allowed:
            continue

        key = _sale_key(row, branch_id)
        grouped[key].append((row, row_date, branch_id))

        if _is_new_flag(row.nuevo) and _is_membership_row(row):
            candidate_keys.add(key)

    result: list[_CommercialSale] = []

    for key in sorted(candidate_keys):
        group = grouped[key]
        membership_rows = [
            item
            for item in group
            if _is_new_flag(item[0].nuevo)
            and _is_membership_row(item[0])
        ]
        if not membership_rows:
            continue

        membership_rows.sort(
            key=lambda item: (item[1], int(item[0].row_index or 0))
        )
        primary_row, sale_date, branch_id = membership_rows[0]

        phone = next(
            (
                normalized
                for row, _, _ in [*membership_rows, *group]
                if (normalized := normalize_phone(row.telefono)) is not None
            ),
            None,
        )
        survey_raw = next(
            (
                str(row.encuesta).strip()
                for row, _, _ in [*membership_rows, *group]
                if str(row.encuesta or "").strip()
            ),
            None,
        )
        revenue = sum(
            (_to_decimal(row.total) for row, _, _ in group),
            Decimal("0"),
        )

        result.append(
            _CommercialSale(
                key,
                branch_id,
                sale_date,
                phone,
                revenue,
                survey_raw,
            )
        )

    return result


def _canonical_runs_for_window(
    window_start: date,
    window_end: date,
) -> list[MarketingIventasSyncRunORM]:
    return (
        MarketingIventasSyncRunORM.query.filter(
            MarketingIventasSyncRunORM.status == "COMPLETED",
            MarketingIventasSyncRunORM.is_canonical.is_(True),
            MarketingIventasSyncRunORM.date_to >= window_start,
            MarketingIventasSyncRunORM.date_from <= window_end,
        )
        .order_by(MarketingIventasSyncRunORM.date_from.asc())
        .all()
    )


def _meta_contact_keys(
    run_ids: tuple[int, ...],
) -> set[tuple[int, int]]:
    if not run_ids:
        return set()

    rows = (
        db.session.query(
            MarketingIventasContactTagORM.sync_run_id,
            MarketingIventasContactTagORM.iventas_contact_row_id,
        )
        .filter(
            MarketingIventasContactTagORM.sync_run_id.in_(run_ids),
            MarketingIventasContactTagORM.tag_kind == "META_AD",
        )
        .all()
    )
    return {
        (int(sync_run_id), int(contact_row_id))
        for sync_run_id, contact_row_id in rows
    }


def _load_iventas_data(
    month_start: date,
    branch_ids: tuple[int, ...],
) -> tuple[
    dict[tuple[int, str], list[_IventasEvidence]],
    dict[int, tuple[int, int]],
    tuple[int, ...],
]:
    month_end = _month_end(month_start)
    lookback_start = month_start - timedelta(days=MATCH_WINDOW_DAYS)
    runs = _canonical_runs_for_window(lookback_start, month_end)
    run_ids = tuple(int(run.id) for run in runs)
    meta_keys = _meta_contact_keys(run_ids)

    evidence: dict[tuple[int, str], list[_IventasEvidence]] = defaultdict(list)
    month_counts: dict[int, list[int]] = {
        branch_id: [0, 0]
        for branch_id in branch_ids
    }

    if not run_ids:
        return evidence, {}, run_ids

    contacts = (
        MarketingIventasContactORM.query.filter(
            MarketingIventasContactORM.sync_run_id.in_(run_ids),
            MarketingIventasContactORM.sucursal_id.in_(branch_ids),
            MarketingIventasContactORM.first_message_at_utc.isnot(None),
            MarketingIventasContactORM.phone_mx10.isnot(None),
        )
        .all()
    )

    current_period_key = f"IVENTAS-{month_start.strftime('%Y-%m')}"
    current_run_ids = {
        int(run.id)
        for run in runs
        if str(run.period_key) == current_period_key
    }

    for contact in contacts:
        branch_id = int(contact.sucursal_id)
        phone = str(contact.phone_mx10 or "").strip()
        interaction_date = contact.first_message_date_local
        if not phone or interaction_date is None:
            continue

        has_meta = (
            (int(contact.sync_run_id), int(contact.id)) in meta_keys
        )
        if lookback_start <= interaction_date <= month_end:
            evidence[(branch_id, phone)].append(
                _IventasEvidence(
                    branch_id,
                    phone,
                    interaction_date,
                    has_meta,
                )
            )

        if int(contact.sync_run_id) in current_run_ids:
            month_counts[branch_id][0] += 1
            if has_meta:
                month_counts[branch_id][1] += 1

    for items in evidence.values():
        items.sort(
            key=lambda item: (item.interaction_date, item.has_meta_ad)
        )

    return (
        evidence,
        {
            branch_id: (counts[0], counts[1])
            for branch_id, counts in month_counts.items()
        },
        run_ids,
    )


def _match_iventas(
    evidence: dict[tuple[int, str], list[_IventasEvidence]],
    branch_id: int,
    phone: str | None,
    target_date: date,
) -> str | None:
    if phone is None:
        return None

    window_start = target_date - timedelta(days=MATCH_WINDOW_DAYS)
    candidates = [
        item
        for item in evidence.get((branch_id, phone), [])
        if window_start <= item.interaction_date <= target_date
    ]
    if not candidates:
        return None

    latest_date = max(item.interaction_date for item in candidates)
    latest = [
        item for item in candidates if item.interaction_date == latest_date
    ]
    if any(item.has_meta_ad for item in latest):
        return ORIGIN_IVENTAS_META
    return ORIGIN_IVENTAS_OTHER


def _serialize_origin_breakdown(
    stats: _BranchStats,
) -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": ORIGIN_LABELS[key],
            "sales": int(stats.origin_counts.get(key, 0)),
            "revenue": float(
                stats.origin_revenue.get(key, Decimal("0"))
            ),
        }
        for key in ORIGIN_DISPLAY_ORDER
    ]


def _serialize_stats(stats: _BranchStats) -> dict[str, Any]:
    return {
        "iventas_contacts": stats.iventas_contacts,
        "leads_meta": stats.leads_meta,
        "visits_total": stats.visits_total,
        "visits_iventas": stats.visits_iventas,
        "visits_iventas_meta": stats.visits_iventas_meta,
        "visits_iventas_other": stats.visits_iventas_other,
        "visits_not_iventas": stats.visits_not_iventas,
        "visits_unmatchable": stats.visits_unmatchable,
        "sales_total": stats.sales_total,
        "sales_iventas": stats.sales_iventas,
        "sales_iventas_meta": stats.sales_iventas_meta,
        "sales_iventas_other": stats.sales_iventas_other,
        "sales_not_iventas": stats.sales_not_iventas,
        "sales_without_valid_phone": stats.sales_without_valid_phone,
        "revenue_total": float(stats.revenue_total),
        "revenue_iventas": float(stats.revenue_iventas),
        "revenue_iventas_meta": float(stats.revenue_iventas_meta),
        "revenue_iventas_other": float(stats.revenue_iventas_other),
        "revenue_not_iventas": float(stats.revenue_not_iventas),
        "meta_lead_to_visit_rate": _safe_ratio(
            stats.visits_iventas_meta,
            stats.leads_meta,
        ),
        "meta_visit_to_sale_rate": _safe_ratio(
            stats.sales_iventas_meta,
            stats.visits_iventas_meta,
        ),
        "meta_lead_to_sale_rate": _safe_ratio(
            stats.sales_iventas_meta,
            stats.leads_meta,
        ),
        "total_visit_to_sale_rate": _safe_ratio(
            stats.sales_total,
            stats.visits_total,
        ),
        "iventas_visit_share": _safe_ratio(
            stats.visits_iventas,
            stats.visits_total,
        ),
        "iventas_sale_share": _safe_ratio(
            stats.sales_iventas,
            stats.sales_total,
        ),
        "origin_breakdown": _serialize_origin_breakdown(stats),
    }


def _merge_stats(target: _BranchStats, source: _BranchStats) -> None:
    integer_fields = (
        "iventas_contacts",
        "leads_meta",
        "visits_total",
        "visits_iventas",
        "visits_iventas_meta",
        "visits_iventas_other",
        "visits_not_iventas",
        "visits_unmatchable",
        "sales_total",
        "sales_iventas",
        "sales_iventas_meta",
        "sales_iventas_other",
        "sales_not_iventas",
        "sales_without_valid_phone",
    )
    decimal_fields = (
        "revenue_total",
        "revenue_iventas",
        "revenue_iventas_meta",
        "revenue_iventas_other",
        "revenue_not_iventas",
    )

    for field_name in integer_fields:
        setattr(
            target,
            field_name,
            getattr(target, field_name) + getattr(source, field_name),
        )
    for field_name in decimal_fields:
        setattr(
            target,
            field_name,
            getattr(target, field_name) + getattr(source, field_name),
        )
    for key, value in source.origin_counts.items():
        target.origin_counts[key] += value
    for key, value in source.origin_revenue.items():
        target.origin_revenue[key] += value


def build_marketing_sales_funnel(
    *,
    month: str,
    access: MarketingAccess,
) -> dict[str, Any]:
    month_start = parse_month(month)
    branches, branch_ids, scope = load_visible_marketing_branches(access)
    stats_by_branch = {
        branch_id: _BranchStats()
        for branch_id in branch_ids
    }

    evidence, month_counts, iventas_run_ids = _load_iventas_data(
        month_start,
        branch_ids,
    )
    for branch_id, (contacts, leads_meta) in month_counts.items():
        stats_by_branch[branch_id].iventas_contacts = contacts
        stats_by_branch[branch_id].leads_meta = leads_meta

    limitations: list[str] = []
    if not iventas_run_ids:
        limitations.append(
            "No existen runs canónicos iVentas para la ventana de cruce."
        )

    snapshot = _select_venta_total_snapshot(month_start)
    if snapshot is None:
        limitations.append(
            "No existe snapshot canónico de Venta Total para el mes."
        )
        return _build_response(
            month_start=month_start,
            scope=scope,
            branches=branches,
            stats_by_branch=stats_by_branch,
            snapshot=None,
            iventas_run_ids=iventas_run_ids,
            limitations=limitations,
        )

    rows = (
        VentaTotalSnapshotRowORM.query.filter_by(snapshot_id=snapshot.id)
        .order_by(VentaTotalSnapshotRowORM.row_index.asc())
        .all()
    )
    alias_map = _load_branch_alias_map()
    visits = _load_visits(rows, month_start, branch_ids, alias_map)
    sales = _load_new_sales(rows, month_start, branch_ids, alias_map)

    for visit in visits:
        stats = stats_by_branch[visit.branch_id]
        stats.visits_total += 1

        if visit.phone is None:
            stats.visits_unmatchable += 1
            continue

        origin = _match_iventas(
            evidence,
            visit.branch_id,
            visit.phone,
            visit.visit_date,
        )
        if origin == ORIGIN_IVENTAS_META:
            stats.visits_iventas += 1
            stats.visits_iventas_meta += 1
        elif origin == ORIGIN_IVENTAS_OTHER:
            stats.visits_iventas += 1
            stats.visits_iventas_other += 1
        else:
            stats.visits_not_iventas += 1

    for sale in sales:
        stats = stats_by_branch[sale.branch_id]
        stats.sales_total += 1
        stats.revenue_total += sale.revenue

        if sale.phone is None:
            stats.sales_without_valid_phone += 1

        origin = _match_iventas(
            evidence,
            sale.branch_id,
            sale.phone,
            sale.sale_date,
        )
        if origin == ORIGIN_IVENTAS_META:
            stats.sales_iventas += 1
            stats.sales_iventas_meta += 1
            stats.revenue_iventas += sale.revenue
            stats.revenue_iventas_meta += sale.revenue
        elif origin == ORIGIN_IVENTAS_OTHER:
            stats.sales_iventas += 1
            stats.sales_iventas_other += 1
            stats.revenue_iventas += sale.revenue
            stats.revenue_iventas_other += sale.revenue
        else:
            origin = _classify_survey(sale.survey_raw)
            stats.sales_not_iventas += 1
            stats.revenue_not_iventas += sale.revenue

        stats.origin_counts[origin] += 1
        stats.origin_revenue[origin] += sale.revenue

    limitations.append(
        "Los tags Meta reflejan el estado observado por la API de iVentas; "
        "una corrección posterior puede reclasificar el origen Meta."
    )

    return _build_response(
        month_start=month_start,
        scope=scope,
        branches=branches,
        stats_by_branch=stats_by_branch,
        snapshot=snapshot,
        iventas_run_ids=iventas_run_ids,
        limitations=limitations,
    )


def _build_response(
    *,
    month_start: date,
    scope: dict[str, object],
    branches: list[Any],
    stats_by_branch: dict[int, _BranchStats],
    snapshot: VentaTotalSnapshotORM | None,
    iventas_run_ids: tuple[int, ...],
    limitations: list[str],
) -> dict[str, Any]:
    total_stats = _BranchStats()
    branch_payloads: list[dict[str, Any]] = []

    for branch in branches:
        stats = stats_by_branch[branch.sucursal_id]
        _merge_stats(total_stats, stats)
        branch_payloads.append(
            {
                "sucursal_id": branch.sucursal_id,
                "sucursal": branch.name,
                **_serialize_stats(stats),
            }
        )

    return {
        "month": month_start.strftime("%Y-%m"),
        "scope": scope,
        "summary": _serialize_stats(total_stats),
        "branches": branch_payloads,
        "source": {
            "venta_total_snapshot_id": (
                int(snapshot.id) if snapshot is not None else None
            ),
            "venta_total_business_date": (
                snapshot.business_date.isoformat()
                if snapshot is not None
                else None
            ),
            "iventas_sync_run_ids": list(iventas_run_ids),
            "match_window_days": MATCH_WINDOW_DAYS,
        },
        "data_quality": {
            "venta_total_available": snapshot is not None,
            "iventas_available": bool(iventas_run_ids),
            "new_sale_rule": (
                "Nuevo=SI + Clave Producto=MEMBRESIA + "
                "Estatus ACTIVO/FACTURADO"
            ),
            "match_mode": (
                "exact_phone_same_branch_first_message_prior_30d"
            ),
            "survey_fallback_only_after_no_iventas_match": True,
            "limitations": limitations,
        },
    }
