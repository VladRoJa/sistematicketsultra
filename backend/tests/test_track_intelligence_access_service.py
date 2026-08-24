from types import SimpleNamespace

import pytest

from app.track_alerts.services.track_intelligence_access_service import (
    TrackIntelligenceAuthorizationError,
    resolve_track_intelligence_access,
)


@pytest.mark.parametrize(
    "role",
    [
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
        "LECTOR_GLOBAL",
        "GERENTE_REGIONAL",
    ],
)
def test_global_roles_receive_global_track_intelligence_access(role):
    access = resolve_track_intelligence_access(
        SimpleNamespace(
            rol=role,
            sucursal_id=None,
        )
    )

    assert access.scope == "global"
    assert access.is_global is True
    assert access.primary_branch_id is None
    assert access.role == role


def test_gerente_is_restricted_to_primary_branch_scope():
    access = resolve_track_intelligence_access(
        SimpleNamespace(
            rol="GERENTE",
            sucursal_id=123,
        )
    )

    assert access.scope == "manager"
    assert access.is_global is False
    assert access.primary_branch_id == 123
    assert access.role == "GERENTE"


def test_gerente_without_primary_branch_is_rejected():
    with pytest.raises(
        TrackIntelligenceAuthorizationError,
        match="sucursal primaria válida",
    ):
        resolve_track_intelligence_access(
            SimpleNamespace(
                rol="GERENTE",
                sucursal_id=None,
            )
        )


@pytest.mark.parametrize(
    "role",
    [
        "SISTEMAS",
        "GERENCIA DEPORTIVA",
        "MARKETING",
        "TIENDA",
        "RECEPCION",
        "",
    ],
)
def test_other_track_read_roles_do_not_gain_operational_intelligence(role):
    with pytest.raises(
        TrackIntelligenceAuthorizationError,
        match="No autorizado",
    ):
        resolve_track_intelligence_access(
            SimpleNamespace(
                rol=role,
                sucursal_id=1,
            )
        )


def test_missing_user_is_rejected():
    with pytest.raises(
        TrackIntelligenceAuthorizationError,
        match="Usuario no encontrado",
    ):
        resolve_track_intelligence_access(None)
