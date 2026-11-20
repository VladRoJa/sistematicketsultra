from dataclasses import replace
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from openpyxl import Workbook, load_workbook
import pytest

from app.warehouse.services.iventas_activity_export_service import (
    IventasActivityExportError,
    write_iventas_activity_xlsx,
)
from app.warehouse.jobs import iventas_activity_hourly_job as hourly_job
from app.warehouse.services.socios_activos_parser import SociosActivosParseResult
from app.warehouse.services.venta_total_parser import (
    EXPECTED_VENTA_TOTAL_RAW_COLUMNS,
    parse_venta_total_xlsx,
)


def _venta_total(tmp_path):
    source = tmp_path / "venta-total.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(("Reporte Venta Total",))
    sheet.append((*EXPECTED_VENTA_TOTAL_RAW_COLUMNS, "Telefono", "IDSocio"))

    def append(member_id, description, kind, new=None, status="ACTIVO", phone="6860000000"):
        total = 0 if kind == "Sin costo" else 549
        sheet.append([
            sheet.max_row - 1, "18-11-26", "TEC MXL", "folio", "clave", "producto",
            description, 1, total, total, 0, 0, total, "EFECTIVO", status,
            None, "recepcion", "10:00", None, None, None, None, None, new, kind,
            phone, member_id,
        ])

    append(20, "PASE 1 DIAS GRATIS", "Sin costo")
    append(20, "ESTUDIANTE", "Mensual sin contrato", "Nuevo", "FACTURADO")
    append(20, "ESTUDIANTE", "Mensual sin contrato", "Nuevo", "FACTURADO")
    append(20, "ESTUDIANTE", "Mensual sin contrato", "Renovación")
    append(21, "PASE RECORRIDO", "Sin costo")
    append(22, "PASE 2 DIAS GRATIS", "Sin costo")
    append(23, "1 MES $899", "Mensual sin contrato", "Nuevo", "CANCELADO")
    append(24, "PASE TOTAL PASS", "Otro")
    append(25, "RENTA TRIMESTRAL", "Locker", "Nuevo")
    append(26, "PASE RECORRIDO", "Sin costo", phone=None)
    append(None, "PASE RECORRIDO", "Sin costo")
    workbook.save(source)
    return parse_venta_total_xlsx(file_path=str(source))


@pytest.mark.parametrize("exclude, expected_members", [(False, [20, 20, 21, 22]), (True, [20, 21, 22])])
def test_iventas_export_applies_filters_and_keeps_layout(tmp_path, exclude, expected_members):
    sales = _venta_total(tmp_path)
    output = tmp_path / "iventas.xlsx"
    active_cutoff = date(2026, 11, 19)
    active_members = SociosActivosParseResult(rows=(
        SimpleNamespace(id_socio="20", tarifa="ESTUDIANTE", fecha_vencimiento_date=date(2026, 12, 19)),
        SimpleNamespace(id_socio="20", tarifa="ESTUDIANTE", fecha_vencimiento_date=active_cutoff),
        SimpleNamespace(id_socio="21", tarifa="PASE RECORRIDO", fecha_vencimiento_date=active_cutoff),
    ))

    result = write_iventas_activity_xlsx(
        sales=sales, active_members=active_members, sales_cutoff=date(2026, 11, 18),
        active_cutoff=active_cutoff, output_path=output, exclude_passes_for_current_members=exclude,
    )

    workbook = load_workbook(output, read_only=True, data_only=True)
    try:
        assert workbook.sheetnames == ["Hoja1"]
        headings, *rows = workbook.active.iter_rows(max_col=6, values_only=True)
        assert headings == ("Fecha", "Sucursal", "Descripcion", "Telefono", "IDSocio", "Fecha Vencimiento")
        assert [row[4] for row in rows] == expected_members
        expiry_by_member = {20: "19-12-26", 21: "19-11-26", 22: None}
        assert [row[5] for row in rows] == [expiry_by_member[member] for member in expected_members]
        assert [row for row in rows if row[2] == "ESTUDIANTE"] == [
            ("18-11-26", "TEC MXL", "ESTUDIANTE", "6860000000", 20, "19-12-26"),
        ]
    finally:
        workbook.close()
    assert result["passes_with_current_membership"] == 1
    assert result["passes_excluded"] == int(exclude)
    assert result["new_sales"] == 1
    assert result["rows_without_valid_phone"] == result["rows_without_valid_member_id"] == 1


def test_export_requires_source_member_id_column(tmp_path):
    sales = _venta_total(tmp_path)
    sales.header_columns = EXPECTED_VENTA_TOTAL_RAW_COLUMNS
    with pytest.raises(IventasActivityExportError, match="IDSocio"):
        write_iventas_activity_xlsx(
            sales=sales, active_members=SociosActivosParseResult(), sales_cutoff=date(2026, 11, 18),
            active_cutoff=date(2026, 11, 19), output_path=tmp_path / "iventas.xlsx",
        )


def test_delta_only_exports_new_movements_even_if_registered_with_an_older_date(tmp_path):
    sales = _venta_total(tmp_path)
    baseline_path = tmp_path / "baseline.xlsx"
    settings = {
        "active_members": SociosActivosParseResult(rows=(
            SimpleNamespace(id_socio="20", tarifa="ESTUDIANTE", fecha_vencimiento_date=date(2026, 12, 19)),
        )),
        "sales_cutoff": date(2026, 11, 19),
        "active_cutoff": date(2026, 11, 19),
    }
    baseline = write_iventas_activity_xlsx(
        sales=sales, output_path=baseline_path, known_movements=set(), baseline_only=True,
        **settings,
    )
    assert len(baseline["movement_keys"]) == 4
    assert not baseline_path.exists()

    sales.rows[0] = replace(sales.rows[0], telefono="6861111111")
    sales.rows.append(replace(sales.rows[0], folio="new-folio", fecha="17-11-26"))
    output = tmp_path / "delta.xlsx"
    result = write_iventas_activity_xlsx(
        sales=sales, output_path=output, known_movements=set(baseline["movement_keys"]),
        **settings,
    )
    assert result["rows"] == 1
    workbook = load_workbook(output, read_only=True)
    try:
        assert list(workbook.active.values)[1:] == [
            ("17-11-26", "TEC MXL", "PASE 1 DIAS GRATIS", "6861111111", 20, "19-12-26"),
        ]
    finally:
        workbook.close()


def test_hourly_job_only_replaces_export_after_successful_active_capture(tmp_path, monkeypatch):
    business_date = datetime.now(ZoneInfo("America/Tijuana")).date()
    output = tmp_path / "result.xlsx"
    output.write_bytes(b"previous complete export")
    full_output = tmp_path / "acumulado_1600.xlsx"
    full_output.write_bytes(b"previous hourly accumulation")
    sales = _venta_total(tmp_path)
    sales.rows = [replace(row, fecha=business_date.strftime("%d-%m-%y")) for row in sales.rows]
    snapshot = SimpleNamespace(id=10, business_date=business_date)
    query = SimpleNamespace(filter_by=lambda **kwargs: SimpleNamespace(one_or_none=lambda: snapshot))
    monkeypatch.setattr(hourly_job, "VentaTotalSnapshotORM", SimpleNamespace(query=query))
    monkeypatch.setattr(hourly_job, "db", SimpleNamespace(session=SimpleNamespace(remove=lambda: None)))
    monkeypatch.setattr(hourly_job, "load_warehouse_upload", lambda **kwargs: {
        "report_type_key": "venta_total",
        "date_from": business_date.replace(day=1), "date_to": business_date,
        "storage_path": str(tmp_path / "venta-total.xlsx"),
    })
    monkeypatch.setattr(hourly_job, "parse_venta_total_xlsx", lambda **kwargs: sales)

    def fail_capture(**kwargs):
        raise RuntimeError("capture failed")

    monkeypatch.setattr(hourly_job, "capture_socios_activos_xlsx", fail_capture)
    with pytest.raises(RuntimeError, match="capture failed"):
        hourly_job.run_job(venta_total_upload_id=42, output_path=output, full_output_path=full_output)
    assert output.read_bytes() == b"previous complete export"
    assert full_output.read_bytes() == b"previous hourly accumulation"
    assert not list(tmp_path.glob(".iventas-*"))

    captures = []

    def capture(*, output_path, business_date):
        captures.append(business_date)
        output_path.write_bytes(b"socios activos")

    monkeypatch.setattr(hourly_job, "capture_socios_activos_xlsx", capture)
    monkeypatch.setattr(hourly_job, "parse_socios_activos_xlsx", lambda **kwargs: SociosActivosParseResult())
    result = hourly_job.run_job(
        venta_total_upload_id=42, output_path=output, full_output_path=full_output,
        known_movements=set(),
    )
    assert result["venta_total_snapshot_id"] == 10
    assert result["full_rows"] == result["rows"] == 4
    assert captures == [business_date]
    assert output.read_bytes().startswith(b"PK")
    workbook = load_workbook(full_output, read_only=True)
    try:
        assert workbook.properties.identifier == full_output.name
    finally:
        workbook.close()
    assert not list(tmp_path.glob(".iventas-*"))
