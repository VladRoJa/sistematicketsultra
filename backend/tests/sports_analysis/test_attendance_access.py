from types import SimpleNamespace

import pytest

from app.sports_analysis import attendance_access as access


def _install_user(monkeypatch, *, username: str, role: str):
    user = SimpleNamespace(
        username=username,
        rol=role,
    )
    fake_db = SimpleNamespace(
        session=SimpleNamespace(
            get=lambda model, user_id: user
        )
    )
    monkeypatch.setattr(
        access,
        "db",
        fake_db,
    )
    monkeypatch.setattr(
        access,
        "get_jwt_identity",
        lambda: "50",
    )
    return user


def test_get_current_allows_gerencia_deportiva(monkeypatch):
    user = _install_user(
        monkeypatch,
        username="GDEPORTIVA",
        role="GERENCIA DEPORTIVA",
    )

    resolved = access.get_current_sports_analysis_user()

    assert resolved is user


def test_gerencia_deportiva_scope_is_global(monkeypatch):
    user = SimpleNamespace(
        username="GDEPORTIVA",
        rol="GERENCIA DEPORTIVA",
    )
    monkeypatch.setattr(
        access,
        "list_sports_analysis_branches",
        lambda: [
            {"id": 1},
            {"id": 7},
            {"id": 25},
        ],
    )

    scope = access.resolve_sports_analysis_scope(user)

    assert scope.role == "GERENCIA DEPORTIVA"
    assert scope.is_global is True
    assert scope.allowed_branch_ids == (1, 7, 25)
    assert scope.fixed_branch_id is None


def test_get_current_rejects_unapproved_role(monkeypatch):
    _install_user(
        monkeypatch,
        username="RECEPCION",
        role="RECEPCIONISTA",
    )

    with pytest.raises(
        access.SportsAnalysisAuthorizationError
    ):
        access.get_current_sports_analysis_user()



def test_get_current_allows_manager(monkeypatch):
    user = _install_user(
        monkeypatch,
        username="GERENTE01",
        role="GERENTE",
    )

    resolved = access.get_current_sports_analysis_user()

    assert resolved is user


def test_manager_scope_is_fixed_to_primary_branch(monkeypatch):
    user = SimpleNamespace(
        username="GERENTE01",
        rol="GERENTE",
        sucursal_id=7,
        sucursales_ids=[7, 25],
    )
    monkeypatch.setattr(
        access,
        "list_sports_analysis_branches",
        lambda: [
            {"id": 1},
            {"id": 7},
            {"id": 25},
        ],
    )

    scope = access.resolve_sports_analysis_scope(user)

    assert scope.role == "GERENTE"
    assert scope.is_global is False
    assert scope.allowed_branch_ids == (7,)
    assert scope.fixed_branch_id == 7


def test_regional_scope_uses_assigned_branches(monkeypatch):
    user = SimpleNamespace(
        username="REGIONAL01",
        rol="GERENTE_REGIONAL",
        sucursal_id=1,
        sucursales_ids=[7, 25, 999],
    )
    monkeypatch.setattr(
        access,
        "list_sports_analysis_branches",
        lambda: [
            {"id": 1},
            {"id": 7},
            {"id": 25},
        ],
    )

    scope = access.resolve_sports_analysis_scope(user)

    assert scope.role == "GERENTE_REGIONAL"
    assert scope.is_global is False
    assert scope.allowed_branch_ids == (7, 25)
    assert scope.fixed_branch_id is None
