# backend/app/warehouse/services/corte_caja_parser.py


from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


CORTE_CAJA_REPORT_TYPE_KEY = "corte_caja"

EXPECTED_CORTE_CAJA_COLUMNS = (
    "#",
    "Clave",
    "Folio",
    "Hora",
    "Nombre",
    "Importe",
    "Pago",
    "Renovación",
    "Operación",
    "Tipo Pago",
    "Recepción",
    "Sucursal",
)


class CorteCajaParserError(RuntimeError):
    """Error base del parser de Corte de Caja."""


class CorteCajaLayoutError(CorteCajaParserError):
    """El archivo no cumple el layout esperado."""


class CorteCajaContentError(CorteCajaParserError):
    """El archivo no contiene filas de negocio válidas."""


@dataclass(slots=True)
class CorteCajaParsedRow:
    row_index: int
    clave: str
    folio: str
    hora: str
    nombre: str
    importe: Decimal
    pago: str
    renovacion: str
    operacion: str
    tipo_pago: str
    recepcion: str
    sucursal: str


@dataclass(slots=True)
class CorteCajaParseResult:
    report_type_key: str = CORTE_CAJA_REPORT_TYPE_KEY
    rows: list[CorteCajaParsedRow] = field(default_factory=list)
    row_count: int = 0
    header_columns: tuple[str, ...] = field(default_factory=tuple)
    skipped_rows: int = 0


def register_corte_caja_parser(app) -> None:
    app.config["WAREHOUSE_CORTE_CAJA_PARSER"] = parse_corte_caja_xlsx


def parse_corte_caja_xlsx(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
) -> CorteCajaParseResult:
    raw_df = _read_corte_caja_dataframe(
        file_path=file_path,
        file_bytes=file_bytes,
    )

    header_row_idx = _find_header_row_index(raw_df)
    normalized_df = _promote_header_row(raw_df, header_row_idx=header_row_idx)

    _validate_expected_columns(normalized_df)

    parsed_rows: list[CorteCajaParsedRow] = []
    skipped_rows = 0

    for source_row_index, row in normalized_df.iterrows():
        if _is_empty_row(row):
            skipped_rows += 1
            continue

        if _is_total_row(row):
            skipped_rows += 1
            continue

        if _is_report_generated_row(row):
            skipped_rows += 1
            continue

        parsed_rows.append(
            CorteCajaParsedRow(
                row_index=int(source_row_index),
                clave=_normalize_text(row.get("Clave")),
                folio=_normalize_required_text(
                    row.get("Folio"),
                    column_name="Folio",
                    row_index=source_row_index,
                ),
                hora=_normalize_text(row.get("Hora")),
                nombre=_normalize_text(row.get("Nombre")),
                importe=_coerce_decimal_money(
                    row.get("Importe"),
                    column_name="Importe",
                    row_index=source_row_index,
                ),
                pago=_normalize_text(row.get("Pago")),
                renovacion=_normalize_text(row.get("Renovación")),
                operacion=_normalize_text(row.get("Operación")),
                tipo_pago=_normalize_text(row.get("Tipo Pago")),
                recepcion=_normalize_text(row.get("Recepción")),
                sucursal=_normalize_required_text(
                    row.get("Sucursal"),
                    column_name="Sucursal",
                    row_index=source_row_index,
                ),
            )
        )

    if not parsed_rows:
        raise CorteCajaContentError(
            "El archivo Corte de Caja no contiene filas de negocio válidas."
        )

    return CorteCajaParseResult(
        rows=parsed_rows,
        row_count=len(parsed_rows),
        header_columns=tuple(str(col) for col in normalized_df.columns.tolist()),
        skipped_rows=skipped_rows,
    )


def _read_corte_caja_dataframe(
    *,
    file_path: str | None,
    file_bytes: bytes | None,
) -> pd.DataFrame:
    if not file_path and file_bytes is None:
        raise CorteCajaParserError(
            "Se requiere 'file_path' o 'file_bytes' para parsear Corte de Caja."
        )

    try:
        source = BytesIO(file_bytes) if file_bytes is not None else Path(file_path)  # type: ignore[arg-type]
        excel_file = pd.ExcelFile(source)
        sheet_name = excel_file.sheet_names[0]
        return pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
    except Exception as exc:
        raise CorteCajaLayoutError(
            "No se pudo leer el archivo XLSX de Corte de Caja."
        ) from exc


def _find_header_row_index(raw_df: pd.DataFrame) -> int:
    expected_tail = tuple(
        _normalize_header_token(col)
        for col in EXPECTED_CORTE_CAJA_COLUMNS[1:]
    )

    for idx in range(len(raw_df)):
        row = raw_df.iloc[idx].tolist()

        first_token = _normalize_header_token(row[0] if len(row) > 0 else None)
        tail_tokens = tuple(
            _normalize_header_token(value)
            for value in row[1: len(EXPECTED_CORTE_CAJA_COLUMNS)]
        )

        first_cell_matches = first_token in {"", "#"}
        if first_cell_matches and tail_tokens == expected_tail:
            return idx

    raise CorteCajaLayoutError(
        "No se encontró la fila del header contractual de Corte de Caja."
    )


def _promote_header_row(
    raw_df: pd.DataFrame,
    *,
    header_row_idx: int,
) -> pd.DataFrame:
    header_values = raw_df.iloc[header_row_idx].tolist()

    normalized_headers = [_normalize_header_name(value) for value in header_values]
    if normalized_headers and normalized_headers[0] == "":
        normalized_headers[0] = "#"

    body_df = raw_df.iloc[header_row_idx + 1 :].copy()
    body_df.columns = normalized_headers
    body_df = body_df.reset_index(drop=True)
    return body_df

def _validate_expected_columns(df: pd.DataFrame) -> None:
    actual_columns = tuple(str(col).strip() for col in df.columns.tolist())

    if actual_columns[: len(EXPECTED_CORTE_CAJA_COLUMNS)] != EXPECTED_CORTE_CAJA_COLUMNS:
        raise CorteCajaLayoutError(
            "El header de Corte de Caja no coincide con el esperado. "
            f"Esperado={EXPECTED_CORTE_CAJA_COLUMNS!r} "
            f"Recibido={actual_columns!r}"
        )


def _normalize_header_token(value: Any) -> str:
    return _normalize_text(value).lower()


def _normalize_header_name(value: Any) -> str:
    return _normalize_text(value)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""

    if pd.isna(value):
        return ""

    # Si viene datetime/date, se respeta como texto observado
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return str(value)
        except Exception:
            pass

    return str(value).strip().replace("\xa0", " ")


def _normalize_required_text(
    value: Any,
    *,
    column_name: str,
    row_index: int,
) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        raise CorteCajaContentError(
            f"Valor vacío en columna {column_name!r} para row_index={row_index}."
        )
    return normalized


def _is_empty_row(row: pd.Series) -> bool:
    for value in row.tolist():
        if _normalize_text(value):
            return False
    return True


def _is_total_row(row: pd.Series) -> bool:
    hora = _normalize_text(row.get("Hora")).strip().lower()
    clave = _normalize_text(row.get("Clave")).strip().lower()
    nombre = _normalize_text(row.get("Nombre")).strip().lower()
    numero = _normalize_text(row.get("#")).strip().lower()

    return hora == "total" or clave == "total" or nombre == "total" or numero == "total"


def _is_report_generated_row(row: pd.Series) -> bool:
    return any(
        _normalize_text(value).strip().lower().startswith("reporte generado:")
        for value in row.tolist()
    )


def _coerce_decimal_money(
    value: Any,
    *,
    column_name: str,
    row_index: int,
) -> Decimal:
    normalized = _normalize_numeric_string(
        value,
        column_name=column_name,
        row_index=row_index,
    )

    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise CorteCajaContentError(
            f"No se pudo convertir a Decimal monetario la columna {column_name!r} "
            f"en row_index={row_index}: {value!r}"
        ) from exc


def _normalize_numeric_string(
    value: Any,
    *,
    column_name: str,
    row_index: int,
) -> str:
    if value is None or pd.isna(value):
        raise CorteCajaContentError(
            f"Valor vacío en columna {column_name!r} para row_index={row_index}."
        )

    if isinstance(value, (int, float, Decimal)):
        return str(value)

    raw = str(value).strip()
    if not raw:
        raise CorteCajaContentError(
            f"Valor vacío en columna {column_name!r} para row_index={row_index}."
        )

    normalized = raw.replace("$", "")
    normalized = normalized.replace(",", "")
    normalized = normalized.replace(" ", "")

    if normalized.startswith("."):
        normalized = "0" + normalized
    if normalized.startswith("-."):
        normalized = normalized.replace("-.", "-0.", 1)

    if normalized in {"", "-", "."}:
        normalized = "0"

    return normalized