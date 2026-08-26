from types import SimpleNamespace

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
