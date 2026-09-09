from io import BytesIO
from types import SimpleNamespace as NS
from zipfile import ZipFile

from openpyxl import load_workbook

from app.services import marketing_campaign_export_service as export_service


def _recipient(phone, branch):
    return {
        "phone_mx10": phone,
        "sucursal": branch,
    }


def test_single_branch_exports_direct_xlsx(monkeypatch):
    monkeypatch.setattr(
        export_service,
        "get_marketing_reactivation_campaign",
        lambda **kwargs: {
            "id": 7,
            "name": "Campaña septiembre",
            "recipients": [
                _recipient("6861000002", "VILLAS DEL REY"),
                _recipient("6861000001", "VILLAS DEL REY"),
            ],
        },
    )
    guarded_calls = []
    monkeypatch.setattr(
        export_service,
        "_validate_and_mark_exported",
        lambda **kwargs: guarded_calls.append(kwargs) or (b"ignored", "ignored.xlsx"),
    )

    data, filename = export_service.export_marketing_reactivation_campaign(
        campaign_id=7,
        allowed_sucursal_keys=("VILLAS DEL REY",),
        session=NS(),
    )

    assert filename == "CAMPANA_SEPTIEMBRE__VILLAS_DEL_REY.xlsx"
    assert export_service.campaign_export_mimetype(filename).endswith("sheet")
    assert list(load_workbook(BytesIO(data)).active.values) == [
        ("telefono",),
        ("6861000001",),
        ("6861000002",),
    ]
    assert guarded_calls[0]["campaign_id"] == 7


def test_multiple_branches_export_zip_with_summary(monkeypatch):
    monkeypatch.setattr(
        export_service,
        "get_marketing_reactivation_campaign",
        lambda **kwargs: {
            "id": 9,
            "name": "Vencidos agosto 2026",
            "recipients": [
                _recipient("6861000001", "VILLAS DEL REY"),
                _recipient("6861000002", "VILLALTA"),
                _recipient("6861000003", "VILLALTA"),
                _recipient("6861000004", "METEPEC"),
            ],
        },
    )
    monkeypatch.setattr(
        export_service,
        "_validate_and_mark_exported",
        lambda **kwargs: (b"ignored", "ignored.xlsx"),
    )

    data, filename = export_service.export_marketing_reactivation_campaign(
        campaign_id=9,
        session=NS(),
    )

    assert filename == "VENCIDOS_AGOSTO_2026.zip"
    assert export_service.campaign_export_mimetype(filename) == "application/zip"
    with ZipFile(BytesIO(data)) as archive:
        assert set(archive.namelist()) == {
            "VENCIDOS_AGOSTO_2026__METEPEC.xlsx",
            "VENCIDOS_AGOSTO_2026__VILLALTA.xlsx",
            "VENCIDOS_AGOSTO_2026__VILLAS_DEL_REY.xlsx",
            "RESUMEN.xlsx",
        }
        villalta = load_workbook(BytesIO(archive.read(
            "VENCIDOS_AGOSTO_2026__VILLALTA.xlsx"
        )))
        assert list(villalta.active.values) == [
            ("telefono",),
            ("6861000002",),
            ("6861000003",),
        ]
        summary = load_workbook(BytesIO(archive.read("RESUMEN.xlsx")))
        assert list(summary.active.values) == [
            ("sucursal", "contactos"),
            ("METEPEC", 1),
            ("VILLALTA", 2),
            ("VILLAS DEL REY", 1),
            ("TOTAL", 4),
        ]


def test_export_package_never_rebuilds_campaign_audience(monkeypatch):
    monkeypatch.setattr(
        export_service,
        "get_marketing_reactivation_campaign",
        lambda **kwargs: {
            "id": 11,
            "name": "Prueba",
            "recipients": [_recipient("6861000001", "CENTRO")],
        },
    )
    called = []
    monkeypatch.setattr(
        export_service,
        "_validate_and_mark_exported",
        lambda **kwargs: called.append(kwargs) or (b"ignored", "ignored.xlsx"),
    )

    export_service.export_marketing_reactivation_campaign(
        campaign_id=11,
        session=NS(),
    )

    assert len(called) == 1
    assert called[0]["campaign_id"] == 11
