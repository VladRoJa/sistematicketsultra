"""Lecturas acotadas de ejecuciones reales para el piloto Marketing/Track.

NO infiere el estado del worker, un corte completo, ni un SLA.
Los errores textuales nunca se devuelven: diagnóstico seguro queda para M1-E.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.models.marketing import MarketingIventasSyncRunORM, MarketingMetaSyncRunORM
from app.models.warehouse import TrackDailyVersionORM


# Los demás jobs del catálogo son visibles, pero aún NO cuentan con
# correlación suficiente de corridas para declarar historial instrumentado.
_RUN_SOURCES: dict[str, tuple[type, str | None]] = {
    "marketing.iventas_sync": (MarketingIventasSyncRunORM, None),
    "marketing.meta_sync": (MarketingMetaSyncRunORM, None),
    "track.preview_operativo": (
        TrackDailyVersionORM, "scheduler_hourly_preview",
    ),
    "track.base_nocturna_canonica": (
        TrackDailyVersionORM, "scheduler_nightly_base",
    ),
    "track.base_nocturna_retry": (
        TrackDailyVersionORM, "scheduler_nightly_retry",
    ),
    "track.request_cierre_canonico": (
        TrackDailyVersionORM, "scheduler_auto_canonical_close",
    ),
}


def has_run_source(job_key: str) -> bool:
    return job_key in _RUN_SOURCES


def _utc_iso(value: datetime | None) -> str | None:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _date_iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_sync_run(row: Any, *, is_meta: bool) -> dict[str, Any]:
    counters = (
        {
            "accounts_requested": int(row.accounts_requested or 0),
            "accounts_completed": int(row.accounts_completed or 0),
            "accounts_failed": int(row.accounts_failed or 0),
        }
        if is_meta
        else {
            "branches_requested": int(row.branches_requested or 0),
            "branches_completed": int(row.branches_completed or 0),
            "branches_failed": int(row.branches_failed or 0),
        }
    )
    return {
        "run_id": int(row.id),
        "business_date": _date_iso(row.date_to),
        "started_at_utc": _utc_iso(row.started_at),
        "finished_at_utc": _utc_iso(row.finished_at),
        "status_raw": str(row.status),
        "is_canonical": bool(row.is_canonical),
        "is_current": None,
        "trigger_source": None,  # No existe en las tablas sync.
        "error_available": False,  # No hay columna de error estructurado.
        "counts": counters,
    }


def _serialize_track_run(row: Any) -> dict[str, Any]:
    return {
        "run_id": int(row.id),
        "business_date": _date_iso(row.track_date),
        "started_at_utc": _utc_iso(row.started_at_utc),
        "finished_at_utc": _utc_iso(row.finished_at_utc),
        "status_raw": str(row.status),
        "is_canonical": None,  # No reemplazar por is_current.
        "is_current": bool(row.is_current),
        "trigger_source": str(row.trigger_source),
        "version_type": str(row.version_type),
        "error_available": bool(row.error_message),
        "counts": {},
    }


def list_job_runs(
    job_key: str, *, limit: int = 20, offset: int = 0
) -> dict[str, Any]:
    """Consulta evidencias por job/trigger, nunca todo el worker como una corrida."""
    if not (1 <= limit <= 100 and 0 <= offset <= 10000):
        raise ValueError("Paginación fuera de rango.")

    source = _RUN_SOURCES.get(job_key)
    if source is None:
        return {
            "coverage": "NOT_INSTRUMENTED",
            "rows": [],
            "has_more": False,
            "limit": limit,
            "offset": offset,
        }

    model, trigger_source = source
    query = model.query
    if trigger_source is not None:
        query = query.filter(model.trigger_source == trigger_source)
        query = query.order_by(model.created_at.desc(), model.id.desc())
    else:
        query = query.order_by(model.started_at.desc(), model.id.desc())

    # +1 determina si hay página siguiente sin COUNT(*) costoso.
    raw_rows = query.offset(offset).limit(limit + 1).all()
    is_meta = job_key == "marketing.meta_sync"
    rows = [
        _serialize_track_run(row) if trigger_source is not None
        else _serialize_sync_run(row, is_meta=is_meta)
        for row in raw_rows[:limit]
    ]
    return {
        "coverage": "DOMAIN_RUNS",
        "rows": rows,
        "has_more": len(raw_rows) > limit,
        "limit": limit,
        "offset": offset,
    }
