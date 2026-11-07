"""Exporta cohortes BI desde padron y MESES DE COBERTURA PAGADA verificables.

cd backend
python -m scripts.ops.export_member_streaks \
  --roster /ruta/padron.csv --coverage /ruta/meses_pagados.csv \
  --as-of 2026-11-07 --output /tmp/rachas_bi.xlsx

No llama a Gasca, no escribe en PostgreSQL ni certifica historiales incompletos.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from app.warehouse.services.member_streak_service import (
    MemberStreak,
    StreakResult,
    reconstruct_member_streaks,
)

ROSTER_COLUMNS = {"estado", "sucursal", "historial_completo", "reinicio_promocion"}
COVERAGE_COLUMNS = {
    "mes_cubierto", "sucursal", "estado_evidencia", "fuente_ref"
}
TARIFFS = ((1, 599), (4, 499), (7, 399), (10, 299))


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = required - fields
        if missing:
            raise ValueError(f"{path.name}: faltan columnas {sorted(missing)}")
        if not ({"id_socio", "pin"} & fields):
            raise ValueError(f"{path.name}: requiere id_socio o pin.")
        rows = list(reader)
    return rows


def _headers(sheet, cells: list[str]) -> None:
    sheet.append(cells)
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="193A5B")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(cells))}1"


def export_workbook(output: Path, result: StreakResult, *, as_of: date) -> None:
    book = Workbook()
    book.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True)
    rules = book.active
    rules.title = "Reglas"
    rules["A1"] = "UMBRAL DE RACHA (mes)"
    rules["B1"] = "PRECIO MENSUAL MXN"
    rules["D1"] = "Fecha de corte"
    rules["E1"] = as_of
    rules["E1"].number_format = "yyyy-mm-dd"
    rules["D2"] = "Regla"
    rules["E2"] = "Vencido: mejor racha historica; activo: racha vigente; reinicio: mes 1"
    rules["D3"] = "Calidad"
    rules["E3"] = "PARCIAL_OBSERVADO no equivale a historia completa verificada"
    for rownum, (threshold, price) in enumerate(TARIFFS, start=4):
        rules.cell(rownum, 1, threshold)
        rules.cell(rownum, 2, price).number_format = '"$"#,##0.00'
    rules.column_dimensions["A"].width = 27
    rules.column_dimensions["B"].width = 25
    rules.column_dimensions["D"].width = 21
    rules.column_dimensions["E"].width = 65

    detail = book.create_sheet("Detalle")
    headers = [
        "Clave interna socio", "Sucursal", "Estado", "Mejor racha observada",
        "Racha vigente observada", "Racha para precio entrada",
        "Precio mensual (MXN)", "Calidad de evidencia",
        "Meses cubiertos distintos", "Reinicio promocion",
    ]
    _headers(detail, headers)
    for idx, member in enumerate(result.members, start=2):
        detail.append([
            member.member_key, member.sucursal, member.estado,
            member.mejor_racha_observada, member.racha_vigente_observada,
            member.racha_de_entrada, None, member.calidad,
            member.evidencia_meses, "SI" if member.racha_reiniciada else "NO",
        ])
        detail.cell(idx, 7).value = (
            f'=IF(F{idx}="","",LOOKUP(F{idx},Reglas!$A$4:$A$7,Reglas!$B$4:$B$7))'
        )
        detail.cell(idx, 7).number_format = '"$"#,##0.00'
    detail.auto_filter.ref = f"A1:J{max(len(result.members) + 1, 2)}"
    for col, width in {"A":28, "B":22, "C":16, "D":23, "E":24,
                       "F":25, "G":23, "H":34, "I":20, "J":20}.items():
        detail.column_dimensions[col].width = width

    cohorts = book.create_sheet("Cohortes_BI")
    _headers(cohorts, ["Estado", "Tramo", "Desde mes", "Hasta mes anterior a",
                       "Socios", "Tarifa", "Ingreso mensual simulado"])
    end = max(2, len(result.members) + 1)
    for status in ("ACTIVO", "VENCIDO", "NUEVO"):
        for level in range(4):
            idx = cohorts.max_row + 1
            rule_row = level + 4
            next_row = rule_row + 1
            cohorts.cell(idx, 1, status)
            cohorts.cell(idx, 2, f"NIVEL {level + 1}")
            cohorts.cell(idx, 3, f"=Reglas!A{rule_row}")
            if level < 3:
                cohorts.cell(idx, 4, f"=Reglas!A{next_row}")
            lower = f'Detalle!$F$2:$F${end}'
            states = f'Detalle!$C$2:$C${end}'
            formula = (
                f'=COUNTIFS({states},A{idx},{lower},">="&C{idx}'
                + (f',{lower},"<"&D{idx}' if level < 3 else "")
                + ")"
            )
            cohorts.cell(idx, 5, formula)
            cohorts.cell(idx, 6, f"=Reglas!B{rule_row}")
            cohorts.cell(idx, 7, f"=E{idx}*F{idx}")
            cohorts.cell(idx, 6).number_format = '"$"#,##0.00'
            cohorts.cell(idx, 7).number_format = '"$"#,##0.00'
    total_row = cohorts.max_row + 2
    cohorts.cell(total_row, 4, "TOTAL CON PRECIO")
    cohorts.cell(total_row, 5, f"=SUM(E2:E{total_row - 2})")
    cohorts.cell(total_row, 7, f"=SUM(G2:G{total_row - 2})")
    cohorts.cell(total_row, 7).number_format = '"$"#,##0.00'
    for col, width in {"A":18, "B":16, "C":17, "D":22, "E":15, "F":19, "G":30}.items():
        cohorts.column_dimensions[col].width = width

    quality = book.create_sheet("Calidad")
    _headers(quality, ["Indicador", "Valor", "Interpretacion"])
    quality.append(["Socios en padron", len(result.members), "Total de filas validas en padron"])
    quality.append(["Filas de cobertura", result.coverage_rows, "Incluye meses repetidos"])
    quality.append(["Meses repetidos", result.duplicate_months, "No inflan la racha"])
    quality.append(["Filas no vinculadas", result.unmatched_coverage, "Revisar identidad"])
    for status in ("SIN_EVIDENCIA", "PARCIAL_OBSERVADO", "CERTIFICABLE_CON_FUENTE_COMPLETA",
                   "REINICIO_PROMOCION", "NUEVO"):
        count = sum(1 for item in result.members if item.calidad == status)
        quality.append([status, count, "Validar fuente antes de campaña masiva"])
    quality["A12"] = "ADVERTENCIA"
    quality["B12"] = "El historial de Venta Total no prueba por si solo meses cubiertos."
    quality.column_dimensions["A"].width = 44
    quality.column_dimensions["B"].width = 55
    quality.column_dimensions["C"].width = 60

    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roster = _read_csv(args.roster, ROSTER_COLUMNS)
    months = _read_csv(args.coverage, COVERAGE_COLUMNS)
    result = reconstruct_member_streaks(roster, months, as_of=args.as_of)
    export_workbook(args.output, result, as_of=args.as_of)
    print(
        f"Generado: {args.output} | socios={len(result.members)} "
        f"| coberturas={result.coverage_rows} | no_vinculadas={result.unmatched_coverage}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
