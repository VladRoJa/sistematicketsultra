from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

from app.services.marketing_phone import normalize_phone
from app.services.marketing_sales_funnel_service import (
    ELIGIBLE_VISIT_DESCRIPTIONS,
    VALID_VENTA_TOTAL_STATUSES,
    _normalize_text,
    _parse_row_date,
)
from app.warehouse.services.socios_activos_parser import SociosActivosParseResult
from app.warehouse.services.venta_total_parser import VentaTotalParsedRow, VentaTotalParseResult


EXPORT_LAYOUT_VERSION = 2
HEADERS = ("Fecha", "Sucursal", "Descripcion", "Telefono", "IDSocio", "Fecha Vencimiento")
MEMBERSHIP_TYPES = frozenset({
    "CONTRATO",
    "MENSUAL SIN CONTRATO",
    "TRIMESTRAL SIN CONTRATO",
    "SEMESTRAL SIN CONTRATO",
    "ANUALIDAD SIN CONTRATO",
})


class IventasActivityExportError(RuntimeError):
    """A source cannot produce a reliable iVentas activity export."""


@dataclass(frozen=True, slots=True)
class Activity:
    day: date
    branch: str
    description: str
    phone: str
    member_id: int

    def values(self, expiry: date | None) -> tuple[str, str, str, str, int, str | None]:
        return (
            self.day.strftime("%d-%m-%y"), self.branch, self.description,
            self.phone, self.member_id, expiry.strftime("%d-%m-%y") if expiry is not None else None,
        )


def _member_id(value: str | None) -> int | None:
    match = re.fullmatch(r"([0-9]+)(?:\.0+)?", value or "")
    if match is None:
        return None
    member_id = int(match[1])
    return member_id if 0 < member_id < 10**15 else None


def _movement_key(row: VentaTotalParsedRow, member_id: int, is_pass: bool) -> str:
    product = row.descripcion if is_pass else (row.clave or row.clave_producto or row.descripcion)
    identity = (_normalize_text(row.sucursal), row.folio, member_id, is_pass, _normalize_text(product))
    return sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


def write_iventas_activity_xlsx(
    *,
    sales: VentaTotalParseResult,
    active_members: SociosActivosParseResult,
    sales_cutoff: date,
    active_cutoff: date,
    output_path: Path,
    exclude_passes_for_current_members: bool = False,
    known_movements: set[str] | None = None,
    baseline_only: bool = False,
    workbook_identifier: str | None = None,
) -> dict[str, int | list[str]]:
    if not {"IDSocio", "ID Socio"}.intersection(sales.header_columns):
        raise IventasActivityExportError("Venta Total no incluye la columna IDSocio.")
    if not {"Telefono", "Teléfono"}.intersection(sales.header_columns):
        raise IventasActivityExportError("Venta Total no incluye la columna Telefono.")

    expiry_by_member: dict[int, date] = {}
    active_memberships: set[int] = set()
    for row in active_members.rows:
        member_id = _member_id(row.id_socio)
        if member_id is None:
            continue
        expiry = row.fecha_vencimiento_date
        expiry_by_member[member_id] = max(expiry_by_member.get(member_id, expiry), expiry)
        tariff = _normalize_text(row.tarifa)
        if expiry >= active_cutoff and tariff and not tariff.startswith("PASE "):
            active_memberships.add(member_id)
    month_start = sales_cutoff.replace(day=1)
    activities: dict[Activity, bool] = {}
    movement_keys: dict[Activity, set[str]] = {}
    seen_movements = set(known_movements) if known_movements is not None else None
    missing_phone = missing_member_id = 0

    for row in sales.rows:
        if _normalize_text(row.estatus) not in VALID_VENTA_TOTAL_STATUSES:
            continue

        is_pass = _normalize_text(row.descripcion) in ELIGIBLE_VISIT_DESCRIPTIONS
        if is_pass:
            if _normalize_text(row.tipo) != "SIN COSTO" or row.total != 0:
                continue
        elif _normalize_text(row.nuevo) != "NUEVO" or _normalize_text(row.tipo) not in MEMBERSHIP_TYPES:
            continue

        try:
            day = _parse_row_date(row.fecha)
        except ValueError:
            raise IventasActivityExportError(
                f"Venta Total tiene una fecha inválida en la fila de datos {row.row_index + 1}."
            ) from None
        if not month_start <= day <= sales_cutoff:
            continue

        phone = normalize_phone(row.telefono)
        if phone is None:
            missing_phone += 1
            continue
        member_id = _member_id(row.id_socio)
        if member_id is None:
            missing_member_id += 1
            continue

        activity = Activity(day, row.sucursal, row.descripcion, phone, member_id)
        if seen_movements is not None:
            key = _movement_key(row, member_id, is_pass)
            if key in seen_movements:
                continue
            seen_movements.add(key)
            movement_keys.setdefault(activity, set()).add(key)
        activities[activity] = is_pass

    export_rows = []
    exported_movements: set[str] = set()
    passes = purchases = current_member_passes = excluded_passes = 0
    for activity in sorted(activities, key=lambda entry: (entry.member_id, entry.day)):
        if activities[activity]:
            if activity.member_id in active_memberships:
                current_member_passes += 1
                if exclude_passes_for_current_members:
                    excluded_passes += 1
                    continue
            passes += 1
        else:
            purchases += 1

        export_rows.append(activity.values(expiry_by_member.get(activity.member_id)))
        exported_movements.update(movement_keys.get(activity, ()))

    if not baseline_only and (known_movements is None or export_rows):
        workbook = Workbook(write_only=True)
        workbook.properties.identifier = workbook_identifier
        sheet = workbook.create_sheet("Hoja1")
        sheet.append(HEADERS)
        for *texts, member_id, expiry in export_rows:
            cells = [WriteOnlyCell(sheet, value=value) for value in texts]
            for cell in cells:
                cell.data_type = "s"
            sheet.append([*cells, member_id, expiry])
        workbook.save(output_path)

    result = {
        "rows": passes + purchases,
        "passes": passes,
        "new_sales": purchases,
        "passes_with_current_membership": current_member_passes,
        "passes_excluded": excluded_passes,
        "rows_without_valid_phone": missing_phone,
        "rows_without_valid_member_id": missing_member_id,
    }
    if known_movements is not None:
        result["movement_keys"] = sorted(exported_movements)
    return result
