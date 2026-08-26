from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
from io import BytesIO
import json
from numbers import Integral, Real
from pathlib import Path
import re
from typing import Any

import pandas as pd


SOCIOS_VENCIDOS_REPORT_TYPE_KEY = "socios_vencidos"
EDAD_STATUS_VALID = "VALID"
EDAD_STATUS_INVALID_OUT_OF_RANGE = "INVALID_OUT_OF_RANGE"
EDAD_STATUS_MISSING = "MISSING"

EXPECTED_SOCIOS_VENCIDOS_COLUMNS = (
    "#",
    "Pin",
    "Nombre",
    "Genero",
    "Edad",
    "Fecha Vencimiento",
    "Fecha Último Pago",
    "Tarifa",
    "Correo",
    "Teléfono",
    "Sucursal",
    "Adeudo",
)

_BUSINESS_COLUMNS = EXPECTED_SOCIOS_VENCIDOS_COLUMNS[1:]
_DECIMAL_IDENTIFIER_RE = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)


class SociosVencidosParserError(RuntimeError):
    """Error base del parser de Socios Vencidos."""


class SociosVencidosLayoutError(SociosVencidosParserError):
    """El archivo no cumple el layout contractual esperado."""


class SociosVencidosContentError(SociosVencidosParserError):
    """El archivo no contiene filas de negocio válidas."""


class _SociosVencidosRowError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class SociosVencidosRejectedRow:
    source_row_index: int
    source_row_number: int | None
    reason: str


@dataclass(frozen=True, slots=True)
class SociosVencidosParsedRow:
    row_index: int
    source_row_number: int | None
    pin: str
    nombre: str | None
    genero: str | None
    edad_raw: int | None
    edad: int | None
    edad_status: str
    fecha_vencimiento_local: datetime
    fecha_vencimiento_date: date
    fecha_ultimo_pago_local: datetime | None
    tarifa: str | None
    correo_raw: str | None
    telefono_raw: str | None
    telefono_digits: str | None
    sucursal_raw: str
    adeudo: Decimal | None
    row_hash: str


@dataclass(frozen=True, slots=True)
class SociosVencidosParseResult:
    report_type_key: str = SOCIOS_VENCIDOS_REPORT_TYPE_KEY
    rows: tuple[SociosVencidosParsedRow, ...] = field(default_factory=tuple)
    rejected_rows: tuple[SociosVencidosRejectedRow, ...] = field(
        default_factory=tuple
    )
    row_count_detected: int = 0
    row_count_valid: int = 0
    row_count_rejected: int = 0
    data_quality_counts: dict[str, int] = field(default_factory=dict)
    header_columns: tuple[str, ...] = field(default_factory=tuple)


def register_socios_vencidos_parser(app) -> None:
    app.config["WAREHOUSE_SOCIOS_VENCIDOS_PARSER"] = (
        parse_socios_vencidos_xlsx
    )


def parse_socios_vencidos_xlsx(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
) -> SociosVencidosParseResult:
    raw_df = _read_dataframe(
        file_path=file_path,
        file_bytes=file_bytes,
    )
    header_row_idx = _find_header_row_index(raw_df)
    body_df = _promote_header_row(
        raw_df,
        header_row_idx=header_row_idx,
    )
    _validate_expected_columns(body_df)

    parsed_rows: list[SociosVencidosParsedRow] = []
    rejected_rows: list[SociosVencidosRejectedRow] = []
    data_quality_counts = {
        "invalid_edad": 0,
        "missing_edad": 0,
    }

    for source_row_index, source_row in body_df.iterrows():
        source_row_number = _coerce_optional_source_row_number(
            source_row.get("#")
        )

        if _is_generated_or_empty_business_row(source_row):
            rejected_rows.append(
                SociosVencidosRejectedRow(
                    source_row_index=int(source_row_index),
                    source_row_number=source_row_number,
                    reason="empty_or_generated_business_row",
                )
            )
            continue

        try:
            parsed_row = _parse_business_row(
                source_row,
                row_index=len(parsed_rows),
                source_row_number=source_row_number,
            )
        except _SociosVencidosRowError as exc:
            rejected_rows.append(
                SociosVencidosRejectedRow(
                    source_row_index=int(source_row_index),
                    source_row_number=source_row_number,
                    reason=exc.reason,
                )
            )
            continue

        parsed_rows.append(parsed_row)
        if parsed_row.edad_status == EDAD_STATUS_INVALID_OUT_OF_RANGE:
            data_quality_counts["invalid_edad"] += 1
        elif parsed_row.edad_status == EDAD_STATUS_MISSING:
            data_quality_counts["missing_edad"] += 1

    if not parsed_rows:
        raise SociosVencidosContentError(
            "El archivo Socios Vencidos no contiene filas de negocio válidas."
        )

    return SociosVencidosParseResult(
        rows=tuple(parsed_rows),
        rejected_rows=tuple(rejected_rows),
        row_count_detected=len(body_df),
        row_count_valid=len(parsed_rows),
        row_count_rejected=len(rejected_rows),
        data_quality_counts=data_quality_counts,
        header_columns=tuple(str(column) for column in body_df.columns),
    )


def _read_dataframe(
    *,
    file_path: str | None,
    file_bytes: bytes | None,
) -> pd.DataFrame:
    if not file_path and file_bytes is None:
        raise SociosVencidosParserError(
            "Se requiere 'file_path' o 'file_bytes' para parsear Socios Vencidos."
        )

    try:
        source = (
            BytesIO(file_bytes)
            if file_bytes is not None
            else Path(file_path)  # type: ignore[arg-type]
        )
        excel_file = pd.ExcelFile(source)
        return pd.read_excel(
            excel_file,
            sheet_name=excel_file.sheet_names[0],
            header=None,
        )
    except Exception as exc:
        raise SociosVencidosLayoutError(
            "No se pudo leer el XLSX de Socios Vencidos."
        ) from exc


def _find_header_row_index(raw_df: pd.DataFrame) -> int:
    expected_tokens = tuple(
        _normalize_header_token(column)
        for column in EXPECTED_SOCIOS_VENCIDOS_COLUMNS
    )

    for idx in range(len(raw_df)):
        row_values = raw_df.iloc[idx].tolist()
        candidate_tokens = tuple(
            _normalize_header_token(
                row_values[column_index]
                if column_index < len(row_values)
                else None
            )
            for column_index in range(
                len(EXPECTED_SOCIOS_VENCIDOS_COLUMNS)
            )
        )
        if candidate_tokens == expected_tokens:
            return idx

    raise SociosVencidosLayoutError(
        "No se encontró el header contractual de Socios Vencidos."
    )


def _promote_header_row(
    raw_df: pd.DataFrame,
    *,
    header_row_idx: int,
) -> pd.DataFrame:
    header_values = raw_df.iloc[header_row_idx].tolist()
    headers = [_normalize_text(value) for value in header_values]
    if headers and not headers[0]:
        headers[0] = "#"

    body_df = raw_df.iloc[header_row_idx + 1 :].copy()
    body_df.columns = headers
    return body_df.reset_index(drop=True)


def _validate_expected_columns(df: pd.DataFrame) -> None:
    actual_columns = tuple(
        str(column).strip() for column in df.columns
    )
    if actual_columns != EXPECTED_SOCIOS_VENCIDOS_COLUMNS:
        raise SociosVencidosLayoutError(
            "El header de Socios Vencidos no coincide con el esperado. "
            f"Esperado={EXPECTED_SOCIOS_VENCIDOS_COLUMNS!r} "
            f"Recibido={actual_columns!r}"
        )


def _parse_business_row(
    row: pd.Series,
    *,
    row_index: int,
    source_row_number: int | None,
) -> SociosVencidosParsedRow:
    pin = _normalize_identifier(
        row.get("Pin"),
        field_name="Pin",
        required=True,
    )
    sucursal_raw = _normalize_required_text(
        row.get("Sucursal"),
        field_name="Sucursal",
    )
    fecha_vencimiento_local = _coerce_local_datetime(
        row.get("Fecha Vencimiento"),
        field_name="Fecha Vencimiento",
        required=True,
    )
    fecha_ultimo_pago_local = _coerce_local_datetime(
        row.get("Fecha Último Pago"),
        field_name="Fecha Último Pago",
        required=False,
    )
    telefono_raw = _normalize_identifier(
        row.get("Teléfono"),
        field_name="Teléfono",
        required=False,
    )
    telefono_digits = (
        "".join(character for character in telefono_raw if character.isdigit())
        if telefono_raw is not None
        else None
    )
    telefono_digits = telefono_digits or None
    edad_raw, edad, edad_status = _normalize_age(row.get("Edad"))

    content = {
        "pin": pin,
        "nombre": _normalize_optional_text(row.get("Nombre")),
        "genero": _normalize_optional_text(row.get("Genero")),
        "edad_raw": edad_raw,
        "edad": edad,
        "edad_status": edad_status,
        "fecha_vencimiento_local": fecha_vencimiento_local,
        "fecha_vencimiento_date": fecha_vencimiento_local.date(),
        "fecha_ultimo_pago_local": fecha_ultimo_pago_local,
        "tarifa": _normalize_optional_text(row.get("Tarifa")),
        "correo_raw": _normalize_optional_text(row.get("Correo")),
        "telefono_raw": telefono_raw,
        "telefono_digits": telefono_digits,
        "sucursal_raw": sucursal_raw,
        "adeudo": _coerce_optional_decimal(
            row.get("Adeudo"),
            field_name="Adeudo",
        ),
    }

    return SociosVencidosParsedRow(
        row_index=row_index,
        source_row_number=source_row_number,
        row_hash=_build_row_hash(content),
        **content,
    )


def _normalize_age(value: Any) -> tuple[int | None, int | None, str]:
    edad_raw = _coerce_optional_integer(
        value,
        field_name="Edad",
    )
    if edad_raw is None:
        return None, None, EDAD_STATUS_MISSING
    if 0 <= edad_raw <= 120:
        return edad_raw, edad_raw, EDAD_STATUS_VALID
    return edad_raw, None, EDAD_STATUS_INVALID_OUT_OF_RANGE


def _build_row_hash(content: dict[str, Any]) -> str:
    canonical_payload: dict[str, Any] = {}
    for key, value in content.items():
        if isinstance(value, datetime):
            canonical_payload[key] = value.isoformat(timespec="seconds")
        elif isinstance(value, date):
            canonical_payload[key] = value.isoformat()
        elif isinstance(value, Decimal):
            canonical_payload[key] = _decimal_hash_text(value)
        else:
            canonical_payload[key] = value

    canonical_json = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _decimal_hash_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def _normalize_header_token(value: Any) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return "#"
    return normalized.casefold()


def _normalize_text(value: Any) -> str:
    if value is None or _is_missing(value):
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def _normalize_optional_text(value: Any) -> str | None:
    normalized = _normalize_text(value)
    return normalized or None


def _normalize_required_text(
    value: Any,
    *,
    field_name: str,
) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        raise _SociosVencidosRowError(
            f"missing_required_{field_name.lower().replace(' ', '_')}"
        )
    return normalized


def _normalize_identifier(
    value: Any,
    *,
    field_name: str,
    required: bool,
) -> str | None:
    if value is None or _is_missing(value):
        if required:
            raise _SociosVencidosRowError(
                f"missing_required_{field_name.lower()}"
            )
        return None

    if isinstance(value, bool):
        raise _SociosVencidosRowError(
            f"invalid_{field_name.lower()}"
        )

    if isinstance(value, Integral):
        return str(int(value))

    if isinstance(value, (Decimal, Real)):
        decimal_value = Decimal(str(value))
        if decimal_value != decimal_value.to_integral_value():
            raise _SociosVencidosRowError(
                f"invalid_{field_name.lower()}"
            )
        return format(decimal_value, "f").split(".", 1)[0]

    text_value = _normalize_text(value)
    if not text_value:
        if required:
            raise _SociosVencidosRowError(
                f"missing_required_{field_name.lower()}"
            )
        return None

    if (
        ("." in text_value or "e" in text_value.casefold())
        and _DECIMAL_IDENTIFIER_RE.fullmatch(text_value)
    ):
        try:
            decimal_value = Decimal(text_value)
        except InvalidOperation as exc:
            raise _SociosVencidosRowError(
                f"invalid_{field_name.lower()}"
            ) from exc
        if decimal_value != decimal_value.to_integral_value():
            raise _SociosVencidosRowError(
                f"invalid_{field_name.lower()}"
            )
        return format(decimal_value, "f").split(".", 1)[0]

    return text_value


def _coerce_optional_source_row_number(value: Any) -> int | None:
    try:
        return _coerce_optional_integer(
            value,
            field_name="#",
        )
    except _SociosVencidosRowError:
        return None


def _coerce_optional_integer(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None or _is_missing(value):
        return None
    if isinstance(value, bool):
        raise _SociosVencidosRowError(
            f"invalid_{field_name.lower()}"
        )

    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise _SociosVencidosRowError(
            f"invalid_{field_name.lower()}"
        ) from exc

    if decimal_value != decimal_value.to_integral_value():
        raise _SociosVencidosRowError(
            f"invalid_{field_name.lower()}"
        )
    return int(decimal_value)


def _coerce_local_datetime(
    value: Any,
    *,
    field_name: str,
    required: bool,
) -> datetime | None:
    if value is None or _is_missing(value):
        if required:
            raise _SociosVencidosRowError(
                f"missing_required_{field_name.lower().replace(' ', '_')}"
            )
        return None

    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, time.min)
        else:
            timestamp = pd.to_datetime(
                str(value).strip(),
                dayfirst=True,
                errors="raise",
            )
            parsed = timestamp.to_pydatetime()
    except Exception as exc:
        raise _SociosVencidosRowError(
            f"invalid_{field_name.lower().replace(' ', '_')}"
        ) from exc

    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _coerce_optional_decimal(
    value: Any,
    *,
    field_name: str,
) -> Decimal | None:
    if value is None or _is_missing(value):
        return None
    if isinstance(value, bool):
        raise _SociosVencidosRowError(
            f"invalid_{field_name.lower()}"
        )

    normalized = str(value).strip()
    normalized = normalized.replace("$", "")
    normalized = normalized.replace(",", "")
    normalized = normalized.replace(" ", "")
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise _SociosVencidosRowError(
            f"invalid_{field_name.lower()}"
        ) from exc


def _is_generated_or_empty_business_row(row: pd.Series) -> bool:
    business_values = [row.get(column) for column in _BUSINESS_COLUMNS]
    if not any(_normalize_text(value) for value in business_values):
        return True
    return any(
        _normalize_text(value).casefold().startswith("reporte generado:")
        for value in row.tolist()
    )


def _is_missing(value: Any) -> bool:
    try:
        result = pd.isna(value)
        return bool(result)
    except (TypeError, ValueError):
        return False
    except Exception:
        return False
