"""Google Ads manual import: actual Spanish export layout, dates and totals."""
from io import BytesIO
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.warehouse.services.google_ads_daily_xlsx_parser import (
    GoogleAdsXlsxValidationError,
    parse_google_ads_daily_xlsx,
)


def make_export(cost=12.50, currency="MXN", repeated=False):
    wb = Workbook()
    sheet = wb.active
    sheet.append(["Informe de campaña"])
    sheet.append(["24 de septiembre de 2026 - 25 de septiembre de 2026"])
    sheet.append([
        "Día", "Estado de la campaña", "Campaña", "Presupuesto",
        "Nombre de presupuesto", "Tipo de presupuesto", "Código de moneda",
        "Estado", "Motivos del estado", "Nivel de optimización",
        "Tipo de campaña", "Coste", "Conversiones", "CPC medio",
        "Coste/conv.", "Valor de conv.", "Valor conv./coste", "Clics", "Impr.",
    ])
    for day in ("2026-09-24", "2026-09-25"):
        row = [
            day, "Habilitada", "UG | Local | Centro", None, None, "Diario",
            currency, "Apto", None, None, "Buscar", cost, 0.5,
            None, None, 2, None, 4, 100,
        ]
        sheet.append(row)
        if repeated and day == "2026-09-24":
            sheet.append(row)
        sheet.append([
            day, "En pausa", "UG | Local | Noreste", None, None, "Diario",
            currency, "En pausa", None, None, "Buscar", 0, 0,
            None, None, 0, None, 0, 0,
        ])
        sheet.append([
            day, "Total: Cuenta", None, None, None, None, currency,
            None, None, None, None, 12.50, 0.5,
            None, None, 2, None, 4, 100,
        ])
    sheet.append([
        "--", "Total: Campañas", "--", None, None, None, "MXN",
        None, None, None, None, 25, 1, None, None, 4, None, 8, 200,
    ])
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_campaign_daily_export_parses_without_subtotals():
    parsed = parse_google_ads_daily_xlsx(make_export())
    assert parsed.date_from == date(2026, 9, 24)
    assert parsed.date_to == date(2026, 9, 25)
    assert len(parsed.rows) == 4
    assert parsed.total_cost == Decimal("25.00")
    assert parsed.rows[0].conversions == Decimal("0.5000")
    assert parsed.rows[0].campaign_key.startswith("name:")


@pytest.mark.parametrize("kwargs", [
    {"cost": 14},
    {"currency": "USD"},
    {"repeated": True},
])
def test_invalid_daily_export_fails_closed(kwargs):
    with pytest.raises(GoogleAdsXlsxValidationError):
        parse_google_ads_daily_xlsx(make_export(**kwargs))


def test_non_xlsx_bytes_fail_closed():
    with pytest.raises(GoogleAdsXlsxValidationError):
        parse_google_ads_daily_xlsx(b"not a valid spreadsheet")
