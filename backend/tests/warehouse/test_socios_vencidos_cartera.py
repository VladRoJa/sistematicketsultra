from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.warehouse import SociosVencidosCarteraORM
import app.warehouse.services.socios_vencidos_repository as repository
import app.warehouse.services.socios_vencidos_current_status_resolver as current_resolver
from app.warehouse.services.socios_vencidos_cartera_sync_service import (
    SociosVencidosCarteraSyncError,
    backfill_socios_vencidos_cartera,
    iter_calendar_month_ranges,
    sync_socios_vencidos_daily,
)


def _row(
    *,
    branch: str = "SUCURSAL ÁLAMO",
    expiration: date = date(2026, 8, 23),
    row_hash: str = "a" * 64,
    phone: str = "6641234567",
    email: str = "persona@example.invalid",
):
    return repository._normalize_row({
        "row_index": 0,
        "source_row_number": 1,
        "pin": "12345",
        "nombre": "PERSONA FICTICIA",
        "genero": "F",
        "edad_raw": 30,
        "edad": 30,
        "edad_status": "VALID",
        "fecha_vencimiento_local": datetime.combine(
            expiration, datetime.min.time()
        ),
        "fecha_vencimiento_date": expiration,
        "fecha_ultimo_pago_local": None,
        "tarifa": "ANUAL",
        "correo_raw": email,
        "telefono_raw": phone,
        "telefono_digits": phone,
        "sucursal_raw": branch,
        "adeudo": Decimal("10.00"),
        "row_hash": row_hash,
    })


class _FakeCartera:
    def __init__(self, **kwargs):
        vars(self).update(kwargs)


class _FakeSession:
    def __init__(self, store):
        self.store = store
        self.flush_calls = 0

    def add(self, value):
        key = (value.sucursal_key, value.pin, value.fecha_vencimiento_date)
        self.store[key] = value

    def flush(self):
        self.flush_calls += 1


@pytest.fixture
def cartera_store(monkeypatch):
    store = {}
    monkeypatch.setattr(repository, "SociosVencidosCarteraORM", _FakeCartera)
    monkeypatch.setattr(
        repository,
        "_read_existing_cartera_rows",
        lambda *, rows, session: {
            key: store[key]
            for key in {repository._cartera_episode_key(row) for row in rows}
            if key in store
        },
    )
    return store


def test_new_episode_insert_and_same_episode_existing(cartera_store):
    session = _FakeSession(cartera_store)
    observed = datetime(2026, 8, 24, tzinfo=timezone.utc)

    first = repository._upsert_cartera_rows(
        snapshot_id=1,
        observed_at=observed,
        rows=[_row()],
        session=session,
    )
    stored = next(iter(cartera_store.values()))
    second_seen = datetime(2026, 8, 25, tzinfo=timezone.utc)
    second = repository._upsert_cartera_rows(
        snapshot_id=2,
        observed_at=second_seen,
        rows=[_row()],
        session=session,
    )

    assert first == {"inserted": 1, "updated": 0, "existing": 0}
    assert second == {"inserted": 0, "updated": 0, "existing": 1}
    assert len(cartera_store) == 1
    assert stored.first_seen_at == observed
    assert stored.first_source_snapshot_id == 1
    assert stored.last_seen_at == second_seen
    assert stored.last_source_snapshot_id == 2


def test_mutable_contact_change_updates_without_duplicate(cartera_store):
    session = _FakeSession(cartera_store)
    repository._upsert_cartera_rows(
        snapshot_id=1,
        observed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        rows=[_row()],
        session=session,
    )
    result = repository._upsert_cartera_rows(
        snapshot_id=2,
        observed_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        rows=[_row(
            row_hash="b" * 64,
            phone="6649999999",
            email="actualizado@example.invalid",
        )],
        session=session,
    )

    stored = next(iter(cartera_store.values()))
    assert result == {"inserted": 0, "updated": 1, "existing": 0}
    assert len(cartera_store) == 1
    assert stored.telefono_raw == "6649999999"
    assert stored.correo_raw == "actualizado@example.invalid"


def test_older_observation_does_not_replace_latest_episode_data(cartera_store):
    session = _FakeSession(cartera_store)
    latest_seen = datetime(2026, 8, 25, tzinfo=timezone.utc)
    repository._upsert_cartera_rows(
        snapshot_id=2,
        observed_at=latest_seen,
        rows=[_row(
            row_hash="b" * 64,
            phone="6649999999",
            email="reciente@example.invalid",
        )],
        session=session,
    )

    result = repository._upsert_cartera_rows(
        snapshot_id=1,
        observed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        rows=[_row()],
        session=session,
    )

    stored = next(iter(cartera_store.values()))
    assert result == {"inserted": 0, "updated": 0, "existing": 1}
    assert stored.telefono_raw == "6649999999"
    assert stored.correo_raw == "reciente@example.invalid"
    assert stored.last_seen_at == latest_seen
    assert stored.last_source_snapshot_id == 2


def test_same_pin_other_branch_or_expiration_creates_new_episode(cartera_store):
    session = _FakeSession(cartera_store)
    counts = repository._upsert_cartera_rows(
        snapshot_id=1,
        observed_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        rows=[
            _row(),
            _row(branch="SUCURSAL B"),
            _row(expiration=date(2026, 8, 24)),
        ],
        session=session,
    )

    assert counts["inserted"] == 3
    assert len(cartera_store) == 3


def test_model_has_real_episode_unique_and_required_indexes():
    episode_unique = next(
        constraint
        for constraint in SociosVencidosCarteraORM.__table__.constraints
        if constraint.name == "uq_socios_vencidos_cartera_episode"
    )
    assert tuple(column.name for column in episode_unique.columns) == (
        "sucursal_key",
        "pin",
        "fecha_vencimiento_date",
    )
    index_names = {index.name for index in SociosVencidosCarteraORM.__table__.indexes}
    assert {
        "ix_socios_vencidos_cartera_expiration_date",
        "ix_socios_vencidos_cartera_branch_expiration",
        "ix_socios_vencidos_cartera_pin",
        "ix_socios_vencidos_cartera_phone_digits",
    } <= index_names


def test_calendar_backfill_chunks_are_month_bounded():
    assert list(iter_calendar_month_ranges(
        date_from=date(2024, 1, 15),
        date_to=date(2024, 3, 2),
    )) == [
        (date(2024, 1, 15), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 2, 29)),
        (date(2024, 3, 1), date(2024, 3, 2)),
    ]


def test_backfill_stops_and_reports_exact_failed_range():
    calls = []

    def runner(**kwargs):
        calls.append((kwargs["date_from"], kwargs["date_to"]))
        if kwargs["date_from"] == date(2024, 2, 1):
            raise RuntimeError("fallo simulado")
        return {
            "ingestion_status": "ingested",
            "snapshot_id": 91,
            "ingestion_metadata": {},
        }

    with pytest.raises(
        SociosVencidosCarteraSyncError,
        match="fallo simulado",
    ) as captured:
        backfill_socios_vencidos_cartera(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 3, 31),
            job_runner=runner,
        )

    assert captured.value.last_successful_range == (
        date(2024, 1, 1),
        date(2024, 1, 31),
    )
    assert captured.value.failed_range == (
        date(2024, 2, 1),
        date(2024, 2, 29),
    )
    assert calls == [
        (date(2024, 1, 1), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 2, 29)),
    ]


def test_daily_sync_requests_only_business_date():
    calls = []

    def runner(**kwargs):
        calls.append(kwargs)
        return {
            "ingestion_status": "ingested",
            "snapshot_id": 91,
            "ingestion_metadata": {"cartera_inserted": 1},
        }

    sync_socios_vencidos_daily(
        business_date=date(2026, 8, 27),
        job_runner=runner,
    )
    assert calls[0]["date_from"] == date(2026, 8, 27)
    assert calls[0]["date_to"] == date(2026, 8, 27)


class _SeedQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_):
        return self

    def order_by(self, *_):
        return self

    def all(self):
        return list(self.rows)


class _SeedSession:
    def __init__(self, snapshot, rows):
        self.snapshot = snapshot
        self.rows = rows
        self.commit_calls = 0
        self.rollback_calls = 0

    def query(self, model):
        if model is repository.SociosVencidosSnapshotORM:
            return _SeedQuery([self.snapshot])
        if model is repository.SociosVencidosSnapshotRowORM:
            return _SeedQuery(self.rows)
        raise AssertionError(model)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


def test_seed_from_existing_snapshot_is_idempotent(monkeypatch):
    normalized = _row()
    snapshot = SimpleNamespace(
        id=1,
        captured_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
    )
    snapshot_row = SimpleNamespace(**{
        key: value
        for key, value in normalized.items()
        if key != "sucursal_key"
    })
    session = _SeedSession(snapshot, [snapshot_row])
    stored_keys = set()

    def fake_upsert(*, rows, **_):
        inserted = 0
        existing = 0
        for row in rows:
            key = repository._cartera_episode_key(row)
            if key in stored_keys:
                existing += 1
            else:
                stored_keys.add(key)
                inserted += 1
        return {"inserted": inserted, "updated": 0, "existing": existing}

    monkeypatch.setattr(repository, "_upsert_cartera_rows", fake_upsert)
    first = repository.seed_socios_vencidos_cartera_from_existing_snapshots(
        snapshot_id=1,
        session=session,
    )
    second = repository.seed_socios_vencidos_cartera_from_existing_snapshots(
        snapshot_id=1,
        session=session,
    )

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["existing"] == 1
    assert len(stored_keys) == 1


class _PeriodQuery:
    def __init__(self, rows):
        self.rows = rows
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def order_by(self, *_):
        return self

    def all(self):
        return list(self.rows)


class _PeriodSession:
    def __init__(self, cartera_rows, activos_rows):
        self.cartera_rows = cartera_rows
        self.activos_rows = activos_rows
        self.queries = []

    def query(self, model):
        rows = (
            self.cartera_rows
            if model is SociosVencidosCarteraORM
            else self.activos_rows
        )
        query = _PeriodQuery(rows)
        self.queries.append((model, query))
        return query


def test_current_status_period_filters_cartera_in_sql(monkeypatch):
    session = _PeriodSession(
        cartera_rows=[SimpleNamespace(
            id=10,
            sucursal_raw="CENTRO",
            pin="123",
            telefono_digits=None,
            correo_raw=None,
        )],
        activos_rows=[SimpleNamespace(
            id_socio="A-1",
            sucursal_raw="CENTRO",
            pin="123",
            telefono_digits=None,
            email_raw=None,
        )],
    )
    monkeypatch.setattr(
        current_resolver,
        "_resolve_activos_snapshot",
        lambda **_: SimpleNamespace(
            id=8,
            cutoff_date=date(2026, 8, 24),
        ),
    )

    result = current_resolver.resolve_socios_vencidos_current_status_for_period(
        date_from=date(2026, 8, 23),
        date_to=date(2026, 8, 24),
        session=session,
    )

    cartera_query = session.queries[0][1]
    sql = str(
        select(SociosVencidosCarteraORM)
        .where(*cartera_query.criteria)
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "between '2026-08-23' and '2026-08-24'" in sql
    assert result.total_rows == 1
    assert result.status_counts["ACTIVE_CONFIRMED"] == 1
