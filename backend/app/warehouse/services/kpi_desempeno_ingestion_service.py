# backend/app/warehouse/services/kpi_desempeno_ingestion_service.py


from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from inspect import signature
from typing import Any, Callable

from flask import current_app

from app.warehouse.services.kpi_desempeno_parser import (
    KpiDesempenoParseResult,
    parse_kpi_desempeno_xlsx,
)
from app.warehouse.services.kpi_desempeno_repository import (
    KPI_DESEMPENO_REPORT_TYPE_KEY,
    persist_kpi_desempeno_snapshot,
)


SUPPORTED_SNAPSHOT_KINDS = frozenset({"daily"})


class KpiDesempenoIngestionError(RuntimeError):
    """Error base de la ingesta estructurada de KPI Desempeño."""


class KpiDesempenoUploadLoadError(KpiDesempenoIngestionError):
    """Fallo al cargar el upload documental desde Warehouse."""


class KpiDesempenoParseInvocationError(KpiDesempenoIngestionError):
    """Fallo al parsear el upload KPI."""


class KpiDesempenoPersistError(KpiDesempenoIngestionError):
    """Fallo al persistir el snapshot estructurado KPI."""


@dataclass(slots=True)
class IngestKpiDesempenoCommand:
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
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.report_type_key != KPI_DESEMPENO_REPORT_TYPE_KEY:
            raise KpiDesempenoUploadLoadError(
                "El upload recibido no corresponde a 'kpi_desempeno'. "
                f"Recibido: {self.report_type_key!r}"
            )

        if not self.file_path and self.file_bytes is None:
            raise KpiDesempenoUploadLoadError(
                "El upload KPI debe traer 'file_path' o 'file_bytes'."
            )

        if self.cutoff_date is None:
            raise KpiDesempenoUploadLoadError(
                "El upload KPI debe traer 'cutoff_date' resuelto."
            )


@dataclass(slots=True)
class IngestKpiDesempenoResult:
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


def register_kpi_desempeno_ingestor(app) -> None:
    app.config["WAREHOUSE_KPI_DESEMPENO_INGESTOR"] = ingest_kpi_desempeno_upload


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

    raise KpiDesempenoIngestionError(
        "Se esperaba dict o dataclass serializable."
    )


def _ensure_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        return date.fromisoformat(value)

    raise KpiDesempenoIngestionError(
        f"No se pudo convertir a date: {value!r}"
    )


def _ensure_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        return datetime.fromisoformat(value)

    raise KpiDesempenoIngestionError(
        f"No se pudo convertir a datetime: {value!r}"
    )


def _ensure_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise KpiDesempenoIngestionError(
            f"{field_name} no puede ser bool."
        )

    try:
        return int(value)
    except Exception as exc:
        raise KpiDesempenoIngestionError(
            f"No se pudo convertir a int {field_name!r}: {value!r}"
        ) from exc


def _validate_command(command: IngestKpiDesempenoCommand) -> None:
    if _ensure_int(command.warehouse_upload_id, field_name="warehouse_upload_id") <= 0:
        raise KpiDesempenoIngestionError(
            "warehouse_upload_id debe ser un entero positivo."
        )

    if command.snapshot_kind not in SUPPORTED_SNAPSHOT_KINDS:
        raise KpiDesempenoIngestionError(
            f"snapshot_kind inválido para KPI Desempeño: {command.snapshot_kind!r}. "
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
        config_keys=("WAREHOUSE_KPI_DESEMPENO_PARSER",),
        description="parsear el XLSX de KPI Desempeño",
        default=parse_kpi_desempeno_xlsx,
    )


def _resolve_repository() -> Callable[..., Any]:
    return _resolve_callable(
        config_keys=("WAREHOUSE_KPI_DESEMPENO_REPOSITORY",),
        description="persistir el snapshot estructurado de KPI Desempeño",
        default=persist_kpi_desempeno_snapshot,
    )


def _resolve_optional_canonicality_resolver() -> Callable[..., dict[str, Any] | None] | None:
    fn = current_app.config.get("WAREHOUSE_KPI_DESEMPENO_CANONICALITY_RESOLVER")
    return fn if callable(fn) else None


def _resolve_optional_advisory_lock_key(
    *,
    upload_doc: WarehouseUploadDocument,
    snapshot_kind: str,
) -> int | None:
    resolver = current_app.config.get("WAREHOUSE_KPI_DESEMPENO_ADVISORY_LOCK_RESOLVER")
    if not callable(resolver):
        return None

    result = _invoke_callable_flexibly(
        resolver,
        warehouse_upload_id=upload_doc.warehouse_upload_id,
        business_date=_ensure_date(upload_doc.cutoff_date),
        snapshot_kind=snapshot_kind,
        report_type_key=upload_doc.report_type_key,
        upload_metadata=upload_doc.metadata,
    )
    if result is None:
        return None
    return int(result)

def _resolve_kpi_cutoff_date_from_artifact(
    *,
    original_filename: str | None,
    file_path: str | None,
) -> date | None:
    import re
    from pathlib import Path

    candidate_name = None

    if original_filename:
        candidate_name = Path(original_filename).name
    elif file_path:
        candidate_name = Path(file_path).name

    if not candidate_name:
        return None

    match = re.match(
        r"^kpi_desempeno_(\d{4})-(\d{2})-(\d{2})_\d{2}-\d{2}\.xlsx$",
        candidate_name,
        re.IGNORECASE,
    )
    if not match:
        return None

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))

    return date(year, month, day)

def _normalize_upload_document(
    *,
    warehouse_upload_id: int,
    raw_result: Any,
) -> WarehouseUploadDocument:
    payload = _as_dict(raw_result)
    metadata = payload.get("metadata") or {}

    resolved_file_path = payload.get("file_path") or payload.get("storage_path")
    resolved_cutoff_date = (
        payload.get("cutoff_date")
        or metadata.get("cutoff_date")
        or _resolve_kpi_cutoff_date_from_artifact(
            original_filename=payload.get("original_filename"),
            file_path=resolved_file_path,
        )
    )

    upload_doc = WarehouseUploadDocument(
        warehouse_upload_id=warehouse_upload_id,
        report_type_key=payload.get("report_type_key") or payload.get("report_type") or "",
        original_filename=payload.get("original_filename"),
        content_type=payload.get("content_type"),
        file_path=resolved_file_path,
        file_bytes=payload.get("file_bytes"),
        captured_at=payload.get("captured_at"),
        cutoff_date=resolved_cutoff_date,
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
        raise KpiDesempenoUploadLoadError(
            f"Falló la carga del upload documental KPI para warehouse_upload_id={warehouse_upload_id}."
        ) from exc

    return _normalize_upload_document(
        warehouse_upload_id=warehouse_upload_id,
        raw_result=raw_result,
    )


def _normalize_parsed_snapshot(raw_result: Any) -> dict[str, Any]:
    if isinstance(raw_result, KpiDesempenoParseResult):
        payload = asdict(raw_result)
    else:
        payload = _as_dict(raw_result)

    rows = payload.get("rows") or []
    if not isinstance(rows, list) or not rows:
        raise KpiDesempenoParseInvocationError(
            "El parser de KPI no devolvió rows válidas."
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
        raise KpiDesempenoParseInvocationError(
            f"Falló el parser de KPI para warehouse_upload_id={upload_doc.warehouse_upload_id}."
        ) from exc

    return _normalize_parsed_snapshot(raw_result)


def _build_result(repository_result: Any) -> IngestKpiDesempenoResult:
    payload = _as_dict(repository_result)

    return IngestKpiDesempenoResult(
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


def ingest_kpi_desempeno_upload(
    *,
    warehouse_upload_id: int,
    snapshot_kind: str,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
) -> dict[str, Any]:
    """
    Flujo alineado a Dirección:
    1) validar command
    2) cargar upload documental
    3) validar que el upload sea KPI Desempeño
    4) parsear el XLSX
    5) persistir vía repository
    """
    command = IngestKpiDesempenoCommand(
        warehouse_upload_id=warehouse_upload_id,
        snapshot_kind=snapshot_kind,
        requested_by=requested_by,
        ingestion_source=ingestion_source,
    )
    _validate_command(command)

    upload_doc = _load_upload_document(
        warehouse_upload_id=command.warehouse_upload_id,
    )

    parsed_snapshot = _parse_upload_document(upload_doc=upload_doc)

    repository = _resolve_repository()
    canonicality_resolver = _resolve_optional_canonicality_resolver()
    advisory_lock_key = _resolve_optional_advisory_lock_key(
        upload_doc=upload_doc,
        snapshot_kind=command.snapshot_kind,
    )

    try:
        repository_result = _invoke_callable_flexibly(
            repository,
            warehouse_upload_id=upload_doc.warehouse_upload_id,
            report_type_key=upload_doc.report_type_key,
            business_date=_ensure_date(upload_doc.cutoff_date),
            captured_at=_ensure_datetime(upload_doc.captured_at),
            snapshot_kind=command.snapshot_kind,
            parsed_snapshot=parsed_snapshot,
            canonicality_resolver=canonicality_resolver,
            advisory_lock_key=advisory_lock_key,
            requested_by=command.requested_by,
            ingestion_source=command.ingestion_source,
        )
    except Exception as exc:
        raise KpiDesempenoPersistError(
            f"Falló la persistencia estructurada de KPI para warehouse_upload_id={upload_doc.warehouse_upload_id}."
        ) from exc

    return _build_result(repository_result).to_dict()