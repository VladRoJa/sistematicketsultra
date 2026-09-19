# backend/app/services/maintenance_preventive_import_service.py

from __future__ import annotations

import csv
import hashlib
import io
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

from app.services.maintenance_preventive_service import MaintenancePreventiveError


TEMPLATE_HEADERS = (
    "Sucursal",
    "Código equipo",
    "Fecha programada",
    "Actividad",
    "Responsable",
    "Observaciones",
)

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 1000


def _normalize_header(value) -> str:
    raw = str(value or "").strip().casefold()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    }
    for source, target in replacements.items():
        raw = raw.replace(source, target)
    return " ".join(raw.replace("_", " ").split())


HEADER_MAP = {
    "sucursal": "sucursal",
    "codigo equipo": "codigo_equipo",
    "fecha programada": "fecha_programada",
    "actividad": "actividad",
    "responsable": "responsable",
    "observaciones": "observaciones",
}


def _date_input(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return None
    return str(value).strip() or None


def _row_is_empty(values) -> bool:
    return not any(
        str(value).strip()
        for value in values
        if value is not None
    )


def _resolve_columns(headers) -> dict[int, str]:
    resolved: dict[int, str] = {}

    for index, value in enumerate(headers):
        key = _normalize_header(value)
        field = HEADER_MAP.get(key)
        if field:
            resolved[index] = field

    missing = [
        header
        for header in TEMPLATE_HEADERS[:-1]
        if HEADER_MAP[_normalize_header(header)] not in resolved.values()
    ]
    if missing:
        raise MaintenancePreventiveError(
            "La plantilla no contiene columnas obligatorias: "
            + ", ".join(missing)
        )

    return resolved


def _build_rows(raw_rows, columns: dict[int, str], *, start_row: int):
    result: list[dict] = []

    for row_number, values in enumerate(raw_rows, start=start_row):
        values = list(values)

        if _row_is_empty(values):
            continue

        payload = {
            "source_row_number": row_number,
            "sucursal": None,
            "codigo_equipo": None,
            "fecha_programada": None,
            "actividad": None,
            "responsable": None,
            "observaciones": None,
        }

        for column_index, field in columns.items():
            value = values[column_index] if column_index < len(values) else None
            if field == "fecha_programada":
                payload[field] = _date_input(value)
            else:
                payload[field] = (
                    str(value).strip()
                    if value is not None and str(value).strip()
                    else None
                )

        result.append(payload)

        if len(result) > MAX_IMPORT_ROWS:
            raise MaintenancePreventiveError(
                f"La carga excede el máximo de {MAX_IMPORT_ROWS} renglones."
            )

    if not result:
        raise MaintenancePreventiveError(
            "La plantilla no contiene renglones de programación."
        )

    return result


def _parse_xlsx(content: bytes) -> list[dict]:
    try:
        workbook = load_workbook(
            io.BytesIO(content),
            read_only=True,
            data_only=True,
        )
    except Exception as exc:
        raise MaintenancePreventiveError(
            "No se pudo leer el archivo Excel."
        ) from exc

    try:
        sheet = workbook.active
        iterator = sheet.iter_rows(values_only=True)
        headers = next(iterator, None)
        if headers is None:
            raise MaintenancePreventiveError(
                "La plantilla Excel está vacía."
            )

        columns = _resolve_columns(headers)
        return _build_rows(iterator, columns, start_row=2)
    finally:
        workbook.close()


def _parse_csv(content: bytes) -> list[dict]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MaintenancePreventiveError(
            "El CSV debe estar codificado en UTF-8."
        ) from exc

    reader = csv.reader(io.StringIO(text))
    headers = next(reader, None)
    if headers is None:
        raise MaintenancePreventiveError("El CSV está vacío.")

    columns = _resolve_columns(headers)
    return _build_rows(reader, columns, start_row=2)


def parse_preventive_import(
    *,
    filename: str,
    content: bytes,
) -> dict:
    if not filename:
        raise MaintenancePreventiveError(
            "El archivo debe tener nombre."
        )

    if not content:
        raise MaintenancePreventiveError(
            "El archivo está vacío."
        )

    if len(content) > MAX_IMPORT_BYTES:
        raise MaintenancePreventiveError(
            "El archivo excede el límite de 5 MB."
        )

    extension = Path(filename).suffix.casefold()
    if extension == ".xlsx":
        rows = _parse_xlsx(content)
    elif extension == ".csv":
        rows = _parse_csv(content)
    else:
        raise MaintenancePreventiveError(
            "Formato no soportado; usa .xlsx o .csv."
        )

    return {
        "filename": Path(filename).name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "rows": rows,
    }


def build_preventive_template_xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Programacion preventiva"
    sheet.append(list(TEMPLATE_HEADERS))

    # Solo guía visual; no se considera registro real.
    sheet.append(
        [
            "VILLAS DEL REY",
            "04CC01",
            "2026-09-20",
            "Mantenimiento preventivo general",
            "TECNICO_PM",
            "",
        ]
    )

    widths = {
        "A": 24,
        "B": 20,
        "C": 20,
        "D": 40,
        "E": 24,
        "F": 40,
    }
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
