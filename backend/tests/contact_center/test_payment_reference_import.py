import csv
from pathlib import Path

import pytest

from app.services.contact_center_payment_reference_service import (
    PaymentReferenceImportError,
    iter_reference_rows,
    normalize_name_key,
    normalize_pin_key,
    validate_payment_reference_csv,
)


HEADERS = ["ID Socio", "Nombre", "PIN", "Sucursal", "Estado"]


def _write(path: Path, rows, headers=HEADERS):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_normalization_accepts_accents_spaces_punctuation_and_leading_pin_zeros():
    assert normalize_name_key("  José-María   PÉREZ  ") == "JOSE MARIA PEREZ"
    assert normalize_pin_key("000123.0") == "123"
    assert normalize_pin_key("not-a-pin") is None


def test_offline_csv_preflight_counts_rows_without_side_effects(tmp_path):
    path = tmp_path / "padron.csv"
    _write(path, [
        {"ID Socio": "00012", "Nombre": "José Pérez", "PIN": "00987",
         "Sucursal": "SEND MXL", "Estado": "Vencido"},
        {"ID Socio": "453", "Nombre": "Ana Gómez", "PIN": "23",
         "Sucursal": "VILLAS DEL REY", "Estado": "Activo"},
    ])
    result = validate_payment_reference_csv(path)
    assert result.row_count == 2
    assert result.active_at_cutoff == 1
    assert result.expired_at_cutoff == 1
    assert len(result.source_sha256) == 64
    rows = list(iter_reference_rows(path))
    assert rows[0]["member_id"] == "00012"
    assert rows[0]["pin_key"] == "987"
    assert rows[0]["name_key"] == "JOSE PEREZ"
    assert rows[0]["status_at_cutoff"] == "VENCIDO"


@pytest.mark.parametrize("invalid", [
    [
        {"ID Socio": "100", "Nombre": "José Pérez", "PIN": "0007",
         "Sucursal": "SEND MXL", "Estado": "Vencido"},
        {"ID Socio": "101", "Nombre": "JOSE-PEREZ", "PIN": "7",
         "Sucursal": "PASEO 2000", "Estado": "Vencido"},
    ],
    [
        {"ID Socio": "100", "Nombre": "Ana Pérez", "PIN": "123",
         "Sucursal": "SEND MXL", "Estado": "Vencido"},
        {"ID Socio": "100", "Nombre": "Ana López", "PIN": "456",
         "Sucursal": "PASEO 2000", "Estado": "Vencido"},
    ],
    [
        {"ID Socio": "bad-id", "Nombre": "Ana Pérez", "PIN": "123",
         "Sucursal": "SEND MXL", "Estado": "Vencido"},
    ],
    [
        {"ID Socio": "100", "Nombre": "Ana Pérez", "PIN": "123",
         "Sucursal": "SEND MXL", "Estado": "UNKNOWN"},
    ],
])
def test_rejects_conflicts_duplicate_ids_or_invalid_identity(tmp_path, invalid):
    path = tmp_path / "padron.csv"
    _write(path, invalid)
    with pytest.raises(PaymentReferenceImportError):
        validate_payment_reference_csv(path)


def test_rejects_missing_required_column(tmp_path):
    path = tmp_path / "padron.csv"
    _write(path, [{"Nombre": "Ana"}], headers=["Nombre"])
    with pytest.raises(PaymentReferenceImportError):
        validate_payment_reference_csv(path)


def test_rejects_empty_roster(tmp_path):
    path = tmp_path / "padron.csv"
    _write(path, [])
    with pytest.raises(PaymentReferenceImportError):
        validate_payment_reference_csv(path)
