# backend/app/warehouse/services/ingresos_wellhub_parser.py

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import unicodedata

import pandas as pd


INGRESOS_WELLHUB_REPORT_TYPE_KEY = "ingresos_wellhub"

WELLHUB_SHEET_CANDIDATES = (
    "Datos de visitantes",
    "datos de visitantes",
)

REQUIRED_COLUMN_ALIASES = {
    "ID de ubicación": "location_id",
    "Localización": "raw_branch_name",
    "Visitante": "visitor_name",
    "ID de Wellhub": "wellhub_member_id",
    "Total de check-ins": "total_checkins_mtd",
    "Pago total": "pago_total_mtd",
}


class IngresosWellhubParseError(RuntimeError):
    """Error base del parser de ingresos_wellhub."""


def register_ingresos_wellhub_parser(app) -> None:
    """
    Registra este parser como hook runtime.

    Esto deja disponible:
        app.config["WAREHOUSE_INGRESOS_WELLHUB_PARSER"]
    """
    app.config["WAREHOUSE_INGRESOS_WELLHUB_PARSER"] = (
        parse_ingresos_wellhub_excel
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
            raise IngresosWellhubParseError(
                f"No se pudo parsear captured_at desde string ISO: {value!r}"
            ) from exc

    if value is None:
        return datetime.now(timezone.utc)

    raise IngresosWellhubParseError(
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
            raise IngresosWellhubParseError(
                f"No se pudo parsear cutoff_date desde string ISO: {value!r}"
            ) from exc

    raise IngresosWellhubParseError(
        "Wellhub requiere cutoff_date válido en el upload manual."
    )


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )
    return " ".join(text.split())


def _resolve_wellhub_sheet_name(path: Path) -> str:
    try:
        xls = pd.ExcelFile(path)
    except Exception as exc:
        raise IngresosWellhubParseError(
            f"No se pudo abrir el archivo Wellhub para inspeccionar hojas: {path.name}"
        ) from exc

    available_sheet_names = list(xls.sheet_names)
    if not available_sheet_names:
        raise IngresosWellhubParseError(
            "El archivo Wellhub no contiene hojas."
        )

    normalized_candidates = {
        _normalize_text(candidate)
        for candidate in WELLHUB_SHEET_CANDIDATES
    }

    for sheet_name in available_sheet_names:
        if _normalize_text(sheet_name) in normalized_candidates:
            return sheet_name

    if len(available_sheet_names) == 1:
        return available_sheet_names[0]

    raise IngresosWellhubParseError(
        "No se encontró una hoja compatible para Wellhub. "
        f"Hojas disponibles: {available_sheet_names}"
    )


def _load_raw_wellhub_dataframe(*, file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise IngresosWellhubParseError(
            f"No existe el archivo de Wellhub: {path}"
        )

    resolved_sheet_name = _resolve_wellhub_sheet_name(path)

    try:
        dataframe = pd.read_excel(path, sheet_name=resolved_sheet_name, header=None)
    except Exception as exc:
        raise IngresosWellhubParseError(
            f"No se pudo leer la hoja {resolved_sheet_name!r} del archivo Wellhub: {path.name}"
        ) from exc

    if dataframe.empty:
        raise IngresosWellhubParseError(
            "El archivo Wellhub no contiene filas."
        )

    return dataframe


def _find_header_row_index(dataframe: pd.DataFrame) -> int:
    expected_headers = {
        _normalize_text(column_name)
        for column_name in REQUIRED_COLUMN_ALIASES.keys()
    }

    max_scan_rows = min(len(dataframe), 30)

    for row_index in range(max_scan_rows):
        row_values = dataframe.iloc[row_index].tolist()
        normalized_row = {
            _normalize_text(value)
            for value in row_values
            if _normalize_text(value)
        }
        if expected_headers.issubset(normalized_row):
            return row_index

    raise IngresosWellhubParseError(
        "No se encontró el header esperado de Wellhub dentro de las primeras filas."
    )


def _extract_wellhub_dataframe(dataframe_raw: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    header_row_index = _find_header_row_index(dataframe_raw)

    header_values = dataframe_raw.iloc[header_row_index].tolist()
    detail_values = dataframe_raw.iloc[header_row_index + 1 :].copy()

    detail_values.columns = [str(value).strip() for value in header_values]
    detail_values = detail_values.reset_index(drop=True)

    missing_columns = [
        column_name
        for column_name in REQUIRED_COLUMN_ALIASES.keys()
        if column_name not in detail_values.columns
    ]
    if missing_columns:
        raise IngresosWellhubParseError(
            "El archivo Wellhub no contiene las columnas requeridas: "
            f"{missing_columns}"
        )

    detected_rows = int(len(detail_values))
    return detail_values, detected_rows


def _parse_numeric(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("$", "").replace(",", "").strip()

    try:
        return float(text)
    except ValueError as exc:
        raise IngresosWellhubParseError(
            f"No se pudo convertir el campo {field_name!r}: {value!r}"
        ) from exc


def _normalize_wellhub_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    normalized = dataframe.copy()

    normalized = normalized.rename(columns=REQUIRED_COLUMN_ALIASES)

    normalized["location_id"] = normalized["location_id"].astype(str).str.strip()
    normalized["raw_branch_name"] = normalized["raw_branch_name"].astype(str).str.strip()
    normalized["visitor_name"] = normalized["visitor_name"].astype(str).str.strip()
    normalized["wellhub_member_id"] = normalized["wellhub_member_id"].astype(str).str.strip()

    normalized["total_checkins_mtd"] = pd.to_numeric(
        normalized["total_checkins_mtd"],
        errors="coerce",
    )
    normalized["pago_total_mtd"] = normalized["pago_total_mtd"].apply(
        lambda value: _parse_numeric(value, field_name="pago_total_mtd")
    )

    normalized = normalized[
        normalized["raw_branch_name"].ne("")
        & normalized["wellhub_member_id"].ne("")
        & normalized["total_checkins_mtd"].notna()
        & normalized["pago_total_mtd"].notna()
    ].copy()

    if normalized.empty:
        raise IngresosWellhubParseError(
            "Después de normalizar, el archivo Wellhub no dejó filas válidas."
        )

    normalized["total_checkins_mtd"] = normalized["total_checkins_mtd"].astype(int)

    return normalized


def _build_rows(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    normalized = dataframe.copy()

    normalized["visitor_name"] = (
        normalized["visitor_name"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    grouped = (
        normalized.groupby(
            ["raw_branch_name", "wellhub_member_id"],
            as_index=False,
        )
        .agg(
            visitor_name=("visitor_name", "first"),
            total_checkins_mtd=("total_checkins_mtd", "sum"),
            pago_total_mtd=("pago_total_mtd", "sum"),
        )
        .sort_values(["raw_branch_name", "wellhub_member_id"])
    )

    rows: list[dict[str, Any]] = []

    for _, row in grouped.iterrows():
        visitor_name = str(row["visitor_name"]).strip()

        rows.append(
            {
                "raw_branch_name": str(row["raw_branch_name"]).strip(),
                "visitor_name": visitor_name or None,
                "wellhub_member_id": str(row["wellhub_member_id"]).strip(),
                "total_checkins_mtd": int(row["total_checkins_mtd"]),
                "pago_total_mtd": float(row["pago_total_mtd"]),
            }
        )

    return rows

def parse_ingresos_wellhub_excel(
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
    if report_type_key not in (None, INGRESOS_WELLHUB_REPORT_TYPE_KEY):
        raise IngresosWellhubParseError(
            "El parser recibió un report_type_key inválido para Wellhub: "
            f"{report_type_key!r}"
        )

    business_date = _ensure_business_date(cutoff_date)
    dataframe_raw = _load_raw_wellhub_dataframe(file_path=file_path)
    dataframe_detail, row_count_detected = _extract_wellhub_dataframe(dataframe_raw)
    dataframe_normalized = _normalize_wellhub_dataframe(dataframe_detail)
    rows = _build_rows(dataframe_normalized)

    return {
        "warehouse_upload_id": warehouse_upload_id,
        "report_type_key": INGRESOS_WELLHUB_REPORT_TYPE_KEY,
        "business_date": business_date.isoformat(),
        "captured_at": _ensure_datetime(captured_at).isoformat(),
        "row_count_detected": row_count_detected,
        "row_count_valid": len(rows),
        "row_count_rejected": max(0, row_count_detected - len(dataframe_normalized)),
        "rows": rows,
        "issues": [],
        "metadata": {
            "original_filename": original_filename,
            "content_type": content_type,
            "storage_path": storage_path,
            "sheet_candidates": list(WELLHUB_SHEET_CANDIDATES),
        },
    }