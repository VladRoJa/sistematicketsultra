from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
import importlib
import inspect
from typing import Any, Callable

from flask import current_app


SOCIOS_ACTIVOS_REPORT_TYPE_KEY = "socios_activos"
SOCIOS_ACTIVOS_PERIOD_TYPE = "diario"
SOCIOS_ACTIVOS_SNAPSHOT_KIND = "daily"
SOCIOS_ACTIVOS_DEFAULT_IS_CANONICAL = False


class SociosActivosIngestionError(RuntimeError):
    """Error base de la ingestión estructurada."""


class SociosActivosUploadLoadError(SociosActivosIngestionError):
    """El WarehouseUpload no puede alimentar esta ingestión."""


class SociosActivosParseError(SociosActivosIngestionError):
    """Falló el parser del XLSX."""


class SociosActivosPersistError(SociosActivosIngestionError):
    """Falló la persistencia del snapshot."""


@dataclass(frozen=True, slots=True)
class IngestSociosActivosCommand:
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
    cutoff_date: date
    metadata: dict[str, Any]

    def validate(self) -> None:
        if self.warehouse_upload_id <= 0:
            raise SociosActivosUploadLoadError(
                "warehouse_upload_id debe ser entero positivo."
            )

        if self.report_type_key != SOCIOS_ACTIVOS_REPORT_TYPE_KEY:
            raise SociosActivosUploadLoadError(
                "El upload no corresponde a socios_activos."
            )

        if self.period_type != SOCIOS_ACTIVOS_PERIOD_TYPE:
            raise SociosActivosUploadLoadError(
                "El upload de socios_activos debe tener "
                "period_type='diario'."
            )

        if not self.file_path and self.file_bytes is None:
            raise SociosActivosUploadLoadError(
                "El upload no contiene ruta ni bytes del XLSX."
            )


def register_socios_activos_ingestor(app) -> None:
    app.config["WAREHOUSE_SOCIOS_ACTIVOS_INGESTOR"] = (
        ingest_socios_activos_upload
    )


def ingest_socios_activos_upload(
    *,
    warehouse_upload_id: int,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
) -> dict[str, Any]:
    command = IngestSociosActivosCommand(
        warehouse_upload_id=warehouse_upload_id,
        requested_by=requested_by,
        ingestion_source=ingestion_source,
    )

    _validate_command(command)

    upload_document = _load_upload_document(
        warehouse_upload_id=command.warehouse_upload_id
    )

    parsed_snapshot = _parse_upload_document(
        upload_document
    )

    repository = _resolve_repository()

    try:
        raw_result = _invoke_callable_flexibly(
            repository,
            warehouse_upload_id=(
                upload_document.warehouse_upload_id
            ),
            report_type_key=(
                upload_document.report_type_key
            ),
            cutoff_date=(
                upload_document.cutoff_date
            ),
            captured_at=(
                upload_document.captured_at
            ),
            snapshot_kind=(
                SOCIOS_ACTIVOS_SNAPSHOT_KIND
            ),
            is_canonical=(
                SOCIOS_ACTIVOS_DEFAULT_IS_CANONICAL
            ),
            parsed_snapshot=parsed_snapshot,
        )
    except Exception as exc:
        raise SociosActivosPersistError(
            "Falló la persistencia de Socios Activos para "
            "warehouse_upload_id="
            f"{upload_document.warehouse_upload_id}."
        ) from exc

    result = _as_dict(raw_result)

    parser_result = _as_dict(
        parsed_snapshot
    )

    data_quality_counts = parser_result.get(
        "data_quality_counts"
    )

    if isinstance(
        data_quality_counts,
        dict,
    ):
        result["data_quality_counts"] = dict(
            data_quality_counts
        )

    current_app.logger.info(
        "Socios Activos ingestion finished: "
        "warehouse_upload_id=%s "
        "snapshot_id=%s "
        "status=%s "
        "valid=%s "
        "rejected=%s "
        "cutoff_date=%s "
        "source=%s",
        upload_document.warehouse_upload_id,
        result.get("snapshot_id"),
        result.get("status"),
        result.get("row_count_valid"),
        result.get("row_count_rejected"),
        upload_document.cutoff_date,
        command.ingestion_source,
    )

    return result


def _validate_command(
    command: IngestSociosActivosCommand,
) -> None:
    if (
        not isinstance(
            command.warehouse_upload_id,
            int,
        )
        or isinstance(
            command.warehouse_upload_id,
            bool,
        )
        or command.warehouse_upload_id <= 0
    ):
        raise ValueError(
            "warehouse_upload_id debe ser entero positivo."
        )


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
        raise SociosActivosUploadLoadError(
            "Falló la carga del upload "
            f"warehouse_upload_id={warehouse_upload_id}."
        ) from exc

    if raw_result is None:
        raise SociosActivosUploadLoadError(
            "No se encontró warehouse_upload_id="
            f"{warehouse_upload_id}."
        )

    try:
        document = _normalize_upload_document(
            expected_upload_id=warehouse_upload_id,
            raw_result=raw_result,
        )

        document.validate()

    except SociosActivosUploadLoadError:
        raise

    except Exception as exc:
        raise SociosActivosUploadLoadError(
            "El upload no contiene metadatos "
            "diarios válidos."
        ) from exc

    return document


def _normalize_upload_document(
    *,
    expected_upload_id: int,
    raw_result: Any,
) -> WarehouseUploadDocument:
    payload = _as_dict(
        raw_result
    )

    upload_id = int(
        payload.get(
            "warehouse_upload_id",
            expected_upload_id,
        )
    )

    if upload_id != expected_upload_id:
        raise SociosActivosUploadLoadError(
            "El loader devolvió un "
            "warehouse_upload_id distinto "
            "al solicitado."
        )

    metadata = payload.get(
        "metadata"
    ) or {}

    if not isinstance(
        metadata,
        dict,
    ):
        raise SociosActivosUploadLoadError(
            "metadata del upload debe ser un objeto."
        )

    file_bytes = payload.get(
        "file_bytes"
    )

    if (
        file_bytes is not None
        and not isinstance(
            file_bytes,
            bytes,
        )
    ):
        raise SociosActivosUploadLoadError(
            "file_bytes del upload debe ser bytes."
        )

    return WarehouseUploadDocument(
        warehouse_upload_id=upload_id,
        report_type_key=str(
            payload.get(
                "report_type_key"
            )
            or ""
        ).strip(),
        original_filename=str(
            payload.get(
                "original_filename"
            )
            or ""
        ).strip(),
        file_path=_normalize_optional_text(
            payload.get(
                "storage_path"
            )
            or payload.get(
                "file_path"
            )
        ),
        file_bytes=file_bytes,
        captured_at=_ensure_datetime(
            payload.get(
                "captured_at"
            )
        ),
        period_type=str(
            payload.get(
                "period_type"
            )
            or ""
        ).strip(),
        cutoff_date=_ensure_date(
            payload.get(
                "cutoff_date"
            ),
            field_name="cutoff_date",
        ),
        metadata=dict(
            metadata
        ),
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
        raise SociosActivosParseError(
            "Falló el parser de Socios Activos para "
            "warehouse_upload_id="
            f"{upload_document.warehouse_upload_id}."
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
        direct_key="WAREHOUSE_SOCIOS_ACTIVOS_PARSER",
        module_key="WAREHOUSE_SOCIOS_ACTIVOS_PARSER_MODULE",
        entrypoint_key="WAREHOUSE_SOCIOS_ACTIVOS_PARSER_ENTRYPOINT",
        description="parser de socios_activos",
    )


def _resolve_repository() -> Callable[..., Any]:
    return _resolve_callable(
        direct_key="WAREHOUSE_SOCIOS_ACTIVOS_REPOSITORY",
        module_key="WAREHOUSE_SOCIOS_ACTIVOS_REPOSITORY_MODULE",
        entrypoint_key="WAREHOUSE_SOCIOS_ACTIVOS_REPOSITORY_ENTRYPOINT",
        description="repository de socios_activos",
    )


def _resolve_callable(
    *,
    direct_key: str,
    module_key: str,
    entrypoint_key: str,
    description: str,
) -> Callable[..., Any]:
    direct_callable = current_app.config.get(
        direct_key
    )

    if callable(
        direct_callable
    ):
        return direct_callable

    module_path = current_app.config.get(
        module_key
    )
    entrypoint_name = current_app.config.get(
        entrypoint_key
    )

    if (
        not isinstance(
            module_path,
            str,
        )
        or not module_path.strip()
    ):
        raise NotImplementedError(
            "No hay implementación configurada "
            f"para {description}."
        )

    if (
        not isinstance(
            entrypoint_name,
            str,
        )
        or not entrypoint_name.strip()
    ):
        raise SociosActivosIngestionError(
            f"{entrypoint_key} debe ser string."
        )

    try:
        module = importlib.import_module(
            module_path.strip()
        )
    except Exception as exc:
        raise SociosActivosIngestionError(
            f"No se pudo importar {module_path!r}."
        ) from exc

    resolved = getattr(
        module,
        entrypoint_name.strip(),
        None,
    )

    if not callable(
        resolved
    ):
        raise SociosActivosIngestionError(
            "El entrypoint de "
            f"{description} no es callable."
        )

    return resolved


def _invoke_callable_flexibly(
    fn: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    try:
        signature = inspect.signature(
            fn
        )
    except (
        TypeError,
        ValueError,
    ):
        return fn(
            **kwargs
        )

    if any(
        parameter.kind
        == inspect.Parameter.VAR_KEYWORD
        for parameter
        in signature.parameters.values()
    ):
        return fn(
            **kwargs
        )

    accepted_kwargs = {
        name: value
        for name, value
        in kwargs.items()
        if name in signature.parameters
    }

    missing_required = [
        name
        for name, parameter
        in signature.parameters.items()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and parameter.default
        is inspect.Parameter.empty
        and name not in accepted_kwargs
    ]

    if missing_required:
        raise SociosActivosIngestionError(
            "El hook requiere parámetros "
            "no soportados: "
            f"{missing_required}."
        )

    return fn(
        **accepted_kwargs
    )


def _as_dict(
    value: Any,
) -> dict[str, Any]:
    if isinstance(
        value,
        dict,
    ):
        return value

    if is_dataclass(
        value
    ):
        return asdict(
            value
        )

    if hasattr(
        value,
        "__dict__",
    ):
        return dict(
            vars(value)
        )

    raise ValueError(
        "Se esperaba dict, dataclass "
        "u objeto serializable."
    )


def _ensure_date(
    value: Any,
    *,
    field_name: str,
) -> date:
    if isinstance(
        value,
        datetime,
    ):
        return value.date()

    if isinstance(
        value,
        date,
    ):
        return value

    if isinstance(
        value,
        str,
    ):
        try:
            return date.fromisoformat(
                value
            )
        except ValueError as exc:
            raise ValueError(
                f"{field_name} debe ser fecha ISO."
            ) from exc

    raise ValueError(
        f"{field_name} es obligatorio."
    )


def _ensure_datetime(
    value: Any,
) -> datetime:
    if isinstance(
        value,
        str,
    ):
        value = datetime.fromisoformat(
            value
        )

    if not isinstance(
        value,
        datetime,
    ):
        raise ValueError(
            "captured_at es obligatorio."
        )

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value


def _normalize_optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(
        value
    ).strip()

    return normalized or None
