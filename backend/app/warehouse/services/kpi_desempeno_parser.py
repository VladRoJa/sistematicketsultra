#  backend/app/warehouse/services/kpi_desempeno_parser.py


from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
import re

import pandas as pd


KPI_DESEMPENO_REPORT_TYPE_KEY = "kpi_desempeno"

EXPECTED_KPI_DESEMPENO_COLUMNS = (
    "Sucursal",
    "Socios Activos Inicio del Mes",
    "Clientes Nuevo Real",
    "Reactivaciones",
    "Renovaciones",
    "Bajas",
    "Socios Activos del Mes",
    "Meta de Socios Activos del Mes",
    "Alcance de meta",
)


class KpiDesempenoParserError(RuntimeError):
    """Error base del parser de KPI Desempeño."""


class KpiDesempenoLayoutError(KpiDesempenoParserError):
    """El archivo no cumple el layout esperado."""


class KpiDesempenoContentError(KpiDesempenoParserError):
    """El archivo no contiene filas de negocio válidas."""


@dataclass(slots=True)
class KpiDesempenoParsedRow:
    row_index: int
    sucursal_nombre: str
    socios_activos_inicio_mes: int
    clientes_nuevo_real: int
    reactivaciones: int
    renovaciones: int
    bajas: int
    socios_activos_del_mes: int
    meta_socios_activos_del_mes: int
    alcance_meta: float


@dataclass(slots=True)
class KpiDesempenoParseResult:
    report_type_key: str = KPI_DESEMPENO_REPORT_TYPE_KEY
    rows: list[KpiDesempenoParsedRow] = field(default_factory=list)
    row_count: int = 0
    header_columns: tuple[str, ...] = field(default_factory=tuple)
    skipped_rows: int = 0
    report_cutoff_date: str | None = None


def parse_kpi_desempeno_xlsx(
    *,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
) -> KpiDesempenoParseResult:
    df, report_cutoff_date = _read_kpi_desempeno_dataframe(
        file_path=file_path,
        file_bytes=file_bytes,
    )

    _validate_expected_columns(df)

    parsed_rows: list[KpiDesempenoParsedRow] = []
    skipped_rows = 0

    for row_index, row in df.iterrows():
        sucursal_raw = row["Sucursal"]
        sucursal = _normalize_sucursal_name(sucursal_raw)

        if not sucursal:
            skipped_rows += 1
            continue

        if _is_totales_row(sucursal) or sucursal.casefold().startswith("reporte generado:"):
            skipped_rows += 1
            continue

        if sucursal.strip().upper().replace("_", " ") == "LA VIGA":
            skipped_rows += 1
            continue

        parsed_rows.append(
            KpiDesempenoParsedRow(
                row_index=int(row_index),
                sucursal_nombre=sucursal,
                socios_activos_inicio_mes=_coerce_int(
                    row["Socios Activos Inicio del Mes"],
                    column_name="Socios Activos Inicio del Mes",
                    row_index=row_index,
                ),
                clientes_nuevo_real=_coerce_int(
                    row["Clientes Nuevo Real"],
                    column_name="Clientes Nuevo Real",
                    row_index=row_index,
                ),
                reactivaciones=_coerce_int(
                    row["Reactivaciones"],
                    column_name="Reactivaciones",
                    row_index=row_index,
                ),
                renovaciones=_coerce_int(
                    row["Renovaciones"],
                    column_name="Renovaciones",
                    row_index=row_index,
                ),
                bajas=_coerce_int(
                    row["Bajas"],
                    column_name="Bajas",
                    row_index=row_index,
                ),
                socios_activos_del_mes=_coerce_int(
                    row["Socios Activos del Mes"],
                    column_name="Socios Activos del Mes",
                    row_index=row_index,
                ),
                meta_socios_activos_del_mes=_coerce_int(
                    row["Meta de Socios Activos del Mes"],
                    column_name="Meta de Socios Activos del Mes",
                    row_index=row_index,
                ),
                alcance_meta=_coerce_float(
                    row["Alcance de meta"],
                    column_name="Alcance de meta",
                    row_index=row_index,
                ),
            )
        )

    if not parsed_rows:
        raise KpiDesempenoContentError(
            "El archivo KPI Desempeño no contiene filas de negocio válidas."
        )

    return KpiDesempenoParseResult(
        rows=parsed_rows,
        row_count=len(parsed_rows),
        header_columns=tuple(str(col) for col in df.columns.tolist()),
        skipped_rows=skipped_rows,
        report_cutoff_date=report_cutoff_date,
    )


def _read_kpi_desempeno_dataframe(
    *,
    file_path: str | None,
    file_bytes: bytes | None,
) -> tuple[pd.DataFrame, str | None]:
    if not file_path and file_bytes is None:
        raise KpiDesempenoParserError(
            "Se requiere 'file_path' o 'file_bytes' para parsear KPI Desempeño."
        )

    try:
        source = BytesIO(file_bytes) if file_bytes is not None else Path(file_path)
        excel_file = pd.ExcelFile(source)
        preferred_sheet_name = next(
            (
                sheet_name
                for sheet_name in excel_file.sheet_names
                if str(sheet_name).strip().lower() == "data"
            ),
            excel_file.sheet_names[0],
        )
        # Gasca exports may place the cutoff title above the real header.
        raw = pd.read_excel(excel_file, sheet_name=preferred_sheet_name, header=None)
        header_row_index = next(
            (
                idx
                for idx in range(min(len(raw), 6))
                if tuple(
                    str(value).strip() if pd.notna(value) else ""
                    for value in raw.iloc[idx].tolist()
                ) == EXPECTED_KPI_DESEMPENO_COLUMNS
            ),
            None,
        )
        if header_row_index is None:
            raise KpiDesempenoLayoutError(
                "No se encontró el encabezado esperado de KPI Desempeño."
            )

        report_cutoff_date = None
        if header_row_index > 0:
            title = str(raw.iat[0, 0] or "")
            cutoff_match = re.search(
                r"Corte:\s*(\d{2}/\d{2}/\d{4})", title, re.IGNORECASE
            )
            if not cutoff_match:
                raise KpiDesempenoLayoutError(
                    "El archivo KPI con título debe indicar la fecha de corte."
                )
            try:
                report_cutoff_date = datetime.strptime(
                    cutoff_match.group(1), "%d/%m/%Y"
                ).date().isoformat()
            except ValueError as exc:
                raise KpiDesempenoLayoutError(
                    "Fecha de corte inválida en el título de KPI Desempeño."
                ) from exc

        return (
            pd.read_excel(
                excel_file,
                sheet_name=preferred_sheet_name,
                header=header_row_index,
            ),
            report_cutoff_date,
        )
    except KpiDesempenoParserError:
        raise
    except Exception as exc:
        raise KpiDesempenoLayoutError(
            "No se pudo leer el archivo XLSX de KPI Desempeño."
        ) from exc


def _validate_expected_columns(df: pd.DataFrame) -> None:
    actual_columns = tuple(str(col).strip() for col in df.columns.tolist())

    if actual_columns != EXPECTED_KPI_DESEMPENO_COLUMNS:
        raise KpiDesempenoLayoutError(
            "El header de KPI Desempeño no coincide con el esperado. "
            f"Esperado={EXPECTED_KPI_DESEMPENO_COLUMNS!r} "
            f"Recibido={actual_columns!r}"
        )


def _normalize_sucursal_name(value: Any) -> str:
    if value is None:
        return ""

    if pd.isna(value):
        return ""

    return str(value).strip()


def _is_totales_row(sucursal_nombre: str) -> bool:
    normalized = sucursal_nombre.strip().lower().replace(" ", "")
    return normalized in {"totales:", "totales"}


def _coerce_int(
    value: Any,
    *,
    column_name: str,
    row_index: int,
) -> int:
    if value is None or pd.isna(value):
        raise KpiDesempenoContentError(
            f"Valor vacío en columna {column_name!r} para row_index={row_index}."
        )

    try:
        return int(float(value))
    except Exception as exc:
        raise KpiDesempenoContentError(
            f"No se pudo convertir a int la columna {column_name!r} "
            f"en row_index={row_index}: {value!r}"
        ) from exc


def _coerce_float(
    value: Any,
    *,
    column_name: str,
    row_index: int,
) -> float:
    if value is None or pd.isna(value):
        raise KpiDesempenoContentError(
            f"Valor vacío en columna {column_name!r} para row_index={row_index}."
        )

    try:
        return float(value)
    except Exception as exc:
        raise KpiDesempenoContentError(
            f"No se pudo convertir a float la columna {column_name!r} "
            f"en row_index={row_index}: {value!r}"
        ) from exc