from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.models.warehouse import SociosActivosSnapshotRowORM
from app.warehouse.services import (
    socios_vencidos_current_status_resolver
    as resolver,
)


def _active(
    *,
    id_socio,
    branch="SUCURSAL TEST",
    pin="100",
    phone=None,
    email=None,
):
    return SimpleNamespace(
        id_socio=id_socio,
        sucursal_raw=branch,
        pin=pin,
        telefono_digits=phone,
        email_raw=email,
    )


def _expired(
    *,
    row_id=1,
    branch="SUCURSAL TEST",
    pin="100",
    phone=None,
    email=None,
):
    return SimpleNamespace(
        id=row_id,
        sucursal_raw=branch,
        pin=pin,
        telefono_digits=phone,
        correo_raw=email,
    )


class _DirectedQuery:
    def __init__(self, rows):
        self.rows = rows
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def all(self):
        return self.rows


class _DirectedSession:
    def __init__(self, rows):
        self.rows = rows
        self.query_value = None

    def query(self, model):
        assert model is SociosActivosSnapshotRowORM
        self.query_value = _DirectedQuery(self.rows)
        return self.query_value


def _resolve_directed(expired, active_rows):
    session = _DirectedSession(active_rows)
    context = resolver.SociosVencidosCurrentStatusContext(
        activos_snapshot_id=8,
        activos_cutoff_date="2026-08-31",
    )
    result = resolver.resolve_socios_vencidos_rows_with_context(
        vencidos_rows=[expired],
        context=context,
        session=session,
    )[0]
    return result, session


def test_prepared_context_contains_only_snapshot_metadata(monkeypatch):
    class _MetadataOnlySession:
        def query(self, _model):
            raise AssertionError("No debe cargar filas activas al preparar contexto.")

    monkeypatch.setattr(
        resolver,
        "_resolve_activos_snapshot",
        lambda **_: SimpleNamespace(id=8, cutoff_date=date(2026, 8, 31)),
    )

    context = resolver.prepare_socios_vencidos_current_status_context(
        minimum_cutoff_date=date(2026, 8, 1),
        session=_MetadataOnlySession(),
    )

    assert context.activos_snapshot_id == 8
    assert context.activos_cutoff_date == "2026-08-31"
    assert not hasattr(context, "indexes")


@pytest.mark.parametrize(
    ("active_phone", "expired_phone"),
    [
        ("6861234567", "6861234567"),
        ("526861234567", "6861234567"),
        ("5216861234567", "6861234567"),
    ],
)
def test_directed_phone_variants_preserve_active_review(
    active_phone,
    expired_phone,
):
    result, _ = _resolve_directed(
        _expired(branch="OTRA", pin="999", phone=expired_phone),
        [_active(id_socio="A1", phone=active_phone)],
    )

    assert result.status == resolver.STATUS_ACTIVE_REVIEW
    assert result.active_id_socio == "A1"
    assert result.matched_signals == (resolver.SIGNAL_PHONE,)


def test_directed_normalized_pin_preserves_branch_pin_confirmation():
    result, _ = _resolve_directed(
        _expired(pin="100.0"),
        [_active(id_socio="A1", pin="100")],
    )

    assert result.status == resolver.STATUS_ACTIVE_CONFIRMED
    assert result.matched_signals == (resolver.SIGNAL_BRANCH_PIN,)


def test_directed_normalized_email_preserves_active_review():
    result, _ = _resolve_directed(
        _expired(branch="OTRA", pin="999", email="member@example.com"),
        [_active(id_socio="A1", email=" MEMBER@EXAMPLE.COM ")],
    )

    assert result.status == resolver.STATUS_ACTIVE_REVIEW
    assert result.matched_signals == (resolver.SIGNAL_EMAIL,)


def test_directed_phone_and_email_same_member_is_confirmed():
    result, _ = _resolve_directed(
        _expired(
            branch="OTRA",
            pin="999",
            phone="6861234567",
            email="member@example.com",
        ),
        [_active(
            id_socio="A1",
            phone="526861234567",
            email="MEMBER@EXAMPLE.COM",
        )],
    )

    assert result.status == resolver.STATUS_ACTIVE_CONFIRMED
    assert set(result.matched_signals) == {
        resolver.SIGNAL_PHONE,
        resolver.SIGNAL_EMAIL,
    }


def test_directed_phone_and_email_different_members_conflict():
    result, _ = _resolve_directed(
        _expired(
            branch="OTRA",
            pin="999",
            phone="6861234567",
            email="member@example.com",
        ),
        [
            _active(id_socio="A1", phone="6861234567"),
            _active(id_socio="A2", email="member@example.com"),
        ],
    )

    assert result.status == resolver.STATUS_IDENTIFIER_CONFLICT
    assert result.active_id_socio is None


def test_directed_duplicate_identifier_remains_ambiguous():
    result, _ = _resolve_directed(
        _expired(branch="OTRA", pin="999", phone="6861234567"),
        [
            _active(id_socio="A1", phone="6861234567"),
            _active(id_socio="A2", phone="526861234567"),
        ],
    )

    assert result.status == resolver.STATUS_AMBIGUOUS
    assert result.phone_candidate_count == 2


def test_directed_no_match_remains_not_found():
    result, _ = _resolve_directed(_expired(), [])

    assert result.status == resolver.STATUS_NOT_FOUND


def test_directed_query_is_scoped_and_uses_normalized_signals():
    _, session = _resolve_directed(
        _expired(
            pin="100.0",
            phone="6861234567",
            email=" MEMBER@EXAMPLE.COM ",
        ),
        [],
    )
    sql = str(
        select(SociosActivosSnapshotRowORM)
        .where(*session.query_value.criteria)
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "snapshot_id = 8" in sql
    assert "pin in ('100')" in sql
    assert "'6861234567'" in sql
    assert "'526861234567'" in sql
    assert "'5216861234567'" in sql
    assert "lower(btrim(socios_activos_snapshot_rows.email_raw))" in sql
    assert "'member@example.com'" in sql


def test_active_model_declares_snapshot_normalized_email_index():
    index = next(
        index
        for index in SociosActivosSnapshotRowORM.__table__.indexes
        if index.name == "ix_socios_activos_rows_snapshot_email_normalized"
    )
    sql = str(CreateIndex(index).compile(dialect=postgresql.dialect())).lower()

    assert "snapshot_id" in sql
    assert "lower(btrim(email_raw))" in sql


def test_unique_branch_pin_is_active_confirmed():
    indexes = resolver._build_active_indexes(
        [
            _active(
                id_socio="A1",
                phone="6861234567",
            )
        ]
    )

    result = resolver._resolve_vencido_row(
        _expired(
            phone=None,
            email=None,
        ),
        indexes=indexes,
    )

    assert (
        result.status
        == resolver.STATUS_ACTIVE_CONFIRMED
    )
    assert result.active_id_socio == "A1"
    assert result.matched_signals == (
        resolver.SIGNAL_BRANCH_PIN,
    )


def test_phone_and_email_agreement_is_active_confirmed():
    indexes = resolver._build_active_indexes(
        [
            _active(
                id_socio="A1",
                branch="OTRA",
                pin="999",
                phone="6861234567",
                email="test@example.com",
            )
        ]
    )

    result = resolver._resolve_vencido_row(
        _expired(
            branch="SUCURSAL TEST",
            pin="100",
            phone="6861234567",
            email="TEST@example.com",
        ),
        indexes=indexes,
    )

    assert (
        result.status
        == resolver.STATUS_ACTIVE_CONFIRMED
    )
    assert result.active_id_socio == "A1"
    assert set(
        result.matched_signals
    ) == {
        resolver.SIGNAL_PHONE,
        resolver.SIGNAL_EMAIL,
    }


def test_phone_only_is_active_review():
    indexes = resolver._build_active_indexes(
        [
            _active(
                id_socio="A1",
                branch="OTRA",
                pin="999",
                phone="6861234567",
            )
        ]
    )

    result = resolver._resolve_vencido_row(
        _expired(
            branch="SUCURSAL TEST",
            pin="100",
            phone="6861234567",
        ),
        indexes=indexes,
    )

    assert (
        result.status
        == resolver.STATUS_ACTIVE_REVIEW
    )
    assert result.active_id_socio == "A1"
    assert result.matched_signals == (
        resolver.SIGNAL_PHONE,
    )


def test_conflicting_unique_identifiers_fail_closed():
    indexes = resolver._build_active_indexes(
        [
            _active(
                id_socio="A1",
                branch="SUCURSAL TEST",
                pin="100",
            ),
            _active(
                id_socio="A2",
                branch="OTRA",
                pin="999",
                phone="6861234567",
            ),
        ]
    )

    result = resolver._resolve_vencido_row(
        _expired(
            branch="SUCURSAL TEST",
            pin="100",
            phone="6861234567",
        ),
        indexes=indexes,
    )

    assert (
        result.status
        == resolver.STATUS_IDENTIFIER_CONFLICT
    )
    assert result.active_id_socio is None


def test_ambiguous_candidates_remain_ambiguous():
    indexes = resolver._build_active_indexes(
        [
            _active(
                id_socio="A1",
                branch="SUCURSAL TEST",
                pin="100",
            ),
            _active(
                id_socio="A2",
                branch="SUCURSAL TEST",
                pin="100",
            ),
        ]
    )

    result = resolver._resolve_vencido_row(
        _expired(),
        indexes=indexes,
    )

    assert (
        result.status
        == resolver.STATUS_AMBIGUOUS
    )
    assert result.active_id_socio is None
    assert (
        result.branch_pin_candidate_count
        == 2
    )


def test_ambiguous_branch_pin_can_be_resolved_by_phone_and_email():
    indexes = resolver._build_active_indexes(
        [
            _active(
                id_socio="A1",
                branch="SUCURSAL TEST",
                pin="100",
                phone="6861111111",
                email="a1@example.com",
            ),
            _active(
                id_socio="A2",
                branch="SUCURSAL TEST",
                pin="100",
                phone="6862222222",
                email="a2@example.com",
            ),
        ]
    )

    result = resolver._resolve_vencido_row(
        _expired(
            phone="6862222222",
            email="a2@example.com",
        ),
        indexes=indexes,
    )

    assert (
        result.status
        == resolver.STATUS_ACTIVE_CONFIRMED
    )
    assert result.active_id_socio == "A2"
    assert set(
        result.matched_signals
    ) == {
        resolver.SIGNAL_PHONE,
        resolver.SIGNAL_EMAIL,
    }
    assert (
        result.branch_pin_candidate_count
        == 2
    )


def test_no_candidates_is_not_found():
    indexes = resolver._build_active_indexes(
        [
            _active(
                id_socio="A1",
                branch="OTRA",
                pin="999",
            )
        ]
    )

    result = resolver._resolve_vencido_row(
        _expired(),
        indexes=indexes,
    )

    assert (
        result.status
        == resolver.STATUS_NOT_FOUND
    )
    assert result.active_id_socio is None
