from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from app.warehouse.services import agregadoras_consolidado_export_service as service


def _acc(visits: int, amount: str, *raw_names: str):
    return service._AccumulatedBranch(
        visits=visits,
        amount=Decimal(amount),
        raw_names=tuple(raw_names),
    )


def _minimal_sheet(last_column: str) -> bytes:
    mc_ns = service.XML_NAMESPACES["mc"]
    x14ac_ns = service.XML_NAMESPACES["x14ac"]
    xr_ns = service.XML_NAMESPACES["xr"]
    xr2_ns = service.XML_NAMESPACES["xr2"]
    xr3_ns = service.XML_NAMESPACES["xr3"]

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet
  xmlns="{service.SPREADSHEET_NS}"
  xmlns:mc="{mc_ns}"
  xmlns:x14ac="{x14ac_ns}"
  xmlns:xr="{xr_ns}"
  xmlns:xr2="{xr2_ns}"
  xmlns:xr3="{xr3_ns}"
  mc:Ignorable="x14ac xr xr2 xr3">
  <dimension ref="A1:{last_column}1"/>
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>Header</t></is></c>
    </row>
  </sheetData>
  <autoFilter ref="A1:{last_column}1"/>
</worksheet>
""".encode("utf-8")

def _minimal_workbook() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(service.SHEET_WELLHUB, _minimal_sheet("E"))
        archive.writestr(service.SHEET_TOTALPASS, _minimal_sheet("E"))
        archive.writestr(service.SHEET_TODO, _minimal_sheet("F"))
        archive.writestr(service.SHEET_CATALOGOS, _minimal_sheet("C"))
        archive.writestr(
            service.TABLE_TODO,
            f"""<?xml version="1.0" encoding="UTF-8"?>
<table xmlns="{service.SPREADSHEET_NS}" ref="A1:F1">
  <autoFilter ref="A1:F1"/>
</table>
""".encode("utf-8"),
        )
        archive.writestr(
            service.PIVOT_CACHE_DEFINITION,
            f"""<?xml version="1.0" encoding="UTF-8"?>
<pivotCacheDefinition xmlns="{service.SPREADSHEET_NS}"/>
""".encode("utf-8"),
        )
        archive.writestr(
            "xl/charts/chart1.xml",
            b"<chart>must-remain-byte-identical</chart>",
        )
        archive.writestr(
            service.CALC_CHAIN,
            (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<calcChain xmlns="{service.SPREADSHEET_NS}">'
                f'<c r="F2" i="3"/>'
                f'</calcChain>'
            ).encode("utf-8"),
        )
        archive.writestr(
            service.WORKBOOK_RELS,
            b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId13"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/calcChain"
    Target="calcChain.xml"/>
</Relationships>
""",
        )
        archive.writestr(
            service.CONTENT_TYPES,
            b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Override PartName="/xl/calcChain.xml"
    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.calcChain+xml"/>
</Types>
""",
        )
    return buffer.getvalue()


def test_daily_delta_builds_only_incremental_values():
    rows = service._daily_delta(
        previous={
            "A": _acc(10, "100.00", "Ultra - A"),
        },
        current={
            "A": _acc(12, "130.00", "Ultra - A"),
            "B": _acc(3, "20.00", "Ultra - B"),
        },
        business_date=date(2026, 9, 29),
        aggregator_code="WH",
        template_catalog={
            ("ultra - a", "WH"): "Sucursal A",
        },
        track_labels={
            "A": "Track A",
            "B": "Sucursal B",
        },
    )

    assert [(row.branch_name, row.visits, row.amount) for row in rows] == [
        ("Sucursal A", 2, Decimal("30.00")),
        ("Sucursal B", 3, Decimal("20.00")),
    ]


def test_daily_delta_rejects_mtd_regression():
    with pytest.raises(service.AgregadorasSourceRegressionError):
        service._daily_delta(
            previous={
                "A": _acc(10, "100.00", "Ultra - A"),
            },
            current={
                "A": _acc(9, "99.00", "Ultra - A"),
            },
            business_date=date(2026, 9, 29),
            aggregator_code="TP",
            template_catalog={},
            track_labels={"A": "Sucursal A"},
        )


def test_render_workbook_only_rewrites_expected_parts():
    template = _minimal_workbook()
    original_parts = {}

    with ZipFile(BytesIO(template), "r") as archive:
        for name in archive.namelist():
            original_parts[name] = archive.read(name)

    result = service._render_workbook(
        template_bytes=template,
        wellhub_rows=[
            service.AgregadoraDailyRow(
                business_date=date(2026, 9, 29),
                branch_name="Sucursal A",
                visits=5,
                amount=Decimal("245.00"),
            )
        ],
        totalpass_rows=[
            service.AgregadoraDailyRow(
                business_date=date(2026, 9, 29),
                branch_name="Sucursal B",
                visits=4,
                amount=Decimal("320.50"),
            )
        ],
    )

    with ZipFile(BytesIO(result), "r") as archive:
        assert archive.read("xl/charts/chart1.xml") == original_parts[
            "xl/charts/chart1.xml"
        ]

        table_xml = archive.read(service.TABLE_TODO).decode("utf-8")
        assert 'ref="A1:F3"' in table_xml

        pivot_xml = archive.read(
            service.PIVOT_CACHE_DEFINITION
        ).decode("utf-8")
        assert 'refreshOnLoad="1"' in pivot_xml
        assert 'enableRefresh="1"' in pivot_xml

        wellhub_xml = archive.read(
            service.SHEET_WELLHUB
        ).decode("utf-8")
        totalpass_xml = archive.read(
            service.SHEET_TOTALPASS
        ).decode("utf-8")
        todo_xml = archive.read(
            service.SHEET_TODO
        ).decode("utf-8")

        assert 'ref="A1:E2"' in wellhub_xml
        assert 'ref="A1:E2"' in totalpass_xml
        assert 'ref="A1:F3"' in todo_xml
        assert "Sucursal A" in wellhub_xml
        assert "Sucursal B" in totalpass_xml
        assert "Wellhub" in todo_xml
        assert "Totalpass" in todo_xml
        assert 'TEXT(Tabla1[[#This Row],[Fecha]],"dd")' in todo_xml

        for worksheet_xml in (wellhub_xml, totalpass_xml, todo_xml):
            assert 'xmlns:xr2="' in worksheet_xml
            assert 'xmlns:xr3="' in worksheet_xml
            assert 'mc:Ignorable="x14ac xr xr2 xr3"' in worksheet_xml

        assert service.CALC_CHAIN not in archive.namelist()

        workbook_rels = archive.read(
            service.WORKBOOK_RELS
        ).decode("utf-8")
        content_types = archive.read(
            service.CONTENT_TYPES
        ).decode("utf-8")

        assert "calcChain" not in workbook_rels
        assert "/xl/calcChain.xml" not in content_types

def _source_sheet(rows: list[tuple[date, str, int, str]]) -> bytes:
    xml_rows = [
        """<row r="1">
          <c r="A1" t="inlineStr"><is><t>Fecha</t></is></c>
          <c r="B1" t="inlineStr"><is><t>Sucursal</t></is></c>
          <c r="D1" t="inlineStr"><is><t>Visitas</t></is></c>
          <c r="E1" t="inlineStr"><is><t>Pago</t></is></c>
        </row>"""
    ]
    for index, (business_date, branch, visits, amount) in enumerate(
        rows,
        start=2,
    ):
        xml_rows.append(
            f"""<row r="{index}">
              <c r="A{index}"><v>{service._excel_serial(business_date)}</v></c>
              <c r="B{index}" t="inlineStr"><is><t>{branch}</t></is></c>
              <c r="D{index}"><v>{visits}</v></c>
              <c r="E{index}"><v>{amount}</v></c>
            </row>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="{service.SPREADSHEET_NS}">
  <dimension ref="A1:E{len(rows) + 1}"/>
  <sheetData>
    {''.join(xml_rows)}
  </sheetData>
</worksheet>
""".encode("utf-8")


def test_template_month_state_uses_template_as_cutoff_baseline():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            service.SHEET_WELLHUB,
            _source_sheet(
                [
                    (date(2026, 7, 31), "Sucursal A", 100, "1000.00"),
                    (date(2026, 8, 1), "Sucursal A", 2, "20.00"),
                    (date(2026, 8, 19), "Sucursal A", 3, "30.00"),
                    (date(2026, 8, 20), "Sucursal A", 99, "990.00"),
                ]
            ),
        )

    state = service._template_month_state(
        buffer.getvalue(),
        sheet_name=service.SHEET_WELLHUB,
        baseline_date=date(2026, 8, 19),
    )

    assert state["sucursal a"].visits == 5
    assert state["sucursal a"].amount == Decimal("50.00")


def test_snapshot_gap_is_absorbed_when_same_month_has_later_snapshot():
    baseline = date(2026, 8, 19)
    target = date(2026, 8, 21)
    snapshots = {
        date(2026, 8, 21): SimpleNamespace(id=21),
    }

    absorbed, unrecoverable = service._classify_snapshot_gaps(
        baseline_date=baseline,
        target_date=target,
        snapshots=snapshots,
    )

    assert absorbed == [date(2026, 8, 20)]
    assert unrecoverable == []


def test_daily_rows_use_template_baseline_and_assign_gap_to_next_snapshot():
    snapshots = {
        date(2026, 8, 21): SimpleNamespace(id=21),
    }
    states = {
        21: {
            "A": _acc(15, "150.00", "Ultra - A"),
        }
    }

    rows = service._build_daily_rows_from_snapshots(
        baseline_date=date(2026, 8, 19),
        target_date=date(2026, 8, 21),
        snapshots=snapshots,
        template_baseline={
            "A": _acc(10, "100.00", "Sucursal A"),
        },
        state_loader=lambda snapshot_id: states[snapshot_id],
        aggregator_code="WH",
        template_catalog={
            ("ultra - a", "WH"): "Sucursal A",
        },
        track_labels={"A": "Sucursal A"},
    )

    assert [
        (
            row.business_date,
            row.branch_name,
            row.visits,
            row.amount,
        )
        for row in rows
    ] == [
        (
            date(2026, 8, 21),
            "Sucursal A",
            5,
            Decimal("50.00"),
        )
    ]

def test_resolve_upload_file_path_includes_stored_filename(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        service,
        "_uploads_root",
        lambda: tmp_path,
    )
    upload = SimpleNamespace(
        stored_path="uploads/warehouse/manual/agregadoras/2026/08",
        stored_filename="plantilla.xlsx",
    )

    resolved = service._resolve_upload_file_path(upload)

    assert resolved == (
        tmp_path
        / "uploads"
        / "warehouse"
        / "manual"
        / "agregadoras"
        / "2026"
        / "08"
        / "plantilla.xlsx"
    ).resolve()

def test_excel_date_from_cell_accepts_spanish_text_date():
    assert service._excel_date_from_cell("29/07/2026") == date(2026, 7, 29)

def test_canonicalize_template_baseline_uses_track_aliases(monkeypatch):
    monkeypatch.setattr(
        service,
        "_track_aliases_by_normalized_raw",
        lambda *, source_family: {
            "ultra - insurgentes sur": "INSURGENTES",
        },
    )

    result = service._canonicalize_template_baseline(
        template_baseline={
            "insurgentes sur": _acc(
                791,
                "46680.00",
                "Insurgentes Sur",
            ),
        },
        aggregator_code="WH",
        source_family="wellhub_family",
        template_catalog={
            ("ultra - insurgentes sur", "WH"): "Insurgentes Sur",
        },
        track_labels={
            "INSURGENTES": "Insurgentes",
        },
    )

    assert result == {
        "INSURGENTES": _acc(
            791,
            "46680.00",
            "Insurgentes Sur",
        ),
    }

def test_canonicalize_template_baseline_matches_historical_suffix_aliases(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "_track_aliases_by_normalized_raw",
        lambda *, source_family: {
            "ultra - insurgentes sur": "INSURGENTES",
            "ultragym san luis río colorado": "SAN_LUIS",
        },
    )

    result = service._canonicalize_template_baseline(
        template_baseline={
            "insurgentes sur": _acc(
                791,
                "46680.00",
                "Insurgentes Sur",
            ),
            "san luis rio colorado": _acc(
                378,
                "17640.00",
                "San Luis Rio Colorado",
            ),
        },
        aggregator_code="WH",
        source_family="wellhub_family",
        template_catalog={
            ("ultra - insurgentes sur", "WH"): "Insurgentes",
            ("ultra - san luis rio colorado", "WH"): "San Luis",
        },
        track_labels={
            "INSURGENTES": "Insurgentes",
            "SAN_LUIS": "San Luis",
        },
    )

    assert result == {
        "INSURGENTES": _acc(
            791,
            "46680.00",
            "Insurgentes Sur",
        ),
        "SAN_LUIS": _acc(
            378,
            "17640.00",
            "San Luis Rio Colorado",
        ),
    }

def test_daily_delta_allows_negative_wellhub_corrections():
    rows = service._daily_delta(
        previous={
            "METEPEC": _acc(777, "44940.00", "Ultra - Metepec"),
        },
        current={
            "METEPEC": _acc(775, "44700.00", "Ultra - Metepec"),
        },
        business_date=date(2026, 8, 23),
        aggregator_code="WH",
        template_catalog={},
        track_labels={"METEPEC": "Metepec"},
    )

    assert [
        (
            row.branch_name,
            row.visits,
            row.amount,
        )
        for row in rows
    ] == [
        (
            "Metepec",
            -2,
            Decimal("-240.00"),
        )
    ]


def test_daily_delta_still_rejects_negative_totalpass_corrections():
    with pytest.raises(service.AgregadorasSourceRegressionError):
        service._daily_delta(
            previous={
                "METEPEC": _acc(777, "44940.00", "Totalpass Metepec"),
            },
            current={
                "METEPEC": _acc(775, "44700.00", "Totalpass Metepec"),
            },
            business_date=date(2026, 8, 23),
            aggregator_code="TP",
            template_catalog={},
            track_labels={"METEPEC": "Metepec"},
        )

