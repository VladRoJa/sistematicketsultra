from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.services.system_daily_check_bi_service import (
    build_system_daily_check_bi_summary,
    get_system_daily_check_bi_detail,
    list_system_daily_check_bi_history,
    list_system_daily_check_bi_issues,
)


HEADER_FILL = PatternFill(
    fill_type="solid",
    fgColor="1E293B",
)
HEADER_FONT = Font(
    color="FFFFFF",
    bold=True,
)
SECTION_FILL = PatternFill(
    fill_type="solid",
    fgColor="E2E8F0",
)
SECTION_FONT = Font(
    color="0F172A",
    bold=True,
)


def _write_headers(worksheet, headers: list[str]) -> None:
    worksheet.append(headers)
    for cell in worksheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions


def _autosize(worksheet, *, max_width: int = 48) -> None:
    for column_cells in worksheet.columns:
        width = 0
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            width = max(width, len(value))
        column_letter = get_column_letter(
            column_cells[0].column
        )
        worksheet.column_dimensions[column_letter].width = min(
            max(width + 2, 10),
            max_width,
        )


def _yes_no(value: object) -> str:
    return "Sí" if bool(value) else "No"


def _collect_history(
    actor,
    *,
    date_from: date,
    date_to: date,
    branch_id: object,
    now: datetime | None,
    session: Session | None,
) -> list[dict]:
    items: list[dict] = []
    page = 1
    page_size = 200

    while True:
        result = list_system_daily_check_bi_history(
            actor,
            date_from=date_from,
            date_to=date_to,
            branch_id=branch_id,
            page=page,
            page_size=page_size,
            now=now,
            session=session,
        )
        batch = list(result["items"])
        items.extend(batch)
        if len(items) >= int(result["total"]):
            return items
        if not batch:
            return items
        page += 1


def _collect_issues(
    actor,
    *,
    date_from: date,
    date_to: date,
    branch_id: object,
    session: Session | None,
) -> list[dict]:
    items: list[dict] = []
    page = 1
    page_size = 200

    while True:
        result = list_system_daily_check_bi_issues(
            actor,
            date_from=date_from,
            date_to=date_to,
            branch_id=branch_id,
            page=page,
            page_size=page_size,
            session=session,
        )
        batch = list(result["items"])
        items.extend(batch)
        if len(items) >= int(result["total"]):
            return items
        if not batch:
            return items
        page += 1


def _build_summary_sheet(
    workbook: Workbook,
    *,
    summary: dict,
) -> None:
    worksheet = workbook.active
    worksheet.title = "Resumen"

    worksheet["A1"] = "Salud de Sistemas"
    worksheet["A1"].font = Font(
        size=16,
        bold=True,
        color="0F172A",
    )

    worksheet["A3"] = "Filtros"
    worksheet["A3"].fill = SECTION_FILL
    worksheet["A3"].font = SECTION_FONT

    filters = summary["filters"]
    summary_rows = [
        ("Desde", filters["date_from"]),
        ("Hasta", filters["date_to"]),
        (
            "Sucursal ID",
            filters["branch_id"]
            if filters["branch_id"] is not None
            else "Todas las participantes",
        ),
        ("", ""),
        ("Indicador", "Valor"),
        (
            "Checklists esperados",
            summary["universe"]["expected_checklists"],
        ),
        (
            "Sucursales esperadas",
            summary["universe"]["expected_branches"],
        ),
        (
            "Completados",
            summary["summary"]["completed"],
        ),
        (
            "Pendientes",
            summary["summary"]["pending"],
        ),
        (
            "Cumplimiento %",
            summary["summary"]["compliance_pct"],
        ),
        (
            "Operación normal",
            summary["summary"]["normal"],
        ),
        (
            "Falla menor",
            summary["summary"]["minor_failure"],
        ),
        (
            "Afectación operativa",
            summary["summary"]["operational_impact"],
        ),
        (
            "Respuestas NO",
            summary["failures"]["no_answers"],
        ),
        (
            "Checks con falla",
            summary["failures"]["checks_with_failure"],
        ),
        (
            "Incidencias reportadas",
            summary["failures"]["reported"],
        ),
        (
            "Incidencias no reportadas",
            summary["failures"]["unreported"],
        ),
        (
            "Reportadas %",
            summary["failures"]["reported_pct"],
        ),
        (
            "Completados sin aplazar",
            summary["postponements"]["completed_without_postpone"],
        ),
        (
            "Completados tras 1 aplazamiento",
            summary["postponements"]["completed_after_1"],
        ),
        (
            "Completados tras 2 aplazamientos",
            summary["postponements"]["completed_after_2"],
        ),
        (
            "Alcanzaron obligatorio",
            summary["postponements"]["reached_mandatory"],
        ),
    ]

    start_row = 4
    for offset, row in enumerate(summary_rows):
        worksheet.append(row)
        target_row = start_row + offset
        if row == ("Indicador", "Valor"):
            for cell in worksheet[target_row][:2]:
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT

    worksheet.column_dimensions["A"].width = 34
    worksheet.column_dimensions["B"].width = 24


def _build_checklists_sheet(
    workbook: Workbook,
    *,
    history: list[dict],
) -> None:
    worksheet = workbook.create_sheet("Checklists")
    _write_headers(
        worksheet,
        [
            "Checklist ID",
            "Fecha operativa",
            "Sucursal ID",
            "Sucursal",
            "Estado general",
            "Usuario ID",
            "Usuario",
            "Enviado",
            "Aplazamientos",
            "Alcanzó obligatorio",
        ],
    )

    for item in history:
        worksheet.append([
            item["id"],
            item["business_date"],
            item["sucursal_id"],
            item["sucursal"],
            item["general_status"],
            item["performed_by_user_id"],
            item["performed_by_username"],
            item["submitted_at"],
            item["postpone_count"],
            _yes_no(item["reached_mandatory"]),
        ])

    _autosize(worksheet)


def _build_issues_sheet(
    workbook: Workbook,
    *,
    issues: list[dict],
) -> None:
    worksheet = workbook.create_sheet("Incidencias")
    _write_headers(
        worksheet,
        [
            "Incidencia ID",
            "Checklist ID",
            "Fecha operativa",
            "Sucursal ID",
            "Sucursal",
            "Clave pregunta",
            "Pregunta",
            "Reportada a Soporte",
            "Alcance",
            "Descripción",
            "Evidencias",
        ],
    )

    for item in issues:
        worksheet.append([
            item["issue_id"],
            item["check_id"],
            item["business_date"],
            item["sucursal_id"],
            item["sucursal"],
            item["question_key"],
            item["question_label"],
            _yes_no(item["reported_to_support"]),
            item["affected_scope"],
            item["description"],
            item["attachment_count"],
        ])

    for row in worksheet.iter_rows(
        min_row=2,
        min_col=10,
        max_col=10,
    ):
        row[0].alignment = Alignment(
            wrap_text=True,
            vertical="top",
        )

    _autosize(worksheet)


def _build_answers_sheet(
    workbook: Workbook,
    *,
    details: list[dict],
) -> None:
    worksheet = workbook.create_sheet("Respuestas")
    _write_headers(
        worksheet,
        [
            "Checklist ID",
            "Fecha operativa",
            "Sucursal ID",
            "Sucursal",
            "Usuario",
            "Clave pregunta",
            "Pregunta",
            "Categoría",
            "Respuesta",
            "Tiene incidencia",
            "Reportada a Soporte",
            "Alcance",
            "Descripción",
            "Evidencias",
        ],
    )

    for detail in details:
        for answer in detail["answers"]:
            issue = answer["issue"]
            worksheet.append([
                detail["id"],
                detail["business_date"],
                detail["sucursal_id"],
                detail["sucursal"],
                detail["performed_by_username"],
                answer["question_key"],
                answer["question_label"],
                answer["category_key"],
                answer["answer"],
                _yes_no(issue is not None),
                (
                    _yes_no(issue["reported_to_support"])
                    if issue is not None
                    else ""
                ),
                (
                    issue["affected_scope"]
                    if issue is not None
                    else ""
                ),
                (
                    issue["description"]
                    if issue is not None
                    else ""
                ),
                (
                    len(issue["attachments"])
                    if issue is not None
                    else 0
                ),
            ])

    for row in worksheet.iter_rows(
        min_row=2,
        min_col=13,
        max_col=13,
    ):
        row[0].alignment = Alignment(
            wrap_text=True,
            vertical="top",
        )

    _autosize(worksheet)


def build_system_daily_check_excel_export(
    actor,
    *,
    date_from: date,
    date_to: date,
    branch_id: object = None,
    now: datetime | None = None,
    session: Session | None = None,
) -> tuple[BytesIO, str]:
    summary = build_system_daily_check_bi_summary(
        actor,
        date_from=date_from,
        date_to=date_to,
        branch_id=branch_id,
        now=now,
        session=session,
    )
    history = _collect_history(
        actor,
        date_from=date_from,
        date_to=date_to,
        branch_id=branch_id,
        now=now,
        session=session,
    )
    issues = _collect_issues(
        actor,
        date_from=date_from,
        date_to=date_to,
        branch_id=branch_id,
        session=session,
    )
    details = [
        get_system_daily_check_bi_detail(
            actor,
            check_id=item["id"],
            now=now,
            session=session,
        )
        for item in history
    ]

    workbook = Workbook()
    _build_summary_sheet(
        workbook,
        summary=summary,
    )
    _build_checklists_sheet(
        workbook,
        history=history,
    )
    _build_issues_sheet(
        workbook,
        issues=issues,
    )
    _build_answers_sheet(
        workbook,
        details=details,
    )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    filename = (
        "salud_sistemas_"
        f"{date_from.isoformat()}_"
        f"{date_to.isoformat()}.xlsx"
    )
    return output, filename
