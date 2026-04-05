# backend/app/warehouse/services/gasca_extractor_adapter.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import mimetypes

from flask import current_app

from app.warehouse.services.gasca_job_orchestrator import (
    GascaProducerError,
    ProducedGascaArtifact,
)


SUPPORTED_REPORT_TYPES = frozenset(
    {
        "reporte_direccion",
        "kpi_desempeno",
        "kpi_ventas_nuevos_socios",
        "corte_caja",
        "cargos_recurrentes"
    }
)

# Claves de config para extractores específicos por reporte.
REPORT_EXTRACTOR_CONFIG_KEYS: dict[str, str] = {
    "reporte_direccion": "WAREHOUSE_GASCA_REPORTE_DIRECCION_EXTRACTOR",
    "kpi_desempeno": "WAREHOUSE_GASCA_KPI_DESEMPENO_EXTRACTOR",
    "kpi_ventas_nuevos_socios": "WAREHOUSE_GASCA_KPI_VENTAS_NUEVOS_EXTRACTOR",
    "corte_caja": "WAREHOUSE_GASCA_CORTE_CAJA_EXTRACTOR",
    "cargos_recurrentes": "WAREHOUSE_GASCA_CARGOS_RECURRENTES_EXTRACTOR",
}

# Fallback opcional: un solo extractor multipropósito.
MULTI_REPORT_EXTRACTOR_CONFIG_KEY = "WAREHOUSE_GASCA_MULTI_REPORT_EXTRACTOR"

DEFAULT_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@dataclass(slots=True)
class RawExtractorCommand:
    report_type_key: str
    run_mode: str
    snapshot_kind: str
    requested_by: str | None = None
    trigger_source: str | None = None
    requested_at: datetime | None = None


def register_gasca_extractor_adapter(app) -> None:
    """
    Registra este adaptador como hook principal del orquestador.

    Uso esperado más adelante, desde init/app factory:
        register_gasca_extractor_adapter(app)

    Esto deja resuelto:
        app.config["WAREHOUSE_GASCA_EXTRACTOR"] = extract_gasca_report
    """
    app.config["WAREHOUSE_GASCA_EXTRACTOR"] = extract_gasca_report


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError as exc:
            raise GascaProducerError(
                f"No se pudo parsear 'captured_at' desde string ISO: {value!r}"
            ) from exc

    if value is None:
        return _utc_now()

    raise GascaProducerError(
        "El extractor devolvió un 'captured_at' con tipo no soportado."
    )


def _guess_content_type_from_filename(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed

    suffix = Path(filename).suffix.lower()
    if suffix == ".xlsx":
        return DEFAULT_XLSX_CONTENT_TYPE

    return "application/octet-stream"


def _build_artifact_from_path(
    *,
    report_type_key: str,
    file_path: Path,
    captured_at: datetime,
    metadata: dict[str, Any] | None = None,
) -> ProducedGascaArtifact:
    return ProducedGascaArtifact(
        report_type_key=report_type_key,
        original_filename=file_path.name,
        content_type=_guess_content_type_from_filename(file_path.name),
        captured_at=captured_at,
        file_path=str(file_path),
        file_bytes=None,
        metadata=metadata or {},
    )


def _normalize_dict_result(
    *,
    command: RawExtractorCommand,
    result: dict[str, Any],
) -> ProducedGascaArtifact:
    original_filename = result.get("original_filename")
    file_path = result.get("file_path")
    file_bytes = result.get("file_bytes")
    content_type = result.get("content_type")
    captured_at = _ensure_datetime(result.get("captured_at"))
    metadata = result.get("metadata") or {}

    if not original_filename and file_path:
        original_filename = Path(str(file_path)).name

    artifact = ProducedGascaArtifact(
        report_type_key=result.get("report_type_key", command.report_type_key),
        original_filename=original_filename or "",
        content_type=content_type
        or _guess_content_type_from_filename(original_filename or "artifact.xlsx"),
        captured_at=captured_at,
        file_path=str(file_path) if file_path else None,
        file_bytes=file_bytes,
        metadata=metadata,
    )
    artifact.validate()
    return artifact


def _normalize_extractor_result(
    *,
    command: RawExtractorCommand,
    result: Any,
) -> ProducedGascaArtifact:
    """
    Formatos soportados que puede devolver un extractor real:

    1) ProducedGascaArtifact
    2) dict con:
       - original_filename
       - content_type
       - captured_at
       - file_path o file_bytes
       - metadata opcional
    3) str | Path apuntando al archivo generado
    """
    if isinstance(result, ProducedGascaArtifact):
        result.validate()
        return result

    if isinstance(result, dict):
        return _normalize_dict_result(command=command, result=result)

    if isinstance(result, (str, Path)):
        path = Path(result)
        if not path.exists():
            raise GascaProducerError(
                f"El extractor devolvió una ruta que no existe: {path}"
            )

        artifact = _build_artifact_from_path(
            report_type_key=command.report_type_key,
            file_path=path,
            captured_at=command.requested_at or _utc_now(),
            metadata={
                "adapter_result_source": "path_only",
                "run_mode": command.run_mode,
                "snapshot_kind": command.snapshot_kind,
            },
        )
        artifact.validate()
        return artifact

    raise GascaProducerError(
        "El extractor devolvió un tipo no soportado. "
        "Debe devolver ProducedGascaArtifact, dict, str o Path."
    )


def _validate_command(command: RawExtractorCommand) -> None:
    if command.report_type_key not in SUPPORTED_REPORT_TYPES:
        raise ValueError(
            "El 'report_type_key' no es válido para el adaptador de Gasca. "
            f"Permitidos: {sorted(SUPPORTED_REPORT_TYPES)}"
        )

    if not command.run_mode:
        raise ValueError("El 'run_mode' es obligatorio.")

    if not command.snapshot_kind:
        raise ValueError("El 'snapshot_kind' es obligatorio.")


def _get_specific_extractor(report_type_key: str) -> Callable[..., Any] | None:
    config_key = REPORT_EXTRACTOR_CONFIG_KEYS[report_type_key]
    extractor = current_app.config.get(config_key)
    return extractor if callable(extractor) else None


def _get_multi_report_extractor() -> Callable[..., Any] | None:
    extractor = current_app.config.get(MULTI_REPORT_EXTRACTOR_CONFIG_KEY)
    return extractor if callable(extractor) else None


def _resolve_extractor(report_type_key: str) -> Callable[..., Any]:
    specific_extractor = _get_specific_extractor(report_type_key)
    if specific_extractor is not None:
        return specific_extractor

    multi_report_extractor = _get_multi_report_extractor()
    if multi_report_extractor is not None:
        return multi_report_extractor

    specific_key = REPORT_EXTRACTOR_CONFIG_KEYS[report_type_key]
    raise NotImplementedError(
        "No hay extractor configurado para este reporte. "
        f"Esperado en app.config: '{specific_key}' o "
        f"'{MULTI_REPORT_EXTRACTOR_CONFIG_KEY}'."
    )


def _call_extractor(
    *,
    extractor: Callable[..., Any],
    command: RawExtractorCommand,
) -> Any:
    """
    Todos los extractores deben aceptar kwargs nombrados.
    Eso nos da un contrato estable y explícito.
    """
    return extractor(
        report_type_key=command.report_type_key,
        run_mode=command.run_mode,
        snapshot_kind=command.snapshot_kind,
        requested_by=command.requested_by,
        trigger_source=command.trigger_source,
        requested_at=command.requested_at,
    )


def extract_gasca_report(
    *,
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
    requested_by: str | None = None,
    trigger_source: str | None = None,
    requested_at: datetime | None = None,
) -> ProducedGascaArtifact:
    """
    Hook principal del orquestador para extracción de artefactos Gasca.

    Flujo:
    1. validar comando
    2. resolver extractor específico o multipropósito
    3. ejecutar extractor
    4. normalizar salida a ProducedGascaArtifact

    Este adaptador no conoce todavía el script real.
    Solo define el contrato limpio de integración.
    """
    command = RawExtractorCommand(
        report_type_key=report_type_key,
        run_mode=run_mode,
        snapshot_kind=snapshot_kind,
        requested_by=requested_by,
        trigger_source=trigger_source,
        requested_at=requested_at or _utc_now(),
    )
    _validate_command(command)

    extractor = _resolve_extractor(command.report_type_key)

    current_app.logger.info(
        "Gasca extractor adapter dispatch: report_type_key=%s run_mode=%s snapshot_kind=%s extractor=%s",
        command.report_type_key,
        command.run_mode,
        command.snapshot_kind,
        getattr(extractor, "__name__", extractor.__class__.__name__),
    )

    try:
        raw_result = _call_extractor(extractor=extractor, command=command)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise GascaProducerError(
            f"Falló el extractor configurado para {command.report_type_key!r}."
        ) from exc

    artifact = _normalize_extractor_result(command=command, result=raw_result)

    current_app.logger.info(
        "Gasca extractor adapter normalized artifact: report_type_key=%s filename=%s captured_at=%s",
        artifact.report_type_key,
        artifact.original_filename,
        artifact.captured_at.isoformat(),
    )

    return artifact