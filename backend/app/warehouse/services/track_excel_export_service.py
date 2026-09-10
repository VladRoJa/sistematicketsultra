# backend\app\warehouse\services\track_excel_export_service.py


from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from io import BytesIO
from typing import Any, Sequence

from openpyxl.formatting.rule import CellIsRule
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.warehouse.services.track_bajas_forecast_service import (
    BAJAS_FORECAST_METHOD,
    build_bajas_historical_progress_curve,
)
from app.warehouse.services.track_forecast_service import (
    build_branch_income_projection_summary,
    load_first_store_income_dates_bulk,
)


MONTH_NAMES_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

TRACK_START_ROW = 4
TRACK_FIRST_COL = 2
TRACK_LAST_COL = 54

CURRENCY_FORMAT = '$#,##0.00;$#,##0.00;$0.00'
INTEGER_FORMAT = '#,##0;#,##0;0'
DECIMAL_FORMAT = '#,##0.00;#,##0.00;0.00'
OCCUPANCY_DECIMAL_FORMAT = '#,##0.00000;#,##0.00000;0.00000'
PERCENT_FORMAT = '0.0%;0.0%;0.0%'

ULTRA_ORANGE = "E54525"
ULTRA_BLUE = "2C4595"
ULTRA_CHARCOAL = "1F1F1F"
HEADER_DARK = "111827"

GOOD_FILL_COLOR = "D9F99D"
GOOD_FONT_COLOR = "166534"

WARN_FILL_COLOR = "FEF3C7"
WARN_FONT_COLOR = "92400E"

BAD_FILL_COLOR = "FECACA"
BAD_FONT_COLOR = "991B1B"

NEUTRAL_FILL_COLOR = "F3F4F6"
SEGMENT_BORDER_COLOR = "111827"


TRACK_GROUPS = [
    ("D2:J2", "Ocupación"),
    ("K2:Q2", "C r e c i m i e n t o"),
    ("R2:Y2", "I n g r e s o s    t o t a l e s"),
    ("Z2:AI2", "V e n t a s   n u e v a s     y     R e a c t i v a c i o n e s "),
    ("AJ2:AQ2", "B a j a s  & Churn"),
    ("AR2:AT2", "D o m i c i l i a d o s"),
    ("AU2:AX2", "A  R  P  U"),
    ("AY2:BB2", "Tienda"),
]

TRACK_BRANCH_ORDER = [
    "VILLAS_DEL_REY",
    "VILLA_VERDE",
    "INDEPENDENCIA",
    "TEC_MXL",
    "SEND_MXL",
    "SAN_LUIS",
    "PABELLON_RTO",
    "MISION_ENS",
    "PASEO_2000",
    "LOMA_BONITA",
    "SANTA_FE",
    "CARROUSEL_TJ",
    "PAPALOTE_TJ",
    "SEND_CUL",
    "SAN_ISIDRO_CUL",
    "AZAHARES_CUL",
    "STA_CATARINA",
    "SEND_SALTILLO",
    "SEND_CHIH",
    "PASEO_LA_PAZ",
    "IXTAPALUCA",
    "INSURGENTES",
    "TLALNEPANTLA",
    "SALTILLO_VILLALTA",
    "METEPEC",
    "SERRANIA",
]

TRACK_BASE_BRANCHES = set(TRACK_BRANCH_ORDER[:21])
TRACK_NEW_BRANCHES = set(TRACK_BRANCH_ORDER[21:])

TRACK_BRANCH_ORDER_INDEX = {
    branch: index
    for index, branch in enumerate(TRACK_BRANCH_ORDER)
}


BASE_HEADERS = {
    "B": "#",
    "C": "Sucursal",
    "D": "M2 sin  circulaciones",
    "E": "Ocupación 1 {month}",
    "F": "Meta Ocupación 2 px m2 ",
    "G": "Meta Ocupación {month}",
    "H": "Ocupación {day_month}",
    "I": "Dif Inicio de mes VS Día Actual",
    "J": "% Alcance meta Ocupación",
    "K": "Usuarios 1 {month}",
    "L": "Proyección Usuarios activos al cierre {month}",
    "M": "Usuarios activos al {day_month}",
    "N": "DIF INICIO MES",
    "O": "Dif meta  vs Real (##)",
    "P": "% Alcance meta crecimiento",
    "Q": "Alcance usuarios activos",
    "R": "Meta FAYCGO {month}",
    "S": " Ingreso ideal al CIERRE {day_month}",
    "T": " Ingreso Venta Total al {day_month}",
    "U": "Ingreso Real al dia anterior {month} agregadora",
    "V": "Ingreso Real total al {day} de {month}",
    "W": "% alcance de meta al {day_month}",
    "X": "Meta del día",
    "Y": "Dif $$ Real vs Meta",
    "Z": "Meta Clientes nuevos",
    "AA": "Alcance ideal clientes nuevos {day_month}",
    "AB": "Real Clientes nuevos {day_month}",
    "AC": "Diferencia Ideal VS  REAL ",
    "AD": "% alcance nuevos {day_month}",
    "AE": "Meta Reactiv",
    "AF": "Reactivaciones IDEALES AL {day_month}",
    "AG": "Real  Reactivaciones {day_month}",
    "AH": "Meta del día REACTIVACIONES ",
    "AI": "%  Alcance",
    "AJ": "Meta bajas",
    "AK": "Bajas Ideales {day_month}",
    "AL": "Bajas reales {day_month}",
    "AM": "Dif Ideal  VS Real",
    "AN": "Meta Churn",
    "AO": "Churn ideal {day_month}",
    "AP": "Churn real {day_month}",
    "AQ": "DIF CHURN IDEAL VS REAL",
    "AR": "Meta nuevos contratos domiciliados",
    "AS": "Nuevos contratos domiciliados {day_month}",
    "AT": "% alcance {day_month}",
    "AU": "Meta ARPU ",
    "AV": "Real ARPU {day_month}",
    "AW": "Dif $$ ARPU",
    "AX": "% Alcance ARPU",
    "AY": "Meta venta Tienda",
    "AZ": "Real {day_month}",
    "BA": "Diferencia $$",
    "BB": "% alcance real",
}

FORECAST_START_ROW = 4
FORECAST_LAST_COL = 69  # BQ
FORECAST_VISIBLE_COLUMNS = {
    "B", "C",
    "R", "V", "X", "Y",
    "AC", "AE", "AG", "AH",
    "AK", "AM", "AO", "AP",
    "AS", "AU", "AW", "AX", "AY",
    "BM", "BN", "BP", "BQ",
}
FORECAST_HELPER_COLUMNS = {"W", "AF", "AN", "AV", "BO"}
FORECAST_GROUPS = [
    ("R2:Y2", "I n g r e s o s   t o t a l e s", ULTRA_ORANGE),
    ("AC2:AH2", "V e n t a s   n u e v a s", ULTRA_ORANGE),
    ("AK2:AP2", "R e a c t i v a c i o n e s", ULTRA_BLUE),
    ("AS2:AY2", "B a j a s  & Churn", ULTRA_ORANGE),
    ("BM2:BQ2", "Tienda", ULTRA_ORANGE),
]
FORECAST_BRANCH_GROUPS = [
    [
        "VILLAS_DEL_REY",
        "VILLA_VERDE",
        "INDEPENDENCIA",
        "TEC_MXL",
        "SEND_MXL",
        "SAN_LUIS",
    ],
    [
        "PABELLON_RTO",
        "MISION_ENS",
        "PASEO_2000",
        "LOMA_BONITA",
        "SANTA_FE",
        "CARROUSEL_TJ",
        "PAPALOTE_TJ",
    ],
    [
        "SEND_CUL",
        "SAN_ISIDRO_CUL",
        "AZAHARES_CUL",
        "PASEO_LA_PAZ",
    ],
    [
        "STA_CATARINA",
        "SEND_SALTILLO",
        "SALTILLO_VILLALTA",
        "SERRANIA",
    ],
    [
        "SEND_CHIH",
        "IXTAPALUCA",
        "INSURGENTES",
        "TLALNEPANTLA",
        "METEPEC",
    ],
]
FORECAST_LEGACY_GROUP_COUNT = 4
FORECAST_SUM_COLUMNS = [
    "M",
    "R", "T", "U", "V", "W", "X", "Y",
    "AC", "AE", "AF", "AG", "AH",
    "AK", "AM", "AN", "AO", "AP",
    "AS", "AU", "AV", "AW", "AY",
    "BM", "BN", "BO", "BP", "BQ",
]


def build_track_daily_mart_excel(
    *,
    track_date: date,
    generation_mode: str,
    resolved_version: Any,
    rows: Sequence[Any],
) -> bytes:
    """Build an .xlsx export that mirrors the original Track 'Metas OP' columns."""

    workbook = Workbook()
    track_sheet = workbook.active
    track_sheet.title = "Metas OP"

    days_in_month = monthrange(track_date.year, track_date.month)[1]
    bajas_progress_curve = build_bajas_historical_progress_curve(
        target_month=track_date.replace(day=1),
    )

    _setup_track_sheet(
        worksheet=track_sheet,
        track_date=track_date,
        generation_mode=generation_mode,
        days_in_month=days_in_month,
        resolved_version=resolved_version,
    )

    ordered_rows = _sort_rows_by_track_order(rows)

    base_rows = [
        row
        for row in ordered_rows
        if _normalize_branch_key(getattr(row, "sucursal_canon", "")) in TRACK_BASE_BRANCHES
    ]

    new_rows = [
        row
        for row in ordered_rows
        if _normalize_branch_key(getattr(row, "sucursal_canon", "")) not in TRACK_BASE_BRANCHES
    ]

    current_row = TRACK_START_ROW
    current_index = 1

    base_start_row = current_row
    for row in base_rows:
        _write_track_data_row(
            worksheet=track_sheet,
            excel_row=current_row,
            index=current_index,
            mart_row=row,
            days_in_month=days_in_month,
        )
        current_row += 1
        current_index += 1

    base_end_row = current_row - 1

    new_start_row = current_row
    for row in new_rows:
        _write_track_data_row(
            worksheet=track_sheet,
            excel_row=current_row,
            index=current_index,
            mart_row=row,
            days_in_month=days_in_month,
        )
        current_row += 1
        current_index += 1

    new_end_row = current_row - 1

    base_totals_row = current_row
    _write_subtotal_row(
        worksheet=track_sheet,
        totals_row=base_totals_row,
        label=f"Subtotales {len(base_rows)} GYMS",
        first_data_row=base_start_row,
        last_data_row=base_end_row,
    )

    new_totals_row = current_row + 1
    _write_subtotal_row(
        worksheet=track_sheet,
        totals_row=new_totals_row,
        label="Subtotales Nuevos",
        first_data_row=new_start_row,
        last_data_row=new_end_row,
    )

    general_totals_row = current_row + 2
    _write_general_totals_row(
        worksheet=track_sheet,
        totals_row=general_totals_row,
        base_totals_row=base_totals_row,
        new_totals_row=new_totals_row,
    )

    _apply_track_sheet_formatting(
        worksheet=track_sheet,
        last_row=general_totals_row,
    )

    _build_forecast_sheet(
        workbook=workbook,
        track_date=track_date,
        resolved_version=resolved_version,
        rows=ordered_rows,
        bajas_progress_curve=bajas_progress_curve,
    )

    _build_raw_sheet(
        workbook=workbook,
        track_date=track_date,
        rows=ordered_rows,
    )
    _build_info_sheet(
        workbook=workbook,
        track_date=track_date,
        generation_mode=generation_mode,
        resolved_version=resolved_version,
        total_rows=len(ordered_rows),
        bajas_progress_curve=bajas_progress_curve,
    )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output.getvalue()


def _setup_track_sheet(
    *,
    worksheet: Worksheet,
    track_date: date,
    generation_mode: str,
    days_in_month: int,
    resolved_version: Any,
) -> None:
    month_label = MONTH_NAMES_ES[track_date.month]
    day_month_label = f"{track_date.day} {month_label}"

    worksheet.sheet_view.showGridLines = False
    worksheet.freeze_panes = "D4"

    worksheet["B1"] = "Track"
    worksheet["C1"] = "A dia"
    worksheet["D1"] = track_date.isoformat()

    worksheet.merge_cells("E1:J1")
    worksheet["E1"] = _format_version_update_label(resolved_version)

    worksheet["C2"] = track_date.day

    for merge_range, title in TRACK_GROUPS:
        worksheet.merge_cells(merge_range)
        first_cell = merge_range.split(":", 1)[0]
        worksheet[first_cell] = title

    for column_letter, header_template in BASE_HEADERS.items():
        worksheet[f"{column_letter}3"] = header_template.format(
            day=track_date.day,
            month=month_label,
            day_month=day_month_label,
        )


def _write_track_data_row(
    *,
    worksheet: Worksheet,
    excel_row: int,
    index: int,
    mart_row: Any,
    days_in_month: int,
) -> None:
    worksheet[f"B{excel_row}"] = index
    worksheet[f"C{excel_row}"] = _format_branch_label(
        getattr(mart_row, "sucursal_canon", "")
    )

    worksheet[f"D{excel_row}"] = _to_number(getattr(mart_row, "m2_sin_circulaciones", None))
    worksheet[f"E{excel_row}"] = f"=IFERROR(K{excel_row}/D{excel_row},0)"
    worksheet[f"F{excel_row}"] = f"=D{excel_row}*2"
    worksheet[f"G{excel_row}"] = f"=IFERROR(L{excel_row}/D{excel_row},0)"
    worksheet[f"H{excel_row}"] = f"=IFERROR(M{excel_row}/D{excel_row},0)"
    worksheet[f"I{excel_row}"] = f"=G{excel_row}-E{excel_row}"
    worksheet[f"J{excel_row}"] = f"=IFERROR(H{excel_row}/G{excel_row},0)"

    worksheet[f"K{excel_row}"] = _to_number(getattr(mart_row, "usuarios_inicio_mes", None))
    worksheet[f"L{excel_row}"] = _to_number(getattr(mart_row, "proyeccion_usuarios_cierre_mes", None))
    worksheet[f"M{excel_row}"] = _to_number(getattr(mart_row, "usuarios_activos_actual", None))
    worksheet[f"N{excel_row}"] = f"=M{excel_row}-K{excel_row}"
    worksheet[f"O{excel_row}"] = f"=M{excel_row}-L{excel_row}"
    worksheet[f"P{excel_row}"] = f"=IFERROR((M{excel_row}/L{excel_row})-1,0)"
    worksheet[f"Q{excel_row}"] = f"=IFERROR((M{excel_row}/K{excel_row})-1,0)"

    worksheet[f"R{excel_row}"] = _to_number(getattr(mart_row, "meta_faycgo_mes", None))
    worksheet[f"S{excel_row}"] = f"=(R{excel_row}/{days_in_month})*$C$2"
    worksheet[f"T{excel_row}"] = _to_number(getattr(mart_row, "ingreso_real_base_mtd", None))
    worksheet[f"U{excel_row}"] = _to_number(getattr(mart_row, "ingreso_real_agregadora_mtd", None))
    worksheet[f"V{excel_row}"] = f"=T{excel_row}+U{excel_row}"
    worksheet[f"W{excel_row}"] = f"=IFERROR(V{excel_row}/R{excel_row},0)"
    worksheet[f"X{excel_row}"] = f"=V{excel_row}-S{excel_row}"
    worksheet[f"Y{excel_row}"] = f"=V{excel_row}-R{excel_row}"

    worksheet[f"Z{excel_row}"] = _to_number(getattr(mart_row, "meta_clientes_nuevos_mes", None))
    worksheet[f"AA{excel_row}"] = f"=(Z{excel_row}/{days_in_month})*$C$2"
    worksheet[f"AB{excel_row}"] = _to_number(getattr(mart_row, "clientes_nuevos_real_mtd", None))
    worksheet[f"AC{excel_row}"] = f"=AB{excel_row}-AA{excel_row}"
    worksheet[f"AD{excel_row}"] = f"=IFERROR(AB{excel_row}/Z{excel_row},0)"

    worksheet[f"AE{excel_row}"] = _to_number(getattr(mart_row, "meta_reactivaciones_mes", None))
    worksheet[f"AF{excel_row}"] = f"=(AE{excel_row}/{days_in_month})*$C$2"
    worksheet[f"AG{excel_row}"] = _to_number(getattr(mart_row, "reactivaciones_real_mtd", None))
    worksheet[f"AH{excel_row}"] = f"=AF{excel_row}-AG{excel_row}"
    worksheet[f"AI{excel_row}"] = f"=IFERROR(AG{excel_row}/AE{excel_row},0)"

    worksheet[f"AJ{excel_row}"] = _to_number(getattr(mart_row, "meta_bajas_mes", None))
    worksheet[f"AK{excel_row}"] = f"=(AJ{excel_row}/{days_in_month})*$C$2"
    worksheet[f"AL{excel_row}"] = _to_number(getattr(mart_row, "bajas_reales_mtd", None))
    worksheet[f"AM{excel_row}"] = f"=AL{excel_row}-AK{excel_row}"
    worksheet[f"AN{excel_row}"] = f"=IFERROR(AJ{excel_row}/L{excel_row},0)"
    worksheet[f"AO{excel_row}"] = f"=(AN{excel_row}/{days_in_month})*$C$2"
    worksheet[f"AP{excel_row}"] = f"=IFERROR(AL{excel_row}/M{excel_row},0)"
    worksheet[f"AQ{excel_row}"] = f"=AP{excel_row}-AO{excel_row}"

    worksheet[f"AR{excel_row}"] = _to_number(getattr(mart_row, "meta_nuevos_domiciliados_mes", None))
    worksheet[f"AS{excel_row}"] = _to_number(getattr(mart_row, "nuevos_domiciliados_real_mtd", None))
    worksheet[f"AT{excel_row}"] = f"=IFERROR(AS{excel_row}/AR{excel_row},0)"

    worksheet[f"AU{excel_row}"] = _to_number(getattr(mart_row, "meta_arpu_mes", None))
    worksheet[f"AV{excel_row}"] = f"=IFERROR(V{excel_row}/M{excel_row},0)"
    worksheet[f"AW{excel_row}"] = f"=AV{excel_row}-AU{excel_row}"
    worksheet[f"AX{excel_row}"] = f"=IFERROR(AV{excel_row}/AU{excel_row},0)"

    worksheet[f"AY{excel_row}"] = _to_number(getattr(mart_row, "meta_venta_tienda_mes", None))
    worksheet[f"AZ{excel_row}"] = _to_number(getattr(mart_row, "venta_tienda_real_mtd", None))
    worksheet[f"BA{excel_row}"] = f"=AY{excel_row}-AZ{excel_row}"
    worksheet[f"BB{excel_row}"] = f"=IFERROR(AZ{excel_row}/AY{excel_row},0)"


def _write_subtotal_row(
    *,
    worksheet: Worksheet,
    totals_row: int,
    label: str,
    first_data_row: int,
    last_data_row: int,
) -> None:
    worksheet[f"C{totals_row}"] = label

    if last_data_row < first_data_row:
        for column_letter in range(TRACK_FIRST_COL, TRACK_LAST_COL + 1):
            worksheet.cell(row=totals_row, column=column_letter).value = None
        worksheet[f"C{totals_row}"] = label
        return

    sum_columns = [
        "D", "K", "L", "M", "N", "O", "R", "S", "T", "U", "V", "X", "Y",
        "Z", "AA", "AB", "AC", "AE", "AF", "AG", "AH", "AJ", "AK", "AL", "AM",
        "AR", "AS", "AY", "AZ", "BA",
    ]

    for column_letter in sum_columns:
        worksheet[f"{column_letter}{totals_row}"] = (
            f"=SUM({column_letter}{first_data_row}:{column_letter}{last_data_row})"
        )

    worksheet[f"E{totals_row}"] = f"=IFERROR(K{totals_row}/D{totals_row},0)"
    worksheet[f"F{totals_row}"] = f"=D{totals_row}*2"
    worksheet[f"G{totals_row}"] = f"=IFERROR(L{totals_row}/D{totals_row},0)"
    worksheet[f"H{totals_row}"] = f"=IFERROR(M{totals_row}/D{totals_row},0)"
    worksheet[f"I{totals_row}"] = f"=AVERAGE(I{first_data_row}:I{last_data_row})"
    worksheet[f"J{totals_row}"] = f"=AVERAGE(J{first_data_row}:J{last_data_row})"
    worksheet[f"P{totals_row}"] = f"=IFERROR((M{totals_row}/L{totals_row})-1,0)"
    worksheet[f"Q{totals_row}"] = f"=IFERROR(M{totals_row}/K{totals_row}-1,0)"
    worksheet[f"W{totals_row}"] = f"=IFERROR(V{totals_row}/R{totals_row},0)"
    worksheet[f"AD{totals_row}"] = f"=IFERROR(AB{totals_row}/Z{totals_row},0)"
    worksheet[f"AI{totals_row}"] = f"=IFERROR(AG{totals_row}/AE{totals_row},0)"
    worksheet[f"AN{totals_row}"] = f"=IFERROR(AJ{totals_row}/L{totals_row},0)"
    worksheet[f"AO{totals_row}"] = f"=AVERAGE(AO{first_data_row}:AO{last_data_row})"
    worksheet[f"AP{totals_row}"] = f"=IFERROR(AL{totals_row}/M{totals_row},0)"
    worksheet[f"AQ{totals_row}"] = f"=AP{totals_row}-AO{totals_row}"
    worksheet[f"AT{totals_row}"] = f"=IFERROR(AS{totals_row}/AR{totals_row},0)"
    worksheet[f"AU{totals_row}"] = f"=AVERAGE(AU{first_data_row}:AU{last_data_row})"
    worksheet[f"AV{totals_row}"] = f"=IFERROR(V{totals_row}/M{totals_row},0)"
    worksheet[f"AW{totals_row}"] = f"=AV{totals_row}-AU{totals_row}"
    worksheet[f"AX{totals_row}"] = f"=IFERROR(AV{totals_row}/AU{totals_row},0)"
    worksheet[f"BB{totals_row}"] = f"=IFERROR(AZ{totals_row}/AY{totals_row},0)"


def _write_general_totals_row(
    *,
    worksheet: Worksheet,
    totals_row: int,
    base_totals_row: int,
    new_totals_row: int,
) -> None:
    worksheet[f"C{totals_row}"] = "TOTAL GENERAL"

    sum_columns = [
        "D", "F", "K", "L", "M", "N", "O", "R", "S", "T", "U", "V", "X", "Y",
        "Z", "AA", "AB", "AC", "AE", "AF", "AG", "AH", "AJ", "AK", "AL", "AM",
        "AR", "AS", "AY", "AZ", "BA",
    ]

    for column_letter in sum_columns:
        worksheet[f"{column_letter}{totals_row}"] = (
            f"={column_letter}{base_totals_row}+{column_letter}{new_totals_row}"
        )

    worksheet[f"E{totals_row}"] = f"=IFERROR(K{totals_row}/D{totals_row},0)"
    worksheet[f"G{totals_row}"] = f"=IFERROR(L{totals_row}/D{totals_row},0)"
    worksheet[f"H{totals_row}"] = f"=IFERROR(M{totals_row}/D{totals_row},0)"
    worksheet[f"I{totals_row}"] = f"=AVERAGE(I{base_totals_row}:I{new_totals_row})"
    worksheet[f"J{totals_row}"] = f"=AVERAGE(J{base_totals_row}:J{new_totals_row})"
    worksheet[f"P{totals_row}"] = f"=IFERROR((M{totals_row}/L{totals_row})-1,0)"
    worksheet[f"Q{totals_row}"] = f"=IFERROR(M{totals_row}/K{totals_row}-1,0)"
    worksheet[f"W{totals_row}"] = f"=IFERROR(V{totals_row}/R{totals_row},0)"
    worksheet[f"AD{totals_row}"] = f"=IFERROR(AB{totals_row}/Z{totals_row},0)"
    worksheet[f"AI{totals_row}"] = f"=IFERROR(AG{totals_row}/AE{totals_row},0)"
    worksheet[f"AN{totals_row}"] = f"=IFERROR(AJ{totals_row}/L{totals_row},0)"
    worksheet[f"AO{totals_row}"] = f"=AVERAGE(AO{base_totals_row}:AO{new_totals_row})"
    worksheet[f"AP{totals_row}"] = f"=IFERROR(AL{totals_row}/M{totals_row},0)"
    worksheet[f"AQ{totals_row}"] = f"=AP{totals_row}-AO{totals_row}"
    worksheet[f"AT{totals_row}"] = f"=IFERROR(AS{totals_row}/AR{totals_row},0)"
    worksheet[f"AU{totals_row}"] = f"=AVERAGE(AU{base_totals_row}:AU{new_totals_row})"
    worksheet[f"AV{totals_row}"] = f"=IFERROR(V{totals_row}/M{totals_row},0)"
    worksheet[f"AW{totals_row}"] = f"=AV{totals_row}-AU{totals_row}"
    worksheet[f"AX{totals_row}"] = f"=IFERROR(AV{totals_row}/AU{totals_row},0)"
    worksheet[f"BB{totals_row}"] = f"=IFERROR(AZ{totals_row}/AY{totals_row},0)"


def _apply_track_sheet_formatting(*, worksheet: Worksheet, last_row: int) -> None:
    black_fill = PatternFill("solid", fgColor="1F1F1F")
    red_fill = PatternFill("solid", fgColor="E54525")
    subtotal_fill = PatternFill("solid", fgColor="FBE3DC")
    white_font = Font(color="FFFFFF", bold=True)
    title_font = Font(color="E54525", bold=True, size=12)
    header_font = Font(color="FFFFFF", bold=True, size=9)
    body_font = Font(color="0F1F3A", size=9)
    thin_side = Side(style="thin", color="D9D9D9")
    border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    worksheet["B1"].font = title_font
    worksheet.column_dimensions["A"].hidden = True
    worksheet["C1"].font = Font(bold=True)
    worksheet["D1"].font = Font(bold=True)
    worksheet["E1"].font = Font(color="E54525", bold=True)
    worksheet["E1"].alignment = Alignment(horizontal="left", vertical="center")

    for merge_range, _title in TRACK_GROUPS:
        first_cell = merge_range.split(":", 1)[0]
        cell = worksheet[first_cell]
        cell.fill = red_fill
        cell.font = white_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for col_idx in range(TRACK_FIRST_COL, TRACK_LAST_COL + 1):
        cell = worksheet.cell(row=3, column=col_idx)
        cell.fill = black_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    for row_idx in range(TRACK_START_ROW, last_row + 1):
        for col_idx in range(TRACK_FIRST_COL, TRACK_LAST_COL + 1):
            cell = worksheet.cell(row=row_idx, column=col_idx)
            cell.font = body_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border

    _apply_zebra_rows(
        worksheet=worksheet,
        last_row=last_row,
    )

    _apply_summary_row_formatting(
        worksheet=worksheet,
        last_row=last_row,
    )

    for row_idx in range(TRACK_START_ROW, last_row + 1):
        worksheet[f"C{row_idx}"].font = Font(color="0F1F3A", bold=True, size=9)
        worksheet[f"C{row_idx}"].alignment = Alignment(horizontal="left", vertical="center")

    _set_number_format(
        worksheet=worksheet,
        column_letters=["R", "S", "T", "U", "V", "X", "Y", "AU", "AV", "AW", "AY", "AZ", "BA"],
        start_row=TRACK_START_ROW,
        end_row=last_row,
        number_format=CURRENCY_FORMAT,
    )
    _set_number_format(
        worksheet=worksheet,
        column_letters=["B", "K", "L", "M", "N", "O", "Z", "AA", "AB", "AC", "AE", "AF", "AG", "AH", "AJ", "AK", "AL", "AM", "AR", "AS"],
        start_row=TRACK_START_ROW,
        end_row=last_row,
        number_format=INTEGER_FORMAT,
    )
    _set_number_format(
        worksheet=worksheet,
        column_letters=["D", "F"],
        start_row=TRACK_START_ROW,
        end_row=last_row,
        number_format=DECIMAL_FORMAT,
    )
    _set_number_format(
        worksheet=worksheet,
        column_letters=["E", "G", "H", "I"],
        start_row=TRACK_START_ROW,
        end_row=last_row,
        number_format=OCCUPANCY_DECIMAL_FORMAT,
    )

    _set_number_format(
        worksheet=worksheet,
        column_letters=["J", "P", "Q", "W", "AD", "AI", "AN", "AO", "AP", "AQ", "AT", "AX", "BB"],
        start_row=TRACK_START_ROW,
        end_row=last_row,
        number_format=PERCENT_FORMAT,
    )

    widths = {
        "B": 6,
        "C": 24,
        "D": 14,
        "E": 14,
        "F": 16,
        "G": 14,
        "H": 14,
        "I": 18,
        "J": 16,
        "K": 14,
        "L": 18,
        "M": 16,
        "R": 16,
        "S": 18,
        "T": 18,
        "U": 20,
        "V": 18,
        "X": 16,
        "Y": 18,
    }

    for col_idx in range(TRACK_FIRST_COL, TRACK_LAST_COL + 1):
        column_letter = get_column_letter(col_idx)
        worksheet.column_dimensions[column_letter].width = widths.get(column_letter, 14)

    worksheet.row_dimensions[2].height = 24
    worksheet.row_dimensions[3].height = 48

    for row_idx in range(TRACK_START_ROW, last_row + 1):
        worksheet.row_dimensions[row_idx].height = 22

    _apply_track_segment_formatting(
        worksheet=worksheet,
        last_row=last_row,
    )

    _apply_track_conditional_formatting(
        worksheet=worksheet,
        last_row=last_row,
    )

    worksheet.auto_filter.ref = f"B3:BB{last_row}"


def _apply_zebra_rows(
    *,
    worksheet: Worksheet,
    last_row: int,
) -> None:
    zebra_fill = PatternFill("solid", fgColor="F9FAFB")
    white_fill = PatternFill("solid", fgColor="FFFFFF")

    data_row_counter = 0

    for row_idx in range(TRACK_START_ROW, last_row + 1):
        label = str(worksheet[f"C{row_idx}"].value or "").strip().upper()

        if label.startswith("SUBTOTALES") or label == "TOTAL GENERAL":
            continue

        row_fill = zebra_fill if data_row_counter % 2 else white_fill

        for col_idx in range(TRACK_FIRST_COL, TRACK_LAST_COL + 1):
            worksheet.cell(row=row_idx, column=col_idx).fill = row_fill

        data_row_counter += 1


def _apply_summary_row_formatting(
    *,
    worksheet: Worksheet,
    last_row: int,
) -> None:
    subtotal_fill = PatternFill("solid", fgColor="E5E7EB")
    total_fill = PatternFill("solid", fgColor="FBE3DC")
    subtotal_font = Font(color="0F1F3A", bold=True, size=9)
    total_font = Font(color="0F1F3A", bold=True, size=9)

    for row_idx in range(TRACK_START_ROW, last_row + 1):
        label = str(worksheet[f"C{row_idx}"].value or "").strip().upper()

        if label.startswith("SUBTOTALES"):
            row_fill = subtotal_fill
            row_font = subtotal_font
        elif label == "TOTAL GENERAL":
            row_fill = total_fill
            row_font = total_font
        else:
            continue

        for col_idx in range(TRACK_FIRST_COL, TRACK_LAST_COL + 1):
            cell = worksheet.cell(row=row_idx, column=col_idx)
            cell.fill = row_fill
            cell.font = row_font


def _apply_track_segment_formatting(
    *,
    worksheet: Worksheet,
    last_row: int,
) -> None:
    segment_title_fills = {
        "D": ULTRA_ORANGE,
        "K": ULTRA_BLUE,
        "R": ULTRA_ORANGE,
        "Z": ULTRA_BLUE,
        "AJ": ULTRA_CHARCOAL,
        "AR": ULTRA_BLUE,
        "AU": ULTRA_CHARCOAL,
        "AY": ULTRA_ORANGE,
    }

    segment_ranges = [
        ("D", "J", "Ocupación"),
        ("K", "Q", "Crecimiento"),
        ("R", "Y", "Ingresos totales"),
        ("Z", "AI", "Ventas nuevas y Reactivaciones"),
        ("AJ", "AQ", "Bajas & Churn"),
        ("AR", "AT", "Domiciliados"),
        ("AU", "AX", "ARPU"),
        ("AY", "BB", "Tienda"),
    ]

    header_fill = PatternFill("solid", fgColor=HEADER_DARK)
    header_font = Font(color="FFFFFF", bold=True, size=8)
    segment_side = Side(style="medium", color=SEGMENT_BORDER_COLOR)

    for start_col, end_col, _title in segment_ranges:
        start_idx = _column_letter_to_index(start_col)
        end_idx = _column_letter_to_index(end_col)

        for col_idx in range(start_idx, end_idx + 1):
            header_cell = worksheet.cell(row=3, column=col_idx)
            header_cell.fill = header_fill
            header_cell.font = header_font
            header_cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

        title_cell = worksheet[f"{start_col}2"]
        title_cell.fill = PatternFill(
            "solid",
            fgColor=segment_title_fills.get(start_col, ULTRA_CHARCOAL),
        )
        title_cell.font = Font(color="FFFFFF", bold=True, size=9)
        title_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

        for row_idx in range(3, last_row + 1):
            left_cell = worksheet[f"{start_col}{row_idx}"]
            right_cell = worksheet[f"{end_col}{row_idx}"]

            left_cell.border = _with_border_side(
                left_cell.border,
                left=segment_side,
            )
            right_cell.border = _with_border_side(
                right_cell.border,
                right=segment_side,
            )

    highlighted_header_columns = {
        "X": ULTRA_ORANGE,
        "Y": ULTRA_ORANGE,
        "AH": "00C853",
        "AM": ULTRA_ORANGE,
        "AQ": ULTRA_ORANGE,
        "AT": ULTRA_BLUE,
        "AW": ULTRA_ORANGE,
        "BA": ULTRA_ORANGE,
        "BB": ULTRA_BLUE,
    }

    for column_letter, color in highlighted_header_columns.items():
        cell = worksheet[f"{column_letter}3"]
        cell.fill = PatternFill("solid", fgColor=color)
        cell.font = Font(color="FFFFFF", bold=True, size=8)


def _apply_track_conditional_formatting(
    *,
    worksheet: Worksheet,
    last_row: int,
) -> None:
    if last_row < TRACK_START_ROW:
        return

    good_fill = PatternFill("solid", fgColor=GOOD_FILL_COLOR)
    warn_fill = PatternFill("solid", fgColor=WARN_FILL_COLOR)
    bad_fill = PatternFill("solid", fgColor=BAD_FILL_COLOR)

    good_font = Font(color=GOOD_FONT_COLOR, bold=True)
    warn_font = Font(color=WARN_FONT_COLOR, bold=True)
    bad_font = Font(color=BAD_FONT_COLOR, bold=True)

    positive_is_good_columns = [
        "N",   # DIF INICIO MES
        "O",   # Dif meta vs Real
        "P",   # % Alcance meta crecimiento
        "Q",   # Alcance usuarios activos
        "X",   # Meta del día ingresos
        "Y",   # Dif $$ Real vs Meta
        "AC",  # Diferencia clientes nuevos
        "AW",  # Dif $$ ARPU
    ]

    positive_is_bad_columns = [
        "AH",  # Meta del día reactivaciones, positivo = falta
        "AM",  # Bajas sobre ideal, positivo = mal
        "AQ",  # Churn sobre ideal, positivo = mal
        "BA",  # Diferencia tienda, positivo = falta
    ]

    percent_goal_columns = [
        "J",   # % Alcance meta Ocupación
        "W",   # % alcance ingreso
        "AD",  # % alcance nuevos
        "AI",  # % alcance reactivaciones
        "AT",  # % alcance domiciliados
        "AX",  # % alcance ARPU
        "BB",  # % alcance tienda
    ]

    for column_letter in positive_is_good_columns:
        cell_range = f"{column_letter}{TRACK_START_ROW}:{column_letter}{last_row}"
        worksheet.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator="greaterThan",
                formula=["0"],
                fill=good_fill,
                font=good_font,
            ),
        )
        worksheet.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator="lessThan",
                formula=["0"],
                fill=bad_fill,
                font=bad_font,
            ),
        )

    for column_letter in positive_is_bad_columns:
        cell_range = f"{column_letter}{TRACK_START_ROW}:{column_letter}{last_row}"
        worksheet.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator="greaterThan",
                formula=["0"],
                fill=bad_fill,
                font=bad_font,
            ),
        )
        worksheet.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator="lessThan",
                formula=["0"],
                fill=good_fill,
                font=good_font,
            ),
        )

    for column_letter in percent_goal_columns:
        cell_range = f"{column_letter}{TRACK_START_ROW}:{column_letter}{last_row}"

        worksheet.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator="greaterThanOrEqual",
                formula=["1"],
                fill=good_fill,
                font=good_font,
            ),
        )
        worksheet.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator="between",
                formula=["0.8", "0.999999"],
                fill=warn_fill,
                font=warn_font,
            ),
        )
        worksheet.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator="lessThan",
                formula=["0.8"],
                fill=bad_fill,
                font=bad_font,
            ),
        )


def _with_border_side(
    border: Border,
    *,
    left: Side | None = None,
    right: Side | None = None,
    top: Side | None = None,
    bottom: Side | None = None,
) -> Border:
    return Border(
        left=left or border.left,
        right=right or border.right,
        top=top or border.top,
        bottom=bottom or border.bottom,
    )


def _column_letter_to_index(column_letter: str) -> int:
    result = 0

    for character in column_letter:
        result = result * 26 + ord(character.upper()) - ord("A") + 1

    return result


def _set_number_format(
    *,
    worksheet: Worksheet,
    column_letters: Sequence[str],
    start_row: int,
    end_row: int,
    number_format: str,
) -> None:
    for column_letter in column_letters:
        for row_idx in range(start_row, end_row + 1):
            worksheet[f"{column_letter}{row_idx}"].number_format = number_format


def _build_forecast_sheet(
    *,
    workbook: Workbook,
    track_date: date,
    resolved_version: Any,
    rows: Sequence[Any],
    bajas_progress_curve: dict[str, Any],
) -> None:
    worksheet = workbook.create_sheet("Forecast", 0)
    days_in_month = monthrange(track_date.year, track_date.month)[1]
    month_label = MONTH_NAMES_ES[track_date.month]
    day_month_label = f"{track_date.day} {month_label}"

    _setup_forecast_sheet(
        worksheet=worksheet,
        track_date=track_date,
        resolved_version=resolved_version,
        month_label=month_label,
        day_month_label=day_month_label,
    )

    grouped_rows = _build_forecast_row_groups(rows)
    current_row = FORECAST_START_ROW
    current_index = 1
    regional_subtotal_rows: list[int] = []

    for group_rows in grouped_rows:
        first_data_row = current_row

        for mart_row in group_rows:
            _write_forecast_data_row(
                worksheet=worksheet,
                excel_row=current_row,
                index=current_index,
                mart_row=mart_row,
                track_date=track_date,
                days_in_month=days_in_month,
                bajas_progress_curve=bajas_progress_curve,
            )
            current_row += 1
            current_index += 1

        last_data_row = current_row - 1
        subtotal_row = current_row
        _write_forecast_subtotal_row(
            worksheet=worksheet,
            totals_row=subtotal_row,
            first_data_row=first_data_row,
            last_data_row=last_data_row,
        )
        regional_subtotal_rows.append(subtotal_row)

        current_row += 2  # subtotal + blank separator, as in the source report

    base_totals_row = current_row
    _write_forecast_summary_row(
        worksheet=worksheet,
        totals_row=base_totals_row,
        label="Subtotales 21 GYMS",
        source_rows=regional_subtotal_rows[:FORECAST_LEGACY_GROUP_COUNT],
    )

    new_totals_row = current_row + 1
    _write_forecast_summary_row(
        worksheet=worksheet,
        totals_row=new_totals_row,
        label="Subtotales Nuevos",
        source_rows=regional_subtotal_rows[FORECAST_LEGACY_GROUP_COUNT:],
    )

    general_totals_row = current_row + 2
    _write_forecast_summary_row(
        worksheet=worksheet,
        totals_row=general_totals_row,
        label="TOTAL GENERAL",
        source_rows=[base_totals_row, new_totals_row],
    )

    _apply_forecast_formatting(
        worksheet=worksheet,
        last_row=general_totals_row,
        regional_subtotal_rows=regional_subtotal_rows,
        summary_rows=[base_totals_row, new_totals_row, general_totals_row],
    )


def _setup_forecast_sheet(
    *,
    worksheet: Worksheet,
    track_date: date,
    resolved_version: Any,
    month_label: str,
    day_month_label: str,
) -> None:
    worksheet.sheet_view.showGridLines = False
    worksheet.sheet_view.zoomScale = 75
    worksheet.freeze_panes = "D4"

    # Forecast keeps only its operational columns visible, so the Track status
    # ribbon is distributed across those same visible columns.
    worksheet["B1"] = "Track"
    worksheet["C1"] = "A dia"
    worksheet["R1"] = track_date.isoformat()
    worksheet["V1"] = _format_version_update_label(resolved_version)

    for merge_range, title, _color in FORECAST_GROUPS:
        worksheet.merge_cells(merge_range)
        worksheet[merge_range.split(":", 1)[0]] = title

    headers = {
        "B": "#",
        "C": "Sucursal",
        "M": f"Usuarios activos al {day_month_label}",
        "R": f"Meta FAYCGO {month_label}",
        "T": "Ingreso base MTD",
        "U": "Ingreso agregadoras MTD",
        "V": f"Ingreso Real total al {track_date.day} de {month_label}",
        "W": "Pronóstico restante",
        "X": "Pronóstico de cierre",
        "Y": "Dif $$ Real vs Pronóstico",
        "AC": "Meta Clientes nuevos",
        "AE": f"Real Clientes nuevos {day_month_label}",
        "AF": "Pronóstico restante",
        "AG": "Pronóstico de cierre",
        "AH": "Dif ## Real vs Pronóstico",
        "AK": "Meta Reactiv",
        "AM": f"Real Reactivaciones {day_month_label}",
        "AN": "Pronóstico restante",
        "AO": "Pronóstico de cierre",
        "AP": "Dif ## Real vs Pronóstico",
        "AS": "Meta bajas",
        "AU": f"Bajas reales {day_month_label}",
        "AV": "Pronóstico restante histórico",
        "AW": "Pronóstico de cierre #",
        "AX": "Pronóstico de cierre %",
        "AY": "Dif ## Real vs Pronóstico",
        "BM": "Meta venta Tienda",
        "BN": f"Real {day_month_label}",
        "BO": "Pronóstico restante",
        "BP": "Pronóstico de cierre",
        "BQ": "Dif ## Real vs Pronóstico",
    }
    for column_letter, header in headers.items():
        worksheet[f"{column_letter}3"] = header


def _build_forecast_row_groups(rows: Sequence[Any]) -> list[list[Any]]:
    rows_by_key = {
        _normalize_branch_key(getattr(row, "sucursal_canon", "")): row
        for row in rows
    }

    groups: list[list[Any]] = []
    consumed: set[str] = set()

    for branch_keys in FORECAST_BRANCH_GROUPS:
        group_rows: list[Any] = []
        for branch_key in branch_keys:
            row = rows_by_key.get(branch_key)
            if row is None:
                continue
            group_rows.append(row)
            consumed.add(branch_key)
        groups.append(group_rows)

    extras = [
        row
        for row in _sort_rows_by_track_order(rows)
        if _normalize_branch_key(getattr(row, "sucursal_canon", "")) not in consumed
    ]
    groups[-1].extend(extras)

    return groups


def _write_forecast_data_row(
    *,
    worksheet: Worksheet,
    excel_row: int,
    index: int,
    mart_row: Any,
    track_date: date,
    days_in_month: int,
    bajas_progress_curve: dict[str, Any],
) -> None:
    ingreso_day = _forecast_source_day(
        mart_row,
        "source_business_date_ingresos",
        track_date,
    )
    agregadoras_day = _forecast_source_day(
        mart_row,
        "source_business_date_agregadoras",
        track_date,
    )
    nuevos_day = _forecast_source_day(
        mart_row,
        "source_business_date_nuevos",
        track_date,
    )
    desempeno_day = _forecast_source_day(
        mart_row,
        "source_business_date_desempeno",
        track_date,
    )
    tienda_day = _forecast_source_day(
        mart_row,
        "source_business_date_tienda",
        track_date,
    )

    bajas_progress_point = bajas_progress_curve.get("points", {}).get(
        desempeno_day
    )
    bajas_progress_reference = (
        f"Info!$G${17 + desempeno_day}"
        if bajas_progress_point is not None
        else None
    )

    worksheet[f"B{excel_row}"] = index
    worksheet[f"C{excel_row}"] = _format_branch_label(
        getattr(mart_row, "sucursal_canon", "")
    )

    worksheet[f"M{excel_row}"] = _to_number(
        getattr(mart_row, "usuarios_activos_actual", None)
    )

    worksheet[f"R{excel_row}"] = _to_number(
        getattr(mart_row, "meta_faycgo_mes", None)
    )
    worksheet[f"T{excel_row}"] = _to_number(
        getattr(mart_row, "ingreso_real_base_mtd", None)
    )
    worksheet[f"U{excel_row}"] = _to_number(
        getattr(mart_row, "ingreso_real_agregadora_mtd", None)
    )
    worksheet[f"V{excel_row}"] = f"=T{excel_row}+U{excel_row}"
    worksheet[f"W{excel_row}"] = _forecast_income_remaining_formula(
        excel_row=excel_row,
        ingreso_day=ingreso_day,
        agregadoras_day=agregadoras_day,
        days_in_month=days_in_month,
    )
    worksheet[f"X{excel_row}"] = f"=V{excel_row}+W{excel_row}"
    worksheet[f"Y{excel_row}"] = f"=X{excel_row}-R{excel_row}"

    worksheet[f"AC{excel_row}"] = _to_number(
        getattr(mart_row, "meta_clientes_nuevos_mes", None)
    )
    worksheet[f"AE{excel_row}"] = _to_number(
        getattr(mart_row, "clientes_nuevos_real_mtd", None)
    )
    worksheet[f"AF{excel_row}"] = _forecast_remaining_formula(
        value_column="AE",
        excel_row=excel_row,
        cutoff_day=nuevos_day,
        days_in_month=days_in_month,
    )
    worksheet[f"AG{excel_row}"] = f"=AE{excel_row}+AF{excel_row}"
    worksheet[f"AH{excel_row}"] = f"=AG{excel_row}-AC{excel_row}"

    worksheet[f"AK{excel_row}"] = _to_number(
        getattr(mart_row, "meta_reactivaciones_mes", None)
    )
    worksheet[f"AM{excel_row}"] = _to_number(
        getattr(mart_row, "reactivaciones_real_mtd", None)
    )
    worksheet[f"AN{excel_row}"] = _forecast_remaining_formula(
        value_column="AM",
        excel_row=excel_row,
        cutoff_day=desempeno_day,
        days_in_month=days_in_month,
    )
    worksheet[f"AO{excel_row}"] = f"=AM{excel_row}+AN{excel_row}"
    worksheet[f"AP{excel_row}"] = f"=AO{excel_row}-AK{excel_row}"

    worksheet[f"AS{excel_row}"] = _to_number(
        getattr(mart_row, "meta_bajas_mes", None)
    )
    worksheet[f"AU{excel_row}"] = _to_number(
        getattr(mart_row, "bajas_reales_mtd", None)
    )
    worksheet[f"AV{excel_row}"] = _forecast_bajas_remaining_formula(
        value_column="AU",
        excel_row=excel_row,
        progress_reference=bajas_progress_reference,
    )
    worksheet[f"AW{excel_row}"] = f"=AU{excel_row}+AV{excel_row}"
    worksheet[f"AX{excel_row}"] = f"=IFERROR(AW{excel_row}/M{excel_row},0)"
    worksheet[f"AY{excel_row}"] = f"=AS{excel_row}-AW{excel_row}"

    worksheet[f"BM{excel_row}"] = _to_number(
        getattr(mart_row, "meta_venta_tienda_mes", None)
    )
    worksheet[f"BN{excel_row}"] = _to_number(
        getattr(mart_row, "venta_tienda_real_mtd", None)
    )
    worksheet[f"BO{excel_row}"] = _forecast_remaining_formula(
        value_column="BN",
        excel_row=excel_row,
        cutoff_day=tienda_day,
        days_in_month=days_in_month,
    )
    worksheet[f"BP{excel_row}"] = f"=BN{excel_row}+BO{excel_row}"
    worksheet[f"BQ{excel_row}"] = f"=BP{excel_row}-BM{excel_row}"


def _forecast_source_day(
    mart_row: Any,
    attribute_name: str,
    track_date: date,
) -> int:
    value = getattr(mart_row, attribute_name, None)
    if isinstance(value, datetime):
        value = value.date()

    if (
        isinstance(value, date)
        and value.year == track_date.year
        and value.month == track_date.month
    ):
        return max(1, min(value.day, track_date.day))

    return max(1, track_date.day)


def _forecast_remaining_formula(
    *,
    value_column: str,
    excel_row: int,
    cutoff_day: int,
    days_in_month: int,
) -> str:
    remaining_days = max(days_in_month - cutoff_day, 0)
    if remaining_days == 0:
        return "=0"

    return (
        f"=IFERROR(({value_column}{excel_row}/{cutoff_day})*"
        f"{remaining_days},0)"
    )


def _forecast_bajas_remaining_formula(
    *,
    value_column: str,
    excel_row: int,
    progress_reference: str | None,
) -> str:
    if not progress_reference:
        return "=NA()"

    return (
        f"=IFERROR(({value_column}{excel_row}/{progress_reference})-"
        f"{value_column}{excel_row},NA())"
    )


def _forecast_income_remaining_formula(
    *,
    excel_row: int,
    ingreso_day: int,
    agregadoras_day: int,
    days_in_month: int,
) -> str:
    ingreso_remaining = max(days_in_month - ingreso_day, 0)
    agregadoras_remaining = max(days_in_month - agregadoras_day, 0)

    parts = [
        f"IFERROR((T{excel_row}/{ingreso_day})*{ingreso_remaining},0)",
        f"IFERROR((U{excel_row}/{agregadoras_day})*{agregadoras_remaining},0)",
    ]
    return "=" + "+".join(parts)


def _write_forecast_subtotal_row(
    *,
    worksheet: Worksheet,
    totals_row: int,
    first_data_row: int,
    last_data_row: int,
) -> None:
    if last_data_row < first_data_row:
        for column_letter in FORECAST_SUM_COLUMNS:
            worksheet[f"{column_letter}{totals_row}"] = 0
        worksheet[f"AX{totals_row}"] = 0
        return

    for column_letter in FORECAST_SUM_COLUMNS:
        worksheet[f"{column_letter}{totals_row}"] = (
            f"=SUM({column_letter}{first_data_row}:{column_letter}{last_data_row})"
        )

    worksheet[f"AX{totals_row}"] = f"=IFERROR(AW{totals_row}/M{totals_row},0)"


def _write_forecast_summary_row(
    *,
    worksheet: Worksheet,
    totals_row: int,
    label: str,
    source_rows: Sequence[int],
) -> None:
    worksheet[f"C{totals_row}"] = label

    if not source_rows:
        for column_letter in FORECAST_SUM_COLUMNS:
            worksheet[f"{column_letter}{totals_row}"] = 0
        worksheet[f"AX{totals_row}"] = 0
        return

    for column_letter in FORECAST_SUM_COLUMNS:
        source_cells = ",".join(
            f"{column_letter}{source_row}" for source_row in source_rows
        )
        worksheet[f"{column_letter}{totals_row}"] = f"=SUM({source_cells})"

    worksheet[f"AX{totals_row}"] = f"=IFERROR(AW{totals_row}/M{totals_row},0)"


def _apply_forecast_formatting(
    *,
    worksheet: Worksheet,
    last_row: int,
    regional_subtotal_rows: Sequence[int],
    summary_rows: Sequence[int],
) -> None:
    thin_side = Side(style="thin", color="D9D9D9")
    medium_side = Side(style="medium", color="111827")
    thin_border = Border(
        left=thin_side,
        right=thin_side,
        top=thin_side,
        bottom=thin_side,
    )
    body_font = Font(color="0F1F3A", size=9)
    header_font = Font(color="FFFFFF", bold=True, size=8)
    projection_fill = PatternFill("solid", fgColor="E2F0D9")
    projection_header_fill = PatternFill("solid", fgColor="F4E36B")
    subtotal_fill = PatternFill("solid", fgColor="F8FAFC")
    summary_fill = PatternFill("solid", fgColor="E5E7EB")
    total_fill = PatternFill("solid", fgColor="FBE3DC")

    worksheet["B1"].font = Font(color=ULTRA_ORANGE, bold=True, size=11)
    worksheet["C1"].font = Font(bold=True)
    worksheet["R1"].font = Font(bold=True)
    worksheet["V1"].font = Font(color=ULTRA_ORANGE, bold=True)
    worksheet["V1"].alignment = Alignment(horizontal="left", vertical="center")

    for merge_range, _title, color in FORECAST_GROUPS:
        start_cell = worksheet[merge_range.split(":", 1)[0]]
        start_cell.fill = PatternFill("solid", fgColor=color)
        start_cell.font = Font(color="FFFFFF", bold=True, size=9)
        start_cell.alignment = Alignment(horizontal="center", vertical="center")

    for column_letter in FORECAST_VISIBLE_COLUMNS | FORECAST_HELPER_COLUMNS | {"M", "T", "U"}:
        cell = worksheet[f"{column_letter}3"]
        cell.fill = PatternFill("solid", fgColor=HEADER_DARK)
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )
        cell.border = thin_border

    for column_letter in ["X", "Y", "AG", "AH", "AO", "AP", "AW", "AX", "AY", "BP", "BQ"]:
        worksheet[f"{column_letter}3"].fill = projection_header_fill
        worksheet[f"{column_letter}3"].font = Font(
            color="111827",
            bold=True,
            size=8,
        )

    for row_idx in range(FORECAST_START_ROW, last_row + 1):
        for column_letter in FORECAST_VISIBLE_COLUMNS | FORECAST_HELPER_COLUMNS | {"M", "T", "U"}:
            cell = worksheet[f"{column_letter}{row_idx}"]
            cell.font = body_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        worksheet[f"C{row_idx}"].font = Font(color="0F1F3A", bold=True, size=9)
        worksheet[f"C{row_idx}"].alignment = Alignment(
            horizontal="left",
            vertical="center",
        )

    for column_letter in ["X", "AG", "AO", "AW", "BP"]:
        for row_idx in range(FORECAST_START_ROW, last_row + 1):
            worksheet[f"{column_letter}{row_idx}"].fill = projection_fill

    for subtotal_row in regional_subtotal_rows:
        for column_letter in FORECAST_VISIBLE_COLUMNS | FORECAST_HELPER_COLUMNS | {"M", "T", "U"}:
            cell = worksheet[f"{column_letter}{subtotal_row}"]
            cell.fill = subtotal_fill
            cell.font = Font(color="111827", bold=True, italic=True, size=9)
            cell.border = Border(top=medium_side, bottom=medium_side)

    for summary_row in summary_rows:
        is_total = str(worksheet[f"C{summary_row}"].value or "").upper() == "TOTAL GENERAL"
        fill = total_fill if is_total else summary_fill
        for column_letter in FORECAST_VISIBLE_COLUMNS | FORECAST_HELPER_COLUMNS | {"M", "T", "U"}:
            cell = worksheet[f"{column_letter}{summary_row}"]
            cell.fill = fill
            cell.font = Font(color="111827", bold=True, size=9)
            cell.border = thin_border

    _set_number_format(
        worksheet=worksheet,
        column_letters=["R", "T", "U", "V", "W", "X", "Y", "BM", "BN", "BO", "BP", "BQ"],
        start_row=FORECAST_START_ROW,
        end_row=last_row,
        number_format=CURRENCY_FORMAT,
    )
    _set_number_format(
        worksheet=worksheet,
        column_letters=["B", "M", "AC", "AE", "AF", "AG", "AH", "AK", "AM", "AN", "AO", "AP", "AS", "AU", "AV", "AW", "AY"],
        start_row=FORECAST_START_ROW,
        end_row=last_row,
        number_format=INTEGER_FORMAT,
    )
    _set_number_format(
        worksheet=worksheet,
        column_letters=["AX"],
        start_row=FORECAST_START_ROW,
        end_row=last_row,
        number_format=PERCENT_FORMAT,
    )

    widths = {
        "B": 5,
        "C": 22,
        "R": 15,
        "V": 15,
        "X": 15,
        "Y": 16,
        "AC": 13,
        "AE": 13,
        "AG": 13,
        "AH": 14,
        "AK": 13,
        "AM": 13,
        "AO": 13,
        "AP": 14,
        "AS": 13,
        "AU": 13,
        "AW": 14,
        "AX": 14,
        "AY": 14,
        "BM": 15,
        "BN": 14,
        "BP": 15,
        "BQ": 16,
    }

    for col_idx in range(1, FORECAST_LAST_COL + 1):
        column_letter = get_column_letter(col_idx)
        dimension = worksheet.column_dimensions[column_letter]
        dimension.hidden = column_letter not in FORECAST_VISIBLE_COLUMNS
        dimension.width = widths.get(column_letter, 12)

    worksheet.row_dimensions[2].height = 22
    worksheet.row_dimensions[3].height = 44
    for row_idx in range(FORECAST_START_ROW, last_row + 1):
        worksheet.row_dimensions[row_idx].height = 20

    for difference_column in ["Y", "AH", "AP", "AY", "BQ"]:
        cell_range = f"{difference_column}{FORECAST_START_ROW}:{difference_column}{last_row}"
        worksheet.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator="greaterThan",
                formula=["0"],
                fill=PatternFill("solid", fgColor=GOOD_FILL_COLOR),
                font=Font(color=GOOD_FONT_COLOR, bold=True),
            ),
        )
        worksheet.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator="lessThan",
                formula=["0"],
                fill=PatternFill("solid", fgColor=BAD_FILL_COLOR),
                font=Font(color=BAD_FONT_COLOR, bold=True),
            ),
        )

    worksheet.page_setup.orientation = "landscape"
    worksheet.page_setup.fitToWidth = 1
    worksheet.page_setup.fitToHeight = 0
    worksheet.sheet_properties.pageSetUpPr.fitToPage = True


def _build_raw_sheet(
    *,
    workbook: Workbook,
    track_date: date,
    rows: Sequence[Any],
) -> None:
    worksheet = workbook.create_sheet("Daily Mart Raw")
    headers = [
        "track_daily_version_id",
        "track_date",
        "generation_mode",
        "sucursal_canon",
        "target_month",
        "m2_sin_circulaciones",
        "usuarios_inicio_mes",
        "usuarios_activos_actual",
        "proyeccion_usuarios_cierre_mes",
        "meta_faycgo_mes",
        "ingreso_real_base_mtd",
        "ingreso_real_agregadora_mtd",
        "ingreso_real_mtd",
        "meta_clientes_nuevos_mes",
        "clientes_nuevos_real_mtd",
        "meta_reactivaciones_mes",
        "reactivaciones_real_mtd",
        "meta_bajas_mes",
        "bajas_reales_mtd",
        "meta_nuevos_domiciliados_mes",
        "nuevos_domiciliados_real_mtd",
        "meta_arpu_mes",
        "meta_venta_tienda_mes",
        "venta_tienda_real_mtd",
        "source_business_date_desempeno",
        "source_business_date_ingresos",
        "source_business_date_agregadoras",
        "source_business_date_domiciliados",
        "source_business_date_tienda",
        "ingreso_proyectado_cierre",
        "ingreso_proyeccion_status",
    ]

    worksheet.append(headers)

    first_store_income_dates = load_first_store_income_dates_bulk(
        [
            str(getattr(row, "sucursal_canon", "") or "")
            .strip()
            .upper()
            for row in rows
        ]
    )

    for row in rows:
        sucursal_canon = str(
            getattr(row, "sucursal_canon", "") or ""
        ).strip().upper()

        current_income_mtd = getattr(
            row,
            "ingreso_real_total_mtd",
            None,
        )

        if current_income_mtd is None:
            current_income_mtd = getattr(
                row,
                "ingreso_real_mtd",
                None,
            )

        projection = build_branch_income_projection_summary(
            sucursal_canon=sucursal_canon,
            target_month=track_date.replace(day=1),
            cutoff_day=track_date.day,
            current_income_mtd=(
                Decimal(str(current_income_mtd))
                if current_income_mtd is not None
                else None
            ),
            first_store_income_date=(
                first_store_income_dates.get(sucursal_canon)
            ),
        )

        projected_close = projection.get("projected_close")

        projected_close_decimal = (
            Decimal(str(projected_close))
            if projected_close not in (None, "")
            else None
        )

        derived_values = {
            "ingreso_proyectado_cierre": _to_number(
                projected_close_decimal
            ),
            "ingreso_proyeccion_status": str(
                projection.get("status") or ""
            ),
        }

        worksheet.append(
            [
                (
                    derived_values[header]
                    if header in derived_values
                    else _serialize_cell_value(
                        getattr(row, header, None)
                    )
                )
                for header in headers
            ]
        )

    header_fill = PatternFill("solid", fgColor="1F1F1F")
    header_font = Font(color="FFFFFF", bold=True)

    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    for column_cells in worksheet.columns:
        column_letter = column_cells[0].column_letter
        worksheet.column_dimensions[column_letter].width = min(
            max(len(str(column_cells[0].value or "")) + 2, 12),
            32,
        )


def _build_info_sheet(
    *,
    workbook: Workbook,
    track_date: date,
    generation_mode: str,
    resolved_version: Any,
    total_rows: int,
    bajas_progress_curve: dict[str, Any],
) -> None:
    worksheet = workbook.create_sheet("Info")
    worksheet.sheet_view.showGridLines = False
    worksheet.append(["Campo", "Valor"])
    worksheet.append(["Fecha Track", track_date.isoformat()])
    worksheet.append(["Modo", generation_mode])
    worksheet.append(["Versión Track ID", getattr(resolved_version, "id", None)])
    worksheet.append(["Tipo versión", getattr(resolved_version, "version_type", None)])
    worksheet.append(["Status versión", getattr(resolved_version, "status", None)])
    worksheet.append([
        "Generated at UTC",
        _serialize_cell_value(getattr(resolved_version, "generated_at_utc", None)),
    ])
    worksheet.append(["Total sucursales", total_rows])
    worksheet.append(["Fuente", "Suite Ultra / Track Daily Mart"])
    worksheet.append([
        "Forecast bajas - método",
        "Bajas MTD / mediana histórica del % acumulado vs cierre mensual, por día de corte",
    ])
    worksheet.append([
        "Forecast bajas - fuente histórica",
        "KPI Desempeño daily canónico; meses completos anteriores al mes del corte; cadena sin BECA",
    ])
    worksheet.append([
        "Forecast bajas - sensibilidad",
        "P25 y P75 se calculan para auditoría; el pronóstico operativo usa la mediana",
    ])
    worksheet.append([
        "Forecast bajas - método técnico",
        bajas_progress_curve.get("method", BAJAS_FORECAST_METHOD),
    ])
    worksheet.append([
        "Forecast bajas - confianza inicial",
        "Días 1-5: baja confiabilidad histórica; desde día 6-7 el backtest mejora de forma material",
    ])

    for cell in worksheet[1]:
        cell.fill = PatternFill("solid", fgColor="1F1F1F")
        cell.font = Font(color="FFFFFF", bold=True)

    curve_title_row = 16
    curve_header_row = 17
    worksheet.merge_cells(
        start_row=curve_title_row,
        start_column=4,
        end_row=curve_title_row,
        end_column=8,
    )
    title_cell = worksheet.cell(row=curve_title_row, column=4)
    title_cell.value = "Curva histórica de avance de bajas (% del cierre mensual)"
    title_cell.fill = PatternFill("solid", fgColor=ULTRA_ORANGE)
    title_cell.font = Font(color="FFFFFF", bold=True)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")

    curve_headers = ["Día", "Meses históricos", "P25", "Mediana aplicada", "P75"]
    thin_side = Side(style="thin", color="D9D9D9")
    thin_border = Border(
        left=thin_side,
        right=thin_side,
        top=thin_side,
        bottom=thin_side,
    )

    for column_offset, header in enumerate(curve_headers, start=4):
        cell = worksheet.cell(row=curve_header_row, column=column_offset)
        cell.value = header
        cell.fill = PatternFill("solid", fgColor=HEADER_DARK)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    points = bajas_progress_curve.get("points", {})
    for day in range(1, 32):
        row_idx = curve_header_row + day
        point = points.get(day)

        worksheet.cell(row=row_idx, column=4).value = day
        if point is not None:
            worksheet.cell(row=row_idx, column=5).value = point.get("samples_count")
            worksheet.cell(row=row_idx, column=6).value = _to_number(point.get("p25"))
            worksheet.cell(row=row_idx, column=7).value = _to_number(point.get("median"))
            worksheet.cell(row=row_idx, column=8).value = _to_number(point.get("p75"))

        for column_idx in range(4, 9):
            cell = worksheet.cell(row=row_idx, column=column_idx)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for column_idx in (6, 7, 8):
            worksheet.cell(row=row_idx, column=column_idx).number_format = PERCENT_FORMAT

    worksheet.column_dimensions["A"].width = 34
    worksheet.column_dimensions["B"].width = 92
    worksheet.column_dimensions["D"].width = 10
    worksheet.column_dimensions["E"].width = 18
    worksheet.column_dimensions["F"].width = 12
    worksheet.column_dimensions["G"].width = 20
    worksheet.column_dimensions["H"].width = 12


def _to_number(value: Any) -> float | int | None:
    if value is None:
        return None

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, (int, float)):
        return value

    return None


def _format_version_update_label(resolved_version: Any) -> str:
    version_datetime = (
        getattr(resolved_version, "finished_at_utc", None)
        or getattr(resolved_version, "generated_at_utc", None)
        or getattr(resolved_version, "started_at_utc", None)
    )

    if not isinstance(version_datetime, datetime):
        return "Actualización no disponible"

    local_datetime = _to_tijuana_datetime(version_datetime)

    return f"Actualizado: {local_datetime.strftime('%d/%m/%Y %H:%M')} h"


def _to_tijuana_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(ZoneInfo("America/Tijuana"))


def _serialize_cell_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    if isinstance(value, date):
        return value.isoformat()

    return value


def _format_branch_label(value: Any) -> str:
    return _normalize_branch_key(value).replace("_", " ")


def _sort_rows_by_track_order(rows: Sequence[Any]) -> list[Any]:
    return sorted(
        rows,
        key=lambda item: (
            TRACK_BRANCH_ORDER_INDEX.get(
                _normalize_branch_key(getattr(item, "sucursal_canon", "")),
                999,
            ),
            _normalize_branch_key(getattr(item, "sucursal_canon", "")),
        ),
    )


def _normalize_branch_key(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .upper()
        .replace(" ", "_")
        .replace("-", "_")
    )
