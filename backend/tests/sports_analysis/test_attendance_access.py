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
