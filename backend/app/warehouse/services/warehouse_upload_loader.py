# backend/app/warehouse/services/warehouse_upload_loader.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
import inspect
from typing import Any, Callable

from flask import current_app


class WarehouseUploadLoaderError(RuntimeError):
    """Error base del loader de uploads documentales."""


@dataclass(slots=True)
class LoadedWarehouseUpload:
    warehouse_upload_id: int
    report_type_key: str
    original_filename: str
    content_type: str | None = None
    storage_path: str | None = None
    captured_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "warehouse_upload_id": self.warehouse_upload_id,
            "report_type_key": self.report_type_key,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "storage_path": self.storage_path,
            "captured_at": (
                self.captured_at.isoformat() if isinstance(self.captured_at, datetime) else None
            ),
            "metadata": self.metadata or {},
        }


def register_warehouse_upload_loader(app) -> None:
    """
    Registra este adaptador como hook runtime.

    Uso esperado más adelante en init/app factory:
        register_warehouse_upload_loader(app)

    Esto deja resuelto:
        app.config["WAREHOUSE_UPLOAD_LOADER"] = load_warehouse_upload
    """
    app.config["WAREHOUSE_UPLOAD_LOADER"] = load_warehouse_upload


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

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
            raise WarehouseUploadLoaderError(
                f"No se pudo parsear datetime desde string ISO: {value!r}"
            ) from exc

    raise WarehouseUploadLoaderError(
        f"Tipo no soportado para captured_at: {type(value).__name__}"
    )


def _import_callable(module_path: str, entrypoint_name: str) -> Callable[..., Any]:
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        raise WarehouseUploadLoaderError(
            f"No se pudo importar el módulo configurado: {module_path!r}"
        ) from exc

    fn = getattr(module, entrypoint_name, None)
    if not callable(fn):
        raise WarehouseUploadLoaderError(
            f"El entrypoint configurado no es callable: {module_path}.{entrypoint_name}"
        )

    return fn


def _resolve_loader_impl() -> Callable[..., Any]:
    """
    Caminos soportados:
    1) app.config["WAREHOUSE_UPLOAD_LOADER_IMPL"] = callable
    2) app.config["WAREHOUSE_UPLOAD_LOADER_MODULE"] + ENTRYPOINT
    """
    direct_callable = current_app.config.get("WAREHOUSE_UPLOAD_LOADER_IMPL")
    if callable(direct_callable):
        return direct_callable

    module_path = current_app.config.get("WAREHOUSE_UPLOAD_LOADER_MODULE")
    entrypoint_name = current_app.config.get("WAREHOUSE_UPLOAD_LOADER_ENTRYPOINT")

    if module_path is None and entrypoint_name is None:
        raise NotImplementedError(
            "No hay implementación configurada para cargar uploads documentales. "
            "Configura uno de estos caminos:\n"
            "1) app.config['WAREHOUSE_UPLOAD_LOADER_IMPL'] = callable\n"
            "2) app.config['WAREHOUSE_UPLOAD_LOADER_MODULE'] + "
            "app.config['WAREHOUSE_UPLOAD_LOADER_ENTRYPOINT']"
        )

    if not isinstance(module_path, str) or not module_path.strip():
        raise WarehouseUploadLoaderError(
            "Debes configurar 'WAREHOUSE_UPLOAD_LOADER_MODULE' como string."
        )

    if not isinstance(entrypoint_name, str) or not entrypoint_name.strip():
        raise WarehouseUploadLoaderError(
            "Debes configurar 'WAREHOUSE_UPLOAD_LOADER_ENTRYPOINT' como string."
        )

    return _import_callable(module_path.strip(), entrypoint_name.strip())


def _invoke_callable_flexibly(
    fn: Callable[..., Any],
    *,
    kwargs: dict[str, Any],
    description: str,
) -> Any:
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

    if (
        len(parameters) == 1
        and "command" in parameters
        and "command" in required_params_without_default
    ):
        return fn(kwargs)

    if required_params_without_default:
        raise WarehouseUploadLoaderError(
            f"La implementación configurada para {description} requiere parámetros "
            f"no soportados por el adaptador actual: {required_params_without_default}"
        )

    return fn(**accepted_kwargs)


def _normalize_loaded_upload(result: Any, warehouse_upload_id: int) -> dict[str, Any] | None:
    """
    Formatos soportados:
    1) None
    2) dict
    3) LoadedWarehouseUpload
    4) objeto con atributos equivalentes
    """
    if result is None:
        return None

    if isinstance(result, LoadedWarehouseUpload):
        payload = result.to_dict()
        payload["warehouse_upload_id"] = warehouse_upload_id
        return payload

    if isinstance(result, dict):
        report_type_key = result.get("report_type_key")
        original_filename = result.get("original_filename")

        if not isinstance(report_type_key, str) or not report_type_key.strip():
            raise WarehouseUploadLoaderError(
                "El loader debe devolver 'report_type_key' válido."
            )

        if not isinstance(original_filename, str) or not original_filename.strip():
            raise WarehouseUploadLoaderError(
                "El loader debe devolver 'original_filename' válido."
            )

        return {
            "warehouse_upload_id": int(result.get("warehouse_upload_id", warehouse_upload_id)),
            "report_type_key": report_type_key.strip(),
            "original_filename": original_filename.strip(),
            "content_type": result.get("content_type"),
            "storage_path": result.get("storage_path") or result.get("file_path"),
            "captured_at": (
                _ensure_datetime(result.get("captured_at")).isoformat()
                if result.get("captured_at") is not None
                else None
            ),
            "metadata": result.get("metadata") or {},
        }

    report_type_key = getattr(result, "report_type_key", None)
    original_filename = getattr(result, "original_filename", None)

    if not isinstance(report_type_key, str) or not report_type_key.strip():
        raise WarehouseUploadLoaderError(
            "El objeto cargado no expone 'report_type_key' válido."
        )

    if not isinstance(original_filename, str) or not original_filename.strip():
        raise WarehouseUploadLoaderError(
            "El objeto cargado no expone 'original_filename' válido."
        )

    captured_at = getattr(result, "captured_at", None)

    return {
        "warehouse_upload_id": int(getattr(result, "id", warehouse_upload_id)),
        "report_type_key": report_type_key.strip(),
        "original_filename": original_filename.strip(),
        "content_type": getattr(result, "content_type", None),
        "storage_path": getattr(result, "storage_path", None)
        or getattr(result, "file_path", None),
        "captured_at": (
            _ensure_datetime(captured_at).isoformat() if captured_at is not None else None
        ),
        "metadata": getattr(result, "metadata", {}) or {},
    }


def load_warehouse_upload(*, warehouse_upload_id: int) -> dict[str, Any] | None:
    """
    Hook principal para cargar un upload documental de Warehouse.

    Este archivo no implementa la consulta real;
    solo estandariza el contrato y delega a una implementación configurable.
    """
    if not isinstance(warehouse_upload_id, int) or warehouse_upload_id <= 0:
        raise ValueError("'warehouse_upload_id' debe ser entero positivo.")

    loader_impl = _resolve_loader_impl()

    current_app.logger.info(
        "Warehouse upload loader dispatch: warehouse_upload_id=%s impl=%s",
        warehouse_upload_id,
        getattr(loader_impl, "__name__", loader_impl.__class__.__name__),
    )

    try:
        raw_result = _invoke_callable_flexibly(
            loader_impl,
            kwargs={"warehouse_upload_id": warehouse_upload_id},
            description="warehouse upload loader",
        )
    except NotImplementedError:
        raise
    except Exception as exc:
        raise WarehouseUploadLoaderError(
            f"Falló la implementación configurada para cargar el upload {warehouse_upload_id}."
        ) from exc

    normalized = _normalize_loaded_upload(raw_result, warehouse_upload_id)

    if normalized is None:
        current_app.logger.info(
            "Warehouse upload loader: warehouse_upload_id=%s no encontrado.",
            warehouse_upload_id,
        )
        return None

    current_app.logger.info(
        "Warehouse upload loaded successfully: warehouse_upload_id=%s report_type_key=%s",
        normalized["warehouse_upload_id"],
        normalized["report_type_key"],
    )

    return normalized