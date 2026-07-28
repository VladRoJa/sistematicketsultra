from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timezone
from inspect import Parameter, signature
from typing import Any

from flask import current_app

from app.warehouse.services.ventas_nuevos_socios_detalle_parser import (
    parse_ventas_nuevos_socios_detalle_xlsx,
)
from app.warehouse.services.ventas_nuevos_socios_detalle_repository import (
    VENTAS_NUEVOS_SOCIOS_DETALLE_REPORT_TYPE_KEY,
    persist_ventas_nuevos_socios_detalle_snapshot,
)
from app.warehouse.services.warehouse_upload_loader import (
    load_warehouse_upload,
)


SUPPORTED_SNAPSHOT_KINDS = frozenset(
    {
        "month_to_date",
    }
)


class VentasNuevosSociosDetalleIngestionError(
    RuntimeError
):
    """Error base de la ingesta estructurada."""


class VentasNuevosSociosDetalleUploadLoadError(
    VentasNuevosSociosDetalleIngestionError
):
    """Fallo al cargar o validar el upload RAW."""


class VentasNuevosSociosDetalleParseError(
    VentasNuevosSociosDetalleIngestionError
):
    """Fallo durante el parsing del XLSX."""


class VentasNuevosSociosDetallePersistError(
    VentasNuevosSociosDetalleIngestionError
):
    """Fallo durante la persistencia estructurada."""


@dataclass(frozen=True, slots=True)
class IngestVentasNuevosSociosDetalleCommand:
    warehouse_upload_id: int
    snapshot_kind: str
    requested_by: str | None = None
    ingestion_source: str | None = None


@dataclass(frozen=True, slots=True)
class WarehouseUploadDocument:
    warehouse_upload_id: int
    report_type_key: str

    original_filename: str | None = None
    content_type: str | None = None

    file_path: str | None = None
    file_bytes: bytes | None = None

    captured_at: datetime | None = None

    period_type: str | None = None
    cutoff_date: date | None = None
    date_from: date | None = None
    date_to: date | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def validate(self) -> None:
        if self.warehouse_upload_id <= 0:
            raise VentasNuevosSociosDetalleUploadLoadError(
                "warehouse_upload_id debe ser positivo."
            )

        if (
            self.report_type_key
            != VENTAS_NUEVOS_SOCIOS_DETALLE_REPORT_TYPE_KEY
        ):
            raise VentasNuevosSociosDetalleUploadLoadError(
                "El upload no corresponde a "
                "'ventas_nuevos_socios_detalle'. "
                f"Recibido={self.report_type_key!r}"
            )

        if not self.file_path and self.file_bytes is None:
            raise VentasNuevosSociosDetalleUploadLoadError(
                "El upload debe proporcionar "
                "file_path/storage_path o file_bytes."
            )

        if self.captured_at is None:
            raise VentasNuevosSociosDetalleUploadLoadError(
                "El upload no tiene captured_at."
            )

        if self.date_from is None:
            raise VentasNuevosSociosDetalleUploadLoadError(
                "El upload no tiene date_from."
            )

        if self.date_to is None:
            raise VentasNuevosSociosDetalleUploadLoadError(
                "El upload no tiene date_to."
            )

        if self.date_from > self.date_to:
            raise VentasNuevosSociosDetalleUploadLoadError(
                "date_from no puede ser posterior a date_to."
            )

        if self.date_from.day != 1:
            raise VentasNuevosSociosDetalleUploadLoadError(
                "date_from debe ser el primer día del mes."
            )

        if (
            self.date_from.year != self.date_to.year
            or self.date_from.month != self.date_to.month
        ):
            raise VentasNuevosSociosDetalleUploadLoadError(
                "date_from y date_to deben pertenecer "
                "al mismo mes."
            )

        if (
            self.cutoff_date is not None
            and self.cutoff_date != self.date_to
        ):
            raise VentasNuevosSociosDetalleUploadLoadError(
                "cutoff_date debe coincidir con date_to."
            )

        if (
            self.period_type is not None
            and self.period_type.strip().lower()
            != "rango"
        ):
            raise VentasNuevosSociosDetalleUploadLoadError(
                "period_type debe ser 'rango'."
            )


def register_ventas_nuevos_socios_detalle_ingestor(
    app,
) -> None:
    app.config[
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_INGESTOR"
    ] = ingest_ventas_nuevos_socios_detalle_upload


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    if is_dataclass(value):
        return asdict(value)

    to_dict = getattr(value, "to_dict", None)

    if callable(to_dict):
        result = to_dict()

        if isinstance(result, Mapping):
            return dict(result)

    attributes = (
        "warehouse_upload_id",
        "id",
        "report_type_key",
        "original_filename",
        "content_type",
        "mime_type",
        "file_path",
        "storage_path",
        "file_bytes",
        "captured_at",
        "created_at",
        "period_type",
        "cutoff_date",
        "date_from",
        "date_to",
        "metadata",
    )

    payload = {
        attribute: getattr(value, attribute)
        for attribute in attributes
        if hasattr(value, attribute)
    }

    if payload:
        return payload

    raise VentasNuevosSociosDetalleIngestionError(
        "Se recibió un tipo no normalizable."
    )


def _ensure_positive_integer(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise VentasNuevosSociosDetalleIngestionError(
            f"{field_name} no puede ser booleano."
        )

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise VentasNuevosSociosDetalleIngestionError(
            f"{field_name} debe ser entero."
        ) from exc

    if parsed <= 0:
        raise VentasNuevosSociosDetalleIngestionError(
            f"{field_name} debe ser positivo."
        )

    return parsed


def _ensure_optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    return normalized or None


def _ensure_required_text(
    value: Any,
    *,
    field_name: str,
) -> str:
    normalized = _ensure_optional_text(value)

    if normalized is None:
        raise VentasNuevosSociosDetalleUploadLoadError(
            f"{field_name} es obligatorio."
        )

    return normalized


def _ensure_date(
    value: Any,
    *,
    field_name: str,
) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise VentasNuevosSociosDetalleUploadLoadError(
                f"{field_name} debe usar YYYY-MM-DD."
            ) from exc

    raise VentasNuevosSociosDetalleUploadLoadError(
        f"{field_name} no contiene una fecha válida."
    )


def _ensure_optional_date(
    value: Any,
    *,
    field_name: str,
) -> date | None:
    if value is None or value == "":
        return None

    return _ensure_date(
        value,
        field_name=field_name,
    )


def _ensure_datetime(
    value: Any,
    *,
    field_name: str,
) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()

        if normalized.endswith("Z"):
            normalized = (
                normalized[:-1]
                + "+00:00"
            )

        try:
            parsed = datetime.fromisoformat(
                normalized
            )
        except ValueError as exc:
            raise VentasNuevosSociosDetalleUploadLoadError(
                f"{field_name} no contiene un ISO datetime válido."
            ) from exc
    else:
        raise VentasNuevosSociosDetalleUploadLoadError(
            f"{field_name} no contiene un datetime válido."
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(timezone.utc)


def _resolve_callable(
    *,
    config_keys: tuple[str, ...],
    description: str,
    default: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    for config_key in config_keys:
        configured = current_app.config.get(
            config_key
        )

        if callable(configured):
            return configured

    if callable(default):
        return default

    raise VentasNuevosSociosDetalleIngestionError(
        f"No hay implementación configurada para {description}."
    )


def _invoke_callable_flexibly(
    callable_object: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    try:
        callable_signature = signature(
            callable_object
        )
    except (TypeError, ValueError):
        return callable_object(**kwargs)

    parameters = callable_signature.parameters

    accepts_kwargs = any(
        parameter.kind
        == Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    if accepts_kwargs:
        return callable_object(**kwargs)

    accepted_kwargs = {
        key: value
        for key, value in kwargs.items()
        if key in parameters
    }

    return callable_object(**accepted_kwargs)


def _validate_command(
    command: IngestVentasNuevosSociosDetalleCommand,
) -> None:
    _ensure_positive_integer(
        command.warehouse_upload_id,
        field_name="warehouse_upload_id",
    )

    if (
        command.snapshot_kind
        not in SUPPORTED_SNAPSHOT_KINDS
    ):
        raise VentasNuevosSociosDetalleIngestionError(
            "snapshot_kind inválido. "
            f"Recibido={command.snapshot_kind!r}; "
            f"permitidos={sorted(SUPPORTED_SNAPSHOT_KINDS)}"
        )


def _resolve_upload_loader() -> Callable[..., Any]:
    return _resolve_callable(
        config_keys=(
            "WAREHOUSE_UPLOAD_LOADER",
            "WAREHOUSE_UPLOAD_LOADER_SQL",
        ),
        description=(
            "cargar el upload documental de Warehouse"
        ),
        default=load_warehouse_upload,
    )


def _resolve_parser() -> Callable[..., Any]:
    return _resolve_callable(
        config_keys=(
            "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_PARSER",
        ),
        description=(
            "parsear Ventas Nuevos Socios Detalle"
        ),
        default=(
            parse_ventas_nuevos_socios_detalle_xlsx
        ),
    )


def _resolve_repository() -> Callable[..., Any]:
    return _resolve_callable(
        config_keys=(
            "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_REPOSITORY",
        ),
        description=(
            "persistir Ventas Nuevos Socios Detalle"
        ),
        default=(
            persist_ventas_nuevos_socios_detalle_snapshot
        ),
    )


def _resolve_optional_branch_resolver(
) -> Callable[[str], int | None] | None:
    configured = current_app.config.get(
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_BRANCH_RESOLVER"
    )

    return (
        configured
        if callable(configured)
        else None
    )


def _resolve_optional_canonicality_resolver(
) -> Callable[..., dict[str, Any] | None] | None:
    configured = current_app.config.get(
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_CANONICALITY_RESOLVER"
    )

    return (
        configured
        if callable(configured)
        else None
    )


def _resolve_optional_advisory_lock_key(
    *,
    upload_document: WarehouseUploadDocument,
    snapshot_kind: str,
) -> int | None:
    resolver = current_app.config.get(
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_ADVISORY_LOCK_RESOLVER"
    )

    if not callable(resolver):
        return None

    result = _invoke_callable_flexibly(
        resolver,
        warehouse_upload_id=(
            upload_document.warehouse_upload_id
        ),
        report_type_key=(
            upload_document.report_type_key
        ),
        business_date=upload_document.date_to,
        date_from=upload_document.date_from,
        date_to=upload_document.date_to,
        snapshot_kind=snapshot_kind,
        upload_metadata=(
            upload_document.metadata
        ),
    )

    if result is None:
        return None

    return int(result)


def _normalize_upload_document(
    *,
    expected_upload_id: int,
    raw_result: Any,
) -> WarehouseUploadDocument:
    if raw_result is None:
        raise VentasNuevosSociosDetalleUploadLoadError(
            "No existe el upload solicitado."
        )

    payload = _as_dict(raw_result)

    received_upload_id = (
        payload.get("warehouse_upload_id")
        or payload.get("id")
    )

    normalized_upload_id = (
        _ensure_positive_integer(
            received_upload_id,
            field_name="warehouse_upload_id",
        )
    )

    if normalized_upload_id != expected_upload_id:
        raise VentasNuevosSociosDetalleUploadLoadError(
            "El loader devolvió un upload distinto "
            "al solicitado."
        )

    raw_metadata = payload.get("metadata") or {}

    if not isinstance(raw_metadata, Mapping):
        raise VentasNuevosSociosDetalleUploadLoadError(
            "metadata debe ser un objeto."
        )

    file_bytes = payload.get("file_bytes")

    if (
        file_bytes is not None
        and not isinstance(file_bytes, bytes)
    ):
        raise VentasNuevosSociosDetalleUploadLoadError(
            "file_bytes debe ser bytes."
        )

    captured_at_raw = (
        payload.get("captured_at")
        or payload.get("created_at")
    )

    date_to_raw = (
        payload.get("date_to")
        or payload.get("cutoff_date")
    )

    cutoff_date_raw = (
        payload.get("cutoff_date")
        or date_to_raw
    )

    upload_document = WarehouseUploadDocument(
        warehouse_upload_id=(
            normalized_upload_id
        ),
        report_type_key=(
            _ensure_required_text(
                payload.get("report_type_key")
                or payload.get("report_type"),
                field_name="report_type_key",
            )
        ),
        original_filename=(
            _ensure_optional_text(
                payload.get("original_filename")
            )
        ),
        content_type=(
            _ensure_optional_text(
                payload.get("content_type")
                or payload.get("mime_type")
            )
        ),
        file_path=(
            _ensure_optional_text(
                payload.get("file_path")
                or payload.get("storage_path")
            )
        ),
        file_bytes=file_bytes,
        captured_at=(
            _ensure_datetime(
                captured_at_raw,
                field_name="captured_at",
            )
        ),
        period_type=(
            _ensure_optional_text(
                payload.get("period_type")
            )
        ),
        cutoff_date=(
            _ensure_optional_date(
                cutoff_date_raw,
                field_name="cutoff_date",
            )
        ),
        date_from=(
            _ensure_optional_date(
                payload.get("date_from"),
                field_name="date_from",
            )
        ),
        date_to=(
            _ensure_optional_date(
                date_to_raw,
                field_name="date_to",
            )
        ),
        metadata=dict(raw_metadata),
    )

    upload_document.validate()
    return upload_document


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
        raise VentasNuevosSociosDetalleUploadLoadError(
            "Falló la carga del upload "
            f"warehouse_upload_id={warehouse_upload_id}."
        ) from exc

    return _normalize_upload_document(
        expected_upload_id=warehouse_upload_id,
        raw_result=raw_result,
    )


def _parse_upload_document(
    *,
    upload_document: WarehouseUploadDocument,
) -> Any:
    parser = _resolve_parser()
    branch_resolver = (
        _resolve_optional_branch_resolver()
    )

    try:
        return _invoke_callable_flexibly(
            parser,
            file_path=upload_document.file_path,
            file_bytes=upload_document.file_bytes,
            branch_resolver=branch_resolver,
        )
    except Exception as exc:
        raise VentasNuevosSociosDetalleParseError(
            "Falló el parser para "
            f"warehouse_upload_id="
            f"{upload_document.warehouse_upload_id}."
        ) from exc


def ingest_ventas_nuevos_socios_detalle_upload(
    *,
    warehouse_upload_id: int,
    snapshot_kind: str,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
) -> dict[str, Any]:
    command = (
        IngestVentasNuevosSociosDetalleCommand(
            warehouse_upload_id=(
                warehouse_upload_id
            ),
            snapshot_kind=snapshot_kind,
            requested_by=requested_by,
            ingestion_source=ingestion_source,
        )
    )

    _validate_command(command)

    upload_document = _load_upload_document(
        warehouse_upload_id=(
            command.warehouse_upload_id
        )
    )

    parsed_snapshot = _parse_upload_document(
        upload_document=upload_document
    )

    repository = _resolve_repository()

    canonicality_resolver = (
        _resolve_optional_canonicality_resolver()
    )

    advisory_lock_key = (
        _resolve_optional_advisory_lock_key(
            upload_document=upload_document,
            snapshot_kind=command.snapshot_kind,
        )
    )

    try:
        repository_result = (
            _invoke_callable_flexibly(
                repository,
                warehouse_upload_id=(
                    upload_document
                    .warehouse_upload_id
                ),
                report_type_key=(
                    upload_document.report_type_key
                ),
                business_date=(
                    upload_document.date_to
                ),
                date_from=(
                    upload_document.date_from
                ),
                date_to=(
                    upload_document.date_to
                ),
                captured_at=(
                    upload_document.captured_at
                ),
                snapshot_kind=(
                    command.snapshot_kind
                ),
                parsed_snapshot=parsed_snapshot,
                canonicality_resolver=(
                    canonicality_resolver
                ),
                advisory_lock_key=(
                    advisory_lock_key
                ),
                requested_by=(
                    command.requested_by
                ),
                ingestion_source=(
                    command.ingestion_source
                ),
            )
        )
    except Exception as exc:
        raise VentasNuevosSociosDetallePersistError(
            "Falló la persistencia para "
            f"warehouse_upload_id="
            f"{upload_document.warehouse_upload_id}."
        ) from exc

    result = _as_dict(repository_result)

    current_app.logger.info(
        "Ventas Nuevos Socios Detalle ingestion finished: "
        "warehouse_upload_id=%s snapshot_id=%s "
        "status=%s valid=%s rejected=%s",
        upload_document.warehouse_upload_id,
        result.get("snapshot_id"),
        result.get("status"),
        result.get("row_count_valid"),
        result.get("row_count_rejected"),
    )

    return result
