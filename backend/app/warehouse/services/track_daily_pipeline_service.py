#   backend\app\warehouse\services\track_daily_pipeline_service.py

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.extensions import db
from app.warehouse.services.gasca_job_orchestrator import run_gasca_report_job
from app.warehouse.services.track_source_desempeno_daily_service import (
    refresh_track_source_desempeno_daily_for_date,
)
from app.warehouse.services.track_source_ingresos_daily_service import (
    refresh_track_source_ingresos_daily_for_date,
)
from app.warehouse.services.track_source_nuevos_daily_service import (
    refresh_track_source_nuevos_daily_for_date,
)
from app.warehouse.services.track_source_domiciliados_efectivos_daily_service import (
    refresh_track_source_domiciliados_efectivos_daily_for_date,
)
from app.warehouse.services.track_daily_mart_service import (
    refresh_track_daily_mart_for_date,
)
from app.warehouse.services.track_daily_version_service import (
    create_track_daily_version,
    get_current_track_daily_version,
    mark_track_daily_version_failed,
    mark_track_daily_version_success,
    replace_current_track_daily_version,
    _now_utc,
)
from app.warehouse.services.track_source_agregadoras_daily_service import (
    refresh_track_source_agregadoras_daily_for_track_date,
)


SUPPORTED_GENERATION_MODES = frozenset(
    {
        "official_closed_day",
        "manual_preview",
    }
)

OPTIONAL_SINGLE_REPORT_TYPE_KEYS = frozenset(
    {
        "cargos_recurrentes",
        "corte_caja",
    }
)


class TrackDailyPipelineServiceError(RuntimeError):
    """Error base del pipeline diario del Track."""


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as exc:
            raise TrackDailyPipelineServiceError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise TrackDailyPipelineServiceError(
        f"Valor inválido para {field_name!r}: {value!r}"
    )


def _ensure_generation_mode(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized not in SUPPORTED_GENERATION_MODES:
        raise TrackDailyPipelineServiceError(
            "generation_mode inválido. "
            f"Permitidos: {sorted(SUPPORTED_GENERATION_MODES)}"
        )
    return normalized


def _resolve_refresh_dates(
    *,
    track_date: date,
    generation_mode: str,
) -> dict[str, date]:
    normalized_generation_mode = _ensure_generation_mode(generation_mode)

    if normalized_generation_mode in {"official_closed_day", "manual_preview"}:
        return {
            "desempeno": track_date,
            "ingresos": track_date,
            "nuevos": track_date,
            "domiciliados": track_date,
        }

    raise TrackDailyPipelineServiceError(
        f"No se pudo resolver refresh dates para generation_mode={normalized_generation_mode!r}"
    )


def _resolve_track_daily_version_type_for_pipeline(
    *,
    generation_mode: str,
) -> str:
    normalized_generation_mode = str(generation_mode or "").strip()

    if normalized_generation_mode == "manual_preview":
        return "preview_operativo"

    if normalized_generation_mode == "official_closed_day":
        return "base_nocturna_canonica"

    raise TrackDailyPipelineServiceError(
        "No se pudo resolver version_type para "
        f"generation_mode={normalized_generation_mode!r}"
    )


def _mark_track_daily_version_failed_safely(
    *,
    version_id: int,
    error_message: str,
) -> None:
    """
    Marca una versión como failed sin ocultar el error original del pipeline.

    Se hace rollback antes porque alguna ingesta previa pudo dejar la sesión
    en estado inválido.
    """
    try:
        db.session.rollback()
        mark_track_daily_version_failed(
            version_id=version_id,
            error_message=error_message,
            finished_at_utc=_now_utc(),
            auto_commit=True,
        )
    except Exception:
        db.session.rollback()


def run_track_daily_pipeline_for_date(
    *,
    business_date: Any,
    generation_mode: str = "official_closed_day",
    requested_by: str | None = None,
    trigger_source: str | None = None,
) -> dict[str, Any]:
    track_date = _ensure_date(
        business_date,
        field_name="business_date",
    )
    normalized_generation_mode = _ensure_generation_mode(generation_mode)

    requested_by_value = requested_by or "track_daily_pipeline"
    trigger_source_value = trigger_source or "track_daily_pipeline_service"

    version_type = _resolve_track_daily_version_type_for_pipeline(
        generation_mode=normalized_generation_mode,
    )

    track_daily_version = None

    try:
        if version_type == "preview_operativo":
            track_daily_version = replace_current_track_daily_version(
                track_date=track_date,
                version_type=version_type,
                status="running",
                started_at_utc=_now_utc(),
                requested_by=requested_by_value,
                trigger_source=trigger_source_value,
                retry_count=0,
                auto_commit=True,
            )
        else:
            track_daily_version = create_track_daily_version(
                track_date=track_date,
                version_type=version_type,
                status="running",
                started_at_utc=_now_utc(),
                requested_by=requested_by_value,
                trigger_source=trigger_source_value,
                retry_count=0,
                auto_commit=True,
            )

        # 1) RAW INGESTION
        legacy_bundle_result = run_gasca_report_job(
            report_type_key="reporte_direccion",
            run_mode="manual_retry",
            snapshot_kind="daily",
            requested_by=requested_by_value,
            trigger_source=trigger_source_value,
            target_business_date=track_date,
            force_ingestion=True,
        )

        legacy_followup_report_type_keys = [
            "kpi_desempeno",
            "kpi_ventas_nuevos_socios",
        ]

        legacy_followup_results: list[dict[str, Any]] = []

        for report_type_key in legacy_followup_report_type_keys:
            result = run_gasca_report_job(
                report_type_key=report_type_key,
                run_mode="manual_retry",
                snapshot_kind="daily",
                requested_by=requested_by_value,
                trigger_source="track_daily_pipeline_recent_disk_only",
                target_business_date=track_date,
                force_ingestion=True,
            )
            legacy_followup_results.append(result)

        single_report_type_keys = [
            "venta_total",
            "cargos_recurrentes",
            "corte_caja",
        ]

        single_report_results: list[dict[str, Any]] = []

        for report_type_key in single_report_type_keys:
            try:
                result = run_gasca_report_job(
                    report_type_key=report_type_key,
                    run_mode="manual_retry",
                    snapshot_kind="daily",
                    requested_by=requested_by_value,
                    trigger_source=trigger_source_value,
                    target_business_date=track_date,
                    force_ingestion=True,
                )
                single_report_results.append(result)

            except Exception as exc:
                if report_type_key not in OPTIONAL_SINGLE_REPORT_TYPE_KEYS:
                    raise

                single_report_results.append(
                    {
                        "report_type_key": report_type_key,
                        "job_status": "failed_optional",
                        "ingestion_status": "not_executed",
                        "error": str(exc),
                    }
                )

        # 2) REFRESH DE FUENTES TRACK
        refresh_dates = _resolve_refresh_dates(
            track_date=track_date,
            generation_mode=normalized_generation_mode,
        )

        source_refresh_results = {
            "desempeno": refresh_track_source_desempeno_daily_for_date(
                business_date=refresh_dates["desempeno"],
            ),
            "agregadoras": refresh_track_source_agregadoras_daily_for_track_date(
                business_date=refresh_dates["ingresos"],
                generation_mode=normalized_generation_mode,
            ),
            "ingresos": refresh_track_source_ingresos_daily_for_date(
                business_date=refresh_dates["ingresos"],
                generation_mode=normalized_generation_mode,
            ),
            "nuevos": refresh_track_source_nuevos_daily_for_date(
                business_date=refresh_dates["nuevos"],
            ),
            "domiciliados": refresh_track_source_domiciliados_efectivos_daily_for_date(
                business_date=refresh_dates["domiciliados"],
            ),
        }

        # 3) REFRESH DEL MART
        mart_refresh_result = refresh_track_daily_mart_for_date(
            business_date=track_date,
            generation_mode=normalized_generation_mode,
            track_daily_version_id=track_daily_version.id,
        )

        mark_track_daily_version_success(
            version_id=track_daily_version.id,
            generated_at_utc=_now_utc(),
            finished_at_utc=_now_utc(),
            auto_commit=True,
        )

        return {
            "status": "completed",
            "track_date": track_date.isoformat(),
            "generation_mode": normalized_generation_mode,
            "track_daily_version": {
                "id": track_daily_version.id,
                "version_type": version_type,
                "status": "success",
            },
            "refresh_dates": {
                key: value.isoformat()
                for key, value in refresh_dates.items()
            },
            "raw_ingestion": {
                "legacy_bundle_result": legacy_bundle_result,
                "legacy_followup_results": legacy_followup_results,
                "single_report_results": single_report_results,
                "jobs_executed": (
                    1
                    + len(legacy_followup_results)
                    + len(single_report_results)
                ),
            },
            "source_refresh_results": source_refresh_results,
            "mart_refresh_result": mart_refresh_result,
        }

    except Exception as exc:
        if track_daily_version is not None:
            _mark_track_daily_version_failed_safely(
                version_id=track_daily_version.id,
                error_message=str(exc),
            )
        raise


def run_track_official_closed_day_job(
    *,
    business_date: Any,
    requested_by: str | None = None,
    trigger_source: str | None = None,
) -> dict[str, Any]:
    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    return run_track_daily_pipeline_for_date(
        business_date=normalized_business_date,
        generation_mode="official_closed_day",
        requested_by=requested_by or "track_official_closed_day_job",
        trigger_source=trigger_source or "track_official_closed_day_job_service",
    )


def run_track_agregadoras_integration_for_date(
    *,
    business_date: Any,
    requested_by: str | None = None,
    trigger_source: str | None = None,
) -> dict[str, Any]:
    track_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    requested_by_value = requested_by or "track_agregadoras_integration"
    trigger_source_value = (
        trigger_source or "track_agregadoras_integration_service"
    )

    base_version = get_current_track_daily_version(
        track_date=track_date,
        version_type="base_nocturna_canonica",
    )

    cierre_version = None

    try:
        cierre_version = replace_current_track_daily_version(
            track_date=track_date,
            version_type="cierre_canonico",
            status="running",
            started_at_utc=_now_utc(),
            base_version_id=base_version.id if base_version else None,
            requested_by=requested_by_value,
            trigger_source=trigger_source_value,
            retry_count=0,
            auto_commit=True,
        )

        agregadoras_refresh_result = refresh_track_source_agregadoras_daily_for_track_date(
            business_date=track_date,
            generation_mode="official_closed_day",
        )

        ingresos_refresh_result = refresh_track_source_ingresos_daily_for_date(
            business_date=track_date,
            generation_mode="official_closed_day",
        )
       
        mart_refresh_result = refresh_track_daily_mart_for_date(
            business_date=track_date,
            generation_mode="official_closed_day",
            track_daily_version_id=cierre_version.id,
        )

        mark_track_daily_version_success(
            version_id=cierre_version.id,
            generated_at_utc=_now_utc(),
            finished_at_utc=_now_utc(),
            auto_commit=True,
        )

        return {
            "status": "completed",
            "track_date": track_date.isoformat(),
            "generation_mode": "official_closed_day",
            "track_daily_version": {
                "id": cierre_version.id,
                "version_type": "cierre_canonico",
                "status": "success",
                "base_version_id": base_version.id if base_version else None,
            },
            "requested_by": requested_by_value,
            "trigger_source": trigger_source_value,
            "source_refresh_results": {
                "agregadoras": agregadoras_refresh_result,
                "ingresos": ingresos_refresh_result,
            },
            "mart_refresh_result": mart_refresh_result,
        }

    except Exception as exc:
        if cierre_version is not None:
            _mark_track_daily_version_failed_safely(
                version_id=cierre_version.id,
                error_message=str(exc),
            )
        raise