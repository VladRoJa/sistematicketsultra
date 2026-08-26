from datetime import date, datetime
from decimal import Decimal

import pytest

from app.warehouse.services import (
    socios_activos_repository as repository,
)


def _valid_row():
    return {
        "row_index": 0,
        "source_row_number": 1,
        "id_socio": "987654",
        "pin": "123",
        "nombre": "PERSONA PRUEBA",
        "sucursal_raw": "SUCURSAL TEST",
        "fecha_ultimo_pago_local": (
            datetime(2026, 8, 20, 10, 30, 0)
        ),
        "fecha_vencimiento_local": (
            datetime(2026, 9, 20, 23, 59, 59)
        ),
        "fecha_vencimiento_date": (
            date(2026, 9, 20)
        ),
        "fecha_ingreso_local": (
            datetime(2025, 1, 15, 8, 0, 0)
        ),
        "fecha_firma_local": None,
        "tarifa": "MENSUAL",
        "importe_tarifa": Decimal("599"),
        "lada_raw": "686",
        "telefono_raw": "6861234567",
        "telefono_digits": "6861234567",
        "aplica_kpi_raw": "Si",
        "aplica_kpi": True,
        "email_raw": "persona@example.com",
        "row_hash": "a" * 64,
    }


def test_normalize_row_accepts_valid_socios_activos_row():
    normalized = repository._normalize_row(
        _valid_row()
    )

    assert normalized["id_socio"] == "987654"
    assert normalized["pin"] == "123"

    assert (
        normalized["fecha_vencimiento_date"]
        == date(2026, 9, 20)
    )

    assert (
        normalized["importe_tarifa"]
        == Decimal("599")
    )

    assert normalized["aplica_kpi_raw"] == "Si"
    assert normalized["aplica_kpi"] is True


def test_normalize_row_accepts_non_kpi_active_member():
    row = _valid_row()

    row["aplica_kpi_raw"] = "No"
    row["aplica_kpi"] = False

    normalized = repository._normalize_row(
        row
    )

    assert normalized["aplica_kpi_raw"] == "No"
    assert normalized["aplica_kpi"] is False


def test_normalize_row_rejects_aplica_kpi_mismatch():
    row = _valid_row()

    row["aplica_kpi_raw"] = "No"
    row["aplica_kpi"] = True

    with pytest.raises(
        ValueError,
        match=(
            "aplica_kpi no coincide "
            "con aplica_kpi_raw"
        ),
    ):
        repository._normalize_row(
            row
        )


def test_normalize_row_rejects_expiration_date_mismatch():
    row = _valid_row()

    row["fecha_vencimiento_date"] = (
        date(2026, 9, 21)
    )

    with pytest.raises(
        ValueError,
        match=(
            "fecha_vencimiento_date "
            "no coincide"
        ),
    ):
        repository._normalize_row(
            row
        )


def test_normalize_parsed_snapshot_requires_consistent_counts():
    payload = {
        "rows": [
            _valid_row(),
        ],
        "row_count_detected": 2,
        "row_count_valid": 1,
        "row_count_rejected": 0,
    }

    with pytest.raises(
        ValueError,
        match=(
            "row_count_detected "
            "debe ser igual"
        ),
    ):
        repository._normalize_parsed_snapshot(
            payload
        )


def test_repository_rejects_wrong_report_type_before_db():
    with pytest.raises(
        ValueError,
        match=(
            "report_type_key no corresponde "
            "a socios_activos"
        ),
    ):
        repository.persist_socios_activos_snapshot(
            warehouse_upload_id=1,
            report_type_key="socios_vencidos",
            cutoff_date="2026-08-25",
            captured_at=(
                "2026-08-25T10:00:00+00:00"
            ),
            snapshot_kind="daily",
            is_canonical=False,
            parsed_snapshot={
                "rows": [],
                "row_count_detected": 0,
                "row_count_valid": 0,
                "row_count_rejected": 0,
            },
        )
