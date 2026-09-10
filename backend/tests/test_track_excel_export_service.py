from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.warehouse.services import track_excel_export_service as service


def _fake_bajas_curve(*, target_month):
    assert target_month.day == 1
    return {
        "status": "available",
        "method": "chain_daily_median_share_of_month_close",
        "target_month": target_month,
        "history_end_exclusive": target_month,
        "points": {
            7: {
                "day": 7,
                "samples_count": 39,
                "p25": Decimal("0.345"),
                "median": Decimal("0.376"),
                "p75": Decimal("0.433"),
            },
            8: {
                "day": 8,
                "samples_count": 40,
                "p25": Decimal("0.345"),
                "median": Decimal("0.376"),
                "p75": Decimal("0.433"),
            },
            27: {
                "day": 27,
                "samples_count": 41,
                "p25": Decimal("0.839"),
                "median": Decimal("0.914"),
                "p75": Decimal("0.977"),
            },
        },
    }


def test_daily_mart_raw_includes_official_branch_income_projection(
    monkeypatch,
):
    row = SimpleNamespace(
        sucursal_canon="TEC_MXL",
        ingreso_real_total_mtd=Decimal("80000"),
        ingreso_real_mtd=Decimal("70000"),
    )

    resolved_version = SimpleNamespace(
        id=123,
        version_type="cierre_canonico",
        status="success",
        generated_at_utc=None,
        finished_at_utc=None,
        started_at_utc=None,
    )

    def fake_first_store_income_dates(sucursal_canons):
        assert sucursal_canons == ["TEC_MXL"]
        return {
            "TEC_MXL": date(2025, 8, 22),
        }

    def fake_projection(**kwargs):
        assert kwargs["sucursal_canon"] == "TEC_MXL"
        assert kwargs["target_month"] == date(2026, 8, 1)
        assert kwargs["cutoff_day"] == 27
        assert kwargs["current_income_mtd"] == Decimal("80000")
        assert kwargs["first_store_income_date"] == date(2025, 8, 22)

        return {
            "status": "available",
            "projected_close": "887460.2043673072",
        }

    monkeypatch.setattr(
        service,
        "load_first_store_income_dates_bulk",
        fake_first_store_income_dates,
    )
    monkeypatch.setattr(
        service,
        "build_branch_income_projection_summary",
        fake_projection,
    )
    monkeypatch.setattr(
        service,
        "build_bajas_historical_progress_curve",
        _fake_bajas_curve,
    )

    excel_bytes = service.build_track_daily_mart_excel(
        track_date=date(2026, 8, 27),
        generation_mode="official_closed_day",
        resolved_version=resolved_version,
        rows=[row],
    )

    workbook = load_workbook(
        BytesIO(excel_bytes),
        data_only=False,
    )

    worksheet = workbook["Daily Mart Raw"]

    headers = {
        cell.value: cell.column
        for cell in worksheet[1]
    }

    assert "ingreso_proyectado_cierre" in headers
    assert "ingreso_proyeccion_status" in headers

    projection_value = worksheet.cell(
        row=2,
        column=headers["ingreso_proyectado_cierre"],
    ).value

    projection_status = worksheet.cell(
        row=2,
        column=headers["ingreso_proyeccion_status"],
    ).value

    assert projection_value == 887460.2043673072
    assert projection_status == "available"


def test_forecast_sheet_uses_source_cutoffs_and_hides_helper_columns(
    monkeypatch,
):
    row = SimpleNamespace(
        sucursal_canon="VILLAS_DEL_REY",
        usuarios_activos_actual=1206,
        meta_faycgo_mes=Decimal("774242.59"),
        ingreso_real_base_mtd=Decimal("137182"),
        ingreso_real_agregadora_mtd=Decimal("11528.64"),
        ingreso_real_mtd=Decimal("148710.64"),
        meta_clientes_nuevos_mes=114,
        clientes_nuevos_real_mtd=21,
        meta_reactivaciones_mes=118,
        reactivaciones_real_mtd=54,
        meta_bajas_mes=176,
        bajas_reales_mtd=119,
        meta_venta_tienda_mes=Decimal("65252.25"),
        venta_tienda_real_mtd=Decimal("15915"),
        source_business_date_ingresos=date(2026, 9, 8),
        source_business_date_agregadoras=date(2026, 9, 8),
        source_business_date_nuevos=date(2026, 9, 7),
        source_business_date_desempeno=date(2026, 9, 8),
        source_business_date_tienda=date(2026, 9, 7),
    )

    resolved_version = SimpleNamespace(
        id=456,
        version_type="preview",
        status="success",
        generated_at_utc=None,
        finished_at_utc=None,
        started_at_utc=None,
    )

    monkeypatch.setattr(
        service,
        "load_first_store_income_dates_bulk",
        lambda _sucursal_canons: {"VILLAS_DEL_REY": date(2020, 1, 1)},
    )
    monkeypatch.setattr(
        service,
        "build_branch_income_projection_summary",
        lambda **_kwargs: {"status": "available", "projected_close": "1"},
    )
    monkeypatch.setattr(
        service,
        "build_bajas_historical_progress_curve",
        _fake_bajas_curve,
    )

    excel_bytes = service.build_track_daily_mart_excel(
        track_date=date(2026, 9, 9),
        generation_mode="manual_preview",
        resolved_version=resolved_version,
        rows=[row],
    )

    workbook = load_workbook(BytesIO(excel_bytes), data_only=False)

    assert workbook.sheetnames[0] == "Forecast"
    worksheet = workbook["Forecast"]

    assert worksheet["B1"].value == "Track"
    assert worksheet["C1"].value == "A dia"
    assert worksheet["R1"].value == "2026-09-09"
    assert worksheet["V1"].value == "Actualización no disponible"
    for cell_address in ["AC1", "AE1", "AK1", "AM1", "AS1", "AU1", "BM1", "BN1"]:
        assert worksheet[cell_address].value is None

    assert worksheet["C4"].value == "VILLAS DEL REY"
    assert worksheet["W4"].value == "=IFERROR((T4/8)*22,0)+IFERROR((U4/8)*22,0)"
    assert worksheet["AF4"].value == "=IFERROR((AE4/7)*23,0)"
    assert worksheet["AN4"].value == "=IFERROR((AM4/8)*22,0)"
    assert worksheet["AV4"].value == "=IFERROR((AU4/Info!$F$25)-AU4,NA())"
    assert worksheet["BO4"].value == "=IFERROR((BN4/7)*23,0)"

    assert worksheet["X4"].value == "=V4+W4"
    assert worksheet["AG4"].value == "=AE4+AF4"
    assert worksheet["AO4"].value == "=AM4+AN4"
    assert worksheet["AW4"].value == "=AU4+AV4"
    assert worksheet["AY4"].value == "=AS4-AW4"
    assert worksheet["BP4"].value == "=BN4+BO4"

    for helper_column in ["W", "AF", "AN", "AV", "BO"]:
        assert worksheet.column_dimensions[helper_column].hidden is True

    for visible_column in [
        "B", "C", "R", "V", "X", "Y", "AC", "AE", "AG", "AH",
        "AK", "AM", "AO", "AP", "AS", "AU", "AW", "AX", "AY",
        "BM", "BN", "BP", "BQ",
    ]:
        assert worksheet.column_dimensions[visible_column].hidden is False

    assert worksheet.column_dimensions["D"].hidden is True
    assert worksheet.column_dimensions["T"].hidden is True
    assert worksheet.column_dimensions["U"].hidden is True

    metas_op = workbook["Metas OP"]
    assert metas_op["B2"].value is None
    assert metas_op["C2"].value == 9
    assert metas_op["S4"].value == "=(R4/30)*$C$2"

    info = workbook["Info"]
    info_values = {
        row[0].value: row[1].value
        for row in info.iter_rows(min_row=2, max_col=2)
    }
    assert info_values["Forecast bajas - método"] == (
        "Bajas MTD / mediana histórica del % acumulado vs cierre mensual, por día de corte"
    )
    assert info_values["Forecast bajas - método técnico"] == (
        "chain_daily_median_share_of_month_close"
    )

    assert info["D16"].value == (
        "Curva histórica de avance de bajas (% del cierre mensual)"
    )
    assert info["D17"].value == "Día"
    assert info["E17"].value == "Meses históricos"
    assert info["F17"].value == "Mediana aplicada"
    assert info["D25"].value == 8
    assert info["E25"].value == 40
    assert info["F25"].value == 0.376
    assert info["F25"].number_format == service.PERCENT_FORMAT
    assert info["G17"].value is None
    assert info["H17"].value is None


def test_bajas_forecast_formula_fails_closed_without_historical_reference():
    assert service._forecast_bajas_remaining_formula(
        value_column="AU",
        excel_row=4,
        progress_reference=None,
    ) == "=NA()"
