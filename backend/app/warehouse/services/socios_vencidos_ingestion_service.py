from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
import importlib
import inspect
from pathlib import Path
from typing import Any, Callable

from flask import current_app

from app.extensions import db
from app.models.warehouse import WarehouseUploadORM


SOCIOS_VENCIDOS_REPORT_TYPE_KEY = "socios_vencidos"
SOCIOS_VENCIDOS_PERIOD_TYPE = "rango"
ROW_STORAGE_MODE_CARTERA_ONLY = "CARTERA_ONLY"


class SociosVencidosIngestionError(RuntimeError):
    """Error base de la ingestión estructurada."""


class SociosVencidosUploadLoadError(SociosVencidosIngestionError):
    """El WarehouseUpload no puede alimentar esta ingestión."""


class SociosVencidosParseError(SociosVencidosIngestionError):
    """Falló el parser del XLSX."""


class SociosVencidosPersistError(SociosVencidosIngestionError):
    """Falló la persistencia del snapshot."""


@dataclass(frozen=True, slots=True)
class IngestSociosVencidosCommand:
    warehouse_upload_id: int
    requested_by: str | None = None
    ingestion_source: str | None = None


@dataclass(frozen=True, slots=True)
class WarehouseUploadDocument:
    warehouse_upload_id: int
    report_type_key: str
    original_filename: str
    file_path: str | None
    file_bytes: bytes | None
    captured_at: datetime
    period_type: str
    date_from: date
    date_to: date
    metadata: dict[str, Any]

    def validate(self) -> None:
        if self.warehouse_upload_id <= 0:
            raise SociosVencidosUploadLoadError(
                "warehouse_upload_id debe ser entero positivo."
            )
        if self.report_type_key != SOCIOS_VENCIDOS_REPORT_TYPE_KEY:
            raise SociosVencidosUploadLoadError(
                "El upload no corresponde a socios_vencidos."
            )
        if self.period_type != SOCIOS_VENCIDOS_PERIOD_TYPE:
            raise SociosVencidosUploadLoadError(
                "El upload de socios_vencidos debe tener period_type='rango'."
            )
        if self.date_from > self.date_to:
            raise SociosVencidosUploadLoadError(
                "date_from no puede ser posterior a date_to."
            )
        if not self.file_path and self.file_bytes is None:
            raise SociosVencidosUploadLoadError(
                "El upload no contiene ruta ni bytes del XLSX."
            )


def register_socios_vencidos_ingestor(app) -> None:
    app.config["WAREHOUSE_SOCIOS_VENCIDOS_INGESTOR"] = (
        ingest_socios_vencidos_upload
    )


def ingest_socios_vencidos_upload(
    *,
    warehouse_upload_id: int,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
    row_storage_mode: str = ROW_STORAGE_MODE_CARTERA_ONLY,
    delete_source_after_success: bool = True,
) -> dict[str, Any]:
    command = IngestSociosVencidosCommand(
        warehouse_upload_id=warehouse_upload_id,
        requested_by=requested_by,
        ingestion_source=ingestion_source,
    )
    _validate_command(command)

    upload_document = _load_upload_document(
        warehouse_upload_id=command.warehouse_upload_id
    )
    parsed_snapshot = _parse_upload_document(upload_document)
    repository = _resolve_repository()

    try:
        raw_result = _invoke_callable_flexibly(
            repository,
            warehouse_upload_id=upload_document.warehouse_upload_id,
            report_type_key=upload_document.report_type_key,
            date_from=upload_document.date_from,
            date_to=upload_document.date_to,
            captured_at=upload_document.captured_at,
            parsed_snapshot=parsed_snapshot,
            row_storage_mode=row_storage_mode,
        )
    except Exception as exc:
        raise SociosVencidosPersistError(
            "Falló la persistencia de Socios Vencidos para "
            f"warehouse_upload_id={upload_document.warehouse_upload_id}."
        ) from exc

    result = _as_dict(raw_result)
    parser_result = _as_dict(parsed_snapshot)
    data_quality_counts = parser_result.get("data_quality_counts")
    if isinstance(data_quality_counts, dict):
        result["data_quality_counts"] = dict(data_quality_counts)

    result["source_file_deleted"] = False
    result["cleanup_warning"] = None
    if delete_source_after_success and upload_document.file_path:
        cleanup_result = _delete_source_after_structured_success(
            upload_document=upload_document,
        )
        result.update(cleanup_result)
    current_app.logger.info(
        "Socios Vencidos ingestion finished: warehouse_upload_id=%s "
        "snapshot_id=%s status=%s valid=%s rejected=%s source=%s",
        upload_document.warehouse_upload_id,
        result.get("snapshot_id"),
        result.get("status"),
        result.get("row_count_valid"),
        result.get("row_count_rejected"),
        command.ingestion_source,
    )
    return result


def _delete_source_after_structured_success(
    *,
    upload_document: WarehouseUploadDocument,
) -> dict[str, Any]:
    source_path = Path(str(upload_document.file_path))
    try:
        source_path.unlink()
    except Exception as exc:
        warning = (
            "La ingesta quedó committed, pero no se pudo eliminar el XLSX "
            f"temporal: {exc}"
        )
        current_app.logger.warning(
            "Socios Vencidos cleanup warning: warehouse_upload_id=%s path=%s",
            upload_document.warehouse_upload_id,
            source_path,
            exc_info=True,
        )
        return {
            "source_file_deleted": False,
            "cleanup_warning": warning,
        }

    deleted_at = datetime.now(timezone.utc)
    try:
        marker = current_app.config.get(
            "WAREHOUSE_SOCIOS_VENCIDOS_SOURCE_DELETION_MARKER"
        )
        if callable(marker):
            _invoke_callable_flexibly(
                marker,
                warehouse_upload_id=upload_document.warehouse_upload_id,
                deleted_at=deleted_at,
            )
        else:
            _mark_upload_source_deleted(
                warehouse_upload_id=upload_document.warehouse_upload_id,
                deleted_at=deleted_at,
            )
    except Exception as exc:
        warning = (
            "El XLSX temporal se eliminó, pero no se pudo registrar el "
            f"marcador de retención: {exc}"
        )
        current_app.logger.warning(
            "Socios Vencidos cleanup marker warning: warehouse_upload_id=%s",
            upload_document.warehouse_upload_id,
            exc_info=True,
        )
        return {
            "source_file_deleted": True,
            "source_file_deleted_at": deleted_at.isoformat(),
            "cleanup_warning": warning,
        }

    return {
        "source_file_deleted": True,
        "source_file_deleted_at": deleted_at.isoformat(),
        "cleanup_warning": None,
    }


def _mark_upload_source_deleted(
    *,
    warehouse_upload_id: int,
    deleted_at: datetime,
) -> None:
    upload = WarehouseUploadORM.query.filter_by(
        id=warehouse_upload_id
    ).one_or_none()
    if upload is None:
        raise SociosVencidosIngestionError(
            "No se encontró el WarehouseUpload para marcar el cleanup."
        )

    upload.source_file_deleted_at = deleted_at
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _validate_command(command: IngestSociosVencidosCommand) -> None:
    if (
        not isinstance(command.warehouse_upload_id, int)
        or isinstance(command.warehouse_upload_id, bool)
        or command.warehouse_upload_id <= 0
    ):
        raise ValueError("warehouse_upload_id debe ser entero positivo.")


def _load_upload_document(
    *,
    warehouse_upload_id: int,
) -> WarehouseUploadDocument:
    loader = _resolve_upload_loader()
    try:
        raw_result = _invoke_callable_flexibly(
            loader,
            warehouse_upload_id=warehouse_upload_id,
        )
    except Exception as exc:
        raise SociosVencidosUploadLoadError(
            "Falló la carga del upload "
            f"warehouse_upload_id={warehouse_upload_id}."
        ) from exc

    if raw_result is None:
        raise SociosVencidosUploadLoadError(
            f"No se encontró warehouse_upload_id={warehouse_upload_id}."
        )

    try:
        document = _normalize_upload_document(
            expected_upload_id=warehouse_upload_id,
            raw_result=raw_result,
        )
        document.validate()
    except SociosVencidosUploadLoadError:
        raise
    except Exception as exc:
        raise SociosVencidosUploadLoadError(
            "El upload no contiene metadatos de rango válidos."
        ) from exc
    return document


def _normalize_upload_document(
    *,
    expected_upload_id: int,
    raw_result: Any,
) -> WarehouseUploadDocument:
    payload = _as_dict(raw_result)
    upload_id = int(
        payload.get("warehouse_upload_id", expected_upload_id)
    )
    if upload_id != expected_upload_id:
        raise SociosVencidosUploadLoadError(
            "El loader devolvió un warehouse_upload_id distinto al solicitado."
        )

    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise SociosVencidosUploadLoadError(
            "metadata del upload debe ser un objeto."
        )

    file_bytes = payload.get("file_bytes")
    if file_bytes is not None and not isinstance(file_bytes, bytes):
        raise SociosVencidosUploadLoadError(
            "file_bytes del upload debe ser bytes."
        )

    return WarehouseUploadDocument(
        warehouse_upload_id=upload_id,
        report_type_key=str(
            payload.get("report_type_key") or ""
        ).strip(),
        original_filename=str(
            payload.get("original_filename") or ""
        ).strip(),
        file_path=_normalize_optional_text(
            payload.get("storage_path") or payload.get("file_path")
        ),
        file_bytes=file_bytes,
        captured_at=_ensure_datetime(payload.get("captured_at")),
        period_type=str(payload.get("period_type") or "").strip(),
        date_from=_ensure_date(
            payload.get("date_from"),
            field_name="date_from",
        ),
        date_to=_ensure_date(
            payload.get("date_to"),
            field_name="date_to",
        ),
        metadata=dict(metadata),
    )


def _parse_upload_document(
    upload_document: WarehouseUploadDocument,
) -> Any:
    parser = _resolve_parser()
    try:
        return _invoke_callable_flexibly(
            parser,
            file_path=upload_document.file_path,
            file_bytes=upload_document.file_bytes,
        )
    except Exception as exc:
        raise SociosVencidosParseError(
            "Falló el parser de Socios Vencidos para "
            f"warehouse_upload_id={upload_document.warehouse_upload_id}."
        ) from exc


def _resolve_upload_loader() -> Callable[..., Any]:
    return _resolve_callable(
        direct_key="WAREHOUSE_UPLOAD_LOADER",
        module_key="WAREHOUSE_UPLOAD_LOADER_MODULE",
        entrypoint_key="WAREHOUSE_UPLOAD_LOADER_ENTRYPOINT",
        description="loader de WarehouseUpload",
    )


def _resolve_parser() -> Callable[..., Any]:
    return _resolve_callable(
        direct_key="WAREHOUSE_SOCIOS_VENCIDOS_PARSER",
        module_key="WAREHOUSE_SOCIOS_VENCIDOS_PARSER_MODULE",
        entrypoint_key="WAREHOUSE_SOCIOS_VENCIDOS_PARSER_ENTRYPOINT",
        description="parser de socios_vencidos",
    )


def _resolve_repository() -> Callable[..., Any]:
    return _resolve_callable(
        direct_key="WAREHOUSE_SOCIOS_VENCIDOS_REPOSITORY",
        module_key="WAREHOUSE_SOCIOS_VENCIDOS_REPOSITORY_MODULE",
        entrypoint_key="WAREHOUSE_SOCIOS_VENCIDOS_REPOSITORY_ENTRYPOINT",
        description="repository de socios_vencidos",
    )


def _resolve_callable(
    *,
    direct_key: str,
    module_key: str,
    entrypoint_key: str,
    description: str,
) -> Callable[..., Any]:
    direct_callable = current_app.config.get(direct_key)
    if callable(direct_callable):
        return direct_callable

    module_path = current_app.config.get(module_key)
    entrypoint_name = current_app.config.get(entrypoint_key)
    if not isinstance(module_path, str) or not module_path.strip():
        raise NotImplementedError(
            f"No hay implementación configurada para {description}."
        )
    if not isinstance(entrypoint_name, str) or not entrypoint_name.strip():
        raise SociosVencidosIngestionError(
            f"{entrypoint_key} debe ser string."
        )

    try:
        module = importlib.import_module(module_path.strip())
    except Exception as exc:
        raise SociosVencidosIngestionError(
            f"No se pudo importar {module_path!r}."
        ) from exc
    resolved = getattr(module, entrypoint_name.strip(), None)
    if not callable(resolved):
        raise SociosVencidosIngestionError(
            f"El entrypoint de {description} no es callable."
        )
    return resolved


def _invoke_callable_flexibly(
    fn: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(**kwargs)

    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return fn(**kwargs)

    accepted_kwargs = {
        name: value
        for name, value in kwargs.items()
        if name in signature.parameters
    }
    missing_required = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and parameter.default is inspect.Parameter.empty
        and name not in accepted_kwargs
    ]
    if missing_required:
        raise SociosVencidosIngestionError(
            "El hook requiere parámetros no soportados: "
            f"{missing_required}."
        )
    return fn(**accepted_kwargs)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    raise ValueError("Se esperaba dict, dataclass u objeto serializable.")


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} debe ser fecha ISO.") from exc
    raise ValueError(f"{field_name} es obligatorio.")


def _ensure_datetime(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise ValueError("captured_at es obligatorio.")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
