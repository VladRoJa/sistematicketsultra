# backend/app/warehouse/services/gasca_script_bridge.py

from __future__ import annotations

from datetime import datetime, timezone
import importlib
import mimetypes
from pathlib import Path
from typing import Any, Callable

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
    }
)

DEFAULT_FILENAME_PREFIXES: dict[str, str] = {
    "reporte_direccion": "ingresos_",
    "kpi_desempeno": "kpi_desempeno_",
    "kpi_ventas_nuevos_socios": "kpi_ventas_nuevos_socios_",
    "corte_caja":"corte_caja"
}

DEFAULT_OUTPUT_DIRS: dict[str, str] = {
    "reporte_direccion": "data/direccion_ingresos",
    "kpi_desempeno": "data/kpi_desempeno",
    "kpi_ventas_nuevos_socios": "data/kpi_ventas_nuevos_socios",
    "corte_caja":"data/corte_caja"
}

DEFAULT_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def register_gasca_script_bridge(app) -> None:
    """
    Registra este bridge como extractor multipropósito del adapter.

    Uso esperado más adelante en init/app factory:
        register_gasca_script_bridge(app)

    Esto deja resuelto:
        app.config["WAREHOUSE_GASCA_MULTI_REPORT_EXTRACTOR"] = extract_with_gasca_script
    """
    app.config["WAREHOUSE_GASCA_MULTI_REPORT_EXTRACTOR"] = extract_with_gasca_script


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError as exc:
            raise GascaProducerError(
                f"No se pudo parsear un datetime ISO válido desde {value!r}."
            ) from exc

    if value is None:
        return _utc_now()

    raise GascaProducerError(
        "Se recibió un valor de fecha/hora con tipo no soportado."
    )


def _guess_content_type(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed

    suffix = Path(filename).suffix.lower()
    if suffix == ".xlsx":
        return DEFAULT_XLSX_CONTENT_TYPE

    return "application/octet-stream"


def _validate_inputs(
    *,
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
) -> None:
    if report_type_key not in SUPPORTED_REPORT_TYPES:
        raise ValueError(
            "El 'report_type_key' no es válido para el bridge del script Gasca. "
            f"Permitidos: {sorted(SUPPORTED_REPORT_TYPES)}"
        )

    if not run_mode:
        raise ValueError("El 'run_mode' es obligatorio.")

    if not snapshot_kind:
        raise ValueError("El 'snapshot_kind' es obligatorio.")


def _get_configured_filename_prefixes() -> dict[str, str]:
    configured = current_app.config.get("WAREHOUSE_GASCA_SCRIPT_FILENAME_PREFIXES")
    if not isinstance(configured, dict):
        return dict(DEFAULT_FILENAME_PREFIXES)

    merged = dict(DEFAULT_FILENAME_PREFIXES)
    for key, value in configured.items():
        if key in SUPPORTED_REPORT_TYPES and isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged


def _get_configured_output_dirs() -> dict[str, str]:
    configured = current_app.config.get("WAREHOUSE_GASCA_SCRIPT_OUTPUT_DIRS")
    if not isinstance(configured, dict):
        return dict(DEFAULT_OUTPUT_DIRS)

    merged = dict(DEFAULT_OUTPUT_DIRS)
    for key, value in configured.items():
        if key in SUPPORTED_REPORT_TYPES and isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged


def _get_recent_file_lookback_seconds() -> int:
    value = current_app.config.get(
        "WAREHOUSE_GASCA_SCRIPT_RECENT_FILE_LOOKBACK_SECONDS",
        3600,
    )
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 3600

    return max(parsed, 60)


def _resolve_runner_from_callable_config() -> Callable[..., Any] | None:
    runner = current_app.config.get("WAREHOUSE_GASCA_SCRIPT_RUNNER")
    return runner if callable(runner) else None


def _resolve_runner_from_module_config() -> Callable[..., Any] | None:
    module_path = current_app.config.get("WAREHOUSE_GASCA_SCRIPT_MODULE")
    entrypoint_name = current_app.config.get("WAREHOUSE_GASCA_SCRIPT_ENTRYPOINT")

    if not module_path or not isinstance(module_path, str):
        return None

    if not entrypoint_name or not isinstance(entrypoint_name, str):
        raise NotImplementedError(
            "Para usar WAREHOUSE_GASCA_SCRIPT_MODULE también debes configurar "
            "'WAREHOUSE_GASCA_SCRIPT_ENTRYPOINT'."
        )

    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        raise GascaProducerError(
            f"No se pudo importar el módulo del script Gasca: {module_path!r}"
        ) from exc

    runner = getattr(module, entrypoint_name, None)
    if not callable(runner):
        raise GascaProducerError(
            f"El entrypoint configurado no es callable: {module_path}.{entrypoint_name}"
        )

    return runner


def _resolve_script_runner() -> Callable[..., Any]:
    callable_runner = _resolve_runner_from_callable_config()
    if callable_runner is not None:
        return callable_runner

    module_runner = _resolve_runner_from_module_config()
    if module_runner is not None:
        return module_runner

    raise NotImplementedError(
        "No hay un runner del script Gasca configurado. "
        "Configura uno de estos caminos:\n"
        "1) app.config['WAREHOUSE_GASCA_SCRIPT_RUNNER'] = callable\n"
        "2) app.config['WAREHOUSE_GASCA_SCRIPT_MODULE'] + "
        "app.config['WAREHOUSE_GASCA_SCRIPT_ENTRYPOINT']"
    )


def _result_has_direct_artifact_payload(result: Any) -> bool:
    if isinstance(result, ProducedGascaArtifact):
        return True

    if isinstance(result, (str, Path)):
        return True

    if isinstance(result, dict):
        return bool(
            result.get("file_path")
            or result.get("file_bytes") is not None
            or result.get("original_filename")
        )

    return False


def _build_artifact_from_path(
    *,
    report_type_key: str,
    file_path: Path,
    captured_at: datetime,
    extra_metadata: dict[str, Any] | None = None,
) -> ProducedGascaArtifact:
    artifact = ProducedGascaArtifact(
        report_type_key=report_type_key,
        original_filename=file_path.name,
        content_type=_guess_content_type(file_path.name),
        captured_at=captured_at,
        file_path=str(file_path),
        file_bytes=None,
        metadata=extra_metadata or {},
    )
    artifact.validate()
    return artifact


def _normalize_runner_result(
    *,
    report_type_key: str,
    result: Any,
    requested_at: datetime,
) -> ProducedGascaArtifact | dict[str, Any] | str | Path:
    """
    Este bridge devuelve algo que el adapter ya sabe normalizar.
    Aun así, aquí validamos lo básico para cortar errores antes.
    """
    if isinstance(result, ProducedGascaArtifact):
        result.validate()
        return result

    if isinstance(result, (str, Path)):
        path = Path(result)
        if not path.exists():
            raise GascaProducerError(
                f"El runner devolvió una ruta que no existe: {path}"
            )
        artifact = _build_artifact_from_path(
            report_type_key=report_type_key,
            file_path=path,
            captured_at=requested_at,
            extra_metadata={"bridge_source": "direct_path_result"},
        )
        return artifact

    if isinstance(result, dict):
        payload = dict(result)

        if payload.get("captured_at") is not None:
            payload["captured_at"] = _ensure_datetime(payload["captured_at"])
        else:
            payload["captured_at"] = requested_at

        if payload.get("file_path"):
            file_path = Path(str(payload["file_path"]))
            if not file_path.exists():
                raise GascaProducerError(
                    f"El runner devolvió un file_path que no existe: {file_path}"
                )

            if not payload.get("original_filename"):
                payload["original_filename"] = file_path.name

            if not payload.get("content_type"):
                payload["content_type"] = _guess_content_type(file_path.name)

        if payload.get("original_filename") and not payload.get("content_type"):
            payload["content_type"] = _guess_content_type(
                str(payload["original_filename"])
            )

        payload.setdefault("report_type_key", report_type_key)
        payload.setdefault("metadata", {})
        payload["metadata"] = {
            "bridge_source": "dict_result",
            **(payload["metadata"] or {}),
        }

        return payload

    raise GascaProducerError(
        "El runner del script Gasca devolvió un tipo no soportado. "
        "Debe devolver ProducedGascaArtifact, dict, str, Path o None."
    )


def _resolve_recent_file_from_disk(
    *,
    report_type_key: str,
    requested_at: datetime,
) -> ProducedGascaArtifact:
    output_dirs = _get_configured_output_dirs()
    prefixes = _get_configured_filename_prefixes()
    lookback_seconds = _get_recent_file_lookback_seconds()

    output_dir = Path(output_dirs[report_type_key])
    prefix = prefixes[report_type_key]

    if not output_dir.exists() or not output_dir.is_dir():
        raise GascaProducerError(
            f"No existe el directorio de salida configurado para {report_type_key!r}: "
            f"{output_dir}"
        )

    min_epoch = requested_at.timestamp() - lookback_seconds
    candidates: list[Path] = []

    for path in output_dir.glob(f"{prefix}*.xlsx"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue

        if mtime >= min_epoch:
            candidates.append(path)

    if not candidates:
        raise GascaProducerError(
            "El script no devolvió el archivo directamente y tampoco se encontró "
            f"un .xlsx reciente en {output_dir} con prefijo {prefix!r}."
        )

    latest_path = max(candidates, key=lambda p: p.stat().st_mtime)
    latest_mtime = datetime.fromtimestamp(
        latest_path.stat().st_mtime,
        tz=timezone.utc,
    )

    current_app.logger.info(
        "Gasca script bridge resolved artifact from disk: report_type_key=%s path=%s",
        report_type_key,
        latest_path,
    )

    return _build_artifact_from_path(
        report_type_key=report_type_key,
        file_path=latest_path,
        captured_at=latest_mtime,
        extra_metadata={
            "bridge_source": "recent_disk_scan",
            "output_dir": str(output_dir),
            "filename_prefix": prefix,
            "lookback_seconds": lookback_seconds,
        },
    )


def _call_runner(
    *,
    runner: Callable[..., Any],
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
    requested_by: str | None,
    trigger_source: str | None,
    requested_at: datetime,
) -> Any:
    return runner(
        report_type_key=report_type_key,
        run_mode=run_mode,
        snapshot_kind=snapshot_kind,
        requested_by=requested_by,
        trigger_source=trigger_source,
        requested_at=requested_at,
    )


def extract_with_gasca_script(
    *,
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
    requested_by: str | None = None,
    trigger_source: str | None = None,
    requested_at: datetime | None = None,
) -> ProducedGascaArtifact | dict[str, Any] | str | Path:
    """
    Bridge entre Suite y el script actual de Gasca.

    Contrato:
    - Ejecuta un runner real configurado por app.config
    - Si el runner devuelve el artefacto/ruta, la usa
    - Si el runner no devuelve artefacto directo (None), busca el archivo en disco
      con base en output_dir + prefijo por report_type_key

    Config keys soportadas:
    - WAREHOUSE_GASCA_SCRIPT_RUNNER
    - WAREHOUSE_GASCA_SCRIPT_MODULE
    - WAREHOUSE_GASCA_SCRIPT_ENTRYPOINT
    - WAREHOUSE_GASCA_SCRIPT_OUTPUT_DIRS
    - WAREHOUSE_GASCA_SCRIPT_FILENAME_PREFIXES
    - WAREHOUSE_GASCA_SCRIPT_RECENT_FILE_LOOKBACK_SECONDS
    """
    _validate_inputs(
        report_type_key=report_type_key,
        run_mode=run_mode,
        snapshot_kind=snapshot_kind,
    )

    effective_requested_at = requested_at or _utc_now()
    runner = _resolve_script_runner()

    current_app.logger.info(
        "Gasca script bridge dispatch: report_type_key=%s run_mode=%s snapshot_kind=%s runner=%s",
        report_type_key,
        run_mode,
        snapshot_kind,
        getattr(runner, "__name__", runner.__class__.__name__),
    )

    try:
        raw_result = _call_runner(
            runner=runner,
            report_type_key=report_type_key,
            run_mode=run_mode,
            snapshot_kind=snapshot_kind,
            requested_by=requested_by,
            trigger_source=trigger_source,
            requested_at=effective_requested_at,
        )
    except NotImplementedError:
        raise
    except Exception as exc:
        raise GascaProducerError(
            f"Falló la ejecución del runner configurado para {report_type_key!r}."
        ) from exc

    if raw_result is None:
        return _resolve_recent_file_from_disk(
            report_type_key=report_type_key,
            requested_at=effective_requested_at,
        )

    if _result_has_direct_artifact_payload(raw_result):
        return _normalize_runner_result(
            report_type_key=report_type_key,
            result=raw_result,
            requested_at=effective_requested_at,
        )

    raise GascaProducerError(
        "El runner del script Gasca devolvió un valor no interpretable. "
        "Devuelve un artifact, dict, ruta o None."
    )