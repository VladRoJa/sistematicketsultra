from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace as NS
from zipfile import ZipFile

from openpyxl import load_workbook
import pytest

from app.services import marketing_campaign_v2_delivery_export_service as service


def _recipient(
    phone: str,
    branch: str,
    family: str,
    name: str,
    tariff: str,
):
    return NS(
        id=int(phone[-3:]),
        phone_mx10=phone,
        member_name=name,
        sucursal=branch,
        audience_family=family,
        tarifa_raw=tariff,
    )


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *args):
        return _Query(self.rows)


def test_single_branch_segment_exports_one_xlsx(monkeypatch):
    rows = [
        _recipient(
            "6861000002",
            "VILLAS DEL REY",
            "DOMICILIADO",
            "ROSA",
            "DOMICILIADO 12 MESES $649 HE",
        ),
        _recipient(
            "6861000001",
            "VILLAS DEL REY",
            "DOMICILIADO",
            "ANA",
            "MENSUALIDAD",
        ),
    ]
    monkeypatch.setattr(
        service,
        "get_campaign_v2",
        lambda **kwargs: {"id": 7, "name": "QA Octubre"},
    )

    data, filename = service.export_campaign_v2_delivery_package(
        campaign_id=7,
        allowed_sucursal_keys=("VILLAS_DEL_REY",),
        session=_Session(rows),
    )

    assert filename == "QA_OCTUBRE__VILLAS_DEL_REY__DOMICILIADO.xlsx"
    assert service.campaign_v2_delivery_export_mimetype(filename).endswith("sheet")
    assert list(load_workbook(BytesIO(data)).active.values) == [
        ("telefono", "nombre", "sucursal", "tarifa"),
        (
            "6861000001",
            "ANA LOPEZ",
            "VILLAS DEL REY",
            "MENSUALIDAD",
        ),
        (
            "6861000002",
            "ROSA MARIA",
            "VILLAS DEL REY",
            "DOMICILIADO 12 MESES $649 HE",
        ),
    ]


def test_multiple_branch_segment_groups_export_zip_with_summary(monkeypatch):
    rows = [
        _recipient(
            "6861000001",
            "VILLAS DEL REY",
            "DOMICILIADO",
            "ANA LOPEZ",
            "MENSUALIDAD",
        ),
        _recipient(
            "6861000002",
            "VILLAS DEL REY",
            "CONVENIO",
            "JUAN PEREZ",
            "CONVENIO EMPRESAS",
        ),
        _recipient(
            "6861000003",
            "TECNOLOGICO",
            "ESTUDIANTE",
            "LUIS GARCIA",
            "COBACH $399",
        ),
        _recipient(
            "6861000004",
            "TECNOLOGICO",
            "ESTUDIANTE",
            "SOFIA RAMIREZ",
            "ESTUDIANTE $599",
        ),
    ]
    monkeypatch.setattr(
        service,
        "get_campaign_v2",
        lambda **kwargs: {"id": 9, "name": "Reactivacion octubre"},
    )

    data, filename = service.export_campaign_v2_delivery_package(
        campaign_id=9,
        allowed_sucursal_keys=None,
        session=_Session(rows),
    )

    assert filename == "REACTIVACION_OCTUBRE.zip"
    assert service.campaign_v2_delivery_export_mimetype(filename) == "application/zip"

    with ZipFile(BytesIO(data)) as archive:
        assert set(archive.namelist()) == {
            "REACTIVACION_OCTUBRE__TECNOLOGICO__ESTUDIANTE.xlsx",
            "REACTIVACION_OCTUBRE__VILLAS_DEL_REY__CONVENIO.xlsx",
            "REACTIVACION_OCTUBRE__VILLAS_DEL_REY__DOMICILIADO.xlsx",
            "RESUMEN.xlsx",
        }
        tecnologico = load_workbook(
            BytesIO(
                archive.read(
                    "REACTIVACION_OCTUBRE__TECNOLOGICO__ESTUDIANTE.xlsx"
                )
            )
        )
        assert list(tecnologico.active.values) == [
            ("telefono", "nombre", "sucursal", "tarifa"),
            ("6861000003", "LUIS", "TECNOLOGICO", "COBACH $399"),
            ("6861000004", "SOFIA", "TECNOLOGICO", "ESTUDIANTE $599"),
        ]

        summary = load_workbook(BytesIO(archive.read("RESUMEN.xlsx")))
        assert list(summary.active.values) == [
            ("sucursal", "segmento", "contactos"),
            ("TECNOLOGICO", "Estudiante", 2),
            ("VILLAS DEL REY", "Convenio", 1),
            ("VILLAS DEL REY", "Domiciliado", 1),
            ("TOTAL", None, 4),
        ]


def test_out_of_segment_and_missing_family_use_explicit_names():
    rows = [
        _recipient("6861000001", "METEPEC", "OUT_OF_SEGMENT", "ANA", "GYMPASS"),
        _recipient("6861000002", "METEPEC", "", "JUAN", "TARIFA RARA"),
    ]

    groups = {}
    for recipient in rows:
        branch = service._clean_text(recipient.sucursal) or "SIN SUCURSAL"
        family = service._clean_text(recipient.audience_family) or "SIN_CLASIFICAR"
        groups.setdefault((branch, family), []).append(recipient)

    data, filename = service._build_delivery_package(
        campaign_part="QA",
        groups=groups,
    )

    assert filename == "QA.zip"
    with ZipFile(BytesIO(data)) as archive:
        assert "QA__METEPEC__FUERA_DE_SEGMENTO.xlsx" in archive.namelist()
        assert "QA__METEPEC__SIN_CLASIFICAR.xlsx" in archive.namelist()



@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("JUAN CARLOS PEREZ", "JUAN"),
        ("ANA LOPEZ", "ANA"),
        ("MA CARMEN LOPEZ", "CARMEN"),
        ("MA. CARMEN LOPEZ", "CARMEN"),
        ("Mª CARMEN LOPEZ", "CARMEN"),
        ("MA DEL CARMEN LOPEZ", "CARMEN"),
        ("", ""),
        (None, ""),
    ],
)
def test_export_first_name_uses_first_useful_name(raw_name, expected):
    assert service._export_first_name(raw_name) == expected


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_delivery_export_sanitizes_formula_like_text(prefix):
    recipient = _recipient(
        "6861000001",
        f"{prefix}SUCURSAL",
        "DOMICILIADO",
        f"{prefix}NOMBRE",
        f"{prefix}TARIFA",
    )

    data = service._recipients_workbook([recipient])
    sheet = load_workbook(BytesIO(data)).active
    values = list(sheet.values)

    assert values[1] == (
        "6861000001",
        f"'{prefix}NOMBRE",
        f"'{prefix}SUCURSAL",
        f"'{prefix}TARIFA",
    )
    for cell in sheet[2]:
        assert cell.data_type != "f"
