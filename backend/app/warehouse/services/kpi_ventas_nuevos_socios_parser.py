# backend/app/warehouse/services/kpi_ventas_nuevos_socios_parser.py


from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


KPI_VENTAS_NUEVOS_SOCIOS_REPORT_TYPE_KEY = "kpi_ventas_nuevos_socios"

EXPECTED_KPI_VENTAS_NUEVOS_SOCIOS_COLUMNS = (
    "Sucursal",
    "Numero de CNM (Meta)",
    "Ingreso por CNM (Meta)",
    "Clientes Nuevos (Real)",
    "Ingreso Clientes Nuevos (Real)",
    "CNReal - MetaCNM",
    "% Meta",
    "CNReal - MetaCNM.1",
    "% Meta.1",
)


class KpiVentasNuevosSociosParserError(RuntimeError):
    """Error base del parser de KPI Ventas Nuevos Socios."""


class KpiVentasNuevosSociosLayoutError(KpiVentasNuevosSociosParserError):
    """El archivo no cumple el layout esperado."""


class KpiVentasNuevosSociosContentError(KpiVentasNuevosSociosParserError):
    """El archivo no contiene filas de negocio válidas."""


@dataclass(slots=True)
class KpiVentasNuevosSociosParsedRow:
    row_index: int
    sucursal: str
    numero_cnm_meta: int
    ingreso_por_cnm_meta: Decimal
    clientes_nuevos_real: int
    ingreso_clientes_nuevos_real: Decimal
    cnreal_menos_meta_cnm: int
    porcentaje_meta: Decimal
    cnreal_menos_meta_cnm_alt: Decimal
    porcentaje_meta_alt: Decimal


@dataclass(slots=True)
class KpiVentasNuevosSociosParseResult:
    report_type_key: str = KPI_VENTAS_NUEVOS_SOCIOS_REPORT_TYPE_KEY
    rows: list[KpiVentasNuevosSociosParsedRow] = field(default_factory=list)
    row_count: int = 0
    header_columns: tuple[str, ...] = field(default_factory=tuple)
    skipped_rows: int = 0


def parse_kpi_ventas_nuevos_socios_xlsx(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
) -> KpiVentasNuevosSociosParseResult:
    df = _read_kpi_ventas_nuevos_socios_dataframe(
        file_path=file_path,
        file_bytes=file_bytes,
    )

    _validate_expected_columns(df)

    parsed_rows: list[KpiVentasNuevosSociosParsedRow] = []
    skipped_rows = 0

    for row_index, row in df.iterrows():
        sucursal = _normalize_sucursal_name(row["Sucursal"])

        if not sucursal:
            skipped_rows += 1
            continue

        if _is_totales_row(sucursal):
            skipped_rows += 1
            continue

        parsed_rows.append(
            KpiVentasNuevosSociosParsedRow(
                row_index=int(row_index),
                sucursal=sucursal,
                numero_cnm_meta=_coerce_int(
                    row["Numero de CNM (Meta)"],
                    column_name="Numero de CNM (Meta)",
                    row_index=row_index,
                ),
                ingreso_por_cnm_meta=_coerce_decimal_money(
                    row["Ingreso por CNM (Meta)"],
                    column_name="Ingreso por CNM (Meta)",
                    row_index=row_index,
                ),
                clientes_nuevos_real=_coerce_int(
                    row["Clientes Nuevos (Real)"],
                    column_name="Clientes Nuevos (Real)",
                    row_index=row_index,
                ),
                ingreso_clientes_nuevos_real=_coerce_decimal_money(
                    row["Ingreso Clientes Nuevos (Real)"],
                    column_name="Ingreso Clientes Nuevos (Real)",
                    row_index=row_index,
                ),
                cnreal_menos_meta_cnm=_coerce_int(
                    row["CNReal - MetaCNM"],
                    column_name="CNReal - MetaCNM",
                    row_index=row_index,
                ),
                porcentaje_meta=_coerce_decimal_percent(
                    row["% Meta"],
                    column_name="% Meta",
                    row_index=row_index,
                ),
                cnreal_menos_meta_cnm_alt=_coerce_decimal_money(
                    row["CNReal - MetaCNM.1"],
                    column_name="CNReal - MetaCNM.1",
                    row_index=row_index,
                ),
                porcentaje_meta_alt=_coerce_decimal_percent(
                    row["% Meta.1"],
                    column_name="% Meta.1",
                    row_index=row_index,
                ),
            )
        )

    if not parsed_rows:
        raise KpiVentasNuevosSociosContentError(
            "El archivo KPI Ventas Nuevos Socios no contiene filas de negocio válidas."
        )

    return KpiVentasNuevosSociosParseResult(
        rows=parsed_rows,
        row_count=len(parsed_rows),
        header_columns=tuple(str(col) for col in df.columns.tolist()),
        skipped_rows=skipped_rows,
    )


def _read_kpi_ventas_nuevos_socios_dataframe(
    *,
    file_path: str | None,
    file_bytes: bytes | None,
) -> pd.DataFrame:
    if not file_path and file_bytes is None:
        raise KpiVentasNuevosSociosParserError(
            "Se requiere 'file_path' o 'file_bytes' para parsear KPI Ventas Nuevos Socios."
        )

    try:
        source = BytesIO(file_bytes) if file_bytes is not None else Path(file_path)  # type: ignore[arg-type]
        excel_file = pd.ExcelFile(source)

        preferred_sheet_name = next(
            (
                sheet_name
                for sheet_name in excel_file.sheet_names
                if str(sheet_name).strip().lower() == "data"
            ),
            excel_file.sheet_names[0],
        )

        return pd.read_excel(excel_file, sheet_name=preferred_sheet_name)
    except Exception as exc:
        raise KpiVentasNuevosSociosLayoutError(
            "No se pudo leer el archivo XLSX de KPI Ventas Nuevos Socios."
        ) from exc


def _validate_expected_columns(df: pd.DataFrame) -> None:
    actual_columns = tuple(str(col).strip() for col in df.columns.tolist())

    if actual_columns != EXPECTED_KPI_VENTAS_NUEVOS_SOCIOS_COLUMNS:
        raise KpiVentasNuevosSociosLayoutError(
            "El header de KPI Ventas Nuevos Socios no coincide con el esperado. "
            f"Esperado={EXPECTED_KPI_VENTAS_NUEVOS_SOCIOS_COLUMNS!r} "
            f"Recibido={actual_columns!r}"
        )


def _normalize_sucursal_name(value: Any) -> str:
    if value is None:
        return ""

    if pd.isna(value):
        return ""

    return str(value).strip()


def _is_totales_row(sucursal: str) -> bool:
    normalized = sucursal.strip().lower().replace(" ", "")
    return normalized in {"totales:", "totales"}


def _coerce_int(
    value: Any,
    *,
    column_name: str,
    row_index: int,
) -> int:
    if value is None or pd.isna(value):
        raise KpiVentasNuevosSociosContentError(
            f"Valor vacío en columna {column_name!r} para row_index={row_index}."
        )

    try:
        return int(float(value))
    except Exception as exc:
        raise KpiVentasNuevosSociosContentError(
            f"No se pudo convertir a int la columna {column_name!r} "
            f"en row_index={row_index}: {value!r}"
        ) from exc


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
        allow_percent=False,
    )

    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise KpiVentasNuevosSociosContentError(
            f"No se pudo convertir a Decimal monetario la columna {column_name!r} "
            f"en row_index={row_index}: {value!r}"
        ) from exc


def _coerce_decimal_percent(
    value: Any,
    *,
    column_name: str,
    row_index: int,
) -> Decimal:
    normalized = _normalize_numeric_string(
        value,
        column_name=column_name,
        row_index=row_index,
        allow_percent=True,
    )

    try:
        # Se conserva el valor mostrado en el reporte.
        # Ejemplo: "12.50 %" -> Decimal("12.50")
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise KpiVentasNuevosSociosContentError(
            f"No se pudo convertir a Decimal porcentual la columna {column_name!r} "
            f"en row_index={row_index}: {value!r}"
        ) from exc


def _normalize_numeric_string(
    value: Any,
    *,
    column_name: str,
    row_index: int,
    allow_percent: bool,
) -> str:
    if value is None or pd.isna(value):
        raise KpiVentasNuevosSociosContentError(
            f"Valor vacío en columna {column_name!r} para row_index={row_index}."
        )

    if isinstance(value, (int, float, Decimal)):
        return str(value)

    raw = str(value).strip()

    if not raw:
        raise KpiVentasNuevosSociosContentError(
            f"Valor vacío en columna {column_name!r} para row_index={row_index}."
        )

    normalized = raw.replace("$", "")
    normalized = normalized.replace(",", "")
    normalized = normalized.replace(" ", "")

    if allow_percent:
        normalized = normalized.replace("%", "")

    # Casos como ".00" o "-.00"
    if normalized.startswith("."):
        normalized = "0" + normalized
    if normalized.startswith("-."):
        normalized = normalized.replace("-.", "-0.", 1)

    # Casos como string vacía tras limpiar "$ .00"
    if normalized in {"", "-", "."}:
        normalized = "0"

    return normalized