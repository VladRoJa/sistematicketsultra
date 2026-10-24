"""Paridad de guards de solo consulta: PM, Inventario y borrado masivo Tickets.

Se compara el evaluador de auditoría con funciones/guards realmente usados.
NO se ejecutan escrituras ni se usan tokens reales/servidor productivo.
Las comparaciones son solo de puertas base; las reglas de objeto permanecen UNKNOWN.
"""
from types import SimpleNamespace

import pytest
from flask import Flask

from app.models.user_model import UserORM
from app.routes import inventarios, ticket_routes
from app.routes import permissions_visual_audit_routes as visual
from app.utils import pm_permissions


def _user(role, branches=(7,), primary=7, uid=125):
    return SimpleNamespace(
        id=uid, username="QA_LEGACY", rol=role, sucursal_id=primary,
        sucursales_ids=list(branches), department_id=1,
    )


def _context(user, *, scoped_pm=False, delete_all=False):
    return {
        "user": user, "role": user.rol,
        "sucursal_ids": sorted(set(user.sucursales_ids + ([user.sucursal_id] if user.sucursal_id else []))),
        "pm_scoped_read": scoped_pm, "allow_ticket_delete_all": delete_all,
        "warehouse_operator": None, "planning_operator": None,
    }


def _action(full_key):
    module, key = full_key.split(".", 1)
    return SimpleNamespace(
        id=77, full_key=full_key, key=key, name=full_key,
        is_active=True, module=SimpleNamespace(
            id=10, key=module, name=module, base_action_id=77,
        ),
    )


def _row(user, key, *, branch_id=None, scoped_pm=False, delete_all=False):
    return visual.evaluate_pair(
        user, _action(key), _context(user, scoped_pm=scoped_pm, delete_all=delete_all),
        branch_id=branch_id,
    )


@pytest.mark.parametrize("role,scoped,branches", [
    ("ADMINISTRADOR", False, (7,)),
    ("MANTENIMIENTO", False, (7,)),
    ("GERENTE", False, (7,)),
    ("AUX_MANTENIMIENTO", False, (7,)),
    ("SISTEMAS", False, (7,)),
    ("RECEPCIONISTA", False, (7,)),
    ("COMPRAS", True, (7, 9)),
    ("COMPRAS", False, (7,)),
    ("COORDINADOR_MANTENIMIENTO", True, (7,)),
    ("COORDINADOR_MANTENIMIENTO", True, ()),
])
@pytest.mark.parametrize("key,method", [
    ("pm.read", "can_pm_view"),
    ("pm.execute", "can_pm_execute"),
    ("pm.validate", "can_pm_validate"),
    ("pm.configure", "can_pm_configure"),
])
def test_pm_base_gate_parity_without_object(monkeypatch, role, scoped, branches, key, method):
    user = _user(role, branches=branches)
    monkeypatch.setattr(
        pm_permissions, "has_scoped_maintenance_read_grant",
        lambda actor: scoped and actor.id == user.id,
    )
    real_role_gate = getattr(pm_permissions, method)(user)
    row = _row(user, key, scoped_pm=scoped)
    expected = real_role_gate
    # /api/pm/access: para lectura individual, también requiere sucursales M:N.
    if key == "pm.read" and role in {"COMPRAS", "COORDINADOR_MANTENIMIENTO"}:
        expected = real_role_gate and bool(branches)
    assert row["legacy_allowed"] is expected
    assert row["legacy_source"] == "pm_permissions.can_pm_*"
    assert row["scope"] == "guard_rol_base"
    # Es solo el gate de rol: nunca prueba capacidad sobre un recurso PM.
    with_branch = _row(user, key, scoped_pm=scoped, branch_id=7)
    assert with_branch["legacy_allowed"] is None
    assert with_branch["comparison"] == "no_concluyente"


@pytest.mark.parametrize("role,allowed", [
    ("ADMINISTRADOR", True), ("SUPER_ADMIN", True),
    ("MANTENIMIENTO", True), ("SISTEMAS", True), ("TECNICO", True),
    ("SR_MANTENIMIENTO", False), ("AUX_MANTENIMIENTO", False),
    ("GERENTE", False), ("RECEPCIONISTA", False),
])
def test_inventory_master_write_exact_guard_role(monkeypatch, role, allowed):
    user = _user(role)
    monkeypatch.setattr(inventarios, "_get_current_inventory_user", lambda: user)
    with Flask(__name__).app_context():
        actual = inventarios._require_inventory_global_write() is None
    row = _row(user, "inventory.master_write")
    assert actual is allowed
    assert row["legacy_allowed"] is actual
    assert row["scope"] == "global"
    assert _row(user, "inventory.master_write", branch_id=9)["legacy_allowed"] is actual


@pytest.mark.parametrize("role,branches,primary,branch,allowed", [
    ("ADMINISTRADOR", (), None, 77, True),
    ("MANTENIMIENTO", (), None, 13, True),
    ("SISTEMAS", (), 100, 77, True),
    ("AUX_MANTENIMIENTO", (7, 9), 7, 7, True),
    ("AUX_MANTENIMIENTO", (7, 9), 7, 9, False),  # AUX solo principal
    ("AUX_MANTENIMIENTO", (), None, 7, False),
    ("SR_MANTENIMIENTO", (7, 9), 100, 9, True),
    ("SR_MANTENIMIENTO", (7, 9), 100, 4, False),
    ("SR_MANTENIMIENTO", (), 7, 7, False),  # SR NO hereda principal
    ("GERENTE", (7,), 7, 7, False),
    ("RECEPCIONISTA", (7,), 7, 7, False),
])
def test_inventory_movement_write_parity_per_branch(
    monkeypatch, role, branches, primary, branch, allowed,
):
    user = _user(role, branches=branches, primary=primary)
    monkeypatch.setattr(inventarios, "_get_current_inventory_user", lambda: user)
    monkeypatch.setattr(
        inventarios, "_get_user_sucursales_scope_from_db",
        lambda uid: list(branches),
    )
    with Flask(__name__).app_context():
        real = inventarios._require_inventory_movement_write(branch) is None
    row = _row(user, "inventory.movement_write", branch_id=branch)
    assert real is allowed
    assert row["legacy_allowed"] is real
    assert row["scope"] == "sucursal"
    assert row["context"]["branch_id"] == branch
    assert _row(user, "inventory.movement_write")["legacy_allowed"] is None


@pytest.mark.parametrize("role,enabled,expected", [
    ("ADMINISTRADOR", True, True),
    ("ADMIN", True, True),
    ("SUPER_ADMIN", True, True),
    ("GERENTE", True, False),
    ("LECTOR_GLOBAL", True, False),
    ("ADMINISTRADOR", False, False),
    ("GERENTE", False, False),
])
def test_tickets_delete_all_double_gate_read_only(monkeypatch, role, enabled, expected):
    user = _user(role)
    monkeypatch.setattr(ticket_routes.UserORM, "get_by_id", lambda uid: user)
    monkeypatch.setattr(ticket_routes, "get_jwt_identity", lambda: str(user.id))
    with Flask(__name__).app_context():
        _, denial = ticket_routes._require_ticket_admin_action()
        role_gate = denial is None
    assert (role_gate and enabled) is expected
    row = _row(user, "tickets.delete_all", delete_all=enabled)
    assert row["legacy_allowed"] is expected
    assert row["scope"] == "global"
    # La acción no ejecuta una eliminación ni comprueba permisos de tickets individuales.
    assert _row(user, "tickets.close", delete_all=enabled)["legacy_allowed"] is None


@pytest.mark.parametrize("role", ["GERENTE", "ADMINISTRADOR", "SR_MANTENIMIENTO"])
@pytest.mark.parametrize("action", [
    "tickets.view", "tickets.close", "tickets.maintenance.coordinate",
    "tickets.maintenance.read_assigned_only", "inventory.read",
])
def test_heterogeneous_or_object_dependent_actions_remain_unknown(role, action):
    user = _user(role)
    for branch_id in (None, 7):
        row = _row(user, action, branch_id=branch_id)
        assert row["legacy_allowed"] is None
        assert row["status"] == "no_concluyente"


def test_inventory_movement_is_never_global_without_branch_even_for_admin():
    user = _user("ADMINISTRADOR")
    row = _row(user, "inventory.movement_write")
    assert row["legacy_allowed"] is None
    assert row["scope"] == "requiere_contexto"


def test_pm_scoped_grant_without_assigned_branch_is_not_authorization():
    user = _user("COMPRAS", branches=(), primary=100)
    row = _row(user, "pm.read", scoped_pm=True)
    assert row["legacy_allowed"] is False
    assert row["scope"] == "guard_rol_base"
