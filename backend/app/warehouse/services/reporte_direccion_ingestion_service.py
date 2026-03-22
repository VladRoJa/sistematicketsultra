# backend/app/warehouse/services/reporte_direccion_ingestion_service.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import importlib
import inspect
from pathlib import Path
from typing import Any, Callable

from flask import current_app


REPORTE_DIRECCION_REPORT_TYPE_KEY = "reporte_direccion"
SUPPORTED_SNAPSHOT_KINDS = frozenset({"daily", "month_end_close"})


class ReporteDireccionIngestionError(RuntimeError):
    """Error base de la ingesta estructurada de Reporte Dirección."""


class WarehouseUploadNotFound(ReporteDireccionIngestionError):
    """No existe el upload documental solicitado."""


class WrongReportTypeForIngestion(ReporteDireccionIngestionError):
    """El upload no corresponde a reporte_direccion."""


class ReporteDireccionParseError(ReporteDireccionIngestionError):
    """Fallo de contrato/layout al parsear el archivo."""


class SnapshotPersistenceError(ReporteDireccionIngestionError):
    """Fallo persistiendo snapshot o rows."""


class CanonicalityConflictError(ReporteDireccionIngestionError):
    """Conflicto inesperado resolviendo canonicalidad."""


@dataclass(slots=True)
class WarehouseUploadDocument:
    warehouse_upload_id: int
    report_type_key: str
    original_filename: str
    content_type: str | None = None
    storage_path: str | None = None
    captured_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedReporteDireccionRow:
    sucursal: str
    socios_activos_totales: int | None = None
    socios_activos_kpi: int | None = None
    socios_kpi_m2: float | None = None
    asistencia_hoy: int | None = None
    diarios_hoy: int | None = None
    gympass: int | None = None
    totalpass: int | None = None
    pases_cortesia: int | None = None
    ingreso_hoy: float | None = None
    ingreso_acumulado_semana_en_curso: float | None = None
    ingreso_acumulado_mes_en_curso: float | None = None
    membresia_domiciliada_mes_en_curso: float | None = None
    pago_posterior_domiciliado_mes_en_curso: float | None = None
    producto_pct_venta: float | None = None
    ingreso_acumulado_mismo_mes_anio_anterior: float | None = None
    hora_apertura_raw: str | None = None
    hora_clausura_raw: str | None = None


@dataclass(slots=True)
class ParsedReporteDireccionSnapshot:
    warehouse_upload_id: int
    report_type_key: str
    business_date: date
    captured_at: datetime
    row_count_detected: int
    row_count_valid: int
    row_count_rejected: int
    rows: list[ParsedReporteDireccionRow]
    issues: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class IngestReporteDireccionCommand:
    warehouse_upload_id: int
    snapshot_kind: str
    requested_by: str | None = None
    ingestion_source: str | None = None


@dataclass(slots=True)
class IngestReporteDireccionResult:
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


def register_reporte_direccion_ingestor(app) -> None:
    """
    Registra este servicio como hook principal del orquestador.

    Uso esperado más adelante en init/app factory:
        register_reporte_direccion_ingestor(app)

    Esto deja resuelto:
        app.config["WAREHOUSE_REPORTE_DIRECCION_INGESTOR"] = ingest_reporte_direccion_upload
    """
    app.config["WAREHOUSE_REPORTE_DIRECCION_INGESTOR"] = ingest_reporte_direccion_upload


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
            raise ReporteDireccionIngestionError(
                f"No se pudo parsear datetime desde string ISO: {value!r}"
            ) from exc

    if value is None:
        return _utc_now()

    raise ReporteDireccionIngestionError(
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
            raise ReporteDireccionIngestionError(
                f"No se pudo parsear date desde string ISO: {value!r}"
            ) from exc

    raise ReporteDireccionIngestionError(
        "Se recibió un business_date con tipo no soportado."
    )


def _validate_command(command: IngestReporteDireccionCommand) -> None:
    if not isinstance(command.warehouse_upload_id, int) or command.warehouse_upload_id <= 0:
        raise ValueError("'warehouse_upload_id' debe ser entero positivo.")

    if command.snapshot_kind not in SUPPORTED_SNAPSHOT_KINDS:
        raise ValueError(
            "El 'snapshot_kind' no es válido para reporte_direccion. "
            f"Permitidos: {sorted(SUPPORTED_SNAPSHOT_KINDS)}"
        )


def _import_callable(module_path: str, entrypoint_name: str) -> Callable[..., Any]:
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        raise ReporteDireccionIngestionError(
            f"No se pudo importar el módulo configurado: {module_path!r}"
        ) from exc

    fn = getattr(module, entrypoint_name, None)
    if not callable(fn):
        raise ReporteDireccionIngestionError(
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
        raise ReporteDireccionIngestionError(
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
        raise ReporteDireccionIngestionError(
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
        direct_callable_key="WAREHOUSE_REPORTE_DIRECCION_PARSER",
        module_key="WAREHOUSE_REPORTE_DIRECCION_PARSER_MODULE",
        entrypoint_key="WAREHOUSE_REPORTE_DIRECCION_PARSER_ENTRYPOINT",
        description="parsear reporte_direccion",
    )


def _resolve_repository() -> Callable[..., Any]:
    return _resolve_callable(
        direct_callable_key="WAREHOUSE_REPORTE_DIRECCION_REPOSITORY",
        module_key="WAREHOUSE_REPORTE_DIRECCION_REPOSITORY_MODULE",
        entrypoint_key="WAREHOUSE_REPORTE_DIRECCION_REPOSITORY_ENTRYPOINT",
        description="persistir snapshots de reporte_direccion",
    )


def _resolve_advisory_lock_impl() -> Callable[..., Any] | None:
    direct_callable = current_app.config.get(
        "WAREHOUSE_REPORTE_DIRECCION_ADVISORY_LOCK"
    )
    if callable(direct_callable):
        return direct_callable

    module_path = current_app.config.get(
        "WAREHOUSE_REPORTE_DIRECCION_ADVISORY_LOCK_MODULE"
    )
    entrypoint_name = current_app.config.get(
        "WAREHOUSE_REPORTE_DIRECCION_ADVISORY_LOCK_ENTRYPOINT"
    )

    if not module_path and not entrypoint_name:
        return None

    if not isinstance(module_path, str) or not module_path.strip():
        raise ReporteDireccionIngestionError(
            "Debes configurar 'WAREHOUSE_REPORTE_DIRECCION_ADVISORY_LOCK_MODULE' como string."
        )

    if not isinstance(entrypoint_name, str) or not entrypoint_name.strip():
        raise ReporteDireccionIngestionError(
            "Debes configurar 'WAREHOUSE_REPORTE_DIRECCION_ADVISORY_LOCK_ENTRYPOINT' como string."
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
        raise ReporteDireccionIngestionError(
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
            raise ReporteDireccionIngestionError(
                "El loader del upload debe devolver 'report_type_key'."
            )

        if not isinstance(original_filename, str) or not original_filename.strip():
            raise ReporteDireccionIngestionError(
                "El loader del upload debe devolver 'original_filename'."
            )

        upload_id = raw_result.get("warehouse_upload_id", warehouse_upload_id)
        if not isinstance(upload_id, int):
            raise ReporteDireccionIngestionError(
                "El loader del upload debe devolver 'warehouse_upload_id' entero."
            )

        return WarehouseUploadDocument(
            warehouse_upload_id=upload_id,
            report_type_key=report_type_key.strip(),
            original_filename=original_filename.strip(),
            content_type=raw_result.get("content_type"),
            storage_path=raw_result.get("storage_path"),
            captured_at=_ensure_datetime(raw_result.get("captured_at")),
            metadata=raw_result.get("metadata") or {},
        )

    raise ReporteDireccionIngestionError(
        "El loader del upload devolvió un tipo no soportado. "
        "Debe devolver WarehouseUploadDocument, dict o None."
    )


def _validate_upload_for_reporte_direccion(upload: WarehouseUploadDocument) -> None:
    if upload.report_type_key != REPORTE_DIRECCION_REPORT_TYPE_KEY:
        raise WrongReportTypeForIngestion(
            f"El upload {upload.warehouse_upload_id} no corresponde a "
            f"{REPORTE_DIRECCION_REPORT_TYPE_KEY!r}, sino a {upload.report_type_key!r}."
        )

    if not upload.storage_path:
        raise ReporteDireccionIngestionError(
            "El upload documental no tiene 'storage_path'."
        )

    path = Path(upload.storage_path)
    if not path.exists():
        raise ReporteDireccionIngestionError(
            f"El archivo del upload documental no existe: {path}"
        )


def _normalize_parsed_row(raw_row: Any) -> ParsedReporteDireccionRow:
    if isinstance(raw_row, ParsedReporteDireccionRow):
        return raw_row

    if not isinstance(raw_row, dict):
        raise ReporteDireccionParseError(
            "El parser devolvió una fila detalle con tipo no soportado."
        )

    sucursal = raw_row.get("sucursal")
    if not isinstance(sucursal, str) or not sucursal.strip():
        raise ReporteDireccionParseError(
            "El parser devolvió una fila detalle sin 'sucursal' válida."
        )

    return ParsedReporteDireccionRow(
        sucursal=sucursal.strip(),
        socios_activos_totales=raw_row.get("socios_activos_totales"),
        socios_activos_kpi=raw_row.get("socios_activos_kpi"),
        socios_kpi_m2=raw_row.get("socios_kpi_m2"),
        asistencia_hoy=raw_row.get("asistencia_hoy"),
        diarios_hoy=raw_row.get("diarios_hoy"),
        gympass=raw_row.get("gympass"),
        totalpass=raw_row.get("totalpass"),
        pases_cortesia=raw_row.get("pases_cortesia"),
        ingreso_hoy=raw_row.get("ingreso_hoy"),
        ingreso_acumulado_semana_en_curso=raw_row.get(
            "ingreso_acumulado_semana_en_curso"
        ),
        ingreso_acumulado_mes_en_curso=raw_row.get(
            "ingreso_acumulado_mes_en_curso"
        ),
        membresia_domiciliada_mes_en_curso=raw_row.get(
            "membresia_domiciliada_mes_en_curso"
        ),
        pago_posterior_domiciliado_mes_en_curso=raw_row.get(
            "pago_posterior_domiciliado_mes_en_curso"
        ),
        producto_pct_venta=raw_row.get("producto_pct_venta"),
        ingreso_acumulado_mismo_mes_anio_anterior=raw_row.get(
            "ingreso_acumulado_mismo_mes_anio_anterior"
        ),
        hora_apertura_raw=raw_row.get("hora_apertura_raw"),
        hora_clausura_raw=raw_row.get("hora_clausura_raw"),
    )


def _normalize_parsed_snapshot(raw_result: Any) -> ParsedReporteDireccionSnapshot:
    if isinstance(raw_result, ParsedReporteDireccionSnapshot):
        return raw_result

    if not isinstance(raw_result, dict):
        raise ReporteDireccionParseError(
            "El parser devolvió un tipo no soportado. Debe devolver dict o ParsedReporteDireccionSnapshot."
        )

    rows_raw = raw_result.get("rows")
    if not isinstance(rows_raw, list):
        raise ReporteDireccionParseError(
            "El parser debe devolver 'rows' como lista."
        )

    rows = [_normalize_parsed_row(item) for item in rows_raw]

    return ParsedReporteDireccionSnapshot(
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


def _parse_upload(upload: WarehouseUploadDocument) -> ParsedReporteDireccionSnapshot:
    parser = _resolve_parser()

    try:
        raw_result = _invoke_callable_flexibly(
            parser,
            kwargs={
                "warehouse_upload_id": upload.warehouse_upload_id,
                "file_path": upload.storage_path,
                "original_filename": upload.original_filename,
                "captured_at": upload.captured_at,
                "report_type_key": upload.report_type_key,
                "content_type": upload.content_type,
                "storage_path": upload.storage_path,
            },
            description="reporte_direccion parser",
        )
    except NotImplementedError:
        raise
    except ReporteDireccionParseError:
        raise
    except Exception as exc:
        raise ReporteDireccionParseError(
            f"Falló el parser de reporte_direccion para upload {upload.warehouse_upload_id}."
        ) from exc

    parsed = _normalize_parsed_snapshot(raw_result)

    if parsed.report_type_key != REPORTE_DIRECCION_REPORT_TYPE_KEY:
        raise ReporteDireccionParseError(
            "El parser devolvió un report_type_key distinto a 'reporte_direccion'."
        )

    if parsed.row_count_valid != len(parsed.rows):
        raise ReporteDireccionParseError(
            "Inconsistencia del parser: row_count_valid no coincide con cantidad de rows."
        )

    if parsed.row_count_valid + parsed.row_count_rejected > parsed.row_count_detected:
        raise ReporteDireccionParseError(
            "Inconsistencia del parser: valid + rejected no puede ser mayor que detected."
        )

    if parsed.row_count_valid <= 0:
        raise ReporteDireccionParseError(
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
            "No hay advisory lock configurado para reporte_direccion; se continúa sin lock explícito."
        )
        return

    try:
        _invoke_callable_flexibly(
            lock_impl,
            kwargs={
                "report_type_key": report_type_key,
                "business_date": business_date,
            },
            description="reporte_direccion advisory lock",
        )
    except Exception as exc:
        raise ReporteDireccionIngestionError(
            "Falló la toma del advisory lock para reporte_direccion."
        ) from exc


def _resolve_canonicality_decision(
    *,
    existing_canonical_snapshot: dict[str, Any] | None,
    snapshot_kind: str,
) -> tuple[bool, int | None]:
    """
    Devuelve:
    - new_snapshot_is_canonical
    - previous_canonical_snapshot_id_to_uncanonicalize
    """
    if existing_canonical_snapshot is None:
        return True, None

    existing_id = existing_canonical_snapshot.get("snapshot_id")
    existing_kind = existing_canonical_snapshot.get("snapshot_kind")

    if snapshot_kind == "daily":
        return False, None

    if snapshot_kind == "month_end_close":
        if existing_kind == "daily":
            if not isinstance(existing_id, int):
                raise CanonicalityConflictError(
                    "El snapshot canónico actual no trae snapshot_id entero."
                )
            return True, existing_id

        if existing_kind == "month_end_close":
            return False, None

    raise CanonicalityConflictError(
        f"No se pudo resolver canonicalidad para snapshot_kind={snapshot_kind!r} "
        f"y existing_kind={existing_kind!r}."
    )


def _persist_snapshot_transactionally(
    *,
    parsed: ParsedReporteDireccionSnapshot,
    command: IngestReporteDireccionCommand,
) -> IngestReporteDireccionResult:
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
            description="reporte_direccion repository",
        )
    except NotImplementedError:
        raise
    except Exception as exc:
        raise SnapshotPersistenceError(
            "Falló la persistencia transaccional de reporte_direccion."
        ) from exc

    if isinstance(raw_result, IngestReporteDireccionResult):
        return raw_result

    if not isinstance(raw_result, dict):
        raise SnapshotPersistenceError(
            "El repositorio de reporte_direccion devolvió un tipo no soportado."
        )

    business_date_raw = raw_result.get("business_date", parsed.business_date)
    business_date = _ensure_date(business_date_raw) if business_date_raw is not None else None

    return IngestReporteDireccionResult(
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


def ingest_reporte_direccion_upload(
    *,
    warehouse_upload_id: int,
    snapshot_kind: str,
    requested_by: str | None = None,
    ingestion_source: str | None = None,
) -> dict[str, Any]:
    """
    Servicio principal de ingesta estructurada de reporte_direccion.

    Flujo:
    1) cargar upload documental
    2) validar que sea reporte_direccion
    3) parsear archivo
    4) persistir snapshot + rows + canonicalidad usando repositorio configurable

    Dependencias esperadas vía app.config:
    - WAREHOUSE_UPLOAD_LOADER
    - WAREHOUSE_REPORTE_DIRECCION_PARSER
    - WAREHOUSE_REPORTE_DIRECCION_REPOSITORY
    - opcional: WAREHOUSE_REPORTE_DIRECCION_ADVISORY_LOCK
    """
    command = IngestReporteDireccionCommand(
        warehouse_upload_id=warehouse_upload_id,
        snapshot_kind=snapshot_kind,
        requested_by=requested_by,
        ingestion_source=ingestion_source,
    )
    _validate_command(command)

    current_app.logger.info(
        "Starting reporte_direccion ingestion: warehouse_upload_id=%s snapshot_kind=%s",
        command.warehouse_upload_id,
        command.snapshot_kind,
    )

    upload = _load_warehouse_upload(command.warehouse_upload_id)
    _validate_upload_for_reporte_direccion(upload)
    parsed = _parse_upload(upload)

    result = _persist_snapshot_transactionally(
        parsed=parsed,
        command=command,
    )

    current_app.logger.info(
        "Reporte_direccion ingestion finished: warehouse_upload_id=%s snapshot_id=%s status=%s is_canonical=%s",
        result.warehouse_upload_id,
        result.snapshot_id,
        result.status,
        result.is_canonical,
    )

    return result.to_dict()