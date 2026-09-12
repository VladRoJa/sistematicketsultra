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
from app.services.marketing_dashboard_service import (
    load_visible_marketing_branches,
)
from app.services.marketing_inputs_service import parse_month
from app.services.marketing_iventas_dashboard_data_service import (
    read_iventas_dashboard_month_data,
)
from app.services.marketing_phone import normalize_phone


MATCH_WINDOW_DAYS = 30
VALID_VENTA_TOTAL_STATUSES = frozenset({"ACTIVO", "FACTURADO"})
ELIGIBLE_VISIT_DESCRIPTIONS = frozenset(
    {
        "PASE 2 DIAS GRATIS",
        "PASE RECORRIDO",
    }
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

ORIGIN_DISPLAY_ORDER = (
    ORIGIN_IVENTAS_META,
    ORIGIN_IVENTAS_OTHER,
    ORIGIN_SOCIAL_UNTRACED,
    ORIGIN_REFERRAL,
    ORIGIN_PROXIMITY,
    ORIGIN_PLAZA,
    ORIGIN_OFFLINE,
    ORIGIN_OTHER_SURVEY,
    ORIGIN_UNKNOWN,
)


@dataclass(frozen=True)
class _IventasEvidence:
    branch_id: int
    phone: str
    created_date: date
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


def _is_visit_row(row: Any) -> bool:
    description = _normalize_text(getattr(row, "descripcion", None))
    if description in ELIGIBLE_VISIT_DESCRIPTIONS:
        return True
    return _normalize_text(getattr(row, "tipo", None)) == "PASE"


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
    *,
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


def _visit_event_key(
    *,
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

    raw_phone = phone or _normalize_text(row.telefono) or "SIN_TELEFONO"
    return (
        f"fallback:{branch_id}:{visit_date.isoformat()}:"
        f"{raw_phone}:{_normalize_text(row.descripcion)}"
    )


def _build_visit_population(
    *,
    rows: list[VentaTotalSnapshotRowORM],
    month_start: date,
    branch_ids: tuple[int, ...],
    alias_map: dict[str, int],
) -> list[_CommercialVisit]:
    allowed_branch_ids = set(branch_ids)
    unique_events: dict[str, _CommercialVisit] = {}

    for row in rows:
        if not _is_valid_status(row.estatus):
            continue

        description = _normalize_text(row.descripcion)
        if description not in ELIGIBLE_VISIT_DESCRIPTIONS:
            continue

        try:
            visit_date = _parse_row_date(row.fecha)
            total = _to_decimal(row.total)
        except ValueError:
            continue

        if visit_date.replace(day=1) != month_start or total != 0:
            continue

        branch_id = alias_map.get(_normalize_text(row.sucursal))
        if branch_id is None or branch_id not in allowed_branch_ids:
            continue

        phone = normalize_phone(row.telefono)
        event_key = _visit_event_key(
            row=row,
            branch_id=branch_id,
            visit_date=visit_date,
            phone=phone,
        )
        unique_events.setdefault(
            event_key,
            _CommercialVisit(
                event_key=event_key,
                branch_id=branch_id,
                visit_date=visit_date,
                phone=phone,
            ),
        )

    return list(unique_events.values())


def _sale_identity(
    *,
    row: VentaTotalSnapshotRowORM,
    branch_id: int,
) -> str:
    pin = str(row.pin or "").strip()
    if pin:
        return f"pin:{branch_id}:{pin}"

    id_orden = str(row.id_orden or "").strip()
    if id_orden:
        return f"id_orden:{branch_id}:{id_orden}"

    folio = str(row.folio or "").strip()
    if folio:
        return f"folio:{branch_id}:{folio}"

    return f"row:{branch_id}:{row.id}"


def _build_new_sale_population(
    *,
    rows: list[VentaTotalSnapshotRowORM],
    month_start: date,
    branch_ids: tuple[int, ...],
    alias_map: dict[str, int],
) -> list[_CommercialSale]:
    allowed_branch_ids = set(branch_ids)
    all_rows_by_identity: dict[
        str,
        list[tuple[VentaTotalSnapshotRowORM, date]],
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
        if branch_id is None or branch_id not in allowed_branch_ids:
            continue

        identity = _sale_identity(row=row, branch_id=branch_id)
        all_rows_by_identity[identity].append((row, row_date))

        if (
            _is_new_flag(row.nuevo)
            and _is_membership_row(row)
            and not _is_visit_row(row)
        ):
            candidate_keys.add(identity)

    result: list[_CommercialSale] = []

    for identity in sorted(candidate_keys):
        grouped_rows = all_rows_by_identity.get(identity, [])
        if not grouped_rows:
            continue

        candidate_rows = [
            (row, row_date)
            for row, row_date in grouped_rows
            if _is_new_flag(row.nuevo)
            and _is_membership_row(row)
            and not _is_visit_row(row)
        ]
        if not candidate_rows:
            continue

        candidate_rows.sort(
            key=lambda pair: (
                pair[1],
                int(pair[0].row_index or 0),
            )
        )
        primary_row, sale_date = candidate_rows[0]
        branch_id = alias_map[_normalize_text(primary_row.sucursal)]

        phone = None
        for row, _ in candidate_rows + grouped_rows:
            phone = normalize_phone(row.telefono)
            if phone is not None:
                break

        survey_raw = next(
            (
                str(row.encuesta).strip()
                for row, _ in candidate_rows + grouped_rows
                if str(row.encuesta or "").strip()
            ),
            None,
        )

        revenue = sum(
            (_to_decimal(row.total) for row, _ in grouped_rows),
            Decimal("0"),
        )

        result.append(
            _CommercialSale(
                sale_key=identity,
                branch_id=branch_id,
                sale_date=sale_date,
                phone=phone,
                revenue=revenue,
                survey_raw=survey_raw,
            )
        )

    return result


def _load_iventas_evidence(
    *,
    month_start: date,
    branch_ids: tuple[int, ...],
) -> tuple[
    dict[tuple[int, str], list[_IventasEvidence]],
    tuple[int, ...],
]:
    lookback_start = month_start - timedelta(days=MATCH_WINDOW_DAYS)
    month_end = _month_end(month_start)

    runs = (
        MarketingIventasSyncRunORM.query.filter(
            MarketingIventasSyncRunORM.status == "COMPLETED",
            MarketingIventasSyncRunORM.is_canonical.is_(True),
            MarketingIventasSyncRunORM.date_to >= lookback_start,
            MarketingIventasSyncRunORM.date_from <= month_end,
        )
        .order_by(MarketingIventasSyncRunORM.date_from.asc())
        .all()
    )
    run_ids = tuple(int(run.id) for run in runs)
    if not run_ids:
        return {}, ()

    contacts = (
        MarketingIventasContactORM.query.filter(
            MarketingIventasContactORM.sync_run_id.in_(run_ids),
            MarketingIventasContactORM.sucursal_id.in_(branch_ids),
            MarketingIventasContactORM.first_message_at_utc.isnot(None),
            MarketingIventasContactORM.phone_mx10.isnot(None),
            MarketingIventasContactORM.created_date_local >= lookback_start,
            MarketingIventasContactORM.created_date_local <= month_end,
        )
        .all()
    )

    meta_rows = (
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
    meta_contact_keys = {
        (int(sync_run_id), int(contact_row_id))
        for sync_run_id, contact_row_id in meta_rows
    }

    evidence_by_identity: dict[
        tuple[int, str],
        list[_IventasEvidence],
    ] = defaultdict(list)

    for contact in contacts:
        phone = str(contact.phone_mx10 or "").strip()
        if not phone:
            continue

        evidence_by_identity[
            (int(contact.sucursal_id), phone)
        ].append(
            _IventasEvidence(
                branch_id=int(contact.sucursal_id),
                phone=phone,
                created_date=contact.created_date_local,
                has_meta_ad=(
                    (int(contact.sync_run_id), int(contact.id))
                    in meta_contact_keys
                ),
            )
        )

    for values in evidence_by_identity.values():
        values.sort(
            key=lambda item: (
                item.created_date,
                item.has_meta_ad,
            )
        )

    return evidence_by_identity, run_ids


def _match_iventas_origin(
    *,
    evidence_by_identity: dict[
        tuple[int, str],
        list[_IventasEvidence],
    ],
    branch_id: int,
    phone: str | None,
    target_date: date,
) -> str | None:
    if phone is None:
        return None

    window_start = target_date - timedelta(days=MATCH_WINDOW_DAYS)
    candidates = [
        item
        for item in evidence_by_identity.get((branch_id, phone), [])
        if window_start <= item.created_date <= target_date
    ]
    if not candidates:
        return None

    latest_date = max(item.created_date for item in candidates)
    latest_candidates = [
        item
        for item in candidates
        if item.created_date == latest_date
    ]
    if any(item.has_meta_ad for item in latest_candidates):
        return ORIGIN_IVENTAS_META
    return ORIGIN_IVENTAS_OTHER


def _unique_visitors(
    events: list[_CommercialVisit],
) -> list[_CommercialVisit]:
    with_phone: dict[tuple[int, str], _CommercialVisit] = {}
    without_phone: dict[str, _CommercialVisit] = {}

    for event in sorted(
        events,
        key=lambda item: (
            item.visit_date,
            item.branch_id,
            item.phone or "",
            item.event_key,
        ),
    ):
        if event.phone is None:
            without_phone.setdefault(event.event_key, event)
            continue
        with_phone.setdefault((event.branch_id, event.phone), event)

    return [*with_phone.values(), *without_phone.values()]


def _serialize_origin_breakdown(
    stats: _BranchStats,
) -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": ORIGIN_LABELS[key],
            "sales": int(stats.origin_counts.get(key, 0)),
            "revenue": float(stats.origin_revenue.get(key, Decimal("0"))),
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
    for field_name in (
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
    ):
        setattr(
            target,
            field_name,
            getattr(target, field_name) + getattr(source, field_name),
        )

    for field_name in (
        "revenue_total",
        "revenue_iventas",
        "revenue_iventas_meta",
        "revenue_iventas_other",
        "revenue_not_iventas",
    ):
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
    branch_names = {
        branch.sucursal_id: branch.name
        for branch in branches
    }

    stats_by_branch = {
        branch_id: _BranchStats()
        for branch_id in branch_ids
    }
    limitations: list[str] = []

    iventas_data = read_iventas_dashboard_month_data(
        month_date=month_start,
    )
    if iventas_data.available:
        for row in iventas_data.branch_metrics or ():
            branch_id = int(row.sucursal_id)
            if branch_id not in stats_by_branch:
                continue
            stats_by_branch[branch_id].iventas_contacts = int(
                row.iventas_contacts_with_first_message
            )
            stats_by_branch[branch_id].leads_meta = int(
                row.meta_observed_leads
            )
    else:
        limitations.append(
            "No existe snapshot canónico iVentas para el periodo; "
            "los cruces iVentas y Meta pueden quedar incompletos."
        )

    snapshot = _select_venta_total_snapshot(month_start=month_start)
    if snapshot is None:
        return {
            "month": month_start.strftime("%Y-%m"),
            "scope": scope,
            "summary": _serialize_stats(_BranchStats()),
            "branches": [
                {
                    "sucursal_id": branch.sucursal_id,
                    "sucursal": branch.name,
                    **_serialize_stats(stats_by_branch[branch.sucursal_id]),
                }
                for branch in branches
            ],
            "source": {
                "venta_total_snapshot_id": None,
                "venta_total_business_date": None,
                "iventas_sync_run_ids": [],
                "match_window_days": MATCH_WINDOW_DAYS,
            },
            "data_quality": {
                "venta_total_available": False,
                "iventas_available": bool(iventas_data.available),
                "new_sale_rule": (
                    "Nuevo=SI + Clave Producto=MEMBRESIA + "
                    "Estatus ACTIVO/FACTURADO"
                ),
                "match_mode": "exact_phone_same_branch_prior_30d",
                "survey_fallback_only_after_no_iventas_match": True,
                "limitations": [
                    *limitations,
                    "No existe snapshot canónico de Venta Total para el mes.",
                ],
            },
        }

    rows = (
        VentaTotalSnapshotRowORM.query.filter_by(snapshot_id=snapshot.id)
        .order_by(VentaTotalSnapshotRowORM.row_index.asc())
        .all()
    )
    alias_map = _load_branch_alias_map()
    visits = _unique_visitors(
        _build_visit_population(
            rows=rows,
            month_start=month_start,
            branch_ids=branch_ids,
            alias_map=alias_map,
        )
    )
    sales = _build_new_sale_population(
        rows=rows,
        month_start=month_start,
        branch_ids=branch_ids,
        alias_map=alias_map,
    )
    evidence_by_identity, iventas_run_ids = _load_iventas_evidence(
        month_start=month_start,
        branch_ids=branch_ids,
    )

    if not iventas_run_ids:
        limitations.append(
            "No hay runs canónicos iVentas suficientes para la ventana "
            "de cruce de 30 días."
        )

    for visit in visits:
        stats = stats_by_branch[visit.branch_id]
        stats.visits_total += 1

        if visit.phone is None:
            stats.visits_unmatchable += 1
            continue

        origin = _match_iventas_origin(
            evidence_by_identity=evidence_by_identity,
            branch_id=visit.branch_id,
            phone=visit.phone,
            target_date=visit.visit_date,
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

        origin = _match_iventas_origin(
            evidence_by_identity=evidence_by_identity,
            branch_id=sale.branch_id,
            phone=sale.phone,
            target_date=sale.sale_date,
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

    total_stats = _BranchStats()
    branch_payloads: list[dict[str, Any]] = []

    for branch in branches:
        stats = stats_by_branch[branch.sucursal_id]
        _merge_stats(total_stats, stats)
        branch_payloads.append(
            {
                "sucursal_id": branch.sucursal_id,
                "sucursal": branch_names[branch.sucursal_id],
                **_serialize_stats(stats),
            }
        )

    limitations.append(
        "Los tags Meta de iVentas representan el estado observado en el "
        "snapshot; una corrección posterior de iVentas puede cambiar la "
        "clasificación Meta sin cambiar la venta de Venta Total."
    )

    return {
        "month": month_start.strftime("%Y-%m"),
        "scope": scope,
        "summary": _serialize_stats(total_stats),
        "branches": branch_payloads,
        "source": {
            "venta_total_snapshot_id": int(snapshot.id),
            "venta_total_business_date": snapshot.business_date.isoformat(),
            "iventas_sync_run_ids": list(iventas_run_ids),
            "match_window_days": MATCH_WINDOW_DAYS,
        },
        "data_quality": {
            "venta_total_available": True,
            "iventas_available": bool(iventas_data.available),
            "new_sale_rule": (
                "Nuevo=SI + Clave Producto=MEMBRESIA + "
                "Estatus ACTIVO/FACTURADO"
            ),
            "match_mode": "exact_phone_same_branch_prior_30d",
            "survey_fallback_only_after_no_iventas_match": True,
            "limitations": limitations,
        },
    }
