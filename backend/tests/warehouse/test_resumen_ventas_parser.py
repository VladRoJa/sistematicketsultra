from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pandas as pd

from app.warehouse.services.resumen_ventas_parser import (
    parse_resumen_ventas_xlsx,
)


def _workbook_bytes() -> bytes:
    summary = pd.DataFrame(
        [
            [None, None, "01 al 16 septiembre", None, "01 al 16 agosto", None],
            [None, "Total de primer pago contrato", 100, None, 90, None],
            [
                None,
                "Total Contratos segundo pago en adelante",
                200,
                None,
                180,
                None,
            ],
            [None, "Total de pagos sin contrato", 150, None, 120, None],
            [None, "Total de penalizaciones", 10, None, 8, None],
            [None, "Total de Inscripciones", 20, None, 18, None],
            [None, "Total de agregadoras", 30, None, 25, None],
            [None, "Total de lockers", 5, None, 4, None],
            [None, "Total de tienda", 15, None, 14, None],
            [None, "Gran Total", 530, None, 459, None],
        ]
    )
    no_contract = pd.DataFrame(
        [
            [
                None,
                None,
                None,
                None,
                None,
                "01 al 16 septiembre",
                None,
                "01 al 16 agosto",
                None,
            ],
            [
                "Familia",
                "Tipo",
                "Tarifa",
                "Costo",
                "Equiv. Mensual",
                "Cantidad",
                "Flujo $",
                "Cantidad",
                "Flujo $",
            ],
            ["Regular 1 mes", "MES", "TARIFA A", 50, 50, 3, 150, 3, 120],
            [None, None, "SUCURSAL A", None, None, 2, 100, 2, 80],
            [None, None, "SUCURSAL B", None, None, 1, 50, 1, 40],
            [None, "Total Regular 1 mes", None, None, None, 3, 150, 3, 120],
        ]
    )
    contract = pd.DataFrame(
        [
            [
                None,
                None,
                None,
                None,
                "01 al 16 septiembre",
                None,
                "01 al 16 agosto",
                None,
            ],
            [
                "Contrato",
                "Tarifa",
                "Costo",
                "Mes Gratis",
                "Cantidad",
                "Flujo $",
                "Cantidad",
                "Flujo $",
            ],
            [
                "Contrato no forzoso",
                "TARIFA B",
                100,
                "2, 3",
                3,
                300,
                3,
                270,
            ],
            [None, "SUCURSAL A", None, None, 2, 200, 2, 180],
            [None, "SUCURSAL B", None, None, 1, 100, 1, 90],
            [None, "Total Contrato no forzoso", None, None, 3, 300, 3, 270],
        ]
    )
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(
            writer,
            sheet_name="Resumen ventas",
            header=False,
            index=False,
        )
        no_contract.to_excel(
            writer,
            sheet_name="Tarifas Sin Contrato",
            header=False,
            index=False,
        )
        contract.to_excel(
            writer,
            sheet_name="Tarifas con Contrato",
            header=False,
            index=False,
        )
    return output.getvalue()


def test_parser_reconciles_tariffs_and_branch_detail():
    result = parse_resumen_ventas_xlsx(file_bytes=_workbook_bytes())

    assert result.current_label == "01 al 16 septiembre"
    assert result.comparison_label == "01 al 16 agosto"
    assert result.data_quality["reconciliation_status"] == "ok"
    assert result.data_quality["tariff_rows"] == 2
    assert result.data_quality["branch_rows"] == 4
    assert result.data_quality["tariff_branch_mismatch_count"] == 0
    assert (
        result.summary_totals["no_contract_payments"]["current"]
        == Decimal("150")
    )

    tariff_rows = [
        row
        for row in result.rows
        if row.row_kind == "TARIFF"
    ]
    assert tariff_rows[0].family == "Regular 1 mes"
    assert tariff_rows[1].contract_type == "Contrato no forzoso"
    assert tariff_rows[1].free_months_raw == "2, 3"
