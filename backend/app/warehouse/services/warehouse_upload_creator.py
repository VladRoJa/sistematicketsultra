# backend/app/warehouse/services/warehouse_upload_creator.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
import inspect
from pathlib import Path
from typing import Any, Callable

from flask import current_app

from app.warehouse.services.gasca_job_orchestrator import WarehouseUploadError


DEFAULT_SOURCE_KEY = "gasca"


@dataclass(slots=True)
class WarehouseUploadCommand:
    report_type_key: str
    original_filename: str
    content_type: str
    file_path: str | None
    file_bytes: bytes | None
    captured_at: datetime
    source_key: str
    metadata: dict[str, Any]


def register_warehouse_upload_creator(app) -> None:
    """
    Registra este adaptador como hook principal para creación de uploads internos.

    Uso esperado más adelante en init/app factory:
        register_warehouse_upload_creator(app)

    Esto deja resuelto:
        app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = create_warehouse_upload_from_artifact
    """
    app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = create_warehouse_upload_from_artifact


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
            raise WarehouseUploadError(
                f"No se pudo parsear 'captured_at' desde string ISO: {value!r}"
            ) from exc

    if value is None:
        return _utc_now()

    raise WarehouseUploadError(
        "Se recibió 'captured_at' con un tipo no soportado."
    )


def _validate_command(command: WarehouseUploadCommand) -> None:
    if not command.report_type_key:
        raise ValueError("El 'report_type_key' es obligatorio.")

    if not command.original_filename:
        raise ValueError("El 'original_filename' es obligatorio.")

    if not command.content_type:
        raise ValueError("El 'content_type' es obligatorio.")

    has_path = bool(command.file_path)
    has_bytes = command.file_bytes is not None

    if not has_path and not has_bytes:
        raise ValueError(
            "Se requiere 'file_path' o 'file_bytes' para crear el upload."
        )

    if has_path:
        path = Path(command.file_path)  # type: ignore[arg-type]
        if not path.exists():
            raise ValueError(
                f"El archivo indicado en 'file_path' no existe: {path}"
            )


def _import_callable(module_path: str, entrypoint_name: str) -> Callable[..., Any]:
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        raise WarehouseUploadError(
            f"No se pudo importar el módulo configurado: {module_path!r}"
        ) from exc

    fn = getattr(module, entrypoint_name, None)
    if not callable(fn):
        raise WarehouseUploadError(
            f"El entrypoint configurado no es callable: {module_path}.{entrypoint_name}"
        )

    return fn


def _resolve_upload_impl() -> Callable[..., Any]:
    """
    Resuelve la implementación real del upload documental.

    Caminos soportados:
    1) app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR_IMPL"] = callable
    2) app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR_MODULE"] + ENTRYPOINT
    """
    direct_callable = current_app.config.get("WAREHOUSE_INTERNAL_UPLOAD_CREATOR_IMPL")
    if callable(direct_callable):
        return direct_callable

    module_path = current_app.config.get("WAREHOUSE_INTERNAL_UPLOAD_CREATOR_MODULE")
    entrypoint_name = current_app.config.get("WAREHOUSE_INTERNAL_UPLOAD_CREATOR_ENTRYPOINT")

    if module_path is None and entrypoint_name is None:
        raise NotImplementedError(
            "No hay implementación configurada para crear uploads internos de Warehouse. "
            "Configura uno de estos caminos:\n"
            "1) app.config['WAREHOUSE_INTERNAL_UPLOAD_CREATOR_IMPL'] = callable\n"
            "2) app.config['WAREHOUSE_INTERNAL_UPLOAD_CREATOR_MODULE'] + "
            "app.config['WAREHOUSE_INTERNAL_UPLOAD_CREATOR_ENTRYPOINT']"
        )

    if not isinstance(module_path, str) or not module_path.strip():
        raise WarehouseUploadError(
            "Debes configurar 'WAREHOUSE_INTERNAL_UPLOAD_CREATOR_MODULE' como string."
        )

    if not isinstance(entrypoint_name, str) or not entrypoint_name.strip():
        raise WarehouseUploadError(
            "Debes configurar 'WAREHOUSE_INTERNAL_UPLOAD_CREATOR_ENTRYPOINT' como string."
        )

    return _import_callable(module_path.strip(), entrypoint_name.strip())


def _build_callable_kwargs(command: WarehouseUploadCommand) -> dict[str, Any]:
    return {
        "report_type_key": command.report_type_key,
        "original_filename": command.original_filename,
        "content_type": command.content_type,
        "file_path": command.file_path,
        "file_bytes": command.file_bytes,
        "captured_at": command.captured_at,
        "source_key": command.source_key,
        "metadata": command.metadata,
    }


def _invoke_callable_flexibly(
    fn: Callable[..., Any],
    *,
    kwargs: dict[str, Any],
    description: str,
) -> Any:
    """
    Soporta implementaciones nuevas con kwargs explícitos y adaptadores viejos
    que acepten menos parámetros o un solo payload.
    """
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(**kwargs)

    parameters = signature.parameters

    if not parameters:
        return fn()

    accepts_var_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in parameters.values()
    )
    if accepts_var_kwargs:
        return fn(**kwargs)

    accepted_kwargs: dict[str, Any] = {}
    required_params_without_default: list[str] = []

    for name, param in parameters.items():
        if param.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            continue

        if name in kwargs:
            accepted_kwargs[name] = kwargs[name]
        elif param.default is inspect.Parameter.empty:
            required_params_without_default.append(name)

    # Soporte para estilo fn(command_dict)
    if (
        len(parameters) == 1
        and "command" in parameters
        and "command" in required_params_without_default
    ):
        return fn(kwargs)

    if required_params_without_default:
        raise WarehouseUploadError(
            f"La implementación configurada para {description} requiere parámetros "
            f"no soportados por el adaptador actual: {required_params_without_default}"
        )

    return fn(**accepted_kwargs)


def _normalize_upload_result(result: Any) -> dict[str, Any]:
    """
    Formatos soportados de respuesta:

    1) int -> warehouse_upload_id
    2) dict con warehouse_upload_id
    3) objeto con atributo .id
    """
    if isinstance(result, int):
        return {
            "warehouse_upload_id": result,
            "upload_status": "created",
            "metadata": {},
        }

    if isinstance(result, dict):
        upload_id = result.get("warehouse_upload_id")
        if not isinstance(upload_id, int):
            raise WarehouseUploadError(
                "La implementación del upload debe devolver 'warehouse_upload_id' entero."
            )

        return {
            "warehouse_upload_id": upload_id,
            "upload_status": result.get("upload_status", "created"),
            "metadata": result.get("metadata") or {},
        }

    upload_id = getattr(result, "id", None)
    if isinstance(upload_id, int):
        return {
            "warehouse_upload_id": upload_id,
            "upload_status": getattr(result, "upload_status", "created"),
            "metadata": getattr(result, "metadata", {}) or {},
        }

    raise WarehouseUploadError(
        "La implementación del upload devolvió un tipo no soportado. "
        "Debe devolver int, dict o un objeto con atributo 'id'."
    )


def create_warehouse_upload_from_artifact(
    *,
    report_type_key: str,
    original_filename: str,
    content_type: str,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
    captured_at: datetime | str | None = None,
    source_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Hook principal para crear el upload documental de Warehouse a partir
    de un artifact ya producido por Gasca.

    Este archivo NO implementa la persistencia real;
    solo estandariza el contrato y delega a una implementación configurable.
    """
    command = WarehouseUploadCommand(
        report_type_key=report_type_key,
        original_filename=original_filename,
        content_type=content_type,
        file_path=file_path,
        file_bytes=file_bytes,
        captured_at=_ensure_datetime(captured_at),
        source_key=source_key or DEFAULT_SOURCE_KEY,
        metadata=metadata or {},
    )
    _validate_command(command)

    upload_impl = _resolve_upload_impl()

    current_app.logger.info(
        "Warehouse upload creator dispatch: report_type_key=%s original_filename=%s source_key=%s impl=%s",
        command.report_type_key,
        command.original_filename,
        command.source_key,
        getattr(upload_impl, "__name__", upload_impl.__class__.__name__),
    )

    try:
        raw_result = _invoke_callable_flexibly(
            upload_impl,
            kwargs=_build_callable_kwargs(command),
            description="warehouse upload creator",
        )
    except NotImplementedError:
        raise
    except Exception as exc:
        raise WarehouseUploadError(
            f"Falló la implementación configurada para crear el upload de "
            f"{command.report_type_key!r}."
        ) from exc

    normalized_result = _normalize_upload_result(raw_result)

    current_app.logger.info(
        "Warehouse upload created successfully: report_type_key=%s warehouse_upload_id=%s",
        command.report_type_key,
        normalized_result["warehouse_upload_id"],
    )

    return normalized_result