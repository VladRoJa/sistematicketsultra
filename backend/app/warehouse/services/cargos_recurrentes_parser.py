#  backend/app/warehouse/services/cargos_recurrentes_parser.py


from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


CARGOS_RECURRENTES_REPORT_TYPE_KEY = "cargos_recurrentes"

EXPECTED_CARGOS_RECURRENTES_COLUMNS = (
    "#",
    "Folio",
    "ID Socio",
    "PIN",
    "Nombre",
    "Sucursal",
    "Fecha Inicio",
    "Fecha De Próximo Pago",
    "# de Intentos",
    "HD",
    "Estatus",
    "Importe",
    "Meses Pendiente",
    "Fecha Fin Contrato",
    "Tipo Contrato",
    "Contrato Ajuste",
    "Acciones",
)


class CargosRecurrentesParserError(RuntimeError):
    """Error base del parser de Cargos Recurrentes."""


class CargosRecurrentesLayoutError(CargosRecurrentesParserError):
    """El archivo no cumple el layout esperado."""


class CargosRecurrentesContentError(CargosRecurrentesParserError):
    """El archivo no contiene filas de negocio válidas."""


@dataclass(slots=True)
class CargosRecurrentesParsedRow:
    row_index: int
    folio: str
    id_socio: str
    pin: str
    nombre: str
    sucursal: str
    fecha_inicio: str
    fecha_proximo_pago: str
    numero_intentos: int
    hd: str
    estatus: str
    importe: Decimal
    meses_pendiente: str
    fecha_fin_contrato: str
    tipo_contrato: str
    contrato_ajuste: str | None
    acciones: str | None


@dataclass(slots=True)
class CargosRecurrentesParseResult:
    report_type_key: str = CARGOS_RECURRENTES_REPORT_TYPE_KEY
    rows: list[CargosRecurrentesParsedRow] = field(default_factory=list)
    row_count: int = 0
    header_columns: tuple[str, ...] = field(default_factory=tuple)
    skipped_rows: int = 0


def register_cargos_recurrentes_parser(app) -> None:
    app.config["WAREHOUSE_CARGOS_RECURRENTES_PARSER"] = parse_cargos_recurrentes_xlsx


def parse_cargos_recurrentes_xlsx(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
) -> CargosRecurrentesParseResult:
    raw_df = _read_cargos_recurrentes_dataframe(
        file_path=file_path,
        file_bytes=file_bytes,
    )

    header_row_idx = _find_header_row_index(raw_df)
    normalized_df = _promote_header_row(raw_df, header_row_idx=header_row_idx)

    _validate_expected_columns(normalized_df)

    parsed_rows: list[CargosRecurrentesParsedRow] = []
    skipped_rows = 0

    for source_row_index, row in normalized_df.iterrows():
        if _is_empty_row(row):
            skipped_rows += 1
            continue

        if _is_report_generated_row(row):
            skipped_rows += 1
            continue

        parsed_rows.append(
            CargosRecurrentesParsedRow(
                row_index=int(source_row_index),
                folio=_normalize_required_text(
                    row.get("Folio"),
                    field_name="Folio",
                    row_index=source_row_index,
                ),
                id_socio=_normalize_required_text(
                    row.get("ID Socio"),
                    field_name="ID Socio",
                    row_index=source_row_index,
                ),
                pin=_normalize_required_text(
                    row.get("PIN"),
                    field_name="PIN",
                    row_index=source_row_index,
                ),
                nombre=_normalize_required_text(
                    row.get("Nombre"),
                    field_name="Nombre",
                    row_index=source_row_index,
                ),
                sucursal=_normalize_required_text(
                    row.get("Sucursal"),
                    field_name="Sucursal",
                    row_index=source_row_index,
                ),
                fecha_inicio=_normalize_required_text(
                    row.get("Fecha Inicio"),
                    field_name="Fecha Inicio",
                    row_index=source_row_index,
                ),
                fecha_proximo_pago=_normalize_required_text(
                    row.get("Fecha De Próximo Pago"),
                    field_name="Fecha De Próximo Pago",
                    row_index=source_row_index,
                ),
                numero_intentos=_ensure_int(
                    row.get("# de Intentos"),
                    field_name="# de Intentos",
                    row_index=source_row_index,
                ),
                hd=_normalize_text(row.get("HD")),
                estatus=_normalize_required_text(
                    row.get("Estatus"),
                    field_name="Estatus",
                    row_index=source_row_index,
                ),
                importe=_coerce_decimal_money(
                    row.get("Importe"),
                    field_name="Importe",
                    row_index=source_row_index,
                ),
                meses_pendiente=_normalize_text(row.get("Meses Pendiente")),
                fecha_fin_contrato=_normalize_text(row.get("Fecha Fin Contrato")),
                tipo_contrato=_normalize_text(row.get("Tipo Contrato")),
                contrato_ajuste=_normalize_optional_text(row.get("Contrato Ajuste")),
                acciones=_normalize_optional_text(row.get("Acciones")),
            )
        )

    if not parsed_rows:
        raise CargosRecurrentesContentError(
            "El archivo Cargos Recurrentes no contiene filas de negocio válidas."
        )

    return CargosRecurrentesParseResult(
        rows=parsed_rows,
        row_count=len(parsed_rows),
        header_columns=tuple(str(col) for col in normalized_df.columns.tolist()),
        skipped_rows=skipped_rows,
    )


def _read_cargos_recurrentes_dataframe(
    *,
    file_path: str | None,
    file_bytes: bytes | None,
) -> pd.DataFrame:
    if not file_path and file_bytes is None:
        raise CargosRecurrentesParserError(
            "Se requiere 'file_path' o 'file_bytes' para parsear Cargos Recurrentes."
        )

    try:
        source = BytesIO(file_bytes) if file_bytes is not None else Path(file_path)  # type: ignore[arg-type]
        excel_file = pd.ExcelFile(source)
        sheet_name = excel_file.sheet_names[0]
        return pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
    except Exception as exc:
        raise CargosRecurrentesLayoutError(
            "No se pudo leer el archivo XLSX de Cargos Recurrentes."
        ) from exc


def _find_header_row_index(raw_df: pd.DataFrame) -> int:
    expected_tail = tuple(
        _normalize_header_token(col)
        for col in EXPECTED_CARGOS_RECURRENTES_COLUMNS[1:]
    )

    for idx in range(len(raw_df)):
        row = raw_df.iloc[idx].tolist()

        first_token = _normalize_header_token(row[0] if len(row) > 0 else None)
        tail_tokens = tuple(
            _normalize_header_token(value)
            for value in row[1: len(EXPECTED_CARGOS_RECURRENTES_COLUMNS)]
        )

        first_cell_matches = first_token in {"", "#"}
        if first_cell_matches and tail_tokens == expected_tail:
            return idx

    raise CargosRecurrentesLayoutError(
        "No se encontró la fila del header contractual de Cargos Recurrentes."
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

    if actual_columns[: len(EXPECTED_CARGOS_RECURRENTES_COLUMNS)] != EXPECTED_CARGOS_RECURRENTES_COLUMNS:
        raise CargosRecurrentesLayoutError(
            "El header de Cargos Recurrentes no coincide con el esperado. "
            f"Esperado={EXPECTED_CARGOS_RECURRENTES_COLUMNS!r} "
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

    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return str(value)
        except Exception:
            pass

    return str(value).strip().replace("\xa0", " ")


def _normalize_optional_text(value: Any) -> str | None:
    text = _normalize_text(value)
    return text or None


def _normalize_required_text(
    value: Any,
    *,
    field_name: str,
    row_index: int,
) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        raise CargosRecurrentesContentError(
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


def _ensure_int(
    value: Any,
    *,
    field_name: str,
    row_index: int,
) -> int:
    if value is None or pd.isna(value):
        raise CargosRecurrentesContentError(
            f"Valor vacío en columna {field_name!r} para row_index={row_index}."
        )

    try:
        return int(value)
    except Exception as exc:
        raise CargosRecurrentesContentError(
            f"No se pudo convertir a int la columna {field_name!r} en row_index={row_index}: {value!r}"
        ) from exc


def _coerce_decimal_money(
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
        raise CargosRecurrentesContentError(
            f"No se pudo convertir a Decimal monetario la columna {field_name!r} "
            f"en row_index={row_index}: {value!r}"
        ) from exc


def _normalize_numeric_string(
    value: Any,
    *,
    field_name: str,
    row_index: int,
) -> str:
    if value is None or pd.isna(value):
        raise CargosRecurrentesContentError(
            f"Valor vacío en columna {field_name!r} para row_index={row_index}."
        )

    if isinstance(value, (int, float, Decimal)):
        return str(value)

    raw = str(value).strip()
    if not raw:
        raise CargosRecurrentesContentError(
            f"Valor vacío en columna {field_name!r} para row_index={row_index}."
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