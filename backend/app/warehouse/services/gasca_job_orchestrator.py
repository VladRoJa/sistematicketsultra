# backend/app/warehouse/services/gasca_job_orchestrator.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from flask import current_app


SUPPORTED_REPORT_TYPES = frozenset(
    {
        "reporte_direccion",
        "kpi_desempeno",
        "kpi_ventas_nuevos_socios",
        "corte_caja",
        "cargos_recurrentes",
        "venta_total"
    }
)

SUPPORTED_RUN_MODES = frozenset(
    {
        "scheduled_daily",
        "scheduled_month_end_close",
        "manual_backfill",
        "manual_retry",
    }
)

RUN_MODE_COMPATIBILITY: dict[str, set[str]] = {
    "reporte_direccion": {
        "scheduled_daily",
        "scheduled_month_end_close",
        "manual_backfill",
        "manual_retry",
    },
    "kpi_desempeno": {
        "scheduled_daily",
        "manual_backfill",
        "manual_retry",
    },
    "kpi_ventas_nuevos_socios": {
        "scheduled_daily",
        "manual_backfill",
        "manual_retry",
    },
        "corte_caja": {
        "scheduled_daily",
        "manual_backfill",
        "manual_retry",
    },
        "cargos_recurrentes": {
        "scheduled_daily",
        "manual_backfill",
        "manual_retry",
    },
        "venta_total": {
        "scheduled_daily",
        "manual_backfill",
        "manual_retry",
    },
}

EXPECTED_SNAPSHOT_KIND_BY_RUN_MODE: dict[str, str] = {
    "scheduled_daily": "daily",
    "scheduled_month_end_close": "month_end_close",
    "manual_backfill": "daily",
    "manual_retry": "daily",
}


class GascaJobOrchestrationError(RuntimeError):
    """Error base del orquestador."""


class GascaProducerError(GascaJobOrchestrationError):
    """Fallo al extraer el archivo desde Gasca."""


class WarehouseUploadError(GascaJobOrchestrationError):
    """Fallo al crear el upload documental en Warehouse."""


class GascaIngestionError(GascaJobOrchestrationError):
    """Fallo al disparar la ingesta estructurada."""


@dataclass(slots=True)
class GascaExtractionCommand:
    report_type_key: str
    run_mode: str
    snapshot_kind: str
    requested_by: str | None = None
    trigger_source: str | None = None
    requested_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(slots=True)
class ProducedGascaArtifact:
    report_type_key: str
    original_filename: str
    content_type: str
    captured_at: datetime
    file_path: str | None = None
    file_bytes: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.report_type_key not in SUPPORTED_REPORT_TYPES:
            raise GascaProducerError(
                f"Artifact con report_type_key inválido: {self.report_type_key!r}"
            )

        if not self.original_filename:
            raise GascaProducerError(
                "El productor de Gasca debe devolver 'original_filename'."
            )

        has_path = bool(self.file_path)
        has_bytes = self.file_bytes is not None
        if not has_path and not has_bytes:
            raise GascaProducerError(
                "El productor debe devolver 'file_path' o 'file_bytes'."
            )

        if has_path:
            path = Path(self.file_path)  # type: ignore[arg-type]
            if not path.exists():
                raise GascaProducerError(
                    f"El archivo producido no existe en disco: {path}"
                )


@dataclass(slots=True)
class WarehouseUploadRef:
    warehouse_upload_id: int
    upload_status: str = "created"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IngestionDispatchResult:
    ingestion_status: str
    snapshot_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _validate_job_inputs(
    *,
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
) -> None:
    if report_type_key not in SUPPORTED_REPORT_TYPES:
        raise ValueError(
            "El 'report_type_key' no es válido. "
            f"Permitidos: {sorted(SUPPORTED_REPORT_TYPES)}"
        )

    if run_mode not in SUPPORTED_RUN_MODES:
        raise ValueError(
            "El 'run_mode' no es válido. "
            f"Permitidos: {sorted(SUPPORTED_RUN_MODES)}"
        )

    allowed_run_modes = RUN_MODE_COMPATIBILITY[report_type_key]
    if run_mode not in allowed_run_modes:
        raise ValueError(
            "La combinación de 'report_type_key' y 'run_mode' no está permitida."
        )

    expected_snapshot_kind = EXPECTED_SNAPSHOT_KIND_BY_RUN_MODE[run_mode]
    if snapshot_kind != expected_snapshot_kind:
        raise ValueError(
            "El 'snapshot_kind' no coincide con el 'run_mode' recibido. "
            f"Esperado: {expected_snapshot_kind!r}, recibido: {snapshot_kind!r}"
        )


def _get_required_callable(
    config_key: str,
    *,
    description: str,
) -> Callable[..., Any]:
    """
    Resuelve un hook/callable inyectado en app.config.

    Esto evita acoplar de golpe el orquestador al extractor real,
    al upload service real y a la ingesta real.
    """
    fn = current_app.config.get(config_key)
    if not callable(fn):
        raise NotImplementedError(
            f"No se encontró un callable configurado en '{config_key}' "
            f"para {description}."
        )
    return fn


def _normalize_artifact_result(
    *,
    result: Any,
    command: GascaExtractionCommand,
) -> ProducedGascaArtifact:
    if isinstance(result, ProducedGascaArtifact):
        artifact = result
    elif isinstance(result, dict):
        artifact = ProducedGascaArtifact(
            report_type_key=result.get("report_type_key", command.report_type_key),
            original_filename=result.get("original_filename", ""),
            content_type=result.get(
                "content_type",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            captured_at=result.get("captured_at") or _utc_now(),
            file_path=result.get("file_path"),
            file_bytes=result.get("file_bytes"),
            metadata=result.get("metadata") or {},
        )
    else:
        raise GascaProducerError(
            "El productor devolvió un tipo no soportado. "
            "Debe devolver ProducedGascaArtifact o dict."
        )

    artifact.validate()
    return artifact


def _extract_gasca_artifact(
    command: GascaExtractionCommand,
) -> ProducedGascaArtifact:
    extractor = _get_required_callable(
        "WAREHOUSE_GASCA_EXTRACTOR",
        description="extraer el raw desde Gasca",
    )

    try:
        result = extractor(
            report_type_key=command.report_type_key,
            run_mode=command.run_mode,
            snapshot_kind=command.snapshot_kind,
            requested_by=command.requested_by,
            trigger_source=command.trigger_source,
            requested_at=command.requested_at,
        )
    except Exception as exc:
        raise GascaProducerError(
            f"Falló la extracción desde Gasca para {command.report_type_key!r}."
        ) from exc

    artifact = _normalize_artifact_result(result=result, command=command)

    current_app.logger.info(
        "Gasca artifact extracted: report_type_key=%s filename=%s captured_at=%s",
        artifact.report_type_key,
        artifact.original_filename,
        artifact.captured_at.isoformat(),
    )

    return artifact


def _normalize_upload_result(result: Any) -> WarehouseUploadRef:
    if isinstance(result, WarehouseUploadRef):
        return result

    if isinstance(result, int):
        return WarehouseUploadRef(warehouse_upload_id=result)

    if isinstance(result, dict):
        upload_id = result.get("warehouse_upload_id")
        if not isinstance(upload_id, int):
            raise WarehouseUploadError(
                "El servicio de upload debe devolver 'warehouse_upload_id' entero."
            )

        return WarehouseUploadRef(
            warehouse_upload_id=upload_id,
            upload_status=result.get("upload_status", "created"),
            metadata=result.get("metadata") or {},
        )

    raise WarehouseUploadError(
        "El servicio de upload devolvió un tipo no soportado. "
        "Debe devolver WarehouseUploadRef, dict o int."
    )


def _create_warehouse_upload(
    *,
    command: GascaExtractionCommand,
    artifact: ProducedGascaArtifact,
) -> WarehouseUploadRef:
    upload_creator = _get_required_callable(
        "WAREHOUSE_INTERNAL_UPLOAD_CREATOR",
        description="crear el upload documental en Warehouse",
    )

    try:
        result = upload_creator(
            report_type_key=command.report_type_key,
            original_filename=artifact.original_filename,
            content_type=artifact.content_type,
            file_path=artifact.file_path,
            file_bytes=artifact.file_bytes,
            captured_at=artifact.captured_at,
            source_key="gasca",
            metadata={
                "run_mode": command.run_mode,
                "snapshot_kind": command.snapshot_kind,
                "requested_by": command.requested_by,
                "trigger_source": command.trigger_source,
                **(artifact.metadata or {}),
            },
        )
    except Exception as exc:
        raise WarehouseUploadError(
            f"Falló la creación del upload documental para {command.report_type_key!r}."
        ) from exc

    upload_ref = _normalize_upload_result(result)

    current_app.logger.info(
        "Warehouse upload created: report_type_key=%s warehouse_upload_id=%s",
        command.report_type_key,
        upload_ref.warehouse_upload_id,
    )

    return upload_ref


def _should_dispatch_ingestion(
    *,
    report_type_key: str,
    force_ingestion: bool,
) -> bool:
    if not force_ingestion:
        return False

    # Habilitados para ingesta estructurada en esta etapa:
    return report_type_key in {
        "reporte_direccion",
        "kpi_desempeno",
        "kpi_ventas_nuevos_socios",
        "corte_caja",
        "cargos_recurrentes"
    }

def _normalize_ingestion_result(result: Any) -> IngestionDispatchResult:
    if isinstance(result, IngestionDispatchResult):
        return result

    if isinstance(result, int):
        return IngestionDispatchResult(
            ingestion_status="ingested",
            snapshot_id=result,
        )

    if isinstance(result, dict):
        return IngestionDispatchResult(
            ingestion_status=result.get("status", "ingested"),
            snapshot_id=result.get("snapshot_id"),
            metadata=result.get("metadata") or {},
        )

    raise GascaIngestionError(
        "El servicio de ingesta devolvió un tipo no soportado. "
        "Debe devolver IngestionDispatchResult, dict o int."
    )


def _dispatch_ingestion_if_applicable(
    *,
    command: GascaExtractionCommand,
    upload_ref: WarehouseUploadRef,
    force_ingestion: bool,
) -> IngestionDispatchResult:
    if not force_ingestion:
        return IngestionDispatchResult(
            ingestion_status="skipped",
            snapshot_id=None,
            metadata={"reason": "force_ingestion_false"},
        )

    if command.report_type_key == "reporte_direccion":
        ingestor = _get_required_callable(
            "WAREHOUSE_REPORTE_DIRECCION_INGESTOR",
            description="ingerir estructuradamente reporte_direccion",
        )

        try:
            result = ingestor(
                warehouse_upload_id=upload_ref.warehouse_upload_id,
                snapshot_kind=command.snapshot_kind,
                requested_by=command.requested_by,
                ingestion_source=command.trigger_source,
            )
        except Exception as exc:
            raise GascaIngestionError(
                "Falló la ingesta estructurada de 'reporte_direccion'."
            ) from exc

        ingestion_result = _normalize_ingestion_result(result)

        current_app.logger.info(
            "Structured ingestion dispatched: warehouse_upload_id=%s report_type_key=%s status=%s snapshot_id=%s",
            upload_ref.warehouse_upload_id,
            command.report_type_key,
            ingestion_result.ingestion_status,
            ingestion_result.snapshot_id,
        )

        return ingestion_result

    if command.report_type_key == "kpi_desempeno":
        ingestor = _get_required_callable(
            "WAREHOUSE_KPI_DESEMPENO_INGESTOR",
            description="ingerir estructuradamente kpi_desempeno",
        )

        try:
            result = ingestor(
                warehouse_upload_id=upload_ref.warehouse_upload_id,
                snapshot_kind=command.snapshot_kind,
                requested_by=command.requested_by,
                ingestion_source=command.trigger_source,
            )
        except Exception as exc:
            raise GascaIngestionError(
                "Falló la ingesta estructurada de 'kpi_desempeno'."
            ) from exc

        ingestion_result = _normalize_ingestion_result(result)

        current_app.logger.info(
            "Structured ingestion dispatched: warehouse_upload_id=%s report_type_key=%s status=%s snapshot_id=%s",
            upload_ref.warehouse_upload_id,
            command.report_type_key,
            ingestion_result.ingestion_status,
            ingestion_result.snapshot_id,
        )

        return ingestion_result

    if command.report_type_key == "kpi_ventas_nuevos_socios":
        ingestor = _get_required_callable(
            "WAREHOUSE_KPI_VENTAS_NUEVOS_SOCIOS_INGESTOR",
            description="ingerir estructuradamente kpi_ventas_nuevos_socios",
        )

        try:
            result = ingestor(
                warehouse_upload_id=upload_ref.warehouse_upload_id,
                snapshot_kind=command.snapshot_kind,
                requested_by=command.requested_by,
                ingestion_source=command.trigger_source,
            )
        except Exception as exc:
            raise GascaIngestionError(
                "Falló la ingesta estructurada de 'kpi_ventas_nuevos_socios'."
            ) from exc

        ingestion_result = _normalize_ingestion_result(result)

        current_app.logger.info(
            "Structured ingestion dispatched: warehouse_upload_id=%s report_type_key=%s status=%s snapshot_id=%s",
            upload_ref.warehouse_upload_id,
            command.report_type_key,
            ingestion_result.ingestion_status,
            ingestion_result.snapshot_id,
        )

        return ingestion_result
    
    if command.report_type_key == "corte_caja":
        ingestor = _get_required_callable(
            "WAREHOUSE_CORTE_CAJA_INGESTOR",
            description="ingerir estructuradamente corte_caja",
        )

        try:
            result = ingestor(
                warehouse_upload_id=upload_ref.warehouse_upload_id,
                snapshot_kind=command.snapshot_kind,
                requested_by=command.requested_by,
                ingestion_source=command.trigger_source,
            )
        except Exception as exc:
            raise GascaIngestionError(
                "Falló la ingesta estructurada de 'corte_caja'."
            ) from exc

        ingestion_result = _normalize_ingestion_result(result)

        current_app.logger.info(
            "Structured ingestion dispatched: warehouse_upload_id=%s report_type_key=%s status=%s snapshot_id=%s",
            upload_ref.warehouse_upload_id,
            command.report_type_key,
            ingestion_result.ingestion_status,
            ingestion_result.snapshot_id,
        )

        return ingestion_result

    return IngestionDispatchResult(
        ingestion_status="not_applicable",
        snapshot_id=None,
        metadata={"reason": "structured_ingestion_not_enabled_for_report_type"},
    )

def _resolve_job_status(ingestion_status: str) -> str:
    if ingestion_status == "ingested":
        return "ingested"

    if ingestion_status in {"not_applicable", "skipped"}:
        return "uploaded_only"

    if ingestion_status == "already_ingested":
        return "completed"

    return "completed"


def run_gasca_report_job(
    *,
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
    requested_by: str | None = None,
    trigger_source: str | None = None,
    force_ingestion: bool = True,
) -> dict[str, Any]:
    """
    Orquesta el flujo completo de un job interno de Gasca:

    1) validar inputs
    2) extraer raw desde Gasca
    3) crear upload documental en Warehouse
    4) si aplica, disparar ingesta estructurada

    Dependencias externas esperadas vía app.config:
    - WAREHOUSE_GASCA_EXTRACTOR
    - WAREHOUSE_INTERNAL_UPLOAD_CREATOR
    - WAREHOUSE_REPORTE_DIRECCION_INGESTOR
    """
    _validate_job_inputs(
        report_type_key=report_type_key,
        run_mode=run_mode,
        snapshot_kind=snapshot_kind,
    )

    command = GascaExtractionCommand(
        report_type_key=report_type_key,
        run_mode=run_mode,
        snapshot_kind=snapshot_kind,
        requested_by=requested_by,
        trigger_source=trigger_source,
    )

    current_app.logger.info(
        "Running Gasca job orchestration: report_type_key=%s run_mode=%s snapshot_kind=%s",
        command.report_type_key,
        command.run_mode,
        command.snapshot_kind,
    )

    artifact = _extract_gasca_artifact(command)
    upload_ref = _create_warehouse_upload(command=command, artifact=artifact)

    should_ingest = _should_dispatch_ingestion(
        report_type_key=command.report_type_key,
        force_ingestion=force_ingestion,
    )

    if should_ingest:
        ingestion_result = _dispatch_ingestion_if_applicable(
            command=command,
            upload_ref=upload_ref,
            force_ingestion=force_ingestion,
        )
    else:
        if force_ingestion:
            ingestion_result = IngestionDispatchResult(
                ingestion_status="not_applicable",
                snapshot_id=None,
                metadata={
                    "reason": "structured_ingestion_not_enabled_for_report_type",
                },
            )
        else:
            ingestion_result = IngestionDispatchResult(
                ingestion_status="skipped",
                snapshot_id=None,
                metadata={"reason": "force_ingestion_false"},
            )

    job_status = _resolve_job_status(ingestion_result.ingestion_status)

    return {
        "job_status": job_status,
        "report_type_key": command.report_type_key,
        "run_mode": command.run_mode,
        "snapshot_kind": command.snapshot_kind,
        "requested_by": command.requested_by,
        "trigger_source": command.trigger_source,
        "force_ingestion": force_ingestion,
        "artifact": {
            "original_filename": artifact.original_filename,
            "content_type": artifact.content_type,
            "captured_at": _serialize_datetime(artifact.captured_at),
            "file_path": artifact.file_path,
            "metadata": artifact.metadata,
        },
        "upload_status": upload_ref.upload_status,
        "warehouse_upload_id": upload_ref.warehouse_upload_id,
        "upload_metadata": upload_ref.metadata,
        "ingestion_status": ingestion_result.ingestion_status,
        "snapshot_id": ingestion_result.snapshot_id,
        "ingestion_metadata": ingestion_result.metadata,
    }