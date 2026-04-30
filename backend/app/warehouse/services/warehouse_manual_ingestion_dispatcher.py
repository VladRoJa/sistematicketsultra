# backend/app/warehouse/services/warehouse_manual_ingestion_dispatcher.py

from __future__ import annotations

import importlib
import inspect
from typing import Any, Callable

from flask import current_app


MANUAL_STRUCTURED_TOTALPASS_REPORT_TYPE_KEY = "ingresos_totalpass"
MANUAL_STRUCTURED_WELLHUB_REPORT_TYPE_KEY = "ingresos_wellhub"
MANUAL_STRUCTURED_TRACK_MONTHLY_TARGETS_REPORT_TYPE_KEY = "track_monthly_targets"

SUPPORTED_MANUAL_STRUCTURED_REPORT_TYPES = frozenset(
    {
        MANUAL_STRUCTURED_TOTALPASS_REPORT_TYPE_KEY,
        MANUAL_STRUCTURED_WELLHUB_REPORT_TYPE_KEY,
        MANUAL_STRUCTURED_TRACK_MONTHLY_TARGETS_REPORT_TYPE_KEY,
    }
)


class WarehouseManualIngestionDispatcherError(RuntimeError):
    """Error base del dispatcher de ingestas estructuradas manuales."""


def register_warehouse_manual_ingestion_dispatcher(app) -> None:
    """
    Registra el dispatcher manual como hook runtime.

    Esto deja disponible:
        app.config["WAREHOUSE_MANUAL_INGESTION_DISPATCHER"]
    """
    app.config["WAREHOUSE_MANUAL_INGESTION_DISPATCHER"] = (
        dispatch_manual_structured_ingestion
    )


def _import_callable(module_path: str, entrypoint_name: str) -> Callable[..., Any]:
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        raise WarehouseManualIngestionDispatcherError(
            f"No se pudo importar el módulo configurado: {module_path!r}"
        ) from exc

    fn = getattr(module, entrypoint_name, None)
    if not callable(fn):
        raise WarehouseManualIngestionDispatcherError(
            f"El entrypoint configurado no es callable: {module_path}.{entrypoint_name}"
        )

    return fn


def _resolve_callable(
    *,
    direct_callable_key: str,
    module_key: str,
    entrypoint_key: str,
    description: str,
) -> Callable[..., Any]:
    direct_callable = current_app.config.get(direct_callable_key)
    if callable(direct_callable):
        return direct_callable

    module_path = current_app.config.get(module_key)
    entrypoint_name = current_app.config.get(entrypoint_key)

    if not isinstance(module_path, str) or not module_path.strip():
        raise NotImplementedError(
            f"No hay implementación configurada para {description}. "
            f"Configura '{direct_callable_key}' o "
            f"'{module_key}' + '{entrypoint_key}'."
        )

    if not isinstance(entrypoint_name, str) or not entrypoint_name.strip():
        raise WarehouseManualIngestionDispatcherError(
            f"Debes configurar '{entrypoint_key}' como string."
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
        raise WarehouseManualIngestionDispatcherError(
            f"La implementación configurada para {description} requiere parámetros "
            f"no soportados por el adaptador actual: {required_params_without_default}"
        )

    return fn(**accepted_kwargs)


def _resolve_upload_loader() -> Callable[..., Any]:
    return _resolve_callable(
        direct_callable_key="WAREHOUSE_UPLOAD_LOADER",
        module_key="WAREHOUSE_UPLOAD_LOADER_MODULE",
        entrypoint_key="WAREHOUSE_UPLOAD_LOADER_ENTRYPOINT",
        description="cargar uploads documentales de Warehouse",
    )


def _resolve_totalpass_ingestor() -> Callable[..., Any]:
    return _resolve_callable(
        direct_callable_key="WAREHOUSE_INGRESOS_TOTALPASS_INGESTOR",
        module_key="WAREHOUSE_INGRESOS_TOTALPASS_INGESTOR_MODULE",
        entrypoint_key="WAREHOUSE_INGRESOS_TOTALPASS_INGESTOR_ENTRYPOINT",
        description="ingestor estructurado de ingresos_totalpass",
    )


def _resolve_wellhub_ingestor() -> Callable[..., Any]:
    return _resolve_callable(
        direct_callable_key="WAREHOUSE_INGRESOS_WELLHUB_INGESTOR",
        module_key="WAREHOUSE_INGRESOS_WELLHUB_INGESTOR_MODULE",
        entrypoint_key="WAREHOUSE_INGRESOS_WELLHUB_INGESTOR_ENTRYPOINT",
        description="ingestor estructurado de ingresos_wellhub",
    )

def _resolve_track_monthly_targets_ingestor() -> Callable[..., Any]:
    return _resolve_callable(
        direct_callable_key="WAREHOUSE_TRACK_MONTHLY_TARGETS_INGESTOR",
        module_key="WAREHOUSE_TRACK_MONTHLY_TARGETS_INGESTOR_MODULE",
        entrypoint_key="WAREHOUSE_TRACK_MONTHLY_TARGETS_INGESTOR_ENTRYPOINT",
        description="ingestor estructurado de track_monthly_targets",
    )

def _load_warehouse_upload(warehouse_upload_id: int) -> dict[str, Any] | None:
    loader = _resolve_upload_loader()

    raw_result = _invoke_callable_flexibly(
        loader,
        kwargs={"warehouse_upload_id": warehouse_upload_id},
        description="warehouse upload loader",
    )

    if raw_result is None:
        return None

    if not isinstance(raw_result, dict):
        raise WarehouseManualIngestionDispatcherError(
            "El loader del upload devolvió un tipo no soportado. Debe devolver dict o None."
        )

    return raw_result


def _resolve_snapshot_kind_for_manual_upload(
    *,
    loaded_upload: dict[str, Any],
) -> str:
    report_type_key = str(loaded_upload.get("report_type_key") or "").strip()

    if report_type_key in {
        MANUAL_STRUCTURED_TOTALPASS_REPORT_TYPE_KEY,
        MANUAL_STRUCTURED_WELLHUB_REPORT_TYPE_KEY,
    }:
        return "daily"

    raise WarehouseManualIngestionDispatcherError(
        f"No hay snapshot_kind configurado para el report_type_key manual {report_type_key!r}."
    )


def _dispatch_totalpass_ingestion(
    *,
    warehouse_upload_id: int,
    requested_by: str | None,
    ingestion_source: str | None,
    snapshot_kind: str,
) -> dict[str, Any]:
    ingestor = _resolve_totalpass_ingestor()

    raw_result = _invoke_callable_flexibly(
        ingestor,
        kwargs={
            "warehouse_upload_id": warehouse_upload_id,
            "snapshot_kind": snapshot_kind,
            "requested_by": requested_by,
            "ingestion_source": ingestion_source,
        },
        description="ingestor estructurado manual de ingresos_totalpass",
    )

    if isinstance(raw_result, dict):
        return raw_result

    raise WarehouseManualIngestionDispatcherError(
        "El ingestor manual de ingresos_totalpass devolvió un tipo no soportado. "
        "Debe devolver dict."
    )


def _dispatch_wellhub_ingestion(
    *,
    warehouse_upload_id: int,
    requested_by: str | None,
    ingestion_source: str | None,
    snapshot_kind: str,
) -> dict[str, Any]:
    ingestor = _resolve_wellhub_ingestor()

    raw_result = _invoke_callable_flexibly(
        ingestor,
        kwargs={
            "warehouse_upload_id": warehouse_upload_id,
            "snapshot_kind": snapshot_kind,
            "requested_by": requested_by,
            "ingestion_source": ingestion_source,
        },
        description="ingestor estructurado manual de ingresos_wellhub",
    )

    if isinstance(raw_result, dict):
        return raw_result

    raise WarehouseManualIngestionDispatcherError(
        "El ingestor manual de ingresos_wellhub devolvió un tipo no soportado. "
        "Debe devolver dict."
    )

def _dispatch_track_monthly_targets_ingestion(
    *,
    warehouse_upload_id: int,
    requested_by: str | None,
    ingestion_source: str | None,
) -> dict[str, Any]:
    ingestor = _resolve_track_monthly_targets_ingestor()

    raw_result = _invoke_callable_flexibly(
        ingestor,
        kwargs={
            "warehouse_upload_id": warehouse_upload_id,
            "requested_by": requested_by,
            "ingestion_source": ingestion_source,
        },
        description="ingestor estructurado manual de track_monthly_targets",
    )

    if isinstance(raw_result, dict):
        return raw_result

    raise WarehouseManualIngestionDispatcherError(
        "El ingestor manual de track_monthly_targets devolvió un tipo no soportado. "
        "Debe devolver dict."
    )

def dispatch_manual_structured_ingestion(
    *,
    warehouse_upload_id: int,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
) -> dict[str, Any]:
    if not isinstance(warehouse_upload_id, int) or warehouse_upload_id <= 0:
        raise ValueError("'warehouse_upload_id' debe ser entero positivo.")

    loaded_upload = _load_warehouse_upload(warehouse_upload_id)
    if loaded_upload is None:
        raise WarehouseManualIngestionDispatcherError(
            f"No se encontró el warehouse_upload_id={warehouse_upload_id}."
        )

    report_type_key = str(loaded_upload.get("report_type_key") or "").strip()
    if not report_type_key:
        raise WarehouseManualIngestionDispatcherError(
            "El upload cargado no contiene report_type_key."
        )

    current_app.logger.info(
        "Warehouse manual ingestion dispatcher: warehouse_upload_id=%s report_type_key=%s",
        warehouse_upload_id,
        report_type_key,
    )

    if report_type_key not in SUPPORTED_MANUAL_STRUCTURED_REPORT_TYPES:
        return {
            "ingestion_status": "not_applicable",
            "warehouse_upload_id": warehouse_upload_id,
            "report_type_key": report_type_key,
            "metadata": {
                "reason": "manual_structured_ingestion_not_applicable",
            },
        }

    if report_type_key == MANUAL_STRUCTURED_TRACK_MONTHLY_TARGETS_REPORT_TYPE_KEY:
        ingestion_result = _dispatch_track_monthly_targets_ingestion(
            warehouse_upload_id=warehouse_upload_id,
            requested_by=requested_by,
            ingestion_source=ingestion_source,
        )
        return {
            "ingestion_status": ingestion_result.get("status", "ingested"),
            "warehouse_upload_id": warehouse_upload_id,
            "report_type_key": report_type_key,
            "structured_result": ingestion_result,
        }

    snapshot_kind = _resolve_snapshot_kind_for_manual_upload(
        loaded_upload=loaded_upload,
    )

    if report_type_key == MANUAL_STRUCTURED_TOTALPASS_REPORT_TYPE_KEY:
        ingestion_result = _dispatch_totalpass_ingestion(
            warehouse_upload_id=warehouse_upload_id,
            requested_by=requested_by,
            ingestion_source=ingestion_source,
            snapshot_kind=snapshot_kind,
        )
        return {
            "ingestion_status": ingestion_result.get("status", "ingested"),
            "warehouse_upload_id": warehouse_upload_id,
            "report_type_key": report_type_key,
            "snapshot_kind": snapshot_kind,
            "structured_result": ingestion_result,
        }

    if report_type_key == MANUAL_STRUCTURED_WELLHUB_REPORT_TYPE_KEY:
        ingestion_result = _dispatch_wellhub_ingestion(
            warehouse_upload_id=warehouse_upload_id,
            requested_by=requested_by,
            ingestion_source=ingestion_source,
            snapshot_kind=snapshot_kind,
        )
        return {
            "ingestion_status": ingestion_result.get("status", "ingested"),
            "warehouse_upload_id": warehouse_upload_id,
            "report_type_key": report_type_key,
            "snapshot_kind": snapshot_kind,
            "structured_result": ingestion_result,
        }

    raise WarehouseManualIngestionDispatcherError(
        f"Dispatcher manual sin branch para report_type_key={report_type_key!r}."
    )