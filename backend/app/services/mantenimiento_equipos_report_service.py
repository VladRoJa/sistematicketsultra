from collections import OrderedDict
from datetime import datetime, timezone
from io import BytesIO

from dateutil import parser
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import joinedload
import pytz

from app.models.ticket_model import Ticket


BUSINESS_TIMEZONE = pytz.timezone("America/Tijuana")
ACTIVE_TICKET_STATUSES = ("abierto", "en progreso", "por_validar")
LEGACY_UNCLASSIFIED_FAMILY = "SIN CLASIFICAR HISTÓRICO"
PENDING_CAPTURE = "Pendiente de captura"
NO_COMMITMENT = "Sin compromiso"

TICKETS_HEADERS = (
    "Ticket ID",
    "Aparato/Dispositivo",
    "Código Interno",
    "Descripción",
    "Estado",
    "Fecha Creación",
    "Sucursal",
    "Familia",
    "Falla detectada",
    "Condición",
    "Reparación",
    "Observación / Plan de trabajo",
)

SUMMARY_FAMILIES = (
    ("CAMINADORA", "Caminadoras"),
    ("ELIPTICA", "Elípticas"),
    ("ESCALADORA", "Escaladoras"),
    ("RECUMBENTE", "Recumbentes"),
    ("SPINNING", "Spinning"),
    ("PESO_LIBRE", "Peso Libre"),
    ("PESO_INTEGRADO", "Peso Integrado"),
)

FAMILY_SHEETS = (
    ("CAMINADORA", "Caminadoras"),
    ("ELIPTICA", "Elípticas"),
    ("ESCALADORA", "Escaladoras"),
    ("SPINNING", "Spinning"),
    ("RECUMBENTE", "Recumbentes"),
    ("PESO_INTEGRADO", "Peso Integrado"),
    ("PESO_LIBRE", "Peso Libre"),
)

FAMILY_HEADERS = (
    "Sucursal",
    "Ticket ID",
    "ID Equipo",
    "Falla",
    "Condición",
    "Reparación",
    "Observación / Plan de trabajo",
)


def obtener_tickets_reporte():
    return (
        Ticket.query
        .options(
            joinedload(Ticket.inventario),
            joinedload(Ticket.familia_equipo),
            joinedload(Ticket.falla_mantenimiento),
            joinedload(Ticket.sucursal),
            joinedload(Ticket.sucursal_destino),
        )
        .filter(
            Ticket.departamento_id == 1,
            Ticket.aparato_id.isnot(None),
            Ticket.estado.in_(ACTIVE_TICKET_STATUSES),
        )
        .order_by(Ticket.sucursal_id_destino.asc(), Ticket.id.asc())
        .all()
    )


def _safe_branch_name(ticket):
    branch = ticket.sucursal_destino or ticket.sucursal
    if not branch:
        return "Sin sucursal"

    return str(
        getattr(branch, "sucursal", None)
        or getattr(branch, "nombre", None)
        or getattr(branch, "nombre_sucursal", None)
        or "Sin sucursal"
    ).strip()


def _to_business_datetime(value):
    if not value:
        return None
    if isinstance(value, str):
        value = parser.isoparse(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BUSINESS_TIMEZONE)


def _format_created_at(value):
    local_value = _to_business_datetime(value)
    return local_value.strftime("%d/%m/%Y %H:%M") if local_value else ""


def _format_commitment(value):
    local_value = _to_business_datetime(value)
    return local_value.strftime("%d/%m/%Y") if local_value else NO_COMMITMENT


def _history_sort_key(item):
    value = (
        item.get("fechaCambio")
        or item.get("fecha_cambio")
        or item.get("fecha")
    )
    try:
        parsed = parser.isoparse(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return datetime.min.replace(tzinfo=timezone.utc)


def plan_trabajo_desde_historial(history):
    normal_entries = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        if item.get("tipo") or item.get("evento"):
            continue

        motive = str(item.get("motivo") or "").strip()
        if motive:
            normal_entries.append((item, motive))

    normal_entries.sort(key=lambda pair: _history_sort_key(pair[0]))
    return "\n".join(motive for _, motive in normal_entries)


def _snapshot_family_key(ticket):
    family = ticket.familia_equipo
    return str(getattr(family, "key", "") or "").strip().upper() or None


def _snapshot_family_name(ticket):
    family = ticket.familia_equipo
    if not ticket.familia_equipo_id or not family:
        return LEGACY_UNCLASSIFIED_FAMILY
    return str(family.nombre or LEGACY_UNCLASSIFIED_FAMILY).strip()


def _failure_name(ticket):
    failure = ticket.falla_mantenimiento
    return str(failure.nombre).strip() if failure else PENDING_CAPTURE


def _condition_name(ticket):
    return str(ticket.condicion_operativa or PENDING_CAPTURE).strip()


def _equipment_name(ticket):
    inventory = ticket.inventario
    return str(getattr(inventory, "nombre", "") or "").strip()


def _equipment_code(ticket):
    inventory = ticket.inventario
    return str(getattr(inventory, "codigo_interno", "") or "").strip()


def _ticket_row(ticket):
    return (
        ticket.id,
        _equipment_name(ticket),
        _equipment_code(ticket),
        str(ticket.descripcion or "").strip(),
        str(ticket.estado or "").strip(),
        _format_created_at(ticket.fecha_creacion),
        _safe_branch_name(ticket),
        _snapshot_family_name(ticket),
        _failure_name(ticket),
        _condition_name(ticket),
        _format_commitment(ticket.fecha_solucion),
        plan_trabajo_desde_historial(ticket.historial_fechas),
    )


def _family_row(ticket):
    return (
        _safe_branch_name(ticket),
        ticket.id,
        _equipment_code(ticket),
        _failure_name(ticket),
        _condition_name(ticket),
        _format_commitment(ticket.fecha_solucion),
        plan_trabajo_desde_historial(ticket.historial_fechas),
    )


def _summary_rows(tickets):
    rows_by_branch = OrderedDict()
    for ticket in tickets:
        branch_name = _safe_branch_name(ticket)
        if branch_name not in rows_by_branch:
            rows_by_branch[branch_name] = {
                "total": 0,
                **{family_key: 0 for family_key, _ in SUMMARY_FAMILIES},
            }

        counts = rows_by_branch[branch_name]
        counts["total"] += 1
        family_key = _snapshot_family_key(ticket)
        if family_key in counts:
            counts[family_key] += 1

    rows = []
    for branch_name in sorted(rows_by_branch, key=str.casefold):
        counts = rows_by_branch[branch_name]
        rows.append(
            (
                branch_name,
                counts["total"],
                *(
                    counts[family_key]
                    for family_key, _ in SUMMARY_FAMILIES
                ),
            )
        )
    return rows


def _style_worksheet(worksheet, headers, widths):
    header_fill = PatternFill("solid", fgColor="E54525")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    worksheet.row_dimensions[1].height = 24

    for index, width in enumerate(widths, start=1):
        worksheet.column_dimensions[get_column_letter(index)].width = width

    for row in worksheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def construir_reporte_xlsx(tickets=None):
    tickets = list(tickets if tickets is not None else obtener_tickets_reporte())

    workbook = Workbook()
    tickets_sheet = workbook.active
    tickets_sheet.title = "Tickets"
    tickets_sheet.append(TICKETS_HEADERS)
    for ticket in tickets:
        tickets_sheet.append(_ticket_row(ticket))
    _style_worksheet(
        tickets_sheet,
        TICKETS_HEADERS,
        (11, 28, 18, 42, 16, 20, 22, 24, 30, 20, 18, 52),
    )

    summary_sheet = workbook.create_sheet("Fallas por familia")
    summary_headers = (
        "Sucursal",
        "Fallas",
        *(label for _, label in SUMMARY_FAMILIES),
    )
    summary_sheet.append(summary_headers)
    for row in _summary_rows(tickets):
        summary_sheet.append(row)
    _style_worksheet(
        summary_sheet,
        summary_headers,
        (24, 12, 14, 14, 14, 14, 14, 14, 16),
    )

    for family_key, sheet_name in FAMILY_SHEETS:
        worksheet = workbook.create_sheet(sheet_name)
        worksheet.append(FAMILY_HEADERS)
        for ticket in tickets:
            if _snapshot_family_key(ticket) == family_key:
                worksheet.append(_family_row(ticket))
        _style_worksheet(
            worksheet,
            FAMILY_HEADERS,
            (24, 11, 18, 32, 20, 18, 52),
        )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output
