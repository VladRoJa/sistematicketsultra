from types import SimpleNamespace

from app.utils.system_daily_check_access import (
    has_system_daily_check_mvp_access,
)


def _user(*, username="user", rol="GERENTE", department_id=10):
    return SimpleNamespace(
        username=username,
        rol=rol,
        department_id=department_id,
    )


def test_sistemas_role_is_allowed_case_insensitively():
    assert has_system_daily_check_mvp_access(
        _user(rol="sistemas")
    ) is True


def test_admicorp_username_is_allowed_case_insensitively():
    assert has_system_daily_check_mvp_access(
        _user(username="admicorp", rol="ADMINISTRADOR")
    ) is True


def test_tecnico_in_sistemas_department_is_not_implicitly_allowed():
    assert has_system_daily_check_mvp_access(
        _user(rol="TECNICO", department_id=7)
    ) is False


def test_generic_department_seven_user_is_not_implicitly_allowed():
    assert has_system_daily_check_mvp_access(
        _user(rol="USUARIO", department_id=7)
    ) is False


def test_administrator_is_not_implicitly_allowed():
    assert has_system_daily_check_mvp_access(
        _user(rol="ADMINISTRADOR")
    ) is False


def test_gerente_is_not_allowed_during_mvp():
    assert has_system_daily_check_mvp_access(
        _user(rol="GERENTE")
    ) is False


def test_none_is_not_allowed():
    assert has_system_daily_check_mvp_access(None) is False
