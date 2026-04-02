# backend/app/warehouse/services/warehouse_upload_loader_sql.py

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import inspect, text

from app.extensions import db


WAREHOUSE_UPLOADS_TABLE = "warehouse_uploads"
WAREHOUSE_REPORT_TYPES_TABLE = "warehouse_report_types"

ORIGINAL_FILENAME_CANDIDATES = [
    "original_filename",
]

CONTENT_TYPE_CANDIDATES = [
    "content_type",
    "mime_type",
]

STORAGE_PATH_CANDIDATES = [
    "storage_path",
    "file_path",
    "stored_path",
    "relative_path",
    "storage_rel_path",
    "stored_rel_path",
]

CAPTURED_AT_CANDIDATES = [
    "captured_at",
    "created_at",
]

METADATA_CANDIDATES = [
    "metadata",
    "details_json",
    "extra_json",
    "notes",
]

STORED_FILENAME_CANDIDATES = [
    "stored_filename",
]

PERIOD_TYPE_CANDIDATES = [
    "period_type",
]

CUTOFF_DATE_CANDIDATES = [
    "cutoff_date",
]

DATE_FROM_CANDIDATES = [
    "date_from",
]

DATE_TO_CANDIDATES = [
    "date_to",
]



class WarehouseUploadLoaderSqlError(RuntimeError):
    """Error base del loader SQL real de Warehouse."""


def register_warehouse_upload_loader_sql_impl(app) -> None:
    """
    Registra esta implementación SQL como loader real del hook.

    Uso esperado más adelante en init/app factory:
        register_warehouse_upload_loader_sql_impl(app)

    Esto deja resuelto:
        app.config["WAREHOUSE_UPLOAD_LOADER_IMPL"] = load_warehouse_upload_from_db
    """
    app.config["WAREHOUSE_UPLOAD_LOADER_IMPL"] = load_warehouse_upload_from_db


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
        except ValueError:
            return None

    return None


def _get_existing_columns(table_name: str) -> set[str]:
    inspector = inspect(db.engine)
    columns = inspector.get_columns(table_name)
    return {col["name"] for col in columns}


def _pick_first_existing_column(
    *,
    existing_columns: set[str],
    candidates: list[str],
) -> str | None:
    for candidate in candidates:
        if candidate in existing_columns:
            return candidate
    return None


def _coerce_storage_path(value: Any) -> str | None:
    if value is None:
        return None

    text_value = str(value).strip()
    if not text_value:
        return None

    return text_value


def _resolve_real_storage_path(
    *,
    raw_storage_path: str | None,
) -> str | None:
    """
    Intenta devolver una ruta usable en disco.

    Reglas:
    1) si ya es absoluta, se usa tal cual
    2) si es relativa, se resuelve contra la raíz del proyecto backend
       porque stored_path en Warehouse F1 es algo como:
       uploads/warehouse/{source}/{report_type}/{yyyy}/{mm}
    """
    if not raw_storage_path:
        return None

    candidate = Path(raw_storage_path)

    if candidate.is_absolute():
        return str(candidate)

    project_root = Path(current_app.root_path).parent.parent
    resolved = (project_root / candidate).resolve()
    return str(resolved)


def _extract_metadata_value(
    *,
    row: dict[str, Any],
    metadata_column: str | None,
) -> dict[str, Any]:
    if not metadata_column:
        return {}

    metadata_value = row.get(metadata_column)
    if isinstance(metadata_value, dict):
        return metadata_value

    if metadata_value is None:
        return {}

    return {"raw_metadata": metadata_value}


def load_warehouse_upload_from_db(*, warehouse_upload_id: int) -> dict[str, Any] | None:
    """
    Implementación real del hook WAREHOUSE_UPLOAD_LOADER.

    En tu esquema real, warehouse_uploads NO guarda report_type_key directo;
    guarda report_type_id, así que aquí resolvemos el key haciendo join con
    warehouse_report_types.
    """
    if not isinstance(warehouse_upload_id, int) or warehouse_upload_id <= 0:
        raise ValueError("'warehouse_upload_id' debe ser entero positivo.")

    upload_columns = _get_existing_columns(WAREHOUSE_UPLOADS_TABLE)
    report_type_columns = _get_existing_columns(WAREHOUSE_REPORT_TYPES_TABLE)

    if "report_type_id" not in upload_columns:
        raise WarehouseUploadLoaderSqlError(
            "No existe la columna 'report_type_id' en warehouse_uploads."
        )

    if "id" not in report_type_columns or "key" not in report_type_columns:
        raise WarehouseUploadLoaderSqlError(
            "La tabla warehouse_report_types debe exponer columnas 'id' y 'key'."
        )

    original_filename_col = _pick_first_existing_column(
        existing_columns=upload_columns,
        candidates=ORIGINAL_FILENAME_CANDIDATES,
    )
    content_type_col = _pick_first_existing_column(
        existing_columns=upload_columns,
        candidates=CONTENT_TYPE_CANDIDATES,
    )
    storage_path_col = _pick_first_existing_column(
        existing_columns=upload_columns,
        candidates=STORAGE_PATH_CANDIDATES,
    )
    captured_at_col = _pick_first_existing_column(
        existing_columns=upload_columns,
        candidates=CAPTURED_AT_CANDIDATES,
    )
    metadata_col = _pick_first_existing_column(
        existing_columns=upload_columns,
        candidates=METADATA_CANDIDATES,
    )
    stored_filename_col = _pick_first_existing_column(
        existing_columns=upload_columns,
        candidates=STORED_FILENAME_CANDIDATES,
    )
    
    period_type_col = _pick_first_existing_column(
        existing_columns=upload_columns,
        candidates=PERIOD_TYPE_CANDIDATES,
    )
    cutoff_date_col = _pick_first_existing_column(
        existing_columns=upload_columns,
        candidates=CUTOFF_DATE_CANDIDATES,
    )
    date_from_col = _pick_first_existing_column(
        existing_columns=upload_columns,
        candidates=DATE_FROM_CANDIDATES,
    )
    date_to_col = _pick_first_existing_column(
        existing_columns=upload_columns,
        candidates=DATE_TO_CANDIDATES,
    )

    if original_filename_col is None:
        raise WarehouseUploadLoaderSqlError(
            "No se encontró una columna compatible para original_filename en warehouse_uploads."
        )
    if stored_filename_col is None:
        raise WarehouseUploadLoaderSqlError(
            "No se encontró una columna compatible para stored_filename en warehouse_uploads."
        )

    selected_columns = [
        "wu.id AS upload_id",
        f"wu.{original_filename_col} AS original_filename",
        f"wu.{stored_filename_col} AS stored_filename",
        "wrt.key AS report_type_key",
    ]

    if content_type_col:
        selected_columns.append(f"wu.{content_type_col} AS content_type")
    if storage_path_col:
        selected_columns.append(f"wu.{storage_path_col} AS storage_path")
    if captured_at_col:
        selected_columns.append(f"wu.{captured_at_col} AS captured_at")
    if period_type_col:
        selected_columns.append(f"wu.{period_type_col} AS period_type")
    if cutoff_date_col:
        selected_columns.append(f"wu.{cutoff_date_col} AS cutoff_date")
    if date_from_col:
        selected_columns.append(f"wu.{date_from_col} AS date_from")
    if date_to_col:
        selected_columns.append(f"wu.{date_to_col} AS date_to")
    if metadata_col:
        selected_columns.append(f"wu.{metadata_col} AS metadata_value")

    sql = text(
        f"""
        SELECT {", ".join(selected_columns)}
        FROM {WAREHOUSE_UPLOADS_TABLE} wu
        JOIN {WAREHOUSE_REPORT_TYPES_TABLE} wrt
          ON wrt.id = wu.report_type_id
        WHERE wu.id = :warehouse_upload_id
        LIMIT 1
        """
    )

    row = db.session.execute(
        sql,
        {"warehouse_upload_id": warehouse_upload_id},
    ).mappings().first()

    if row is None:
        current_app.logger.info(
            "Warehouse upload SQL loader: no se encontró warehouse_upload_id=%s",
            warehouse_upload_id,
        )
        return None

    row_dict = dict(row)

    raw_storage_dir = _coerce_storage_path(row_dict.get("storage_path"))
    stored_filename = str(row_dict["stored_filename"]).strip()

    resolved_storage_dir = _resolve_real_storage_path(
        raw_storage_path=raw_storage_dir,
    )

    resolved_storage_path = None
    if resolved_storage_dir and stored_filename:
        resolved_storage_path = str(Path(resolved_storage_dir) / stored_filename)

    result = {
        "warehouse_upload_id": int(row_dict["upload_id"]),
        "report_type_key": str(row_dict["report_type_key"]).strip(),
        "original_filename": str(row_dict["original_filename"]).strip(),
        "content_type": row_dict.get("content_type"),
        "storage_path": resolved_storage_path,
        "captured_at": _ensure_datetime(row_dict.get("captured_at")),
        "period_type": row_dict.get("period_type"),
        "cutoff_date": row_dict.get("cutoff_date"),
        "date_from": row_dict.get("date_from"),
        "date_to": row_dict.get("date_to"),
        "metadata": _extract_metadata_value(
            row=row_dict,
            metadata_column="metadata_value" if "metadata_value" in row_dict else None,
        ),
    }

    current_app.logger.info(
        "Warehouse upload SQL loader resolved upload_id=%s report_type_key=%s storage_path=%s",
        result["warehouse_upload_id"],
        result["report_type_key"],
        result["storage_path"],
    )

    return result