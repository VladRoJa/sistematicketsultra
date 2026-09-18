from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.warehouse.services import track_excel_export_service as service


def _empty_forecast_histories(
    *,
    track_date,
    current_version,
    sucursal_canons,
):
    return {
        str(canon).strip().upper(): {
            "history": [],
            "missing_dates": [],
        }
        for canon in sucursal_canons
    }


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
    monkeypatch.setattr(
        service,
        "_load_operational_forecast_histories_bulk",
        _empty_forecast_histories,
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
    monkeypatch.setattr(
        service,
        "_load_operational_forecast_histories_bulk",
        _empty_forecast_histories,
    )

    excel_bytes = service.build_track_daily_mart_excel(
        track_date=date(2026, 9, 9),
        generation_mode="manual_preview",
        resolved_version=resolved_version,
        rows=[row],
    )

    workbook = load_workbook(BytesIO(excel_bytes), data_only=False)

    assert workbook.sheetnames[0] == "Forecast"
    assert workbook.sheetnames[1] == service.SENSITIZED_FORECAST_SHEET
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


def test_sensitized_forecast_sheet_uses_shared_operational_contract_and_info_support(
    monkeypatch,
):
    track_date = date(2026, 9, 18)
    row = SimpleNamespace(
        track_date=track_date,
        target_month=date(2026, 9, 1),
        sucursal_canon="VILLAS_DEL_REY",
        usuarios_activos_actual=1000,
        meta_faycgo_mes=Decimal("1200"),
        ingreso_real_total_mtd=Decimal("800"),
        ingreso_real_mtd=Decimal("800"),
        ingreso_real_base_mtd=Decimal("700"),
        ingreso_real_agregadora_mtd=Decimal("100"),
        meta_clientes_nuevos_mes=300,
        clientes_nuevos_real_mtd=100,
        meta_reactivaciones_mes=400,
        reactivaciones_real_mtd=200,
        meta_bajas_mes=70,
        bajas_reales_mtd=50,
        meta_venta_tienda_mes=Decimal("5000"),
        venta_tienda_real_mtd=Decimal("3000"),
        source_business_date_ingresos=track_date,
        source_business_date_agregadoras=track_date,
        source_business_date_nuevos=track_date,
        source_business_date_desempeno=track_date,
        source_business_date_tienda=track_date,
    )
    resolved_version = SimpleNamespace(
        id=3918,
        version_type="preview_operativo",
        status="success",
        generated_at_utc=None,
        finished_at_utc=None,
        started_at_utc=None,
    )

    history = [
        {
            "track_date": f"2026-09-{day:02d}",
            "track_daily_version_id": 3900 + day,
            "previous_track_date": f"2026-09-{day - 1:02d}",
            "days_since_previous": 1,
            "is_consecutive_previous_date": True,
            "metrics": {
                "clientes_nuevos": {"daily_delta": "10"},
                "reactivaciones": {"daily_delta": "8"},
                "tienda": {"daily_delta": "100"},
            },
        }
        for day in range(12, 19)
    ]

    monkeypatch.setattr(
        service,
        "load_first_store_income_dates_bulk",
        lambda _canons: {
            "VILLAS_DEL_REY": date(2020, 1, 1),
        },
    )
    monkeypatch.setattr(
        service,
        "build_branch_income_projection_summary",
        lambda **_kwargs: {
            "status": "available",
            "method": "existing_stable_historical_pace",
            "projected_close": "1000",
            "historical_progress_pct_at_cutoff": "80",
            "historical_months": 4,
            "confidence": "alta",
        },
    )
    monkeypatch.setattr(
        service,
        "build_bajas_historical_progress_curve",
        lambda **_kwargs: {
            "status": "available",
            "method": "chain_daily_median_share_of_month_close",
            "points": {
                18: {
                    "day": 18,
                    "samples_count": 42,
                    "p25": Decimal("0.45"),
                    "median": Decimal("0.50"),
                    "p75": Decimal("0.55"),
                }
            },
        },
    )
    monkeypatch.setattr(
        service,
        "_load_operational_forecast_histories_bulk",
        lambda **_kwargs: {
            "VILLAS_DEL_REY": {
                "history": history,
                "missing_dates": [],
            }
        },
    )

    excel_bytes = service.build_track_daily_mart_excel(
        track_date=track_date,
        generation_mode="manual_preview",
        resolved_version=resolved_version,
        rows=[row],
    )

    workbook = load_workbook(
        BytesIO(excel_bytes),
        data_only=False,
    )

    legacy = workbook["Forecast"]
    assert legacy["W4"].value == (
        "=IFERROR((T4/18)*12,0)+IFERROR((U4/18)*12,0)"
    )

    sensitized = workbook[service.SENSITIZED_FORECAST_SHEET]
    assert sensitized["C4"].value == "VILLAS DEL REY"

    assert sensitized["D4"].value == 800
    assert sensitized["E4"].value == 1000
    assert sensitized["F4"].value == 1200
    assert sensitized["G4"].value == -200

    assert sensitized["H4"].value == 100
    assert sensitized["I4"].value == 220
    assert sensitized["J4"].value == 300
    assert sensitized["K4"].value == -80

    assert sensitized["L4"].value == 200
    assert sensitized["M4"].value == 296
    assert sensitized["N4"].value == 400
    assert sensitized["O4"].value == -104

    assert sensitized["P4"].value == 50
    assert sensitized["Q4"].value == 100
    assert sensitized["R4"].value == 70
    assert sensitized["S4"].value == 30

    assert sensitized["T4"].value == 3000
    assert sensitized["U4"].value == 4200
    assert sensitized["V4"].value == 5000
    assert sensitized["W4"].value == -800

    total_row = next(
        row_idx
        for row_idx in range(1, sensitized.max_row + 1)
        if sensitized[f"C{row_idx}"].value == "TOTAL GENERAL"
    )
    assert sensitized[f"E{total_row}"].value == 1000
    assert sensitized[f"I{total_row}"].value == 220
    assert sensitized[f"Q{total_row}"].value == 100
    assert sensitized[f"U{total_row}"].value == 4200

    info = workbook["Info"]
    assert info["H2"].value == "Métodos del Forecast Sensibilizado"
    assert info["H10"].value == (
        "Soporte de forecast de ingresos por sucursal"
    )
    assert info["H12"].value == "VILLAS DEL REY"
    assert info["J12"].value == "existing_stable_historical_pace"
    assert info["M12"].value == 0.8
    assert info["M12"].number_format == service.PERCENT_FORMAT

    assert info["T2"].value == (
        "Ventana reciente de deltas (7 días calendario)"
    )
    assert info["T4"].value == "VILLAS DEL REY"
    assert info["U4"].value == "2026-09-12"
    assert info["Y4"].value == 10
    assert info["Z4"].value == 8
    assert info["AA4"].value == 100
