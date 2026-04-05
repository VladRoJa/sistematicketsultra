#  backend\app\warehouse\services\venta_total_parser.py


from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


VENTA_TOTAL_REPORT_TYPE_KEY = "venta_total"

EXPECTED_VENTA_TOTAL_RAW_COLUMNS = (
    "#",
    "Fecha",
    "Sucursal",
    "Folio",
    "Clave",
    "Clave Producto",
    "Descripcion",
    "Cant.",
    "Prec. Unit.",
    "Subtotal",
    "IVA",
    "IVA",
    "Total",
    "Forma De Pago",
    "Estatus",
    "Motivo",
    "Realizo Venta",
    "Hora",
    "IDOrden",
    "Encuesta",
    "Capturista",
    "PIN",
    "Socio",
    "Nuevo",
    "Tipo",
)

EXPECTED_VENTA_TOTAL_INTERNAL_COLUMNS = (
    "#",
    "Fecha",
    "Sucursal",
    "Folio",
    "Clave",
    "Clave Producto",
    "Descripcion",
    "Cant.",
    "Prec. Unit.",
    "Subtotal",
    "IVA Importe",
    "IVA Tasa",
    "Total",
    "Forma De Pago",
    "Estatus",
    "Motivo",
    "Realizo Venta",
    "Hora",
    "IDOrden",
    "Encuesta",
    "Capturista",
    "PIN",
    "Socio",
    "Nuevo",
    "Tipo",
)


class VentaTotalParserError(RuntimeError):
    """Error base del parser de Venta Total."""


class VentaTotalLayoutError(VentaTotalParserError):
    """El archivo no cumple el layout esperado."""


class VentaTotalContentError(VentaTotalParserError):
    """El archivo no contiene filas de negocio válidas."""


@dataclass(slots=True)
class VentaTotalParsedRow:
    row_index: int
    fecha: str
    sucursal: str
    folio: str
    clave: str | None
    clave_producto: str | None
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    subtotal: Decimal
    iva_importe: Decimal
    iva_tasa: Decimal
    total: Decimal
    forma_pago: str
    estatus: str
    motivo: str | None
    realizo_venta: str
    hora: str
    id_orden: str | None
    encuesta: str | None
    capturista: str | None
    pin: str | None
    socio: str | None
    nuevo: str | None
    tipo: str | None


@dataclass(slots=True)
class VentaTotalParseResult:
    report_type_key: str = VENTA_TOTAL_REPORT_TYPE_KEY
    rows: list[VentaTotalParsedRow] = field(default_factory=list)
    row_count: int = 0
    header_columns: tuple[str, ...] = field(default_factory=tuple)
    skipped_rows: int = 0


def register_venta_total_parser(app) -> None:
    app.config["WAREHOUSE_VENTA_TOTAL_PARSER"] = parse_venta_total_xlsx


def parse_venta_total_xlsx(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
) -> VentaTotalParseResult:
    raw_df = _read_venta_total_dataframe(
        file_path=file_path,
        file_bytes=file_bytes,
    )

    header_row_idx = _find_header_row_index(raw_df)
    normalized_df = _promote_header_row(raw_df, header_row_idx=header_row_idx)

    _validate_expected_columns(normalized_df)

    parsed_rows: list[VentaTotalParsedRow] = []
    skipped_rows = 0

    for source_row_index, row in normalized_df.iterrows():
        if _is_empty_row(row):
            skipped_rows += 1
            continue

        if _is_report_generated_row(row):
            skipped_rows += 1
            continue

        parsed_rows.append(
            VentaTotalParsedRow(
                row_index=int(source_row_index),
                fecha=_normalize_required_text(
                    row.get("Fecha"),
                    field_name="Fecha",
                    row_index=source_row_index,
                ),
                sucursal=_normalize_required_text(
                    row.get("Sucursal"),
                    field_name="Sucursal",
                    row_index=source_row_index,
                ),
                folio=_normalize_required_text(
                    row.get("Folio"),
                    field_name="Folio",
                    row_index=source_row_index,
                ),
                clave=_normalize_optional_text(row.get("Clave")),
                clave_producto=_normalize_optional_text(row.get("Clave Producto")),
                descripcion=_normalize_required_text(
                    row.get("Descripcion"),
                    field_name="Descripcion",
                    row_index=source_row_index,
                ),
                cantidad=_coerce_decimal_numeric(
                    row.get("Cant."),
                    field_name="Cant.",
                    row_index=source_row_index,
                ),
                precio_unitario=_coerce_decimal_numeric(
                    row.get("Prec. Unit."),
                    field_name="Prec. Unit.",
                    row_index=source_row_index,
                ),
                subtotal=_coerce_decimal_numeric(
                    row.get("Subtotal"),
                    field_name="Subtotal",
                    row_index=source_row_index,
                ),
                iva_importe=_coerce_decimal_numeric(
                    row.get("IVA Importe"),
                    field_name="IVA Importe",
                    row_index=source_row_index,
                ),
                iva_tasa=_coerce_decimal_numeric(
                    row.get("IVA Tasa"),
                    field_name="IVA Tasa",
                    row_index=source_row_index,
                ),
                total=_coerce_decimal_numeric(
                    row.get("Total"),
                    field_name="Total",
                    row_index=source_row_index,
                ),
                forma_pago=_normalize_required_text(
                    row.get("Forma De Pago"),
                    field_name="Forma De Pago",
                    row_index=source_row_index,
                ),
                estatus=_normalize_required_text(
                    row.get("Estatus"),
                    field_name="Estatus",
                    row_index=source_row_index,
                ),
                motivo=_normalize_optional_text(row.get("Motivo")),
                realizo_venta=_normalize_required_text(
                    row.get("Realizo Venta"),
                    field_name="Realizo Venta",
                    row_index=source_row_index,
                ),
                hora=_normalize_required_text(
                    row.get("Hora"),
                    field_name="Hora",
                    row_index=source_row_index,
                ),
                id_orden=_normalize_optional_text(row.get("IDOrden")),
                encuesta=_normalize_optional_text(row.get("Encuesta")),
                capturista=_normalize_optional_text(row.get("Capturista")),
                pin=_normalize_optional_text(row.get("PIN")),
                socio=_normalize_optional_text(row.get("Socio")),
                nuevo=_normalize_optional_text(row.get("Nuevo")),
                tipo=_normalize_optional_text(row.get("Tipo")),
            )
        )

    if not parsed_rows:
        raise VentaTotalContentError(
            "El archivo Venta Total no contiene filas de negocio válidas."
        )

    return VentaTotalParseResult(
        rows=parsed_rows,
        row_count=len(parsed_rows),
        header_columns=tuple(str(col) for col in normalized_df.columns.tolist()),
        skipped_rows=skipped_rows,
    )


def _read_venta_total_dataframe(
    *,
    file_path: str | None,
    file_bytes: bytes | None,
) -> pd.DataFrame:
    if not file_path and file_bytes is None:
        raise VentaTotalParserError(
            "Se requiere 'file_path' o 'file_bytes' para parsear Venta Total."
        )

    try:
        source = BytesIO(file_bytes) if file_bytes is not None else Path(file_path)  # type: ignore[arg-type]
        excel_file = pd.ExcelFile(source)
        sheet_name = excel_file.sheet_names[0]
        return pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
    except Exception as exc:
        raise VentaTotalLayoutError(
            "No se pudo leer el archivo XLSX de Venta Total."
        ) from exc


def _find_header_row_index(raw_df: pd.DataFrame) -> int:
    expected_tail = tuple(
        _normalize_header_token(col)
        for col in EXPECTED_VENTA_TOTAL_RAW_COLUMNS[1:]
    )

    for idx in range(len(raw_df)):
        row = raw_df.iloc[idx].tolist()

        first_token = _normalize_header_token(row[0] if len(row) > 0 else None)
        tail_tokens = tuple(
            _normalize_header_token(value)
            for value in row[1 : len(EXPECTED_VENTA_TOTAL_RAW_COLUMNS)]
        )

        first_cell_matches = first_token in {"", "#"}
        if first_cell_matches and tail_tokens == expected_tail:
            return idx

    raise VentaTotalLayoutError(
        "No se encontró la fila del header contractual de Venta Total."
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

    normalized_headers = _dedupe_venta_total_headers(normalized_headers)

    body_df = raw_df.iloc[header_row_idx + 1 :].copy()
    body_df.columns = normalized_headers
    body_df = body_df.reset_index(drop=True)
    return body_df


def _dedupe_venta_total_headers(headers: list[str]) -> list[str]:
    iva_count = 0
    deduped: list[str] = []

    for header in headers:
        if header == "IVA":
            iva_count += 1
            if iva_count == 1:
                deduped.append("IVA Importe")
            elif iva_count == 2:
                deduped.append("IVA Tasa")
            else:
                deduped.append(f"IVA {iva_count}")
        else:
            deduped.append(header)

    return deduped


def _validate_expected_columns(df: pd.DataFrame) -> None:
    actual_columns = tuple(str(col).strip() for col in df.columns.tolist())

    if actual_columns[: len(EXPECTED_VENTA_TOTAL_INTERNAL_COLUMNS)] != EXPECTED_VENTA_TOTAL_INTERNAL_COLUMNS:
        raise VentaTotalLayoutError(
            "El header de Venta Total no coincide con el esperado. "
            f"Esperado={EXPECTED_VENTA_TOTAL_INTERNAL_COLUMNS!r} "
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

    text = str(value).replace("\xa0", " ")
    return " ".join(text.split())


def _normalize_optional_text(value: Any) -> str | None:
    normalized = _normalize_text(value)
    return normalized or None


def _normalize_required_text(
    value: Any,
    *,
    field_name: str,
    row_index: int,
) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        raise VentaTotalContentError(
            f"Valor vacío en columna {field_name!r} para row_index={row_index}."
        )
    return normalized


def _is_empty_row(row: pd.Series) -> bool:
    for value in row.tolist():
        if _normalize_text(value):
            return False
    return True


def _is_report_generated_row(row: pd.Series) -> bool:
    return any(
        _normalize_text(value).strip().lower().startswith("reporte generado:")
        for value in row.tolist()
    )


def _coerce_decimal_numeric(
    value: Any,
    *,
    field_name: str,
    row_index: int,
) -> Decimal:
    normalized = _normalize_numeric_string(
        value,
        field_name=field_name,
        row_index=row_index,
    )

    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise VentaTotalContentError(
            f"No se pudo convertir a Decimal la columna {field_name!r} "
            f"en row_index={row_index}: {value!r}"
        ) from exc


def _normalize_numeric_string(
    value: Any,
    *,
    field_name: str,
    row_index: int,
) -> str:
    if value is None or pd.isna(value):
        raise VentaTotalContentError(
            f"Valor vacío en columna {field_name!r} para row_index={row_index}."
        )

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (int, float)):
        return str(value)

    raw = str(value).strip()
    if not raw:
        raise VentaTotalContentError(
            f"Valor vacío en columna {field_name!r} para row_index={row_index}."
        )

    normalized = raw.replace("$", "")
    normalized = normalized.replace(",", "")
    normalized = normalized.replace(" ", "")

    if normalized.startswith("."):
        normalized = "0" + normalized
    if normalized.startswith("-."):
        normalized = normalized.replace("-.", "-0.", 1)

    return normalized