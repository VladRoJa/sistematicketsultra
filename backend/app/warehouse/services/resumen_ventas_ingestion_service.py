from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from inspect import signature
from typing import Any, Callable

from flask import current_app

from app.warehouse.services.resumen_ventas_parser import (
    parse_resumen_ventas_xlsx,
)
from app.warehouse.services.resumen_ventas_repository import (
    persist_resumen_ventas_snapshot,
)


RESUMEN_VENTAS_REPORT_TYPE_KEY = "resumen_ventas"
RESUMEN_VENTAS_PERIOD_TYPE = "rango"


class ResumenVentasIngestionError(RuntimeError):
    pass


class ResumenVentasUploadLoadError(ResumenVentasIngestionError):
    pass


class ResumenVentasParseInvocationError(ResumenVentasIngestionError):
    pass


class ResumenVentasPersistError(ResumenVentasIngestionError):
    pass


def register_resumen_ventas_ingestor(app) -> None:
    app.config["WAREHOUSE_RESUMEN_VENTAS_INGESTOR"] = (
        ingest_resumen_ventas_upload
    )


def ingest_resumen_ventas_upload(
    *,
    warehouse_upload_id: int,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
) -> dict[str, Any]:
    if (
        not isinstance(warehouse_upload_id, int)
        or isinstance(warehouse_upload_id, bool)
        or warehouse_upload_id <= 0
    ):
        raise ValueError("warehouse_upload_id debe ser entero positivo.")

    upload = _load_upload(warehouse_upload_id)
    parser = _resolve_callable(
        "WAREHOUSE_RESUMEN_VENTAS_PARSER",
        parse_resumen_ventas_xlsx,
    )
    try:
        parsed = _invoke(
            parser,
            file_path=upload["file_path"],
            file_bytes=upload["file_bytes"],
        )
    except Exception as exc:
        raise ResumenVentasParseInvocationError(
            "Falló el parser de Resumen Ventas para "
            f"warehouse_upload_id={warehouse_upload_id}."
        ) from exc

    repository = _resolve_callable(
        "WAREHOUSE_RESUMEN_VENTAS_REPOSITORY",
        persist_resumen_ventas_snapshot,
    )
    try:
        result = _invoke(
            repository,
            warehouse_upload_id=warehouse_upload_id,
            report_type_key=RESUMEN_VENTAS_REPORT_TYPE_KEY,
            date_from=upload["date_from"],
            date_to=upload["date_to"],
            captured_at=upload["captured_at"],
            parsed_snapshot=parsed,
        )
    except Exception as exc:
        raise ResumenVentasPersistError(
            "Falló la persistencia de Resumen Ventas para "
            f"warehouse_upload_id={warehouse_upload_id}."
        ) from exc

    payload = _as_dict(result)
    current_app.logger.info(
        "Resumen Ventas ingestion finished: warehouse_upload_id=%s "
        "snapshot_id=%s status=%s source=%s",
        warehouse_upload_id,
        payload.get("snapshot_id"),
        payload.get("status"),
        ingestion_source,
    )
    return payload


def _load_upload(warehouse_upload_id: int) -> dict[str, Any]:
    loader = current_app.config.get("WAREHOUSE_UPLOAD_LOADER")
    if not callable(loader):
        raise ResumenVentasUploadLoadError(
            "WAREHOUSE_UPLOAD_LOADER no está configurado."
        )
    try:
        raw = _invoke(loader, warehouse_upload_id=warehouse_upload_id)
    except Exception as exc:
        raise ResumenVentasUploadLoadError(
            "Falló la carga del upload documental."
        ) from exc
    if raw is None:
        raise ResumenVentasUploadLoadError(
            f"No se encontró warehouse_upload_id={warehouse_upload_id}."
        )
    payload = _as_dict(raw)

    report_type = str(payload.get("report_type_key") or "").strip()
    period_type = str(payload.get("period_type") or "").strip()
    if report_type != RESUMEN_VENTAS_REPORT_TYPE_KEY:
        raise ResumenVentasUploadLoadError(
            "El upload no corresponde a resumen_ventas."
        )
    if period_type != RESUMEN_VENTAS_PERIOD_TYPE:
        raise ResumenVentasUploadLoadError(
            "resumen_ventas requiere period_type='rango'."
        )

    date_from = _as_date(payload.get("date_from"), "date_from")
    date_to = _as_date(payload.get("date_to"), "date_to")
    if date_from > date_to:
        raise ResumenVentasUploadLoadError(
            "date_from no puede ser posterior a date_to."
        )
    file_path = payload.get("storage_path") or payload.get("file_path")
    file_bytes = payload.get("file_bytes")
    if not file_path and file_bytes is None:
        raise ResumenVentasUploadLoadError(
            "El upload no contiene ruta ni bytes."
        )
    if file_bytes is not None and not isinstance(file_bytes, bytes):
        raise ResumenVentasUploadLoadError("file_bytes debe ser bytes.")

    return {
        "file_path": str(file_path).strip() if file_path else None,
        "file_bytes": file_bytes,
        "date_from": date_from,
        "date_to": date_to,
        "captured_at": _as_datetime(payload.get("captured_at")),
    }


def _resolve_callable(
    config_key: str,
    default: Callable[..., Any],
) -> Callable[..., Any]:
    candidate = current_app.config.get(config_key)
    return candidate if callable(candidate) else default


def _invoke(fn: Callable[..., Any], **kwargs: Any) -> Any:
    fn_signature = signature(fn)
    if any(
        param.kind == param.VAR_KEYWORD
        for param in fn_signature.parameters.values()
    ):
        return fn(**kwargs)
    accepted = {
        name: value
        for name, value in kwargs.items()
        if name in fn_signature.parameters
    }
    return fn(**accepted)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    raise ValueError("Se esperaba dict o dataclass serializable.")


def _as_date(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value.strip())
    raise ResumenVentasUploadLoadError(
        f"{field} es requerido y debe ser fecha ISO."
    )


def _as_datetime(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return (
            value
            if value.tzinfo
            else value.replace(tzinfo=timezone.utc)
        )
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        return (
            parsed
            if parsed.tzinfo
            else parsed.replace(tzinfo=timezone.utc)
        )
    raise ResumenVentasUploadLoadError("captured_at inválido.")
