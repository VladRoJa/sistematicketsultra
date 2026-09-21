from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, Mapping

from app.extensions import db
from app.models import (
    MarketingIventasContactORM,
    MarketingIventasContactTagORM,
    MarketingIventasSyncRunORM,
    MarketingMetaSyncRunORM,
)
from app.models.warehouse import (
    KpiDesempenoSnapshotORM,
    VentaTotalSnapshotORM,
    VentaTotalSnapshotRowORM,
    VentasNuevosSociosDetalleSnapshotORM,
)
from app.services.marketing_access import MarketingAccess
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.services.marketing_inputs_service import (
    MarketingInputValidationError,
    parse_month,
)
from app.services.marketing_iventas_leads_service import (
    MarketingIventasLeadMetricsByBranchMonth,
    list_iventas_lead_metrics_by_branch_month_for_run,
)
from app.services.marketing_meta_dashboard_service import (
    MetaDashboardInvestmentData,
    _aggregate_campaign_investment,
    build_iventas_campaign_evidence_statement,
    build_meta_campaign_insights_statement,
    build_meta_month_period_key,
)
from app.services.marketing_sales_funnel_service import (
    MATCH_WINDOW_DAYS,
    ORIGIN_IVENTAS_META,
    ORIGIN_IVENTAS_OTHER,
    SALE_CATEGORY_DIGITAL,
    SALE_CATEGORY_DIGITAL_ORGANIC,
    SALE_CATEGORY_WEB,
    TIJUANA_TIMEZONE,
    MarketingSalesFunnelBuildResult,
    MarketingSalesFunnelLoadedData,
    _BranchStats,
    _IventasEvidence,
    _build_response,
    _classify_sale_category,
    _classify_survey,
    _load_branch_alias_map,
    _load_kpi_new_sales_control,
    _load_new_sales,
    _load_visits,
    _match_iventas,
    _month_end,
)


COMPLETED = "COMPLETED"

FUNNEL_CUTOFF_POLICY_EXACT = "exact"
FUNNEL_CUTOFF_POLICY_LATEST_AVAILABLE_AT_OR_BEFORE = (
    "latest_available_at_or_before"
)
SUPPORTED_FUNNEL_CUTOFF_POLICIES = frozenset(
    {
        FUNNEL_CUTOFF_POLICY_EXACT,
        FUNNEL_CUTOFF_POLICY_LATEST_AVAILABLE_AT_OR_BEFORE,
    }
)


def _period_key(prefix: str, month_start: date) -> str:
    return f"{prefix}-{month_start.strftime('%Y-%m')}"


def parse_cutoff_date(
    *,
    month_start: date,
    raw_value: Any,
) -> date | None:
    raw = str(raw_value or "").strip()
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise MarketingInputValidationError(
            "cutoff_date debe ser una fecha ISO válida (YYYY-MM-DD)."
        ) from exc

    if parsed.replace(day=1) != month_start:
        raise MarketingInputValidationError(
            "cutoff_date debe pertenecer al mes solicitado."
        )
    return parsed


def parse_cutoff_policy(raw_value: Any) -> str:
    policy = str(
        raw_value or FUNNEL_CUTOFF_POLICY_EXACT
    ).strip().lower()

    if policy not in SUPPORTED_FUNNEL_CUTOFF_POLICIES:
        raise MarketingInputValidationError(
            "cutoff_policy inválido. Valores permitidos: "
            + ", ".join(sorted(SUPPORTED_FUNNEL_CUTOFF_POLICIES))
            + "."
        )

    return policy


def _iventas_cutoff_dates(month_start: date) -> set[date]:
    rows = (
        db.session.query(MarketingIventasSyncRunORM.date_to)
        .filter(
            MarketingIventasSyncRunORM.period_key
            == _period_key("IVENTAS", month_start),
            MarketingIventasSyncRunORM.status == COMPLETED,
            MarketingIventasSyncRunORM.date_from == month_start,
            MarketingIventasSyncRunORM.date_to >= month_start,
            MarketingIventasSyncRunORM.date_to <= _month_end(month_start),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows if row[0] is not None}


def _meta_cutoff_dates(month_start: date) -> set[date]:
    rows = (
        db.session.query(MarketingMetaSyncRunORM.date_to)
        .filter(
            MarketingMetaSyncRunORM.period_key
            == build_meta_month_period_key(month_start),
            MarketingMetaSyncRunORM.status == COMPLETED,
            MarketingMetaSyncRunORM.date_from == month_start,
            MarketingMetaSyncRunORM.date_to >= month_start,
            MarketingMetaSyncRunORM.date_to <= _month_end(month_start),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows if row[0] is not None}


def _venta_total_cutoff_dates(month_start: date) -> set[date]:
    rows = (
        db.session.query(VentaTotalSnapshotORM.business_date)
        .filter(
            VentaTotalSnapshotORM.report_type_key == "venta_total",
            VentaTotalSnapshotORM.snapshot_kind == "daily",
            VentaTotalSnapshotORM.is_canonical.is_(True),
            VentaTotalSnapshotORM.business_date >= month_start,
            VentaTotalSnapshotORM.business_date <= _month_end(month_start),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows if row[0] is not None}


def _new_sales_cutoff_dates(month_start: date) -> set[date]:
    rows = (
        db.session.query(VentasNuevosSociosDetalleSnapshotORM.business_date)
        .filter(
            VentasNuevosSociosDetalleSnapshotORM.report_type_key
            == "ventas_nuevos_socios_detalle",
            VentasNuevosSociosDetalleSnapshotORM.snapshot_kind
            == "month_to_date",
            VentasNuevosSociosDetalleSnapshotORM.is_canonical.is_(True),
            VentasNuevosSociosDetalleSnapshotORM.date_from == month_start,
            VentasNuevosSociosDetalleSnapshotORM.business_date >= month_start,
            VentasNuevosSociosDetalleSnapshotORM.business_date
            <= _month_end(month_start),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows if row[0] is not None}


def _kpi_cutoff_dates(month_start: date) -> set[date]:
    rows = (
        db.session.query(KpiDesempenoSnapshotORM.business_date)
        .filter(
            KpiDesempenoSnapshotORM.report_type_key == "kpi_desempeno",
            KpiDesempenoSnapshotORM.snapshot_kind == "daily",
            KpiDesempenoSnapshotORM.is_canonical.is_(True),
            KpiDesempenoSnapshotORM.business_date >= month_start,
            KpiDesempenoSnapshotORM.business_date <= _month_end(month_start),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows if row[0] is not None}


def list_available_funnel_cutoffs(month_start: date) -> tuple[date, ...]:
    sources = (
        _iventas_cutoff_dates(month_start),
        _meta_cutoff_dates(month_start),
        _venta_total_cutoff_dates(month_start),
        _new_sales_cutoff_dates(month_start),
        _kpi_cutoff_dates(month_start),
    )
    if any(not values for values in sources):
        return ()

    common = set.intersection(*sources)
    return tuple(sorted(common, reverse=True))


def resolve_funnel_cutoff(
    *,
    month_start: date,
    requested_cutoff: date | None,
    cutoff_policy: str = FUNNEL_CUTOFF_POLICY_EXACT,
) -> tuple[date, tuple[date, ...]]:
    policy = parse_cutoff_policy(cutoff_policy)
    available = list_available_funnel_cutoffs(month_start)

    if not available:
        raise MarketingInputValidationError(
            "No existe un corte completo y alineado para el mes solicitado."
        )

    if requested_cutoff is None:
        return available[0], available

    if requested_cutoff in set(available):
        return requested_cutoff, available

    if policy == FUNNEL_CUTOFF_POLICY_LATEST_AVAILABLE_AT_OR_BEFORE:
        fallback_cutoff = next(
            (
                available_cutoff
                for available_cutoff in available
                if available_cutoff <= requested_cutoff
            ),
            None,
        )
        if fallback_cutoff is not None:
            return fallback_cutoff, available

    raise MarketingInputValidationError(
        "El corte solicitado no está completo en todas las fuentes del Funnel."
    )


def _select_exact_iventas_run(
    month_start: date,
    cutoff_date: date,
) -> MarketingIventasSyncRunORM:
    run = (
        MarketingIventasSyncRunORM.query.filter(
            MarketingIventasSyncRunORM.period_key
            == _period_key("IVENTAS", month_start),
            MarketingIventasSyncRunORM.status == COMPLETED,
            MarketingIventasSyncRunORM.date_from == month_start,
            MarketingIventasSyncRunORM.date_to == cutoff_date,
        )
        .order_by(MarketingIventasSyncRunORM.id.desc())
        .first()
    )
    if run is None:
        raise MarketingInputValidationError(
            "No existe snapshot iVentas COMPLETED para el corte solicitado."
        )
    return run


def _select_exact_meta_run(
    month_start: date,
    cutoff_date: date,
) -> MarketingMetaSyncRunORM:
    run = (
        MarketingMetaSyncRunORM.query.filter(
            MarketingMetaSyncRunORM.period_key
            == build_meta_month_period_key(month_start),
            MarketingMetaSyncRunORM.status == COMPLETED,
            MarketingMetaSyncRunORM.date_from == month_start,
            MarketingMetaSyncRunORM.date_to == cutoff_date,
        )
        .order_by(MarketingMetaSyncRunORM.id.desc())
        .first()
    )
    if run is None:
        raise MarketingInputValidationError(
            "No existe snapshot Meta COMPLETED para el corte solicitado."
        )
    return run


def _select_exact_venta_total_snapshot(
    month_start: date,
    cutoff_date: date,
) -> VentaTotalSnapshotORM | None:
    return (
        VentaTotalSnapshotORM.query.filter(
            VentaTotalSnapshotORM.report_type_key == "venta_total",
            VentaTotalSnapshotORM.snapshot_kind == "daily",
            VentaTotalSnapshotORM.is_canonical.is_(True),
            VentaTotalSnapshotORM.business_date == cutoff_date,
        )
        .order_by(VentaTotalSnapshotORM.captured_at.desc(), VentaTotalSnapshotORM.id.desc())
        .first()
    )


def _select_exact_new_sales_snapshot(
    month_start: date,
    cutoff_date: date,
) -> VentasNuevosSociosDetalleSnapshotORM | None:
    return (
        VentasNuevosSociosDetalleSnapshotORM.query.filter(
            VentasNuevosSociosDetalleSnapshotORM.report_type_key
            == "ventas_nuevos_socios_detalle",
            VentasNuevosSociosDetalleSnapshotORM.snapshot_kind
            == "month_to_date",
            VentasNuevosSociosDetalleSnapshotORM.is_canonical.is_(True),
            VentasNuevosSociosDetalleSnapshotORM.date_from == month_start,
            VentasNuevosSociosDetalleSnapshotORM.business_date == cutoff_date,
        )
        .order_by(
            VentasNuevosSociosDetalleSnapshotORM.captured_at.desc(),
            VentasNuevosSociosDetalleSnapshotORM.id.desc(),
        )
        .first()
    )


def _select_exact_kpi_snapshot(cutoff_date: date) -> KpiDesempenoSnapshotORM | None:
    return (
        KpiDesempenoSnapshotORM.query.filter(
            KpiDesempenoSnapshotORM.report_type_key == "kpi_desempeno",
            KpiDesempenoSnapshotORM.snapshot_kind == "daily",
            KpiDesempenoSnapshotORM.is_canonical.is_(True),
            KpiDesempenoSnapshotORM.business_date == cutoff_date,
        )
        .order_by(
            KpiDesempenoSnapshotORM.captured_at.desc(),
            KpiDesempenoSnapshotORM.id.desc(),
        )
        .first()
    )


def _selected_iventas_branch_metrics(
    *,
    run: MarketingIventasSyncRunORM,
    month_start: date,
) -> tuple[MarketingIventasLeadMetricsByBranchMonth, ...]:
    return list_iventas_lead_metrics_by_branch_month_for_run(
        sync_run_id=int(run.id),
        period_key=str(run.period_key),
        session=db.session,
    )


def _load_iventas_data_for_cutoff(
    *,
    month_start: date,
    cutoff_date: date,
    branch_ids: tuple[int, ...],
    current_run: MarketingIventasSyncRunORM,
) -> tuple[
    dict[tuple[int, str], list[_IventasEvidence]],
    tuple[int, ...],
]:
    lookback_start = month_start - timedelta(days=MATCH_WINDOW_DAYS)
    previous_runs = (
        MarketingIventasSyncRunORM.query.filter(
            MarketingIventasSyncRunORM.status == COMPLETED,
            MarketingIventasSyncRunORM.is_canonical.is_(True),
            MarketingIventasSyncRunORM.period_key != str(current_run.period_key),
            MarketingIventasSyncRunORM.date_to >= lookback_start,
            MarketingIventasSyncRunORM.date_from <= cutoff_date,
        )
        .order_by(MarketingIventasSyncRunORM.date_from.asc())
        .all()
    )
    runs = [*previous_runs, current_run]
    run_ids = tuple(dict.fromkeys(int(run.id) for run in runs))

    evidence: dict[tuple[int, str], list[_IventasEvidence]] = defaultdict(list)
    if not run_ids or not branch_ids:
        return evidence, run_ids

    meta_tag_exists = (
        db.session.query(MarketingIventasContactTagORM.id)
        .filter(
            MarketingIventasContactTagORM.sync_run_id
            == MarketingIventasContactORM.sync_run_id,
            MarketingIventasContactTagORM.iventas_contact_row_id
            == MarketingIventasContactORM.id,
            MarketingIventasContactTagORM.tag_kind == "META_AD",
        )
        .exists()
    )

    contacts = (
        db.session.query(
            MarketingIventasContactORM.sucursal_id,
            MarketingIventasContactORM.phone_mx10,
            MarketingIventasContactORM.first_message_date_local,
            MarketingIventasContactORM.is_from_ads,
            meta_tag_exists.label("legacy_has_meta"),
        )
        .filter(
            MarketingIventasContactORM.sync_run_id.in_(run_ids),
            MarketingIventasContactORM.sucursal_id.in_(branch_ids),
            MarketingIventasContactORM.first_message_at_utc.isnot(None),
            MarketingIventasContactORM.first_message_date_local
            >= lookback_start,
            MarketingIventasContactORM.first_message_date_local
            <= cutoff_date,
            MarketingIventasContactORM.phone_mx10.isnot(None),
        )
        .all()
    )
    for contact in contacts:
        interaction_date = contact.first_message_date_local
        phone = str(contact.phone_mx10 or "").strip()
        if (
            interaction_date is None
            or not phone
            or interaction_date < lookback_start
            or interaction_date > cutoff_date
        ):
            continue
        branch_id = int(contact.sucursal_id)
        has_meta = (
            contact.is_from_ads is True
            or (
                contact.is_from_ads is None
                and bool(contact.legacy_has_meta)
            )
        )
        evidence[(branch_id, phone)].append(
            _IventasEvidence(
                branch_id=branch_id,
                phone=phone,
                interaction_date=interaction_date,
                has_meta_ad=has_meta,
            )
        )

    for rows in evidence.values():
        rows.sort(key=lambda item: (item.interaction_date, item.has_meta_ad))
    return evidence, run_ids


def _read_meta_investment_for_cutoff(
    *,
    meta_run: MarketingMetaSyncRunORM,
    iventas_run: MarketingIventasSyncRunORM,
) -> MetaDashboardInvestmentData:
    insights = (
        db.session.execute(
            build_meta_campaign_insights_statement(
                meta_sync_run_id=int(meta_run.id)
            )
        )
        .mappings()
        .all()
    )
    meta_ad_ids = {
        str(row["ad_id"]).strip()
        for row in insights
        if str(row["ad_id"] or "").strip()
    }

    evidence: Iterable[Mapping[str, Any]] = ()
    if meta_ad_ids:
        evidence = (
            db.session.execute(
                build_iventas_campaign_evidence_statement(
                    iventas_sync_run_id=int(iventas_run.id),
                    meta_ad_ids=meta_ad_ids,
                )
            )
            .mappings()
            .all()
        )

    return _aggregate_campaign_investment(
        meta_sync_run_id=int(meta_run.id),
        iventas_sync_run_id=int(iventas_run.id),
        date_from=meta_run.date_from,
        date_to=meta_run.date_to,
        insight_rows=insights,
        evidence_rows=evidence,
    )


def build_marketing_sales_funnel_at_cutoff(
    *,
    month: str,
    access: MarketingAccess,
    cutoff_date: Any = None,
    cutoff_policy: Any = None,
) -> MarketingSalesFunnelBuildResult:
    month_start = parse_month(month)
    requested_cutoff = parse_cutoff_date(
        month_start=month_start,
        raw_value=cutoff_date,
    )
    selected_cutoff, available_cutoffs = resolve_funnel_cutoff(
        month_start=month_start,
        requested_cutoff=requested_cutoff,
        cutoff_policy=parse_cutoff_policy(cutoff_policy),
    )

    branches, branch_ids, scope = load_visible_marketing_branches(access)
    stats_by_branch = {branch_id: _BranchStats() for branch_id in branch_ids}

    iventas_run = _select_exact_iventas_run(month_start, selected_cutoff)
    meta_run = _select_exact_meta_run(month_start, selected_cutoff)
    branch_metrics = _selected_iventas_branch_metrics(
        run=iventas_run,
        month_start=month_start,
    )
    metrics_by_branch = {
        int(row.sucursal_id): row
        for row in branch_metrics
    }
    for branch_id in branch_ids:
        row = metrics_by_branch.get(branch_id)
        if row is None:
            continue
        stats_by_branch[branch_id].iventas_contacts = int(row.iventas_contacts)
        stats_by_branch[branch_id].leads_iventas = int(
            row.iventas_contacts_with_first_message
        )
        stats_by_branch[branch_id].leads_meta = int(row.meta_observed_leads)

    evidence, iventas_run_ids = _load_iventas_data_for_cutoff(
        month_start=month_start,
        cutoff_date=selected_cutoff,
        branch_ids=branch_ids,
        current_run=iventas_run,
    )

    alias_map = _load_branch_alias_map()
    venta_total_snapshot = _select_exact_venta_total_snapshot(
        month_start,
        selected_cutoff,
    )
    sales_detail_snapshot = _select_exact_new_sales_snapshot(
        month_start,
        selected_cutoff,
    )
    kpi_snapshot = _select_exact_kpi_snapshot(selected_cutoff)

    limitations: list[str] = []
    venta_total_rows: list[VentaTotalSnapshotRowORM] = []
    visits = []
    if venta_total_snapshot is not None:
        venta_total_rows = (
            db.session.query(
                VentaTotalSnapshotRowORM.fecha,
                VentaTotalSnapshotRowORM.sucursal,
                VentaTotalSnapshotRowORM.folio,
                VentaTotalSnapshotRowORM.descripcion,
                VentaTotalSnapshotRowORM.total,
                VentaTotalSnapshotRowORM.estatus,
                VentaTotalSnapshotRowORM.id_orden,
                VentaTotalSnapshotRowORM.encuesta,
                VentaTotalSnapshotRowORM.pin,
                VentaTotalSnapshotRowORM.telefono,
                VentaTotalSnapshotRowORM.api,
            )
            .filter(
                VentaTotalSnapshotRowORM.snapshot_id
                == venta_total_snapshot.id
            )
            .order_by(VentaTotalSnapshotRowORM.row_index.asc())
            .all()
        )
        visits = _load_visits(
            venta_total_rows,
            month_start,
            branch_ids,
            alias_map,
        )

    sales_result = _load_new_sales(
        snapshot=sales_detail_snapshot,
        venta_total_rows=venta_total_rows,
        month_start=month_start,
        branch_ids=branch_ids,
    )
    sales = sales_result.sales

    kpi_control = _load_kpi_new_sales_control(
        snapshot=kpi_snapshot,
        branch_ids=branch_ids,
        alias_map=alias_map,
    )
    kpi_control_total = (
        sum(kpi_control.values()) if kpi_snapshot is not None else None
    )
    detail_total = len(sales)
    reconciliation_difference = (
        detail_total - kpi_control_total
        if kpi_control_total is not None
        else None
    )
    if reconciliation_difference not in (None, 0):
        limitations.append(
            "Ventas Nuevos Socios Detalle no cuadra exactamente con KPI "
            f"en el corte {selected_cutoff.isoformat()}: detalle={detail_total}, "
            f"KPI={kpi_control_total}, diferencia={reconciliation_difference}."
        )

    for visit in visits:
        stats = stats_by_branch[visit.branch_id]
        stats.visits_total += 1
        if visit.phone is None:
            stats.visits_unmatchable += 1
            stats.visits_not_iventas += 1
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

        iventas_origin = _match_iventas(
            evidence,
            sale.branch_id,
            sale.phone,
            sale.sale_date,
        )
        origin = iventas_origin
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

        category = _classify_sale_category(
            iventas_origin=iventas_origin,
            api_raw=sale.api_raw,
            survey_raw=sale.survey_raw,
        )
        if category == SALE_CATEGORY_DIGITAL:
            stats.sales_digital += 1
            stats.revenue_digital += sale.revenue
        elif category == SALE_CATEGORY_DIGITAL_ORGANIC:
            stats.sales_digital_organic += 1
            stats.revenue_digital += sale.revenue
        elif category == SALE_CATEGORY_WEB:
            stats.sales_web += 1
            stats.revenue_web += sale.revenue
        else:
            stats.sales_btl += 1
            stats.revenue_btl += sale.revenue
            stats.btl_origin_counts[origin] += 1
            stats.btl_origin_revenue[origin] += sale.revenue

        stats.origin_counts[origin] += 1
        stats.origin_revenue[origin] += sale.revenue

    payload = _build_response(
        month_start=month_start,
        scope=scope,
        branches=branches,
        stats_by_branch=stats_by_branch,
        venta_total_snapshot=venta_total_snapshot,
        sales_detail_snapshot=sales_detail_snapshot,
        kpi_snapshot=kpi_snapshot,
        iventas_run_ids=iventas_run_ids,
        detail_total=detail_total,
        kpi_control_total=kpi_control_total,
        reconciliation_difference=reconciliation_difference,
        enriched_sales_count=sales_result.enriched_with_venta_total,
        limitations=limitations,
    )

    meta_data = _read_meta_investment_for_cutoff(
        meta_run=meta_run,
        iventas_run=iventas_run,
    )
    total_investment = Decimal("0")
    for branch_payload in payload["branches"]:
        investment = meta_data.branch_spend.get(
            int(branch_payload["sucursal_id"]),
            Decimal("0"),
        )
        branch_payload["investment"] = float(investment)
        total_investment += investment
    payload["summary"]["investment"] = float(total_investment)

    payload["selected_cutoff_date"] = selected_cutoff.isoformat()
    payload["available_cutoff_dates"] = [
        value.isoformat() for value in available_cutoffs
    ]
    payload["source"].update(
        {
            "iventas_sync_run_id": int(iventas_run.id),
            "meta_sync_run_id": int(meta_run.id),
            "meta_date_from": meta_run.date_from.isoformat(),
            "meta_date_to": meta_run.date_to.isoformat(),
        }
    )

    loaded = MarketingSalesFunnelLoadedData(
        month_start=month_start,
        branch_ids=branch_ids,
        venta_total_rows=(
            tuple(venta_total_rows)
            if venta_total_snapshot is not None
            else None
        ),
        alias_map=alias_map,
        visits=tuple(visits),
        evidence=evidence,
    )
    return MarketingSalesFunnelBuildResult(
        payload=payload,
        loaded=loaded,
    )
