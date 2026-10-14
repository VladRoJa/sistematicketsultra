"""Conservative per-dataset freshness evidence. No invented SLA or green states.

Global evidence is accessible only under explicit ADMICORP/GLOBAL scope in M1-F1.
Other authorized viewers receive no global dates because branch-level completeness
is not yet certified. All queries are read-only.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.warehouse import TrackDailyVersionORM, TrackDailyMartORM
from app.services.automation_control.track_coverage_service import read_track_current_catalog_coverage
from app.services.automation_control.track_base_sla_service import read_track_base_sla
from app.services.automation_control.marketing_slot_sla_service import read_marketing_sync_sla
from app.services.marketing_sales_funnel_cutoff_service import (
    _crm_history_available,
    _iventas_cutoff_dates,
    _meta_cutoff_dates,
    _venta_total_cutoff_dates,
    _new_sales_cutoff_dates,
    _kpi_cutoff_dates,
)

TIJUANA = ZoneInfo("America/Tijuana")
DATASETS = {"marketing.sales_funnel", "track.daily"}
FUNNEL_SOURCE_KEYS = (
    "iventas", "meta", "venta_total", "ventas_nuevos_socios", "kpi_desempeno",
)


def _base(module_key: str, *, checked_at: datetime, reason: str) -> dict:
    return {
        "module_key": module_key,
        "dataset_key": module_key,
        "status": "UNKNOWN",
        "label": "Sin verificar",
        "detail": "No hay un SLA de publicación ratificado para este dataset.",
        "reason_code": reason,
        "checked_at": checked_at.isoformat(),
        "timezone": "America/Tijuana",
        "expected_business_date": None,
        "latest_complete_business_date": None,
        "latest_observed_business_date": None,
        "due_at": None,
        "next_due_at": None,
        "sources": [],
    }


def _date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _funnel_evidence(payload: dict, *, period_start: date, cutoff: date, checked_at: datetime) -> None:
    # Sync SLA is a distinct indicator; it never turns the 5-source Funnel green.
    payload["marketing_sync_sla"] = read_marketing_sync_sla(
        business_date=cutoff, now=checked_at,
    )
    if not _crm_history_available(period_start):
        payload["reason_code"] = "HISTORICAL_CRM_UNAVAILABLE"
        payload["detail"] = "Este periodo no tiene las cinco fuentes históricas certificadas."
        return

    get_dates = (
        _iventas_cutoff_dates, _meta_cutoff_dates,
        _venta_total_cutoff_dates, _new_sales_cutoff_dates,
        _kpi_cutoff_dates,
    )
    # Reuse exactly the same source predicates used by the Funnel cutoff reader.
    source_dates = [
        {d for d in reader(period_start) if d is not None and d <= cutoff}
        for reader in get_dates
    ]
    all_dates = set().union(*source_dates)
    candidate = max(all_dates) if all_dates else None
    common = set.intersection(*source_dates) if all(source_dates) else set()
    complete = max(common) if common else None
    payload["latest_complete_business_date"] = _date(complete)
    payload["latest_observed_business_date"] = _date(candidate)
    payload["sources"] = [
        {
            "key": key,
            "latest_complete_business_date": _date(max(dates) if dates else None),
            "complete": candidate in dates if candidate else False,
            "reason_code": (
                "PRESENT_AT_OBSERVED_CUT" if candidate in dates
                else "MISSING_AT_OBSERVED_CUT"
            ),
        }
        for key, dates in zip(FUNNEL_SOURCE_KEYS, source_dates)
    ]
    payload["reason_code"] = "SLA_NOT_RATIFIED"
    payload["detail"] = (
        "Último corte conjunto según el lector del Funnel. "
        "No certifica que el corte exigible actual ya esté publicado."
    )


def _track_evidence(payload: dict, *, cutoff: date, checked_at: datetime) -> None:
    """Track requires current success + actual mart rows, not a green from success."""
    start = cutoff - timedelta(days=14)
    rows = (
        db.session.query(
            TrackDailyVersionORM.id, TrackDailyVersionORM.track_date,
        )
        .filter(
            TrackDailyVersionORM.track_date.between(start, cutoff),
            TrackDailyVersionORM.is_current.is_(True),
            TrackDailyVersionORM.status == "success",
            TrackDailyVersionORM.version_type.in_(
                ("base_nocturna_canonica", "cierre_canonico")
            ),
        )
        .all()
    )
    id_to_date = {row[0]: row[1] for row in rows}
    version_date = max(id_to_date.values()) if id_to_date else None
    mart_date = None
    if id_to_date:
        present_ids = (
            db.session.query(TrackDailyMartORM.track_daily_version_id)
            .filter(TrackDailyMartORM.track_daily_version_id.in_(tuple(id_to_date)))
            .distinct()
            .all()
        )
        candidate_dates = [
            id_to_date[row[0]] for row in present_ids if row[0] in id_to_date
        ]
        mart_date = max(candidate_dates) if candidate_dates else None

    payload["latest_observed_business_date"] = _date(mart_date or version_date)
    payload["sources"] = [
        {
            "key": "track_version",
            "latest_complete_business_date": _date(version_date),
            "complete": None,
            "reason_code": (
                "CURRENT_SUCCESS_VERSION" if version_date else "NO_SUCCESS_VERSION"
            ),
        },
        {
            "key": "track_mart",
            "latest_complete_business_date": _date(mart_date),
            "complete": None,
            "reason_code": (
                "MART_ROWS_PRESENT_COVERAGE_UNVERIFIED" if mart_date
                else "NO_MART_FOR_CURRENT_SUCCESS"
            ),
        },
    ]
    coverage = read_track_current_catalog_coverage(cutoff=cutoff)
    payload["track_coverage"] = coverage
    payload["latest_catalog_matched_business_date"] = (
        coverage["latest_catalog_matched_date"]
    )
    if coverage["ambiguous_current_version_dates"]:
        payload["reason_code"] = "AMBIGUOUS_CURRENT_VERSION"
    elif coverage["coverage"] and not coverage["coverage"]["matches_current_catalog"]:
        payload["reason_code"] = "TRACK_CURRENT_CATALOG_MISMATCH"
    else:
        payload["reason_code"] = "TRACK_HISTORICAL_ROSTER_UNVERIFIED"
    payload["detail"] = (
        "Cobertura de filas comparada contra el catálogo Track activo actual. "
        "El catálogo no tiene vigencia histórica por fecha; coincidencia con "
        "el catálogo actual no certifica todas las sucursales del corte ni su SLA."
    )
    base_sla = read_track_base_sla(business_date=cutoff, now=checked_at)
    payload["track_base_sla"] = base_sla
    payload["expected_business_date"] = base_sla["expected_business_date"]
    payload["due_at"] = base_sla["due_at"]
    payload["late_at"] = base_sla["late_at"]
    payload["status"] = base_sla["status"]
    if base_sla["status"] != "UNKNOWN":
        payload["reason_code"] = base_sla["reason_code"]
        payload["label"] = {
            "NOT_DUE": "Aún no vence", "LAGGING": "Pendiente",
            "LATE": "Atrasado",
        }[base_sla["status"]]
        payload["detail"] += (
            " Base nocturna D+1: exigible a las 02:00; atrasada desde "
            "las 03:00 de Tijuana, todos los días. "
            "No se confunde con el cierre canónico."
        )
    else:
        payload["reason_code"] = base_sla["reason_code"]
        payload["detail"] += (
            " La base tiene versión vigente o información ambigua, pero no "
            "existe cobertura histórica por sucursal certificada: "
            "no se puede confirmar cumplimiento ni atraso."
        )


def read_freshness(
    module_key: str,
    *,
    scope_global_certified: bool,
    month: str | None = None,
    cutoff_date: str | None = None,
    track_date: str | None = None,
    now: datetime | None = None,
) -> dict:
    if module_key not in DATASETS:
        raise ValueError("Dataset no registrado.")
    checked = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = checked.astimezone(TIJUANA).date()
    payload = _base(module_key, checked_at=checked, reason="SLA_NOT_RATIFIED")

    if module_key == "marketing.sales_funnel":
        try:
            period = (
                date.fromisoformat(month + "-01") if month is not None
                else today.replace(day=1)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("month debe tener formato YYYY-MM.") from exc
        if month is not None and month != period.strftime("%Y-%m"):
            raise ValueError("month debe tener formato YYYY-MM.")
        if period > today.replace(day=1) or period < date(2026, 1, 1):
            raise ValueError("month fuera de rango.")
        last_day = (
            (period.replace(year=period.year + 1, month=1)
             if period.month == 12
             else period.replace(month=period.month + 1)) - timedelta(days=1)
        )
        cutoff = min(today, last_day)
        if cutoff_date is not None:
            try:
                selected = date.fromisoformat(cutoff_date)
            except (TypeError, ValueError) as exc:
                raise ValueError("cutoff_date debe ser YYYY-MM-DD.") from exc
            if not period <= selected <= cutoff:
                raise ValueError("cutoff_date fuera del periodo solicitado.")
            cutoff = selected
    else:
        # Without a chosen date, monitor the last nightly-base business day.
        # Track's page can explicitly request today's date before its deadline.
        try:
            cutoff = date.fromisoformat(track_date) if track_date else (today - timedelta(days=1))
        except (ValueError, TypeError) as exc:
            raise ValueError("track_date debe ser YYYY-MM-DD.") from exc
        if cutoff > today or cutoff < today - timedelta(days=730):
            raise ValueError("track_date fuera de rango.")

    if not scope_global_certified:
        payload["reason_code"] = "SCOPE_NOT_CERTIFIED"
        payload["detail"] = (
            "No se ha certificado la frescura para este alcance. "
            "No se muestran fechas globales de otras sucursales."
        )
        return payload

    if module_key == "marketing.sales_funnel":
        _funnel_evidence(payload, period_start=period, cutoff=cutoff, checked_at=checked)
    else:
        _track_evidence(payload, cutoff=cutoff, checked_at=checked)
    return payload
