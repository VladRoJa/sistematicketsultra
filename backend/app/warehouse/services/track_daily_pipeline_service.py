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
    delete_track_daily_mart_rows_for_version,
    refresh_track_daily_mart_for_date,
)
from app.warehouse.services.track_daily_version_service import (
    create_track_daily_version,
    get_current_track_daily_version,
    get_track_daily_version_by_id,
    mark_track_daily_version_failed,
    mark_track_daily_version_running,
    mark_track_daily_version_success,
    promote_track_canonical_close,
    replace_current_track_daily_version,
    _now_utc,
)
from app.warehouse.services.track_source_agregadoras_daily_service import (
    AGREGADORAS_POLICY_EXACT_REQUIRED,
    AGREGADORAS_POLICY_LATEST_AVAILABLE,
    refresh_track_source_agregadoras_daily_for_track_date,
    resolve_exact_agregadoras_snapshot_status_for_date,
)
from app.warehouse.services.track_upload_retention_service import (
    archive_warehouse_uploads_for_track_daily_version,
    extract_warehouse_upload_ids_from_track_raw_ingestion,
    link_warehouse_uploads_to_track_daily_version,
)
from app.warehouse.services.track_source_tienda_daily_service import (
    refresh_track_source_tienda_daily_for_date,
)
from app.warehouse.services.venta_total_repository import (
    promote_venta_total_snapshot_canonical,
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
        
        raw_ingestion = {
            "legacy_bundle_result": legacy_bundle_result,
            "legacy_followup_results": legacy_followup_results,
            "single_report_results": single_report_results,
            "jobs_executed": (
                1
                + len(legacy_followup_results)
                + len(single_report_results)
            ),
        }

        warehouse_upload_ids = extract_warehouse_upload_ids_from_track_raw_ingestion(
            raw_ingestion,
        )

        upload_link_result = link_warehouse_uploads_to_track_daily_version(
            track_daily_version_id=track_daily_version.id,
            warehouse_upload_ids=warehouse_upload_ids,
            auto_commit=False,
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
                agregadoras_policy=AGREGADORAS_POLICY_LATEST_AVAILABLE,
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
            "tienda": refresh_track_source_tienda_daily_for_date(
                business_date=track_date,
            ),
        }

        # 3) REFRESH DEL MART
        mart_refresh_result = refresh_track_daily_mart_for_date(
            business_date=track_date,
            generation_mode=normalized_generation_mode,
            track_daily_version_id=track_daily_version.id,
        )

        replaced_preview_cleanup_result = None
        replaced_preview_upload_archive_result = None

        if (
            version_type == "preview_operativo"
            and track_daily_version.replaces_version_id
        ):
            replaced_preview_cleanup_result = delete_track_daily_mart_rows_for_version(
                track_daily_version_id=track_daily_version.replaces_version_id,
                auto_commit=False,
            )

            replaced_preview_upload_archive_result = (
                archive_warehouse_uploads_for_track_daily_version(
                    track_daily_version_id=track_daily_version.replaces_version_id,
                    auto_commit=False,
                )
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
            "raw_ingestion": raw_ingestion,
            "source_refresh_results": source_refresh_results,
            "mart_refresh_result": mart_refresh_result,
            "upload_link_result": upload_link_result,
            "replaced_preview_cleanup_result": replaced_preview_cleanup_result,
            "replaced_preview_upload_archive_result": replaced_preview_upload_archive_result,
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



def run_requested_track_canonical_close(
    *,
    track_daily_version_id: int,
) -> dict[str, Any]:
    """
    Ejecuta una solicitud persistida de cierre_canonico.

    La versión solicitada permanece non-current durante todo el trabajo.
    Venta Total se ingiere como staging non-canonical y ambas promociones
    (Venta Total + Track) ocurren únicamente después de construir el mart.
    """
    try:
        normalized_version_id = int(track_daily_version_id)
    except Exception as exc:
        raise TrackDailyPipelineServiceError(
            "track_daily_version_id inválido: "
            f"{track_daily_version_id!r}"
        ) from exc

    if normalized_version_id <= 0:
        raise TrackDailyPipelineServiceError(
            "track_daily_version_id debe ser un entero positivo."
        )

    request_version = get_track_daily_version_by_id(
        normalized_version_id
    )

    if request_version.version_type != "cierre_canonico":
        raise TrackDailyPipelineServiceError(
            "La versión solicitada no es cierre_canonico. "
            f"version_id={normalized_version_id} "
            f"version_type={request_version.version_type!r}."
        )

    if (
        request_version.is_current
        and request_version.status == "success"
    ):
        return {
            "status": "already_completed",
            "track_date": request_version.track_date.isoformat(),
            "generation_mode": "official_closed_day",
            "track_daily_version": {
                "id": request_version.id,
                "version_type": "cierre_canonico",
                "status": "success",
                "is_current": True,
                "base_version_id": request_version.base_version_id,
            },
        }

    if request_version.is_current:
        raise TrackDailyPipelineServiceError(
            "Una solicitud pendiente/running de cierre_canonico "
            "no puede ser current. "
            f"version_id={normalized_version_id} "
            f"status={request_version.status!r}."
        )

    if request_version.status not in {"pending", "running"}:
        raise TrackDailyPipelineServiceError(
            "Solo se puede ejecutar una solicitud cierre_canonico "
            "pending o running. "
            f"version_id={normalized_version_id} "
            f"status={request_version.status!r}."
        )

    track_date = request_version.track_date
    requested_by_value = (
        request_version.requested_by
        or "track_manual_canonical_close"
    )
    trigger_source_value = (
        request_version.trigger_source
        or "manual_canonical_close_request"
    )

    if request_version.status == "pending":
        mark_track_daily_version_running(
            version_id=normalized_version_id,
            started_at_utc=_now_utc(),
            auto_commit=True,
        )

    try:
        # La base vinculada al request debe seguir siendo la base
        # current/success. Si cambió, el request quedó obsoleto.
        base_version = get_current_track_daily_version(
            track_date=track_date,
            version_type="base_nocturna_canonica",
        )

        if (
            base_version is None
            or base_version.status != "success"
            or base_version.id != request_version.base_version_id
        ):
            raise TrackDailyPipelineServiceError(
                "La base_nocturna_canonica vinculada al cierre "
                "ya no es la base current/success. "
                f"track_date={track_date.isoformat()} "
                f"expected_base_version_id="
                f"{request_version.base_version_id!r} "
                f"actual_base_version_id="
                f"{base_version.id if base_version else None!r}."
            )

        # Debe existir agregadora exacta antes de invertir tiempo
        # en regenerar Venta Total.
        agregadoras_readiness_before = (
            resolve_exact_agregadoras_snapshot_status_for_date(
                business_date=track_date,
            )
        )

        if not agregadoras_readiness_before.get("is_ready"):
            raise TrackDailyPipelineServiceError(
                "El cierre_canonico requiere agregadoras exactas "
                "del mismo día antes de iniciar. "
                f"track_date={track_date.isoformat()}."
            )

        # 1) Rerun histórico de Venta Total.
        # Se ingiere expresamente como NON-CANONICAL.
        venta_total_job_result = run_gasca_report_job(
            report_type_key="venta_total",
            run_mode="manual_retry",
            snapshot_kind="daily",
            requested_by=requested_by_value,
            trigger_source=(
                "track_manual_canonical_close_venta_total"
            ),
            target_business_date=track_date,
            force_ingestion=True,
            force_non_canonical=True,
        )

        raw_snapshot_id = venta_total_job_result.get(
            "snapshot_id"
        )

        raw_warehouse_upload_id = venta_total_job_result.get(
            "warehouse_upload_id"
        )

        try:
            venta_total_warehouse_upload_id = int(
                raw_warehouse_upload_id
            )
        except Exception as exc:
            raise TrackDailyPipelineServiceError(
                "El rerun de Venta Total no devolvió "
                "warehouse_upload_id válido. "
                f"warehouse_upload_id="
                f"{raw_warehouse_upload_id!r}."
            ) from exc

        if venta_total_warehouse_upload_id <= 0:
            raise TrackDailyPipelineServiceError(
                "El rerun de Venta Total devolvió "
                "warehouse_upload_id no positivo. "
                f"warehouse_upload_id="
                f"{venta_total_warehouse_upload_id!r}."
            )

        upload_link_result = (
            link_warehouse_uploads_to_track_daily_version(
                track_daily_version_id=normalized_version_id,
                warehouse_upload_ids=[
                    venta_total_warehouse_upload_id
                ],
                auto_commit=False,
            )
        )

        try:
            venta_total_snapshot_id = int(raw_snapshot_id)
        except Exception as exc:
            raise TrackDailyPipelineServiceError(
                "El rerun de Venta Total no devolvió "
                "snapshot_id válido. "
                f"snapshot_id={raw_snapshot_id!r}."
            ) from exc

        if venta_total_snapshot_id <= 0:
            raise TrackDailyPipelineServiceError(
                "El rerun de Venta Total devolvió "
                "snapshot_id no positivo. "
                f"snapshot_id={venta_total_snapshot_id!r}."
            )

        # Revalidación: el snapshot exacto de agregadoras debe
        # seguir disponible después del job largo de Venta Total.
        agregadoras_readiness_after = (
            resolve_exact_agregadoras_snapshot_status_for_date(
                business_date=track_date,
            )
        )

        if not agregadoras_readiness_after.get("is_ready"):
            raise TrackDailyPipelineServiceError(
                "Las agregadoras exactas dejaron de estar "
                "disponibles durante el cierre_canonico. "
                f"track_date={track_date.isoformat()}."
            )

        # 2) Refresh exacto de agregadoras.
        agregadoras_refresh_result = (
            refresh_track_source_agregadoras_daily_for_track_date(
                business_date=track_date,
                generation_mode="official_closed_day",
                agregadoras_policy=(
                    AGREGADORAS_POLICY_EXACT_REQUIRED
                ),
            )
        )

        agregadoras_business_date = (
            agregadoras_refresh_result.get(
                "agregadoras_business_date"
            )
        )

        if agregadoras_business_date != track_date.isoformat():
            raise TrackDailyPipelineServiceError(
                "El cierre_canonico requiere agregadoras "
                "exactas del mismo día. "
                f"track_date={track_date.isoformat()} "
                f"agregadoras_business_date="
                f"{agregadoras_business_date!r}."
            )

        if (
            int(
                agregadoras_refresh_result.get(
                    "rows_inserted"
                )
                or 0
            )
            <= 0
        ):
            raise TrackDailyPipelineServiceError(
                "No existen agregadoras exactas para crear "
                "cierre_canonico de "
                f"track_date={track_date.isoformat()}."
            )

        # 3) Ingresos usa EXACTAMENTE el snapshot de Venta Total
        # recién generado aunque aún sea non-canonical.
        ingresos_refresh_result = (
            refresh_track_source_ingresos_daily_for_date(
                business_date=track_date,
                generation_mode="official_closed_day",
                venta_total_snapshot_id=(
                    venta_total_snapshot_id
                ),
            )
        )

        # 4) Tienda mantiene el comportamiento existente.
        tienda_refresh_result = (
            refresh_track_source_tienda_daily_for_date(
                business_date=track_date,
            )
        )

        # 5) El mart se construye sobre la versión solicitada,
        # que sigue non-current.
        mart_refresh_result = refresh_track_daily_mart_for_date(
            business_date=track_date,
            generation_mode="official_closed_day",
            track_daily_version_id=normalized_version_id,
        )

        # 6) PROMOCIÓN FINAL.
        #
        # Ambos cambios comparten la misma sesión y ninguno hace
        # commit por separado. Si cualquiera falla, el except hace
        # rollback antes de marcar la solicitud failed.
        venta_total_promotion_result = (
            promote_venta_total_snapshot_canonical(
                snapshot_id=venta_total_snapshot_id,
                expected_business_date=track_date,
                expected_snapshot_kind="daily",
                auto_commit=False,
            )
        )

        promoted_version = promote_track_canonical_close(
            version_id=normalized_version_id,
            generated_at_utc=_now_utc(),
            finished_at_utc=_now_utc(),
            auto_commit=False,
        )

        db.session.commit()

        return {
            "status": "completed",
            "track_date": track_date.isoformat(),
            "generation_mode": "official_closed_day",
            "track_daily_version": {
                "id": promoted_version.id,
                "version_type": "cierre_canonico",
                "status": promoted_version.status,
                "is_current": promoted_version.is_current,
                "base_version_id": promoted_version.base_version_id,
            },
            "requested_by": requested_by_value,
            "trigger_source": trigger_source_value,
            "venta_total_job_result": venta_total_job_result,
            "venta_total_snapshot_id": venta_total_snapshot_id,
            "venta_total_warehouse_upload_id": (
                venta_total_warehouse_upload_id
            ),
            "upload_link_result": upload_link_result,
            "venta_total_promotion_result": (
                venta_total_promotion_result
            ),
            "agregadoras_readiness_before": (
                agregadoras_readiness_before
            ),
            "agregadoras_readiness_after": (
                agregadoras_readiness_after
            ),
            "source_refresh_results": {
                "agregadoras": agregadoras_refresh_result,
                "ingresos": ingresos_refresh_result,
                "tienda": tienda_refresh_result,
            },
            "mart_refresh_result": mart_refresh_result,
        }

    except Exception as exc:
        _mark_track_daily_version_failed_safely(
            version_id=normalized_version_id,
            error_message=str(exc),
        )
        raise

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

    if base_version is None or base_version.status != "success":
        return {
            "status": "not_ready",
            "track_date": track_date.isoformat(),
            "generation_mode": "official_closed_day",
            "reason": "missing_success_base_nocturna_canonica",
            "base_version_id": base_version.id if base_version else None,
            "requested_by": requested_by_value,
            "trigger_source": trigger_source_value,
        }

    agregadoras_readiness = resolve_exact_agregadoras_snapshot_status_for_date(
        business_date=track_date,
    )
    
    if not agregadoras_readiness.get("is_ready"):
        return {
            "status": "not_ready",
            "track_date": track_date.isoformat(),
            "generation_mode": "official_closed_day",
            "reason": "missing_exact_agregadoras",
            "base_version_id": base_version.id,
            "agregadoras_readiness": agregadoras_readiness,
            "requested_by": requested_by_value,
            "trigger_source": trigger_source_value,
        }

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
            agregadoras_policy=AGREGADORAS_POLICY_EXACT_REQUIRED,
        
        )

        agregadoras_business_date = agregadoras_refresh_result.get(
            "agregadoras_business_date"
        )

        if agregadoras_business_date != track_date.isoformat():
            raise TrackDailyPipelineServiceError(
                "El cierre_canonico requiere agregadoras exactas del mismo día. "
                f"track_date={track_date.isoformat()} "
                f"agregadoras_business_date={agregadoras_business_date!r}."
            )

        if int(agregadoras_refresh_result.get("rows_inserted") or 0) <= 0:
            raise TrackDailyPipelineServiceError(
                "No existen agregadoras exactas para crear cierre_canonico "
                f"de track_date={track_date.isoformat()}."
            )   


        ingresos_refresh_result = refresh_track_source_ingresos_daily_for_date(
            business_date=track_date,
            generation_mode="official_closed_day",
        )
       
        tienda_refresh_result = refresh_track_source_tienda_daily_for_date(
            business_date=track_date,
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
                "tienda": tienda_refresh_result,
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