# backend/app/services/maintenance_preventive_import_service.py

from __future__ import annotations

import csv
import hashlib
import io
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName

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

    raw = str(value).strip()
    if not raw:
        return None

    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, date_format).date().isoformat()
        except ValueError:
            continue

    return raw


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


def _clean_catalog_values(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue

        key = text.casefold()
        if key in seen:
            continue

        seen.add(key)
        result.append(text)

    return result


def _add_named_list(
    workbook,
    *,
    name: str,
    sheet_name: str,
    column: str,
    start_row: int,
    end_row: int,
) -> None:
    if end_row < start_row:
        return

    sheet_ref = sheet_name.replace("'", "''")
    attr_text = (
        "'" + sheet_ref + "'!$"
        + column + "$" + str(start_row)
        + ":$" + column + "$" + str(end_row)
    )
    workbook.defined_names.add(
        DefinedName(name, attr_text=attr_text)
    )


def build_preventive_template_xlsx(
    *,
    sucursales: list[str] | None = None,
    responsables: list[str] | None = None,
    equipos: list[dict] | None = None,
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Programacion preventiva"
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = "A1:F1001"

    header_fill = PatternFill("solid", fgColor="E54525")
    header_font = Font(color="FFFFFF", bold=True)
    header_alignment = Alignment(
        horizontal="center",
        vertical="center",
    )
    thin = Side(style="thin", color="D8DEE8")
    input_border = Border(
        left=thin,
        right=thin,
        top=thin,
        bottom=thin,
    )

    for column_index, header in enumerate(TEMPLATE_HEADERS, start=1):
        cell = sheet.cell(row=1, column=column_index, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = input_border

    sheet["A1"].comment = Comment(
        "Selecciona una sucursal del catálogo disponible.",
        "Suite Ultra",
    )
    sheet["B1"].comment = Comment(
        "Captura el código interno del equipo. Consulta la hoja "
        "Catálogos para validar sucursal y equipo.",
        "Suite Ultra",
    )
    sheet["C1"].comment = Comment(
        "Captura la fecha en formato dd/mm/aaaa.",
        "Suite Ultra",
    )
    sheet["D1"].comment = Comment(
        "Describe el mantenimiento preventivo que se realizará.",
        "Suite Ultra",
    )
    sheet["E1"].comment = Comment(
        "Selecciona un responsable activo del catálogo de Mantenimiento.",
        "Suite Ultra",
    )
    sheet["F1"].comment = Comment(
        "Campo opcional para notas de programación.",
        "Suite Ultra",
    )

    widths = {
        "A": 26,
        "B": 22,
        "C": 18,
        "D": 42,
        "E": 26,
        "F": 42,
    }
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    for row in range(2, MAX_IMPORT_ROWS + 2):
        for column in range(1, len(TEMPLATE_HEADERS) + 1):
            cell = sheet.cell(row=row, column=column)
            cell.border = input_border
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=(column in {4, 6}),
            )
        sheet.cell(row=row, column=3).number_format = "dd/mm/yyyy"

    date_validation = DataValidation(
        type="date",
        operator="between",
        formula1="DATE(2020,1,1)",
        formula2="DATE(2100,12,31)",
        allow_blank=False,
    )
    date_validation.error = (
        "Captura una fecha válida en formato dd/mm/aaaa."
    )
    date_validation.errorTitle = "Fecha inválida"
    date_validation.prompt = "Formato esperado: dd/mm/aaaa"
    date_validation.promptTitle = "Fecha programada"
    date_validation.showErrorMessage = True
    date_validation.showInputMessage = True
    sheet.add_data_validation(date_validation)
    date_validation.add("C2:C1001")

    catalogs = workbook.create_sheet("Catálogos")
    catalogs.sheet_view.showGridLines = False
    catalogs.freeze_panes = "A2"

    branch_values = _clean_catalog_values(sucursales)
    responsible_values = _clean_catalog_values(responsables)
    equipment_rows = list(equipos or [])

    catalogs.append([
        "Sucursales",
        "Responsables",
        "",
        "Sucursal equipo",
        "Código equipo",
        "Equipo",
        "Familia",
    ])

    for cell in catalogs[1]:
        if cell.column == 3:
            continue
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = input_border

    max_catalog_rows = max(
        len(branch_values),
        len(responsible_values),
        len(equipment_rows),
        1,
    )

    for index in range(max_catalog_rows):
        row_number = index + 2
        if index < len(branch_values):
            catalogs.cell(row=row_number, column=1, value=branch_values[index])
        if index < len(responsible_values):
            catalogs.cell(row=row_number, column=2, value=responsible_values[index])
        if index < len(equipment_rows):
            equipment = equipment_rows[index] or {}
            catalogs.cell(row=row_number, column=4, value=str(equipment.get("sucursal") or ""))
            catalogs.cell(row=row_number, column=5, value=str(equipment.get("codigo_interno") or ""))
            catalogs.cell(row=row_number, column=6, value=str(equipment.get("nombre") or ""))
            catalogs.cell(row=row_number, column=7, value=str(equipment.get("familia") or ""))

    catalog_widths = {
        "A": 28,
        "B": 28,
        "C": 3,
        "D": 28,
        "E": 22,
        "F": 34,
        "G": 28,
    }
    for column, width in catalog_widths.items():
        catalogs.column_dimensions[column].width = width

    equipment_end = max(len(equipment_rows) + 1, 2)
    catalogs.auto_filter.ref = "D1:G" + str(equipment_end)

    if branch_values:
        _add_named_list(
            workbook,
            name="CatalogoSucursales",
            sheet_name=catalogs.title,
            column="A",
            start_row=2,
            end_row=len(branch_values) + 1,
        )
        branch_validation = DataValidation(
            type="list",
            formula1="=CatalogoSucursales",
            allow_blank=False,
        )
        branch_validation.error = (
            "Selecciona una sucursal incluida en el catálogo."
        )
        branch_validation.errorTitle = "Sucursal inválida"
        branch_validation.showErrorMessage = True
        sheet.add_data_validation(branch_validation)
        branch_validation.add("A2:A1001")

    if responsible_values:
        _add_named_list(
            workbook,
            name="CatalogoResponsables",
            sheet_name=catalogs.title,
            column="B",
            start_row=2,
            end_row=len(responsible_values) + 1,
        )
        responsible_validation = DataValidation(
            type="list",
            formula1="=CatalogoResponsables",
            allow_blank=False,
        )
        responsible_validation.error = (
            "Selecciona un responsable incluido en el catálogo."
        )
        responsible_validation.errorTitle = "Responsable inválido"
        responsible_validation.showErrorMessage = True
        sheet.add_data_validation(responsible_validation)
        responsible_validation.add("E2:E1001")

    sheet.row_dimensions[1].height = 26

    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
