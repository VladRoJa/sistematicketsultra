from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.warehouse.services.ventas_nuevos_socios_detalle_repository as repository
from app.warehouse.services.ventas_nuevos_socios_detalle_canonicality_resolver import (
    resolve_ventas_nuevos_socios_detalle_canonicality,
)


def _parsed_row() -> dict[str, object]:
    return {
        "row_index": 2,
        "row_hash": "a" * 64,
        "id_socio": "123456",
        "pin": "12345",
        "sucursal_raw": "PASEO 2000",
        "sucursal_id": 7,
        "nombre": "NOMBRE",
        "apellido_paterno": "PATERNO",
        "apellido_materno": "MATERNO",
        "lada": "686",
        "telefono": "1234567",
        "domicilio": None,
        "genero": "Masculino",
        "fecha_nacimiento": date(2000, 1, 1),
        "email": "persona@example.com",
        "fecha_creacion_at": datetime(
            2026,
            7,
            1,
            15,
            0,
            tzinfo=timezone.utc,
        ),
        "inscripcion": "Inscripcion $99",
        "tipo_membresia": "No Forzoso",
        "tarifa": "DOMICILIADO SIN PLAZO $599",
        "total": Decimal("599.00"),
        "fecha_pago_at": datetime(
            2026,
            7,
            1,
            15,
            5,
            tzinfo=timezone.utc,
        ),
        "fecha_renovacion_at": datetime(
            2026,
            8,
            1,
            6,
            59,
            59,
            tzinfo=timezone.utc,
        ),
        "fecha_firma_contrato_at": None,
        "tipo_pago_code": 2,
        "tipo_tarjeta_code": None,
        "lugar_pago": "Sucursal",
        "id_folio": "12345678901234567890",
        "pase": None,
        "anfitrion": None,
        "total_pagado": Decimal("599.00"),
        "quality_flags": (
            "BRANCH_NOT_RESOLVED",
        ),
    }


def _parsed_snapshot() -> dict[str, object]:
    return {
        "rows": [_parsed_row()],
        "rejected_rows": [],
        "row_count": 1,
        "row_count_valid": 1,
        "row_count_rejected": 0,
        "quality_flag_counts": {
            "BRANCH_NOT_RESOLVED": 1,
        },
        "metadata": {
            "sheet_name": "Socios",
            "source_timezone": "America/Tijuana",
        },
    }


class _FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def execute(self, *args, **kwargs):
        raise AssertionError(
            "No se esperaba advisory lock."
        )


def test_persist_new_snapshot(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = _FakeSession()

    monkeypatch.setattr(
        repository,
        "db",
        SimpleNamespace(session=fake_session),
    )

    monkeypatch.setattr(
        repository,
        "_fetch_existing_snapshot_by_upload",
        lambda **_: None,
    )

    monkeypatch.setattr(
        repository,
        "_resolve_canonicality_decision",
        lambda **_: {
            "is_canonical": False,
            "replace_existing_canonical": False,
            "existing_canonical_snapshot": None,
            "existing_canonical_snapshot_id": None,
            "reason": "canonicality_not_configured",
        },
    )

    captured_header: dict[str, object] = {}
    captured_rows: dict[str, object] = {}

    def fake_insert_header(**kwargs):
        captured_header.update(kwargs)

        return SimpleNamespace(
            id=91,
            warehouse_upload_id=kwargs[
                "warehouse_upload_id"
            ],
            report_type_key=kwargs[
                "report_type_key"
            ],
            business_date=kwargs[
                "business_date"
            ],
            date_from=kwargs["date_from"],
            date_to=kwargs["date_to"],
            captured_at=kwargs["captured_at"],
            snapshot_kind=kwargs[
                "snapshot_kind"
            ],
            is_canonical=kwargs["is_canonical"],
            row_count_detected=kwargs[
                "row_count_detected"
            ],
            row_count_valid=kwargs[
                "row_count_valid"
            ],
            row_count_rejected=kwargs[
                "row_count_rejected"
            ],
            metadata_json=kwargs["metadata"],
        )

    def fake_insert_rows(**kwargs):
        captured_rows.update(kwargs)
        return len(kwargs["rows"])

    monkeypatch.setattr(
        repository,
        "_insert_snapshot_header",
        fake_insert_header,
    )

    monkeypatch.setattr(
        repository,
        "_insert_snapshot_rows",
        fake_insert_rows,
    )

    result = (
        repository
        .persist_ventas_nuevos_socios_detalle_snapshot(
            warehouse_upload_id=12134,
            report_type_key=(
                "ventas_nuevos_socios_detalle"
            ),
            business_date=date(2026, 7, 27),
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 27),
            captured_at=datetime(
                2026,
                7,
                27,
                15,
                30,
                tzinfo=timezone.utc,
            ),
            snapshot_kind="month_to_date",
            parsed_snapshot=_parsed_snapshot(),
            requested_by="routine-control",
            ingestion_source="automated_pipeline",
        )
    )

    assert result["status"] == "ingested"
    assert result["was_idempotent"] is False
    assert result["snapshot_id"] == 91
    assert result["rows_inserted"] == 1
    assert result["is_canonical"] is False

    assert captured_header["date_from"] == date(
        2026,
        7,
        1,
    )

    assert captured_header["date_to"] == date(
        2026,
        7,
        27,
    )

    assert (
        captured_header["business_date"]
        == captured_header["date_to"]
    )

    assert captured_rows["snapshot_id"] == 91
    assert len(captured_rows["rows"]) == 1

    assert fake_session.commit_calls == 1
    assert fake_session.rollback_calls == 0


def test_existing_upload_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = _FakeSession()

    monkeypatch.setattr(
        repository,
        "db",
        SimpleNamespace(session=fake_session),
    )

    existing_snapshot = SimpleNamespace(
        id=45,
        warehouse_upload_id=12134,
        report_type_key=(
            "ventas_nuevos_socios_detalle"
        ),
        business_date=date(2026, 7, 27),
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 27),
        captured_at=datetime(
            2026,
            7,
            27,
            15,
            30,
            tzinfo=timezone.utc,
        ),
        snapshot_kind="month_to_date",
        is_canonical=False,
        row_count_detected=1942,
        row_count_valid=1942,
        row_count_rejected=0,
        metadata_json={
            "sheet_name": "Socios",
        },
    )

    monkeypatch.setattr(
        repository,
        "_fetch_existing_snapshot_by_upload",
        lambda **_: existing_snapshot,
    )

    result = (
        repository
        .persist_ventas_nuevos_socios_detalle_snapshot(
            warehouse_upload_id=12134,
            report_type_key=(
                "ventas_nuevos_socios_detalle"
            ),
            business_date=date(2026, 7, 27),
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 27),
            captured_at=datetime(
                2026,
                7,
                27,
                15,
                30,
                tzinfo=timezone.utc,
            ),
            snapshot_kind="month_to_date",
            parsed_snapshot=_parsed_snapshot(),
        )
    )

    assert result["status"] == "already_ingested"
    assert result["was_idempotent"] is True
    assert result["snapshot_id"] == 45
    assert result["rows_inserted"] is None

    assert fake_session.commit_calls == 0
    assert fake_session.rollback_calls == 0


def test_business_date_must_equal_date_to():
    with pytest.raises(
        repository
        .VentasNuevosSociosDetalleRepositoryError,
        match="business_date debe ser igual",
    ):
        (
            repository
            .persist_ventas_nuevos_socios_detalle_snapshot(
                warehouse_upload_id=12134,
                report_type_key=(
                    "ventas_nuevos_socios_detalle"
                ),
                business_date=date(2026, 7, 26),
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 27),
                captured_at=datetime(
                    2026,
                    7,
                    27,
                    15,
                    30,
                    tzinfo=timezone.utc,
                ),
                snapshot_kind="month_to_date",
                parsed_snapshot=_parsed_snapshot(),
            )
        )


def test_count_mismatch_is_rejected():
    invalid_snapshot = _parsed_snapshot()
    invalid_snapshot["row_count"] = 2

    with pytest.raises(
        repository
        .VentasNuevosSociosDetalleRepositoryError,
        match="valid \\+ rejected",
    ):
        (
            repository
            .persist_ventas_nuevos_socios_detalle_snapshot(
                warehouse_upload_id=12134,
                report_type_key=(
                    "ventas_nuevos_socios_detalle"
                ),
                business_date=date(2026, 7, 27),
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 27),
                captured_at=datetime(
                    2026,
                    7,
                    27,
                    15,
                    30,
                    tzinfo=timezone.utc,
                ),
                snapshot_kind="month_to_date",
                parsed_snapshot=invalid_snapshot,
            )
        )



def test_repository_passes_quality_to_real_canonicality_resolver(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        repository,
        "_fetch_existing_canonical_snapshot",
        lambda **_: None,
    )

    result = repository._resolve_canonicality_decision(
        business_date=date(2026, 7, 27),
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 27),
        snapshot_kind="month_to_date",
        captured_at=datetime(
            2026,
            7,
            27,
            17,
            37,
            tzinfo=timezone.utc,
        ),
        row_count_valid=1942,
        row_count_rejected=0,
        canonicality_resolver=(
            resolve_ventas_nuevos_socios_detalle_canonicality
        ),
    )

    assert result["is_canonical"] is True
    assert (
        result["replace_existing_canonical"]
        is False
    )
    assert (
        result["reason"]
        == "first_snapshot_for_business_date"
    )
