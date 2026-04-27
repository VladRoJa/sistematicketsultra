# backend/app/warehouse/services/ingresos_totalpass_ingestion_service.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import importlib
import inspect
from pathlib import Path
from typing import Any, Callable

from flask import current_app

from app.warehouse.services.track_branch_alias_resolver_service import (
    resolve_track_branch_alias,
)


INGRESOS_TOTALPASS_REPORT_TYPE_KEY = "ingresos_totalpass"
SUPPORTED_SNAPSHOT_KINDS = frozenset({"daily"})


class IngresosTotalpassIngestionServiceError(RuntimeError):
    """Error base de la ingesta estructurada de ingresos_totalpass."""


class WarehouseUploadNotFound(IngresosTotalpassIngestionServiceError):
    """No existe el upload documental solicitado."""


class WrongReportTypeForIngestion(IngresosTotalpassIngestionServiceError):
    """El upload no corresponde a ingresos_totalpass."""


class IngresosTotalpassParseError(IngresosTotalpassIngestionServiceError):
    """Fallo de contrato/layout al parsear el archivo."""


class SnapshotPersistenceError(IngresosTotalpassIngestionServiceError):
    """Fallo persistiendo snapshot o rows."""


class CanonicalityConflictError(IngresosTotalpassIngestionServiceError):
    """Conflicto inesperado resolviendo canonicalidad."""


@dataclass(slots=True)
class WarehouseUploadDocument:
    warehouse_upload_id: int
    report_type_key: str
    original_filename: str
    content_type: str | None = None
    storage_path: str | None = None
    captured_at: datetime | None = None
    cutoff_date: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedIngresosTotalpassRow:
    raw_branch_name: str
    sucursal_canon: str
    monto_acumulado_mes: float | None = None
    usage_count: int | None = None
    student_count: int | None = None


@dataclass(slots=True)
class ParsedIngresosTotalpassSnapshot:
    warehouse_upload_id: int
    report_type_key: str
    business_date: date
    captured_at: datetime
    row_count_detected: int
    row_count_valid: int
    row_count_rejected: int
    rows: list[ParsedIngresosTotalpassRow]
    issues: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class IngestIngresosTotalpassCommand:
    warehouse_upload_id: int
    snapshot_kind: str
    requested_by: str | None = None
    ingestion_source: str | None = None


@dataclass(slots=True)
class IngestIngresosTotalpassResult:
    snapshot_id: int | None
    warehouse_upload_id: int
    business_date: date | None
    snapshot_kind: str
    is_canonical: bool
    status: str
    was_idempotent: bool
    row_count_detected: int
    row_count_valid: int
    row_count_rejected: int
    issues_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "warehouse_upload_id": self.warehouse_upload_id,
            "business_date": (
                self.business_date.isoformat() if self.business_date else None
            ),
            "snapshot_kind": self.snapshot_kind,
            "is_canonical": self.is_canonical,
            "status": self.status,
            "was_idempotent": self.was_idempotent,
            "row_count_detected": self.row_count_detected,
            "row_count_valid": self.row_count_valid,
            "row_count_rejected": self.row_count_rejected,
            "issues_count": self.issues_count,
            "metadata": self.metadata,
        }


def register_ingresos_totalpass_ingestor(app) -> None:
    app.config["WAREHOUSE_INGRESOS_TOTALPASS_INGESTOR"] = (
        ingest_ingresos_totalpass_upload
    )


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
            raise IngresosTotalpassIngestionServiceError(
                f"No se pudo parsear datetime desde string ISO: {value!r}"
            ) from exc

    if value is None:
        return _utc_now()

    raise IngresosTotalpassIngestionServiceError(
        "Se recibió un datetime con tipo no soportado."
    )


def _ensure_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise IngresosTotalpassIngestionServiceError(
                f"No se pudo parsear date desde string ISO: {value!r}"
            ) from exc

    raise IngresosTotalpassIngestionServiceError(
        "Se recibió un business_date con tipo no soportado."
    )


def _validate_command(command: IngestIngresosTotalpassCommand) -> None:
    if (
        not isinstance(command.warehouse_upload_id, int)
        or command.warehouse_upload_id <= 0
    ):
        raise ValueError("'warehouse_upload_id' debe ser entero positivo.")

    if command.snapshot_kind not in SUPPORTED_SNAPSHOT_KINDS:
        raise ValueError(
            "El 'snapshot_kind' no es válido para ingresos_totalpass. "
            f"Permitidos: {sorted(SUPPORTED_SNAPSHOT_KINDS)}"
        )


def _import_callable(module_path: str, entrypoint_name: str) -> Callable[..., Any]:
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        raise IngresosTotalpassIngestionServiceError(
            f"No se pudo importar el módulo configurado: {module_path!r}"
        ) from exc

    fn = getattr(module, entrypoint_name, None)
    if not callable(fn):
        raise IngresosTotalpassIngestionServiceError(
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
        raise IngresosTotalpassIngestionServiceError(
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
        raise IngresosTotalpassIngestionServiceError(
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


def _resolve_parser() -> Callable[..., Any]:
    return _resolve_callable(
        direct_callable_key="WAREHOUSE_INGRESOS_TOTALPASS_PARSER",
        module_key="WAREHOUSE_INGRESOS_TOTALPASS_PARSER_MODULE",
        entrypoint_key="WAREHOUSE_INGRESOS_TOTALPASS_PARSER_ENTRYPOINT",
        description="parsear ingresos_totalpass",
    )


def _resolve_repository() -> Callable[..., Any]:
    return _resolve_callable(
        direct_callable_key="WAREHOUSE_INGRESOS_TOTALPASS_REPOSITORY",
        module_key="WAREHOUSE_INGRESOS_TOTALPASS_REPOSITORY_MODULE",
        entrypoint_key="WAREHOUSE_INGRESOS_TOTALPASS_REPOSITORY_ENTRYPOINT",
        description="persistir snapshots de ingresos_totalpass",
    )


def _resolve_advisory_lock_impl() -> Callable[..., Any] | None:
    direct_callable = current_app.config.get(
        "WAREHOUSE_INGRESOS_TOTALPASS_ADVISORY_LOCK"
    )
    if callable(direct_callable):
        return direct_callable

    module_path = current_app.config.get(
        "WAREHOUSE_INGRESOS_TOTALPASS_ADVISORY_LOCK_MODULE"
    )
    entrypoint_name = current_app.config.get(
        "WAREHOUSE_INGRESOS_TOTALPASS_ADVISORY_LOCK_ENTRYPOINT"
    )

    if not module_path and not entrypoint_name:
        return None

    if not isinstance(module_path, str) or not module_path.strip():
        raise IngresosTotalpassIngestionServiceError(
            "Debes configurar 'WAREHOUSE_INGRESOS_TOTALPASS_ADVISORY_LOCK_MODULE' como string."
        )

    if not isinstance(entrypoint_name, str) or not entrypoint_name.strip():
        raise IngresosTotalpassIngestionServiceError(
            "Debes configurar 'WAREHOUSE_INGRESOS_TOTALPASS_ADVISORY_LOCK_ENTRYPOINT' como string."
        )

    return _import_callable(module_path.strip(), entrypoint_name.strip())


def _load_warehouse_upload(warehouse_upload_id: int) -> WarehouseUploadDocument:
    loader = _resolve_upload_loader()

    try:
        raw_result = _invoke_callable_flexibly(
            loader,
            kwargs={"warehouse_upload_id": warehouse_upload_id},
            description="warehouse upload loader",
        )
    except NotImplementedError:
        raise
    except Exception as exc:
        raise IngresosTotalpassIngestionServiceError(
            f"Falló la carga del upload documental {warehouse_upload_id}."
        ) from exc

    if raw_result is None:
        raise WarehouseUploadNotFound(
            f"No se encontró el warehouse_upload_id={warehouse_upload_id}."
        )

    if isinstance(raw_result, WarehouseUploadDocument):
        return raw_result

    if isinstance(raw_result, dict):
        report_type_key = raw_result.get("report_type_key")
        original_filename = raw_result.get("original_filename")

        if not isinstance(report_type_key, str) or not report_type_key.strip():
            raise IngresosTotalpassIngestionServiceError(
                "El loader del upload debe devolver 'report_type_key'."
            )

        if not isinstance(original_filename, str) or not original_filename.strip():
            raise IngresosTotalpassIngestionServiceError(
                "El loader del upload debe devolver 'original_filename'."
            )

        upload_id = raw_result.get("warehouse_upload_id", warehouse_upload_id)
        if not isinstance(upload_id, int):
            raise IngresosTotalpassIngestionServiceError(
                "El loader del upload debe devolver 'warehouse_upload_id' entero."
            )

        return WarehouseUploadDocument(
            warehouse_upload_id=upload_id,
            report_type_key=report_type_key.strip(),
            original_filename=original_filename.strip(),
            content_type=raw_result.get("content_type"),
            storage_path=raw_result.get("storage_path"),
            captured_at=_ensure_datetime(raw_result.get("captured_at")),
            cutoff_date=raw_result.get("cutoff_date"),
            metadata=raw_result.get("metadata") or {},
        )

    raise IngresosTotalpassIngestionServiceError(
        "El loader del upload devolvió un tipo no soportado. "
        "Debe devolver WarehouseUploadDocument, dict o None."
    )


def _validate_upload_for_ingresos_totalpass(upload: WarehouseUploadDocument) -> None:
    if upload.report_type_key != INGRESOS_TOTALPASS_REPORT_TYPE_KEY:
        raise WrongReportTypeForIngestion(
            f"El upload {upload.warehouse_upload_id} no corresponde a "
            f"{INGRESOS_TOTALPASS_REPORT_TYPE_KEY!r}, sino a {upload.report_type_key!r}."
        )

    if not upload.storage_path:
        raise IngresosTotalpassIngestionServiceError(
            "El upload documental no tiene 'storage_path'."
        )

    path = Path(upload.storage_path)
    if not path.exists():
        raise IngresosTotalpassIngestionServiceError(
            f"El archivo del upload documental no existe: {path}"
        )


def _normalize_parsed_row(raw_row: Any) -> ParsedIngresosTotalpassRow:
    if isinstance(raw_row, ParsedIngresosTotalpassRow):
        return raw_row

    if not isinstance(raw_row, dict):
        raise IngresosTotalpassParseError(
            "El parser devolvió una fila detalle con tipo no soportado."
        )

    raw_branch_name = raw_row.get("raw_branch_name") or raw_row.get("name")
    if not isinstance(raw_branch_name, str) or not raw_branch_name.strip():
        raise IngresosTotalpassParseError(
            "El parser devolvió una fila detalle sin 'raw_branch_name' válida."
        )

    sucursal_canon = resolve_track_branch_alias(
        source_family="totalpass_family",
        raw_branch_name=raw_branch_name.strip(),
    )
    if sucursal_canon is None:
        raise IngresosTotalpassParseError(
            f"No se pudo resolver alias de sucursal para TotalPass: {raw_branch_name!r}"
        )

    return ParsedIngresosTotalpassRow(
        raw_branch_name=raw_branch_name.strip(),
        sucursal_canon=sucursal_canon,
        monto_acumulado_mes=raw_row.get("monto_acumulado_mes") or raw_row.get("value"),
        usage_count=raw_row.get("usage_count") or raw_row.get("usageCount"),
        student_count=raw_row.get("student_count") or raw_row.get("studentCount"),
    )


def _normalize_parsed_snapshot(raw_result: Any) -> ParsedIngresosTotalpassSnapshot:
    if isinstance(raw_result, ParsedIngresosTotalpassSnapshot):
        return raw_result

    if not isinstance(raw_result, dict):
        raise IngresosTotalpassParseError(
            "El parser devolvió un tipo no soportado. Debe devolver dict o ParsedIngresosTotalpassSnapshot."
        )

    rows_raw = raw_result.get("rows")
    if not isinstance(rows_raw, list):
        raise IngresosTotalpassParseError(
            "El parser debe devolver 'rows' como lista."
        )

    rows = [_normalize_parsed_row(item) for item in rows_raw]

    return ParsedIngresosTotalpassSnapshot(
        warehouse_upload_id=int(raw_result["warehouse_upload_id"]),
        report_type_key=str(raw_result["report_type_key"]),
        business_date=_ensure_date(raw_result["business_date"]),
        captured_at=_ensure_datetime(raw_result.get("captured_at")),
        row_count_detected=int(raw_result.get("row_count_detected", len(rows))),
        row_count_valid=int(raw_result.get("row_count_valid", len(rows))),
        row_count_rejected=int(raw_result.get("row_count_rejected", 0)),
        rows=rows,
        issues=raw_result.get("issues") or [],
    )


def _parse_upload(upload: WarehouseUploadDocument) -> ParsedIngresosTotalpassSnapshot:
    parser = _resolve_parser()

    try:
        raw_result = _invoke_callable_flexibly(
            parser,
            kwargs={
                "warehouse_upload_id": upload.warehouse_upload_id,
                "file_path": upload.storage_path,
                "original_filename": upload.original_filename,
                "captured_at": upload.captured_at,
                "cutoff_date": upload.cutoff_date,                
                "report_type_key": upload.report_type_key,
                "content_type": upload.content_type,
                "storage_path": upload.storage_path,
            },
            description="ingresos_totalpass parser",
        )
    except NotImplementedError:
        raise
    except IngresosTotalpassParseError:
        raise
    except Exception as exc:
        raise IngresosTotalpassParseError(
            f"Falló el parser de ingresos_totalpass para upload {upload.warehouse_upload_id}."
        ) from exc

    parsed = _normalize_parsed_snapshot(raw_result)

    if parsed.report_type_key != INGRESOS_TOTALPASS_REPORT_TYPE_KEY:
        raise IngresosTotalpassParseError(
            "El parser devolvió un report_type_key distinto a 'ingresos_totalpass'."
        )

    if parsed.row_count_valid != len(parsed.rows):
        raise IngresosTotalpassParseError(
            "Inconsistencia del parser: row_count_valid no coincide con cantidad de rows."
        )

    if parsed.row_count_valid + parsed.row_count_rejected > parsed.row_count_detected:
        raise IngresosTotalpassParseError(
            "Inconsistencia del parser: valid + rejected no puede ser mayor que detected."
        )

    if parsed.row_count_valid <= 0:
        raise IngresosTotalpassParseError(
            "El parser no devolvió filas válidas de detalle."
        )

    return parsed


def _apply_advisory_lock_if_configured(
    *,
    business_date: date,
    report_type_key: str,
) -> None:
    lock_impl = _resolve_advisory_lock_impl()
    if lock_impl is None:
        current_app.logger.info(
            "No hay advisory lock configurado para ingresos_totalpass; se continúa sin lock explícito."
        )
        return

    try:
        _invoke_callable_flexibly(
            lock_impl,
            kwargs={
                "report_type_key": report_type_key,
                "business_date": business_date,
            },
            description="ingresos_totalpass advisory lock",
        )
    except Exception as exc:
        raise IngresosTotalpassIngestionServiceError(
            "Falló la toma del advisory lock para ingresos_totalpass."
        ) from exc


def _resolve_canonicality_decision(
    *,
    existing_canonical_snapshot: dict[str, Any] | None,
    snapshot_kind: str,
) -> tuple[bool, int | None]:
    if existing_canonical_snapshot is None:
        return True, None

    if snapshot_kind == "daily":
        return False, None

    raise CanonicalityConflictError(
        f"No se pudo resolver canonicalidad para snapshot_kind={snapshot_kind!r}."
    )


def _persist_snapshot_transactionally(
    *,
    parsed: ParsedIngresosTotalpassSnapshot,
    command: IngestIngresosTotalpassCommand,
) -> IngestIngresosTotalpassResult:
    repository = _resolve_repository()

    try:
        raw_result = _invoke_callable_flexibly(
            repository,
            kwargs={
                "parsed_snapshot": parsed,
                "snapshot_kind": command.snapshot_kind,
                "requested_by": command.requested_by,
                "ingestion_source": command.ingestion_source,
                "advisory_lock_callback": _apply_advisory_lock_if_configured,
                "canonicality_resolver": _resolve_canonicality_decision,
            },
            description="ingresos_totalpass repository",
        )
    except NotImplementedError:
        raise
    except Exception as exc:
        raise SnapshotPersistenceError(
            "Falló la persistencia transaccional de ingresos_totalpass."
        ) from exc

    if isinstance(raw_result, IngestIngresosTotalpassResult):
        return raw_result

    if not isinstance(raw_result, dict):
        raise SnapshotPersistenceError(
            "El repositorio de ingresos_totalpass devolvió un tipo no soportado."
        )

    business_date_raw = raw_result.get("business_date", parsed.business_date)
    business_date = (
        _ensure_date(business_date_raw)
        if business_date_raw is not None else None
    )

    return IngestIngresosTotalpassResult(
        snapshot_id=raw_result.get("snapshot_id"),
        warehouse_upload_id=parsed.warehouse_upload_id,
        business_date=business_date,
        snapshot_kind=raw_result.get("snapshot_kind", command.snapshot_kind),
        is_canonical=bool(raw_result.get("is_canonical", False)),
        status=str(raw_result.get("status", "ingested")),
        was_idempotent=bool(raw_result.get("was_idempotent", False)),
        row_count_detected=int(
            raw_result.get("row_count_detected", parsed.row_count_detected)
        ),
        row_count_valid=int(
            raw_result.get("row_count_valid", parsed.row_count_valid)
        ),
        row_count_rejected=int(
            raw_result.get("row_count_rejected", parsed.row_count_rejected)
        ),
        issues_count=int(raw_result.get("issues_count", len(parsed.issues))),
        metadata=raw_result.get("metadata") or {},
    )


def ingest_ingresos_totalpass_upload(
    *,
    warehouse_upload_id: int,
    snapshot_kind: str,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
) -> dict[str, Any]:
    command = IngestIngresosTotalpassCommand(
        warehouse_upload_id=warehouse_upload_id,
        snapshot_kind=snapshot_kind,
        requested_by=requested_by,
        ingestion_source=ingestion_source,
    )
    _validate_command(command)

    current_app.logger.info(
        "Starting ingresos_totalpass ingestion: warehouse_upload_id=%s snapshot_kind=%s",
        command.warehouse_upload_id,
        command.snapshot_kind,
    )

    upload = _load_warehouse_upload(command.warehouse_upload_id)
    _validate_upload_for_ingresos_totalpass(upload)
    parsed = _parse_upload(upload)

    result = _persist_snapshot_transactionally(
        parsed=parsed,
        command=command,
    )

    current_app.logger.info(
        "Ingresos_totalpass ingestion finished: warehouse_upload_id=%s snapshot_id=%s status=%s is_canonical=%s",
        result.warehouse_upload_id,
        result.snapshot_id,
        result.status,
        result.is_canonical,
    )

    return result.to_dict()