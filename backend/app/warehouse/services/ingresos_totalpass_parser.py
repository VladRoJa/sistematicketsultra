# backend/app/warehouse/services/ingresos_totalpass_parser.py


from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import unicodedata

import pandas as pd

from app.warehouse.services.ingresos_totalpass_ingestion_service import (
    INGRESOS_TOTALPASS_REPORT_TYPE_KEY,
    IngresosTotalpassParseError,
)


TOTALPASS_SHEET_CANDIDATES = (
    "Sheet1",
    "sheet1",
    "Hoja1",
    "Resumen del Grupo",
    "Resumen del grupo",
)

REQUIRED_COLUMNS = frozenset(
    {"id", "name", "value", "usageCount", "studentCount"}
)


def register_ingresos_totalpass_parser(app) -> None:
    """
    Registra este parser como hook runtime.

    Esto deja disponible:
        app.config["WAREHOUSE_INGRESOS_TOTALPASS_PARSER"]
    """
    app.config["WAREHOUSE_INGRESOS_TOTALPASS_PARSER"] = (
        parse_ingresos_totalpass_excel
    )


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
            raise IngresosTotalpassParseError(
                f"No se pudo parsear captured_at desde string ISO: {value!r}"
            ) from exc

    if value is None:
        return datetime.now(timezone.utc)

    raise IngresosTotalpassParseError(
        f"Tipo inválido para captured_at: {type(value).__name__}"
    )


def _ensure_business_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise IngresosTotalpassParseError(
                f"No se pudo parsear cutoff_date desde string ISO: {value!r}"
            ) from exc

    raise IngresosTotalpassParseError(
        "TotalPass requiere cutoff_date válido en el upload manual."
    )


def _normalize_sheet_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )
    return " ".join(text.split())


def _resolve_totalpass_sheet_name(path: Path) -> str:
    try:
        xls = pd.ExcelFile(path)
    except Exception as exc:
        raise IngresosTotalpassParseError(
            f"No se pudo abrir el archivo TotalPass para inspeccionar hojas: {path.name}"
        ) from exc

    available_sheet_names = list(xls.sheet_names)
    if not available_sheet_names:
        raise IngresosTotalpassParseError(
            "El archivo TotalPass no contiene hojas."
        )

    normalized_candidates = {
        _normalize_sheet_name(candidate)
        for candidate in TOTALPASS_SHEET_CANDIDATES
    }

    for sheet_name in available_sheet_names:
        if _normalize_sheet_name(sheet_name) in normalized_candidates:
            return sheet_name

    if len(available_sheet_names) == 1:
        return available_sheet_names[0]

    raise IngresosTotalpassParseError(
        "No se encontró una hoja compatible para TotalPass. "
        f"Hojas disponibles: {available_sheet_names}"
    )


def _load_totalpass_dataframe(*, file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise IngresosTotalpassParseError(
            f"No existe el archivo de TotalPass: {path}"
        )

    resolved_sheet_name = _resolve_totalpass_sheet_name(path)

    try:
        dataframe = pd.read_excel(path, sheet_name=resolved_sheet_name)
    except Exception as exc:
        raise IngresosTotalpassParseError(
            f"No se pudo leer la hoja {resolved_sheet_name!r} del archivo TotalPass: {path.name}"
        ) from exc

    if dataframe.empty:
        raise IngresosTotalpassParseError(
            "El archivo TotalPass no contiene filas."
        )

    dataframe.columns = [str(col).strip() for col in dataframe.columns]

    missing_columns = REQUIRED_COLUMNS.difference(dataframe.columns)
    if missing_columns:
        raise IngresosTotalpassParseError(
            "El archivo TotalPass no contiene las columnas requeridas: "
            f"{sorted(missing_columns)}. "
            f"Hoja detectada: {resolved_sheet_name!r}"
        )

    return dataframe


def _parse_currency_value(value: Any) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("$", "").replace(",", "").strip()

    try:
        return float(text)
    except ValueError as exc:
        raise IngresosTotalpassParseError(
            f"No se pudo convertir el monto TotalPass: {value!r}"
        ) from exc


def _normalize_totalpass_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    normalized = dataframe.copy()

    normalized["name"] = normalized["name"].astype(str).str.strip()
    normalized["value"] = normalized["value"].apply(_parse_currency_value)
    normalized["usageCount"] = pd.to_numeric(
        normalized["usageCount"],
        errors="coerce",
    )
    normalized["studentCount"] = pd.to_numeric(
        normalized["studentCount"],
        errors="coerce",
    )

    normalized = normalized[
        normalized["name"].ne("")
        & normalized["value"].notna()
        & normalized["usageCount"].notna()
    ].copy()

    if normalized.empty:
        raise IngresosTotalpassParseError(
            "Después de normalizar, el archivo TotalPass no dejó filas válidas."
        )

    normalized["usageCount"] = normalized["usageCount"].astype(int)
    normalized["studentCount"] = (
        normalized["studentCount"]
        .fillna(0)
        .astype(int)
    )

    return normalized


def _build_grouped_rows(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    grouped = (
        dataframe.groupby("name", as_index=False)
        .agg(
            monto_acumulado_mes=("value", "sum"),
            usage_count=("usageCount", "sum"),
            student_count=("studentCount", "sum"),
        )
        .sort_values("name")
    )

    rows: list[dict[str, Any]] = []

    for _, row in grouped.iterrows():
        rows.append(
            {
                "raw_branch_name": str(row["name"]).strip(),
                "monto_acumulado_mes": float(row["monto_acumulado_mes"]),
                "usage_count": int(row["usage_count"]),
                "student_count": int(row["student_count"]),
            }
        )

    return rows


def parse_ingresos_totalpass_excel(
    *,
    warehouse_upload_id: int,
    file_path: str,
    original_filename: str,
    captured_at: str | datetime | None = None,
    cutoff_date: str | date | datetime | None = None,
    report_type_key: str | None = None,
    content_type: str | None = None,
    storage_path: str | None = None,
) -> dict[str, Any]:
    if report_type_key not in (None, INGRESOS_TOTALPASS_REPORT_TYPE_KEY):
        raise IngresosTotalpassParseError(
            "El parser recibió un report_type_key inválido para TotalPass: "
            f"{report_type_key!r}"
        )

    business_date = _ensure_business_date(cutoff_date)
    dataframe_raw = _load_totalpass_dataframe(file_path=file_path)
    row_count_detected = int(len(dataframe_raw))

    dataframe = _normalize_totalpass_dataframe(dataframe_raw)
    rows = _build_grouped_rows(dataframe)

    return {
        "warehouse_upload_id": warehouse_upload_id,
        "report_type_key": INGRESOS_TOTALPASS_REPORT_TYPE_KEY,
        "business_date": business_date.isoformat(),
        "captured_at": _ensure_datetime(captured_at).isoformat(),
        "row_count_detected": row_count_detected,
        "row_count_valid": len(rows),
        "row_count_rejected": max(0, row_count_detected - len(dataframe)),
        "rows": rows,
        "issues": [],
        "metadata": {
            "original_filename": original_filename,
            "content_type": content_type,
            "storage_path": storage_path,
            "sheet_candidates": list(TOTALPASS_SHEET_CANDIDATES),
        },
    }