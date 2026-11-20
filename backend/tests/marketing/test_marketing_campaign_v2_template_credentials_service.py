from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from app.services import marketing_campaign_v2_template_credentials_service as service


HEADERS = ('sucursal', 'CORREO', 'contraseña')
EMAIL = 'qa@example.test'
PASSWORD = ' qa-example-password '


@pytest.fixture
def workbook(tmp_path, monkeypatch):
    path = tmp_path / 'accesos.xlsx'
    monkeypatch.setenv(service.CREDENTIALS_FILE_ENV, str(path))

    branches = {'TEC MXL': 4, 'Tecnológico': 4, 'VILLAS DEL REY': 1}

    class BranchResolver:
        def __init__(self, *, session=None):
            pass

        def resolve(self, label):
            branch_id = branches.get(label)
            return None if branch_id is None else SimpleNamespace(sucursal_id=branch_id)

    monkeypatch.setattr(service, 'CampaignV2DispatchBranchResolver', BranchResolver)

    def write_workbook(rows, *, second_matching_sheet=False):
        book = Workbook()
        book.active.append(['portada'])
        sheet = book.create_sheet('Accesos de sucursales')
        for row in rows:
            sheet.append(row)
        if second_matching_sheet:
            book.create_sheet('Copia').append(HEADERS)
        book.save(path)
        book.close()
        return path

    return write_workbook


def test_reads_excel_keys_by_suite_branch_and_preserves_password(workbook):
    workbook([
        HEADERS,
        (' TEC MXL ', f' {EMAIL} ', PASSWORD),
        (None, None, None),
        ('VILLAS DEL REY', 'villas@example.test', 'second-example-password'),
    ])

    credentials = service.load_iventas_template_credentials()

    assert sorted(credentials) == [1, 4]
    assert credentials[4].email == EMAIL
    assert credentials[4].password == PASSWORD
    assert EMAIL not in repr(credentials)
    assert PASSWORD not in repr(credentials)


@pytest.mark.parametrize(
    ('rows', 'expected_error'),
    [
        ([('TEC MXL', EMAIL, None)], 'Fila 2'),
        ([('SIN ALIAS', EMAIL, PASSWORD)], 'sucursal activa única'),
        ([('TEC MXL', EMAIL, PASSWORD), ('Tecnológico', EMAIL, PASSWORD)], 'Fila 3'),
    ],
)
def test_rejects_invalid_rows_without_revealing_login(workbook, rows, expected_error):
    workbook([HEADERS, *rows])

    with pytest.raises(service.IventasTemplateCredentialsError, match=expected_error) as error:
        service.load_iventas_template_credentials()

    assert EMAIL not in str(error.value)
    assert PASSWORD not in str(error.value)


def test_rejects_two_matching_sheets(workbook):
    workbook([HEADERS], second_matching_sheet=True)

    with pytest.raises(service.IventasTemplateCredentialsError, match='más de una pestaña'):
        service.load_iventas_template_credentials()


def test_missing_file_has_sanitized_error(workbook):
    path = workbook([HEADERS])
    path.unlink()

    with pytest.raises(service.IventasTemplateCredentialsError, match='No fue posible leer') as error:
        service.load_iventas_template_credentials()

    assert str(path) not in str(error.value)
