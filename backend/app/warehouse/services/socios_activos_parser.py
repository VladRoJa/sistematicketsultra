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
import unicodedata

import pandas as pd


SOCIOS_ACTIVOS_REPORT_TYPE_KEY = "socios_activos"

EXPECTED_SOCIOS_ACTIVOS_COLUMNS = (
    "#",
    "Pin",
    "Nombre",
    "Fecha Último Pago",
    "Fecha Vencimiento",
    "Sucursal",
    "Tarifa",
    "Importe Tarifa",
    "Fecha Ingreso",
    "Lada",
    "Teléfono",
    "Fecha Firma",
    "Aplica KPI",
    "Email",
    "ID Socio",
)

_BUSINESS_COLUMNS = EXPECTED_SOCIOS_ACTIVOS_COLUMNS[1:]

_DECIMAL_IDENTIFIER_RE = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)


class SociosActivosParserError(RuntimeError):
    """Error base del parser de Socios Activos."""


class SociosActivosLayoutError(SociosActivosParserError):
    """El archivo no cumple el layout contractual esperado."""


class SociosActivosContentError(SociosActivosParserError):
    """El archivo no contiene filas de negocio válidas."""


class _SociosActivosRowError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class SociosActivosRejectedRow:
    source_row_index: int
    source_row_number: int | None
    reason: str


@dataclass(frozen=True, slots=True)
class SociosActivosParsedRow:
    row_index: int
    source_row_number: int | None

    id_socio: str
    pin: str
    nombre: str | None
    sucursal_raw: str

    fecha_ultimo_pago_local: datetime | None
    fecha_vencimiento_local: datetime
    fecha_vencimiento_date: date
    fecha_ingreso_local: datetime | None
    fecha_firma_local: datetime | None

    tarifa: str | None
    importe_tarifa: Decimal | None

    lada_raw: str | None
    telefono_raw: str | None
    telefono_digits: str | None

    aplica_kpi_raw: str
    aplica_kpi: bool

    email_raw: str | None

    row_hash: str


@dataclass(frozen=True, slots=True)
class SociosActivosParseResult:
    report_type_key: str = SOCIOS_ACTIVOS_REPORT_TYPE_KEY
    rows: tuple[SociosActivosParsedRow, ...] = field(
        default_factory=tuple
    )
    rejected_rows: tuple[SociosActivosRejectedRow, ...] = field(
        default_factory=tuple
    )
    row_count_detected: int = 0
    row_count_valid: int = 0
    row_count_rejected: int = 0
    data_quality_counts: dict[str, int] = field(
        default_factory=dict
    )
    header_columns: tuple[str, ...] = field(
        default_factory=tuple
    )


def register_socios_activos_parser(app) -> None:
    app.config["WAREHOUSE_SOCIOS_ACTIVOS_PARSER"] = (
        parse_socios_activos_xlsx
    )


def parse_socios_activos_xlsx(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
) -> SociosActivosParseResult:
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

    parsed_rows: list[SociosActivosParsedRow] = []
    rejected_rows: list[SociosActivosRejectedRow] = []

    data_quality_counts = {
        "missing_phone": 0,
        "missing_email": 0,
        "aplica_kpi_no": 0,
    }

    for source_row_index, source_row in body_df.iterrows():
        source_row_number = _coerce_optional_source_row_number(
            source_row.get("#")
        )

        if _is_generated_or_empty_business_row(source_row):
            rejected_rows.append(
                SociosActivosRejectedRow(
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
        except _SociosActivosRowError as exc:
            rejected_rows.append(
                SociosActivosRejectedRow(
                    source_row_index=int(source_row_index),
                    source_row_number=source_row_number,
                    reason=exc.reason,
                )
            )
            continue

        parsed_rows.append(parsed_row)

        if parsed_row.telefono_digits is None:
            data_quality_counts["missing_phone"] += 1

        if parsed_row.email_raw is None:
            data_quality_counts["missing_email"] += 1

        if not parsed_row.aplica_kpi:
            data_quality_counts["aplica_kpi_no"] += 1

    if not parsed_rows:
        raise SociosActivosContentError(
            "El archivo Socios Activos no contiene filas "
            "de negocio válidas."
        )

    return SociosActivosParseResult(
        rows=tuple(parsed_rows),
        rejected_rows=tuple(rejected_rows),
        row_count_detected=len(body_df),
        row_count_valid=len(parsed_rows),
        row_count_rejected=len(rejected_rows),
        data_quality_counts=data_quality_counts,
        header_columns=tuple(
            str(column)
            for column in body_df.columns
        ),
    )


def _read_dataframe(
    *,
    file_path: str | None,
    file_bytes: bytes | None,
) -> pd.DataFrame:
    if not file_path and file_bytes is None:
        raise SociosActivosParserError(
            "Se requiere 'file_path' o 'file_bytes' "
            "para parsear Socios Activos."
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
        raise SociosActivosLayoutError(
            "No se pudo leer el XLSX de Socios Activos."
        ) from exc


def _find_header_row_index(
    raw_df: pd.DataFrame,
) -> int:
    expected_tokens = tuple(
        _normalize_header_token(column)
        for column in EXPECTED_SOCIOS_ACTIVOS_COLUMNS
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
                len(EXPECTED_SOCIOS_ACTIVOS_COLUMNS)
            )
        )

        if candidate_tokens == expected_tokens:
            return idx

    raise SociosActivosLayoutError(
        "No se encontró el header contractual "
        "de Socios Activos."
    )


def _promote_header_row(
    raw_df: pd.DataFrame,
    *,
    header_row_idx: int,
) -> pd.DataFrame:
    header_values = raw_df.iloc[
        header_row_idx
    ].tolist()

    headers = [
        _normalize_text(value)
        for value in header_values
    ]

    if headers and not headers[0]:
        headers[0] = "#"

    body_df = raw_df.iloc[
        header_row_idx + 1 :
    ].copy()

    body_df.columns = headers

    return body_df.reset_index(drop=True)


def _validate_expected_columns(
    df: pd.DataFrame,
) -> None:
    actual_columns = tuple(
        str(column).strip()
        for column in df.columns
    )

    if (
        actual_columns
        != EXPECTED_SOCIOS_ACTIVOS_COLUMNS
    ):
        raise SociosActivosLayoutError(
            "El header de Socios Activos no coincide "
            "con el esperado. "
            f"Esperado={EXPECTED_SOCIOS_ACTIVOS_COLUMNS!r} "
            f"Recibido={actual_columns!r}"
        )


def _parse_business_row(
    row: pd.Series,
    *,
    row_index: int,
    source_row_number: int | None,
) -> SociosActivosParsedRow:
    id_socio = _normalize_identifier(
        row.get("ID Socio"),
        field_name="ID Socio",
        required=True,
    )

    pin = _normalize_identifier(
        row.get("Pin"),
        field_name="Pin",
        required=True,
    )

    sucursal_raw = _normalize_required_text(
        row.get("Sucursal"),
        field_name="Sucursal",
    )

    fecha_ultimo_pago_local = _coerce_local_datetime(
        row.get("Fecha Último Pago"),
        field_name="Fecha Último Pago",
        required=False,
    )

    fecha_vencimiento_local = _coerce_local_datetime(
        row.get("Fecha Vencimiento"),
        field_name="Fecha Vencimiento",
        required=True,
    )

    fecha_ingreso_local = _coerce_local_datetime(
        row.get("Fecha Ingreso"),
        field_name="Fecha Ingreso",
        required=False,
    )

    fecha_firma_local = _coerce_local_datetime(
        row.get("Fecha Firma"),
        field_name="Fecha Firma",
        required=False,
    )

    lada_raw = _normalize_identifier(
        row.get("Lada"),
        field_name="Lada",
        required=False,
    )

    telefono_raw = _normalize_identifier(
        row.get("Teléfono"),
        field_name="Teléfono",
        required=False,
    )

    telefono_digits = (
        "".join(
            character
            for character in telefono_raw
            if character.isdigit()
        )
        if telefono_raw is not None
        else None
    )

    telefono_digits = (
        telefono_digits or None
    )

    (
        aplica_kpi_raw,
        aplica_kpi,
    ) = _coerce_aplica_kpi(
        row.get("Aplica KPI")
    )

    content = {
        "id_socio": id_socio,
        "pin": pin,
        "nombre": _normalize_optional_text(
            row.get("Nombre")
        ),
        "sucursal_raw": sucursal_raw,
        "fecha_ultimo_pago_local": (
            fecha_ultimo_pago_local
        ),
        "fecha_vencimiento_local": (
            fecha_vencimiento_local
        ),
        "fecha_vencimiento_date": (
            fecha_vencimiento_local.date()
        ),
        "fecha_ingreso_local": (
            fecha_ingreso_local
        ),
        "fecha_firma_local": (
            fecha_firma_local
        ),
        "tarifa": _normalize_optional_text(
            row.get("Tarifa")
        ),
        "importe_tarifa": _coerce_optional_decimal(
            row.get("Importe Tarifa"),
            field_name="Importe Tarifa",
        ),
        "lada_raw": lada_raw,
        "telefono_raw": telefono_raw,
        "telefono_digits": telefono_digits,
        "aplica_kpi_raw": aplica_kpi_raw,
        "aplica_kpi": aplica_kpi,
        "email_raw": _normalize_optional_text(
            row.get("Email")
        ),
    }

    return SociosActivosParsedRow(
        row_index=row_index,
        source_row_number=source_row_number,
        row_hash=_build_row_hash(content),
        **content,
    )


def _coerce_aplica_kpi(
    value: Any,
) -> tuple[str, bool]:
    raw = _normalize_required_text(
        value,
        field_name="Aplica KPI",
    )

    token = "".join(
        character
        for character in unicodedata.normalize(
            "NFKD",
            raw,
        )
        if not unicodedata.combining(character)
    ).casefold()

    if token == "si":
        return raw, True

    if token == "no":
        return raw, False

    raise _SociosActivosRowError(
        "invalid_aplica_kpi"
    )


def _build_row_hash(
    content: dict[str, Any],
) -> str:
    canonical_payload: dict[str, Any] = {}

    for key, value in content.items():
        if isinstance(value, datetime):
            canonical_payload[key] = (
                value.isoformat(
                    timespec="seconds"
                )
            )
        elif isinstance(value, date):
            canonical_payload[key] = (
                value.isoformat()
            )
        elif isinstance(value, Decimal):
            canonical_payload[key] = (
                _decimal_hash_text(value)
            )
        else:
            canonical_payload[key] = value

    canonical_json = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


def _decimal_hash_text(
    value: Decimal,
) -> str:
    if value == 0:
        return "0"

    normalized = format(
        value.normalize(),
        "f",
    )

    if "." in normalized:
        normalized = (
            normalized
            .rstrip("0")
            .rstrip(".")
        )

    return normalized


def _normalize_header_token(
    value: Any,
) -> str:
    normalized = _normalize_text(value)

    if not normalized:
        return "#"

    return normalized.casefold()


def _normalize_text(
    value: Any,
) -> str:
    if value is None or _is_missing(value):
        return ""

    return " ".join(
        str(value)
        .replace("\xa0", " ")
        .split()
    )


def _normalize_optional_text(
    value: Any,
) -> str | None:
    normalized = _normalize_text(value)

    return normalized or None


def _normalize_required_text(
    value: Any,
    *,
    field_name: str,
) -> str:
    normalized = _normalize_text(value)

    if not normalized:
        raise _SociosActivosRowError(
            "missing_required_"
            + field_name
            .lower()
            .replace(" ", "_")
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
            raise _SociosActivosRowError(
                "missing_required_"
                + field_name
                .lower()
                .replace(" ", "_")
        )

        return None

    if isinstance(value, bool):
        raise _SociosActivosRowError(
            "invalid_"
            + field_name
            .lower()
            .replace(" ", "_")
        )

    if isinstance(value, Integral):
        return str(int(value))

    if isinstance(value, (Decimal, Real)):
        decimal_value = Decimal(
            str(value)
        )

        if (
            decimal_value
            != decimal_value.to_integral_value()
        ):
            raise _SociosActivosRowError(
                "invalid_"
                + field_name
                .lower()
                .replace(" ", "_")
            )

        return format(
            decimal_value,
            "f",
        ).split(".", 1)[0]

    text_value = _normalize_text(value)

    if not text_value:
        if required:
            raise _SociosActivosRowError(
                "missing_required_"
                + field_name
                .lower()
                .replace(" ", "_")
            )

        return None

    if (
        (
            "." in text_value
            or "e" in text_value.casefold()
        )
        and _DECIMAL_IDENTIFIER_RE.fullmatch(
            text_value
        )
    ):
        try:
            decimal_value = Decimal(
                text_value
            )
        except InvalidOperation as exc:
            raise _SociosActivosRowError(
                "invalid_"
                + field_name
                .lower()
                .replace(" ", "_")
            ) from exc

        if (
            decimal_value
            != decimal_value.to_integral_value()
        ):
            raise _SociosActivosRowError(
                "invalid_"
                + field_name
                .lower()
                .replace(" ", "_")
            )

        return format(
            decimal_value,
            "f",
        ).split(".", 1)[0]

    return text_value


def _coerce_optional_source_row_number(
    value: Any,
) -> int | None:
    try:
        return _coerce_optional_integer(
            value,
            field_name="#",
        )
    except _SociosActivosRowError:
        return None


def _coerce_optional_integer(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None or _is_missing(value):
        return None

    if isinstance(value, bool):
        raise _SociosActivosRowError(
            f"invalid_{field_name.lower()}"
        )

    try:
        decimal_value = Decimal(
            str(value).strip()
        )
    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise _SociosActivosRowError(
            f"invalid_{field_name.lower()}"
        ) from exc

    if (
        decimal_value
        != decimal_value.to_integral_value()
    ):
        raise _SociosActivosRowError(
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
            raise _SociosActivosRowError(
                "missing_required_"
                + field_name
                .lower()
                .replace(" ", "_")
            )

        return None

    try:
        if isinstance(value, datetime):
            parsed = value

        elif isinstance(value, date):
            parsed = datetime.combine(
                value,
                time.min,
            )

        else:
            timestamp = pd.to_datetime(
                str(value).strip(),
                dayfirst=True,
                errors="raise",
            )

            parsed = timestamp.to_pydatetime()

    except Exception as exc:
        raise _SociosActivosRowError(
            "invalid_"
            + field_name
            .lower()
            .replace(" ", "_")
        ) from exc

    if parsed.tzinfo is not None:
        parsed = parsed.replace(
            tzinfo=None
        )

    return parsed


def _coerce_optional_decimal(
    value: Any,
    *,
    field_name: str,
) -> Decimal | None:
    if value is None or _is_missing(value):
        return None

    if isinstance(value, bool):
        raise _SociosActivosRowError(
            "invalid_"
            + field_name
            .lower()
            .replace(" ", "_")
        )

    normalized = (
        str(value)
        .strip()
        .replace("$", "")
        .replace(",", "")
        .replace(" ", "")
    )

    try:
        return Decimal(normalized)

    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise _SociosActivosRowError(
            "invalid_"
            + field_name
            .lower()
            .replace(" ", "_")
        ) from exc


def _is_generated_or_empty_business_row(
    row: pd.Series,
) -> bool:
    business_values = [
        row.get(column)
        for column in _BUSINESS_COLUMNS
    ]

    if not any(
        _normalize_text(value)
        for value in business_values
    ):
        return True

    return any(
        _normalize_text(value)
        .casefold()
        .startswith("reporte generado:")
        for value in row.tolist()
    )


def _is_missing(
    value: Any,
) -> bool:
    try:
        result = pd.isna(value)
        return bool(result)

    except (TypeError, ValueError):
        return False

    except Exception:
        return False
