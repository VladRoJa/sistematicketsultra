from types import SimpleNamespace

from app.utils.maintenance_ticket_update_guard import (
    generic_pm_update_is_forbidden,
    is_maintenance_ticket,
)


def _user(role):
    return SimpleNamespace(rol=role)


def _ticket(department_id):
    return SimpleNamespace(departamento_id=department_id)


def test_detects_only_maintenance_department():
    assert is_maintenance_ticket(_ticket(1)) is True
    assert is_maintenance_ticket(_ticket("1")) is True
    assert is_maintenance_ticket(_ticket(2)) is False
    assert is_maintenance_ticket(_ticket(None)) is False


def test_manager_cannot_use_generic_update_for_maintenance_ticket():
    assert generic_pm_update_is_forbidden(
        _user("GERENTE"),
        _ticket(1),
    ) is True


def test_regional_manager_cannot_use_generic_update_for_maintenance_ticket():
    assert generic_pm_update_is_forbidden(
        _user("GERENTE_REGIONAL"),
        _ticket(1),
    ) is True


def test_pm_execution_roles_keep_access_for_maintenance_ticket():
    for role in (
        "MANTENIMIENTO",
        "SR_MANTENIMIENTO",
        "AUX_MANTENIMIENTO",
        "SISTEMAS",
        "TECNICO",
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
    ):
        assert generic_pm_update_is_forbidden(
            _user(role),
            _ticket(1),
        ) is False


def test_guard_does_not_change_generic_updates_for_other_departments():
    assert generic_pm_update_is_forbidden(
        _user("GERENTE"),
        _ticket(7),
    ) is False
