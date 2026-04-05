#  backend\app\warehouse\services\cargos_recurrentes_ingestion_service.py


from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from inspect import signature
from typing import Any, Callable

from flask import current_app

from app.warehouse.services.cargos_recurrentes_parser import (
    CargosRecurrentesParseResult,
    parse_cargos_recurrentes_xlsx,
)
from app.warehouse.services.cargos_recurrentes_repository import (
    CARGOS_RECURRENTES_REPORT_TYPE_KEY,
    persist_cargos_recurrentes_snapshot,
)


SUPPORTED_SNAPSHOT_KINDS = frozenset({"daily"})


class CargosRecurrentesIngestionError(RuntimeError):
    """Error base de la ingesta estructurada de Cargos Recurrentes."""


class CargosRecurrentesUploadLoadError(CargosRecurrentesIngestionError):
    """Fallo al cargar el upload documental desde Warehouse."""


class CargosRecurrentesParseInvocationError(CargosRecurrentesIngestionError):
    """Fallo al parsear el upload de Cargos Recurrentes."""


class CargosRecurrentesPersistError(CargosRecurrentesIngestionError):
    """Fallo al persistir el snapshot estructurado de Cargos Recurrentes."""


@dataclass(slots=True)
class IngestCargosRecurrentesCommand:
    warehouse_upload_id: int
    snapshot_kind: str
    requested_by: str | None = None
    ingestion_source: str | None = None


@dataclass(slots=True)
class WarehouseUploadDocument:
    warehouse_upload_id: int
    report_type_key: str
    original_filename: str | None = None
    content_type: str | None = None
    file_path: str | None = None
    file_bytes: bytes | None = None
    captured_at: datetime | str | None = None
    cutoff_date: date | datetime | str | None = None
    date_from: date | datetime | str | None = None
    date_to: date | datetime | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.report_type_key != CARGOS_RECURRENTES_REPORT_TYPE_KEY:
            raise CargosRecurrentesUploadLoadError(
                "El upload recibido no corresponde a 'cargos_recurrentes'. "
                f"Recibido: {self.report_type_key!r}"
            )

        if not self.file_path and self.file_bytes is None:
            raise CargosRecurrentesUploadLoadError(
                "El upload Cargos Recurrentes debe traer 'file_path' o 'file_bytes'."
            )

        if self.date_to is None and self.cutoff_date is None:
            raise CargosRecurrentesUploadLoadError(
                "El upload Cargos Recurrentes debe traer 'date_to' o 'cutoff_date' resuelto."
            )


@dataclass(slots=True)
class IngestCargosRecurrentesResult:
    status: str
    was_idempotent: bool
    snapshot_id: int
    warehouse_upload_id: int
    report_type_key: str
    business_date: str
    captured_at: str
    snapshot_kind: str
    is_canonical: bool
    row_count_detected: int
    row_count_valid: int
    row_count_rejected: int
    rows_inserted: int | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def register_cargos_recurrentes_ingestor(app) -> None:
    app.config["WAREHOUSE_CARGOS_RECURRENTES_INGESTOR"] = ingest_cargos_recurrentes_upload


def _resolve_callable(
    *,
    config_keys: tuple[str, ...],
    description: str,
    default: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    for config_key in config_keys:
        fn = current_app.config.get(config_key)
        if callable(fn):
            return fn

    if callable(default):
        return default

    raise NotImplementedError(
        f"No se encontró un callable configurado para {description}. "
        f"Se intentó con: {config_keys!r}"
    )


def _invoke_callable_flexibly(fn: Callable[..., Any], **kwargs: Any) -> Any:
    accepted_kwargs = {}
    fn_signature = signature(fn)

    for name, param in fn_signature.parameters.items():
        if name in kwargs:
            accepted_kwargs[name] = kwargs[name]
        elif param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            return fn(**kwargs)

    return fn(**accepted_kwargs)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)

    if is_dataclass(value):
        return asdict(value)

    raise CargosRecurrentesIngestionError(
        "Se esperaba dict o dataclass serializable."
    )


def _ensure_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        return date.fromisoformat(value)

    raise CargosRecurrentesIngestionError(
        f"No se pudo convertir a date: {value!r}"
    )


def _ensure_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        return datetime.fromisoformat(value)

    raise CargosRecurrentesIngestionError(
        f"No se pudo convertir a datetime: {value!r}"
    )


def _ensure_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise CargosRecurrentesIngestionError(
            f"{field_name} no puede ser bool."
        )

    try:
        return int(value)
    except Exception as exc:
        raise CargosRecurrentesIngestionError(
            f"No se pudo convertir a int {field_name!r}: {value!r}"
        ) from exc


def _validate_command(command: IngestCargosRecurrentesCommand) -> None:
    if _ensure_int(command.warehouse_upload_id, field_name="warehouse_upload_id") <= 0:
        raise CargosRecurrentesIngestionError(
            "warehouse_upload_id debe ser un entero positivo."
        )

    if command.snapshot_kind not in SUPPORTED_SNAPSHOT_KINDS:
        raise CargosRecurrentesIngestionError(
            f"snapshot_kind inválido para Cargos Recurrentes: {command.snapshot_kind!r}. "
            f"Permitidos: {sorted(SUPPORTED_SNAPSHOT_KINDS)}"
        )


def _resolve_upload_loader() -> Callable[..., Any]:
    return _resolve_callable(
        config_keys=(
            "WAREHOUSE_UPLOAD_LOADER",
            "WAREHOUSE_UPLOAD_LOADER_SQL",
        ),
        description="cargar el upload documental de Warehouse",
    )


def _resolve_parser() -> Callable[..., Any]:
    return _resolve_callable(
        config_keys=("WAREHOUSE_CARGOS_RECURRENTES_PARSER",),
        description="parsear el XLSX de Cargos Recurrentes",
        default=parse_cargos_recurrentes_xlsx,
    )


def _resolve_repository() -> Callable[..., Any]:
    return _resolve_callable(
        config_keys=("WAREHOUSE_CARGOS_RECURRENTES_REPOSITORY",),
        description="persistir el snapshot estructurado de Cargos Recurrentes",
        default=persist_cargos_recurrentes_snapshot,
    )


def _resolve_optional_canonicality_resolver() -> Callable[..., dict[str, Any] | None] | None:
    fn = current_app.config.get("WAREHOUSE_CARGOS_RECURRENTES_CANONICALITY_RESOLVER")
    return fn if callable(fn) else None


def _resolve_optional_advisory_lock_key(
    *,
    upload_doc: WarehouseUploadDocument,
    snapshot_kind: str,
    business_date: date,
) -> int | None:
    resolver = current_app.config.get("WAREHOUSE_CARGOS_RECURRENTES_ADVISORY_LOCK_RESOLVER")
    if not callable(resolver):
        return None

    result = _invoke_callable_flexibly(
        resolver,
        warehouse_upload_id=upload_doc.warehouse_upload_id,
        business_date=business_date,
        snapshot_kind=snapshot_kind,
        report_type_key=upload_doc.report_type_key,
        upload_metadata=upload_doc.metadata,
    )
    if result is None:
        return None
    return int(result)


def _normalize_upload_document(
    *,
    warehouse_upload_id: int,
    raw_result: Any,
) -> WarehouseUploadDocument:
    payload = _as_dict(raw_result)
    metadata = payload.get("metadata") or {}

    upload_doc = WarehouseUploadDocument(
        warehouse_upload_id=warehouse_upload_id,
        report_type_key=payload.get("report_type_key") or payload.get("report_type") or "",
        original_filename=payload.get("original_filename"),
        content_type=payload.get("content_type"),
        file_path=payload.get("file_path") or payload.get("storage_path"),
        file_bytes=payload.get("file_bytes"),
        captured_at=payload.get("captured_at"),
        cutoff_date=payload.get("cutoff_date") or metadata.get("cutoff_date"),
        date_from=payload.get("date_from") or metadata.get("date_from"),
        date_to=payload.get("date_to") or metadata.get("date_to"),
        metadata=metadata,
    )
    upload_doc.validate()
    return upload_doc


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
        raise CargosRecurrentesUploadLoadError(
            f"Falló la carga del upload documental Cargos Recurrentes para warehouse_upload_id={warehouse_upload_id}."
        ) from exc

    return _normalize_upload_document(
        warehouse_upload_id=warehouse_upload_id,
        raw_result=raw_result,
    )


def _normalize_parsed_snapshot(raw_result: Any) -> dict[str, Any]:
    if isinstance(raw_result, CargosRecurrentesParseResult):
        payload = asdict(raw_result)
    else:
        payload = _as_dict(raw_result)

    rows = payload.get("rows") or []
    if not isinstance(rows, list) or not rows:
        raise CargosRecurrentesParseInvocationError(
            "El parser de Cargos Recurrentes no devolvió rows válidas."
        )

    row_count = _ensure_int(
        payload.get("row_count", len(rows)),
        field_name="row_count",
    )

    return {
        **payload,
        "rows": rows,
        "row_count": row_count,
        "row_count_valid": row_count,
        "row_count_rejected": 0,
    }


def _parse_upload_document(
    *,
    upload_doc: WarehouseUploadDocument,
) -> dict[str, Any]:
    parser = _resolve_parser()

    try:
        raw_result = _invoke_callable_flexibly(
            parser,
            file_path=upload_doc.file_path,
            file_bytes=upload_doc.file_bytes,
        )
    except Exception as exc:
        raise CargosRecurrentesParseInvocationError(
            f"Falló el parser de Cargos Recurrentes para warehouse_upload_id={upload_doc.warehouse_upload_id}."
        ) from exc

    return _normalize_parsed_snapshot(raw_result)


def _resolve_business_date(upload_doc: WarehouseUploadDocument) -> date:
    if upload_doc.date_to is not None:
        return _ensure_date(upload_doc.date_to)

    if upload_doc.cutoff_date is not None:
        return _ensure_date(upload_doc.cutoff_date)

    raise CargosRecurrentesUploadLoadError(
        "No se pudo resolver business_date para Cargos Recurrentes."
    )


def _build_result(repository_result: Any) -> IngestCargosRecurrentesResult:
    payload = _as_dict(repository_result)

    return IngestCargosRecurrentesResult(
        status=str(payload["status"]),
        was_idempotent=bool(payload["was_idempotent"]),
        snapshot_id=int(payload["snapshot_id"]),
        warehouse_upload_id=int(payload["warehouse_upload_id"]),
        report_type_key=str(payload["report_type_key"]),
        business_date=str(payload["business_date"]),
        captured_at=str(payload["captured_at"]),
        snapshot_kind=str(payload["snapshot_kind"]),
        is_canonical=bool(payload["is_canonical"]),
        row_count_detected=int(payload["row_count_detected"]),
        row_count_valid=int(payload["row_count_valid"]),
        row_count_rejected=int(payload["row_count_rejected"]),
        rows_inserted=(
            None if payload.get("rows_inserted") is None else int(payload["rows_inserted"])
        ),
        metadata=dict(payload.get("metadata") or {}),
    )


def ingest_cargos_recurrentes_upload(
    *,
    warehouse_upload_id: int,
    snapshot_kind: str,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
) -> dict[str, Any]:
    command = IngestCargosRecurrentesCommand(
        warehouse_upload_id=warehouse_upload_id,
        snapshot_kind=snapshot_kind,
        requested_by=requested_by,
        ingestion_source=ingestion_source,
    )
    _validate_command(command)

    upload_doc = _load_upload_document(
        warehouse_upload_id=command.warehouse_upload_id,
    )

    business_date = _resolve_business_date(upload_doc)
    parsed_snapshot = _parse_upload_document(upload_doc=upload_doc)

    repository = _resolve_repository()
    canonicality_resolver = _resolve_optional_canonicality_resolver()
    advisory_lock_key = _resolve_optional_advisory_lock_key(
        upload_doc=upload_doc,
        snapshot_kind=command.snapshot_kind,
        business_date=business_date,
    )

    try:
        repository_result = _invoke_callable_flexibly(
            repository,
            warehouse_upload_id=upload_doc.warehouse_upload_id,
            report_type_key=upload_doc.report_type_key,
            business_date=business_date,
            captured_at=_ensure_datetime(upload_doc.captured_at),
            snapshot_kind=command.snapshot_kind,
            parsed_snapshot=parsed_snapshot,
            canonicality_resolver=canonicality_resolver,
            advisory_lock_key=advisory_lock_key,
            requested_by=command.requested_by,
            ingestion_source=command.ingestion_source,
        )
    except Exception as exc:
        raise CargosRecurrentesPersistError(
            f"Falló la persistencia estructurada de Cargos Recurrentes para warehouse_upload_id={upload_doc.warehouse_upload_id}."
        ) from exc

    return _build_result(repository_result).to_dict()