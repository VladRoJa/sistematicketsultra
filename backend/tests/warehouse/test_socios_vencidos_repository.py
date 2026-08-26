from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.warehouse.services.socios_vencidos_repository as repository


CAPTURED_AT = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)


def _parsed_snapshot(
    *,
    pin: str = "PIN-FICTICIO",
    branch: str = "SUCURSAL FICTICIA",
    expiration: datetime = datetime(2026, 8, 23, 14, 25, 51),
    edad_raw: int | None = 30,
    edad: int | None = 30,
    edad_status: str = "VALID",
) -> dict[str, object]:
    return {
        "rows": [
            {
                "row_index": 0,
                "source_row_number": 1,
                "pin": pin,
                "nombre": "PERSONA FICTICIA",
                "genero": "F",
                "edad_raw": edad_raw,
                "edad": edad,
                "edad_status": edad_status,
                "fecha_vencimiento_local": expiration,
                "fecha_vencimiento_date": expiration.date(),
                "fecha_ultimo_pago_local": None,
                "tarifa": "TARIFA FICTICIA",
                "correo_raw": "persona@example.invalid",
                "telefono_raw": "6641234567",
                "telefono_digits": "6641234567",
                "sucursal_raw": branch,
                "adeudo": Decimal("999.00"),
                "row_hash": "a" * 64,
            }
        ],
        "row_count_detected": 1,
        "row_count_valid": 1,
        "row_count_rejected": 0,
    }


class _FakeSession:
    def __init__(self, *, fail_on_flush: int | None = None):
        self.fail_on_flush = fail_on_flush
        self.flush_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self.snapshots: list[object] = []
        self.rows: list[object] = []

    def add(self, value):
        self.snapshots.append(value)

    def add_all(self, values):
        self.rows.extend(values)

    def flush(self):
        self.flush_calls += 1
        if self.flush_calls == self.fail_on_flush:
            raise RuntimeError("falla ficticia")

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


def _install_fake_orm(
    monkeypatch: pytest.MonkeyPatch,
    session: _FakeSession,
):
    next_snapshot_id = iter(range(91, 200))

    class FakeSnapshot:
        def __init__(self, **kwargs):
            self.id = next(next_snapshot_id)
            vars(self).update(kwargs)

    class FakeRow:
        def __init__(self, **kwargs):
            vars(self).update(kwargs)

    monkeypatch.setattr(
        repository,
        "db",
        SimpleNamespace(session=session),
    )
    monkeypatch.setattr(
        repository,
        "SociosVencidosSnapshotORM",
        FakeSnapshot,
    )
    monkeypatch.setattr(
        repository,
        "SociosVencidosSnapshotRowORM",
        FakeRow,
    )


def _persist(
    *,
    warehouse_upload_id: int,
    parsed_snapshot: dict[str, object],
    date_from: date = date(2026, 8, 23),
    date_to: date = date(2026, 8, 23),
):
    return repository.persist_socios_vencidos_snapshot(
        warehouse_upload_id=warehouse_upload_id,
        report_type_key="socios_vencidos",
        date_from=date_from,
        date_to=date_to,
        captured_at=CAPTURED_AT,
        parsed_snapshot=parsed_snapshot,
    )


def test_new_upload_inserts_snapshot_and_rows_atomically(monkeypatch):
    session = _FakeSession()
    _install_fake_orm(monkeypatch, session)
    monkeypatch.setattr(
        repository,
        "_find_snapshot_by_upload",
        lambda **_: None,
    )

    result = _persist(
        warehouse_upload_id=101,
        parsed_snapshot=_parsed_snapshot(),
    )

    assert result["status"] == "ingested"
    assert result["was_idempotent"] is False
    assert result["rows_inserted"] == 1
    assert session.commit_calls == 1
    assert session.rollback_calls == 0
    assert session.rows[0].pin == "PIN-FICTICIO"


def test_same_upload_is_idempotent_with_zero_rows_inserted(monkeypatch):
    session = _FakeSession()
    existing = SimpleNamespace(
        id=91,
        warehouse_upload_id=101,
        report_type_key="socios_vencidos",
        date_from=date(2026, 8, 23),
        date_to=date(2026, 8, 23),
        captured_at=CAPTURED_AT,
        row_count_detected=1,
        row_count_valid=1,
        row_count_rejected=0,
    )
    monkeypatch.setattr(
        repository,
        "db",
        SimpleNamespace(session=session),
    )
    monkeypatch.setattr(
        repository,
        "_find_snapshot_by_upload",
        lambda **_: existing,
    )

    result = _persist(
        warehouse_upload_id=101,
        parsed_snapshot=_parsed_snapshot(),
    )

    assert result["status"] == "already_ingested"
    assert result["was_idempotent"] is True
    assert result["rows_inserted"] == 0
    assert session.commit_calls == 0


def test_distinct_uploads_preserve_same_pin_in_different_branches(
    monkeypatch,
):
    session = _FakeSession()
    _install_fake_orm(monkeypatch, session)
    monkeypatch.setattr(
        repository,
        "_find_snapshot_by_upload",
        lambda **_: None,
    )

    first = _persist(
        warehouse_upload_id=101,
        parsed_snapshot=_parsed_snapshot(branch="SUCURSAL A"),
    )
    second = _persist(
        warehouse_upload_id=102,
        parsed_snapshot=_parsed_snapshot(branch="SUCURSAL B"),
    )

    assert first["snapshot_id"] != second["snapshot_id"]
    assert [row.pin for row in session.rows] == [
        "PIN-FICTICIO",
        "PIN-FICTICIO",
    ]
    assert [row.sucursal_raw for row in session.rows] == [
        "SUCURSAL A",
        "SUCURSAL B",
    ]


def test_distinct_uploads_preserve_same_pin_with_different_expiration_dates(
    monkeypatch,
):
    session = _FakeSession()
    _install_fake_orm(monkeypatch, session)
    monkeypatch.setattr(
        repository,
        "_find_snapshot_by_upload",
        lambda **_: None,
    )

    _persist(
        warehouse_upload_id=101,
        parsed_snapshot=_parsed_snapshot(
            expiration=datetime(2026, 8, 23, 10, 0)
        ),
        date_from=date(2026, 8, 23),
        date_to=date(2026, 8, 23),
    )
    _persist(
        warehouse_upload_id=102,
        parsed_snapshot=_parsed_snapshot(
            expiration=datetime(2026, 8, 24, 10, 0)
        ),
        date_from=date(2026, 8, 24),
        date_to=date(2026, 8, 24),
    )

    assert [row.fecha_vencimiento_date for row in session.rows] == [
        date(2026, 8, 23),
        date(2026, 8, 24),
    ]


def test_failure_rolls_back_snapshot_and_rows(monkeypatch):
    session = _FakeSession(fail_on_flush=2)
    _install_fake_orm(monkeypatch, session)
    monkeypatch.setattr(
        repository,
        "_find_snapshot_by_upload",
        lambda **_: None,
    )

    with pytest.raises(repository.SociosVencidosRepositoryError):
        _persist(
            warehouse_upload_id=101,
            parsed_snapshot=_parsed_snapshot(),
        )

    assert session.commit_calls == 0
    assert session.rollback_calls == 1


def test_out_of_range_age_is_persisted_as_quality_issue_not_rejection(
    monkeypatch,
):
    session = _FakeSession()
    _install_fake_orm(monkeypatch, session)
    monkeypatch.setattr(
        repository,
        "_find_snapshot_by_upload",
        lambda **_: None,
    )

    result = _persist(
        warehouse_upload_id=101,
        parsed_snapshot=_parsed_snapshot(
            edad_raw=-7974,
            edad=None,
            edad_status="INVALID_OUT_OF_RANGE",
        ),
    )

    assert result["status"] == "ingested"
    assert result["row_count_valid"] == 1
    assert result["row_count_rejected"] == 0
    assert session.rows[0].edad_raw == -7974
    assert session.rows[0].edad is None
    assert session.rows[0].edad_status == "INVALID_OUT_OF_RANGE"


def test_invalid_date_range_is_rejected_before_persistence(monkeypatch):
    lookup_calls = 0

    def lookup(**_):
        nonlocal lookup_calls
        lookup_calls += 1
        return None

    monkeypatch.setattr(
        repository,
        "_find_snapshot_by_upload",
        lookup,
    )

    with pytest.raises(ValueError, match="posterior"):
        _persist(
            warehouse_upload_id=101,
            parsed_snapshot=_parsed_snapshot(),
            date_from=date(2026, 8, 24),
            date_to=date(2026, 8, 23),
        )

    assert lookup_calls == 0
