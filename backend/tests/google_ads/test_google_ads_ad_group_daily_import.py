"""Google Ads group/day export validation with two filtered actions."""
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.warehouse.services.google_ads_ad_group_daily_xlsx_parser import (
    parse_google_ads_ad_group_daily_xlsx,
)
from app.warehouse.services.google_ads_daily_xlsx_parser import GoogleAdsXlsxValidationError


HEADERS = [
    "Día", "Estado del grupo de anuncios", "Grupo de anuncios", "Campaña",
    "Código de moneda", "Impr.", "Coste", "Código de moneda",
    "Pase gratis Ads", "Compras web Ads", "Clics", "Conversiones",
    "Valor de conv. original",
]


def export(*, account_cost=10, change_header=False, duplicate=False):
    wb = Workbook()
    sh = wb.active
    sh.append(["Informe de grupo de anuncios"])
    sh.append(["24 de septiembre de 2026 - 25 de septiembre de 2026"])
    cols = HEADERS.copy()
    if change_header:
        cols[9] = "Compas web Ads"
    sh.append(cols)
    for day in ("2026-09-24", "2026-09-25"):
        sh.append([day, "Habilitado", "Metepec", "UG | Local | Centro",
                   "MXN", 100, 10, "MXN", "1,00", "0,50", 4, 1.5, 20])
        if duplicate and day == "2026-09-24":
            sh.append([day, "Habilitado", "Metepec", "UG | Local | Centro",
                       "MXN", 100, 10, "MXN", "1,00", "0,50", 4, 1.5, 20])
        sh.append([day, "Total: Grupos de anuncios", None, None, None,
                   100, 10, "MXN", "1,00", "0,50", 4, 1.5, 20])
        sh.append([day, "Total: Cuenta", None, None, None,
                   100, account_cost, "MXN", "1,01", "0,50", 4, 1.51, 20.01])
    sh.append([None, "Total: Cuenta", None, None, None,
               200, 20, "MXN", "2,00", "1,00", 8, 3.0, 40])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_ad_group_export_parses_and_keeps_action_columns():
    parsed = parse_google_ads_ad_group_daily_xlsx(export())
    assert len(parsed.rows) == 2
    assert parsed.total_cost == Decimal("20.00")
    assert parsed.total_free_pass == Decimal("2.0000")
    assert parsed.total_web_purchase == Decimal("1.0000")
    assert parsed.rows[0].ad_group_key.startswith("name:")


@pytest.mark.parametrize("kwargs", [
    {"account_cost": 11}, {"change_header": True}, {"duplicate": True},
])
def test_ad_group_invalid_exports_fail_closed(kwargs):
    with pytest.raises(GoogleAdsXlsxValidationError):
        parse_google_ads_ad_group_daily_xlsx(export(**kwargs))
