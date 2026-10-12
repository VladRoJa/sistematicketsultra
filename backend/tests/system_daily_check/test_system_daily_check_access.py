from types import SimpleNamespace

from app.utils.system_daily_check_access import (
    has_system_daily_check_mvp_access,
    has_system_daily_check_bi_access,
    has_system_daily_check_rollout_access,
)


def user(role, username):
    return SimpleNamespace(rol=role, username=username)


def test_permissions_are_separated():
    gerente = user("gerente", "gerente.sucursal")
    sistemas = user("sistemas", "operador")
    admicorp = user("ADMINISTRADOR", "admicorp")
    administrador = user("ADMINISTRADOR", "admin2")
    for actor in (sistemas, admicorp, administrador):
        assert not has_system_daily_check_mvp_access(actor)
    assert has_system_daily_check_mvp_access(gerente)
    assert not has_system_daily_check_bi_access(gerente)
    assert has_system_daily_check_bi_access(sistemas)
    assert has_system_daily_check_bi_access(admicorp)
    assert not has_system_daily_check_bi_access(administrador)
    assert has_system_daily_check_rollout_access(admicorp)
    for actor in (gerente, sistemas, administrador):
        assert not has_system_daily_check_rollout_access(actor)


def test_missing_user_has_no_permissions():
    assert not has_system_daily_check_mvp_access(None)
    assert not has_system_daily_check_bi_access(None)
    assert not has_system_daily_check_rollout_access(None)
