"""M1-F5: ratified five-source operational Funnel deadline, without false green.

For business day D: 03:00 D+1 due, 04:00 D+1 late, America/Tijuana.
This evaluates source *presence*, not final canonical closure or historical
branch roster. A complete set remains UNKNOWN until lineage is certified.
Only call after backend GLOBAL scope guard; never query on filtered scope.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.marketing import MarketingIventasSyncRunORM, MarketingMetaSyncRunORM
from app.models.warehouse import (
    VentaTotalSnapshotORM,
    VentasNuevosSociosDetalleSnapshotORM,
    KpiDesempenoSnapshotORM,
)
from app.services.marketing_sales_funnel_cutoff_service import _crm_history_available

TIJUANA = ZoneInfo("America/Tijuana")
DUE = time(3, 0)
LATE = time(4, 0)
SOURCE_KEYS = ("iventas", "meta", "venta_total", "ventas_nuevos_socios", "kpi_desempeno")
POLICY = "FUNNEL_OPERATIONAL_D_PLUS_1_0300_0400_V1"


def operational_sla_window(*, business_date: date, now: datetime) -> dict:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    tomorrow = business_date + timedelta(days=1)
    due = datetime.combine(tomorrow, DUE, tzinfo=TIJUANA)
    late = datetime.combine(tomorrow, LATE, tzinfo=TIJUANA)
    instant = now.astimezone(timezone.utc)
    phase = (
        "NOT_DUE" if instant < due.astimezone(timezone.utc)
        else "LAGGING" if instant < late.astimezone(timezone.utc)
        else "LATE"
    )
    return {
        "expected_business_date": business_date.isoformat(),
        "due_at": due.isoformat(),
        "late_at": late.isoformat(),
        "phase_if_unavailable": phase,
        "timezone": TIJUANA.key,
        "policy_key": POLICY,
        "applies_every_day": True,
    }


def _exact_current_sources(business_date: date) -> list[dict]:
    """Five bounded queries: distinguish true absence from superseded evidence.

    Monthly CRM canonicality can move to a newer date. A completed run
    for D that is no longer canonical cannot certify historical punctuality
    but must also not be called definitively missing.
    """
    start = business_date.replace(day=1)
    month = start.strftime("%Y-%m")
    queries = (
        db.session.query(MarketingIventasSyncRunORM.id, MarketingIventasSyncRunORM.is_canonical).filter(
            MarketingIventasSyncRunORM.period_key == f"IVENTAS-{month}",
            MarketingIventasSyncRunORM.status == "COMPLETED",
            MarketingIventasSyncRunORM.date_from == start,
            MarketingIventasSyncRunORM.date_to == business_date,
        ),
        db.session.query(MarketingMetaSyncRunORM.id, MarketingMetaSyncRunORM.is_canonical).filter(
            MarketingMetaSyncRunORM.period_key == f"META-{month}",
            MarketingMetaSyncRunORM.status == "COMPLETED",
            MarketingMetaSyncRunORM.date_from == start,
            MarketingMetaSyncRunORM.date_to == business_date,
        ),
        db.session.query(VentaTotalSnapshotORM.id, VentaTotalSnapshotORM.is_canonical).filter(
            VentaTotalSnapshotORM.report_type_key == "venta_total",
            VentaTotalSnapshotORM.snapshot_kind == "daily",
            VentaTotalSnapshotORM.business_date == business_date,
        ),
        db.session.query(
            VentasNuevosSociosDetalleSnapshotORM.id,
            VentasNuevosSociosDetalleSnapshotORM.is_canonical,
        ).filter(
            VentasNuevosSociosDetalleSnapshotORM.report_type_key == "ventas_nuevos_socios_detalle",
            VentasNuevosSociosDetalleSnapshotORM.snapshot_kind == "month_to_date",
            VentasNuevosSociosDetalleSnapshotORM.date_from == start,
            VentasNuevosSociosDetalleSnapshotORM.date_to == business_date,
            VentasNuevosSociosDetalleSnapshotORM.business_date == business_date,
        ),
        db.session.query(KpiDesempenoSnapshotORM.id, KpiDesempenoSnapshotORM.is_canonical).filter(
            KpiDesempenoSnapshotORM.report_type_key == "kpi_desempeno",
            KpiDesempenoSnapshotORM.snapshot_kind == "daily",
            KpiDesempenoSnapshotORM.business_date == business_date,
        ),
    )
    results = []
    for key, query in zip(SOURCE_KEYS, queries):
        rows = query.limit(20).all()
        if len(rows) >= 20:
            reason = "ATTEMPTS_LIMIT"
            present = None
        else:
            canonicals = [row for row in rows if row[1] is True]
            if len(canonicals) > 1:
                reason, present = "AMBIGUOUS_CANONICAL_DATE", None
            elif len(canonicals) == 1:
                reason, present = "CANONICAL_DATE_PRESENT_LINEAGE_UNVERIFIED", True
            elif rows:
                # Historical/superseded completed evidence: never false red.
                reason, present = "SUPERSEDED_OR_NONCANONICAL_EVIDENCE", None
            else:
                reason, present = "NO_EXACT_COMPLETED_SOURCE", False
        results.append({"key": key, "present": present, "reason_code": reason})
    return results


def read_funnel_operational_sla(*, business_date: date, now: datetime) -> dict:
    """Date D may be selected independently from the dashboard cutoff."""
    result = operational_sla_window(business_date=business_date, now=now)
    result.update({
        "status": "UNKNOWN",
        "reason_code": "OPERATIONAL_EVIDENCE_UNVERIFIED",
        "sources": [],
        "missing_sources": [],
        "operational_not_final": True,
        "lineage_verified": False,
        "historical_roster_verified": False,
        "canonical_close_sla": "SEPARATE_CONDITIONAL_NOT_RATIFIED",
    })
    if not _crm_history_available(business_date.replace(day=1)):
        result["reason_code"] = "HISTORICAL_CRM_UNAVAILABLE"
        return result

    sources = _exact_current_sources(business_date)
    result["sources"] = sources
    if any(item["present"] is None for item in sources):
        result["reason_code"] = "EXACT_SOURCE_CANNOT_CERTIFY_HISTORY"
        return result

    missing = [item["key"] for item in sources if item["present"] is False]
    result["missing_sources"] = missing
    if missing:
        result["status"] = result["phase_if_unavailable"]
        result["reason_code"] = "EXACT_OPERATIONAL_SOURCES_MISSING"
    else:
        # Snapshot flags alone cannot prove source lineage to a valid Track
        # version, historical branch coverage, or final canonical close.
        result["reason_code"] = "FIVE_DATES_PRESENT_LINEAGE_UNVERIFIED"
    return result
