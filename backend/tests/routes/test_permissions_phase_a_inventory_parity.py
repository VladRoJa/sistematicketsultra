"""P11/P12 — compara sucursales reales de Inventario vs catálogo diagnóstico.

Todos los usuarios son ficticios; el fallback M:N se simula (sin PostgreSQL).
No se modifican permisos ni se emiten solicitudes autenticadas.
"""
from types import SimpleNamespace

import pytest
from flask import Flask

from app.routes import inventarios as inventory
from app.routes import permissions_catalog_routes as catalog


def _user(role, *, primary, branches):
    return SimpleNamespace(
        id=-501,
        rol=role,
        username="FICTICIO_QA",
        sucursal_id=primary,
        sucursales_ids=list(branches),
        department_id=1,
    )


def _preview(user, action_key):
    context = {
        "role": catalog._normalize_role(user),
        "sucursal_ids": catalog._get_user_assigned_sucursal_ids(user),
        "warehouse_operator": None,
        "planning_operator": None,
        "allow_ticket_delete_all": False,
    }
    return catalog._effective_action_decision(
        SimpleNamespace(full_key=action_key), user, context
    )


def _legacy_read(user, branch_id, monkeypatch, fallback=None):
    monkeypatch.setattr(inventory, "_get_current_inventory_user", lambda: user)
    monkeypatch.setattr(
        inventory, "_get_user_sucursales_scope_from_db",
        lambda uid: list(fallback or []),
    )
    _, error = inventory._resolve_inventory_read_sucursal_ids(branch_id)
    return error is None


def _legacy_move(user, branch_id, monkeypatch, fallback=None):
    monkeypatch.setattr(inventory, "_get_current_inventory_user", lambda: user)
    monkeypatch.setattr(
        inventory, "_get_user_sucursales_scope_from_db",
        lambda uid: list(fallback or []),
    )
    return inventory._require_inventory_movement_write(branch_id) is None


@pytest.mark.parametrize("branch_id,actual", [(7, True), (8, True), (9, False), (10, False)])
def test_p11_sr_mantenimiento_read_scope_does_not_inherit_primary(
    monkeypatch, branch_id, actual
):
    with Flask(__name__).test_request_context():
        user = _user("SR_MANTENIMIENTO", primary=9, branches=[7, 8])
        assert _legacy_read(user, branch_id, monkeypatch) is actual

        observed = _preview(user, "inventory.read")
        assert observed["allowed"] is True
        assert observed["scope_type"] == "branch_scope"
        assert observed["scope_values"] == [7, 8, 9]
        # branch 9 es falso positivo del catálogo, NO acceso productivo.


@pytest.mark.parametrize("branch_id,actual", [(7, True), (8, True), (9, False)])
def test_p11_sr_mantenimiento_movement_scope_does_not_inherit_primary(
    monkeypatch, branch_id, actual
):
    with Flask(__name__).test_request_context():
        user = _user("SR_MANTENIMIENTO", primary=9, branches=[7, 8])
        assert _legacy_move(user, branch_id, monkeypatch) is actual

        observed = _preview(user, "inventory.movement_write")
        assert observed["scope_values"] == [7, 8, 9]
        assert observed["allowed"] is True


def test_p11_sr_mantenimiento_uses_db_fallback_when_m2m_list_empty(monkeypatch):
    with Flask(__name__).test_request_context():
        user = _user("SR_MANTENIMIENTO", primary=9, branches=[])
        assert _legacy_read(user, 7, monkeypatch, fallback=[7]) is True
        assert _legacy_move(user, 7, monkeypatch, fallback=[7]) is True
        assert _legacy_read(user, 9, monkeypatch, fallback=[7]) is False

        observed = _preview(user, "inventory.read")
        assert observed["scope_values"] == [9]
        # Catálogo omite sucursal 7, que el guard real obtiene de M:N.


@pytest.mark.parametrize("branch_id,actual", [(7, True), (8, False), (9, False)])
def test_p12_aux_mantenimiento_only_primary_for_read_and_movement(
    monkeypatch, branch_id, actual
):
    with Flask(__name__).test_request_context():
        user = _user("AUX_MANTENIMIENTO", primary=7, branches=[7, 8])
        assert _legacy_read(user, branch_id, monkeypatch) is actual
        assert _legacy_move(user, branch_id, monkeypatch) is actual

        read = _preview(user, "inventory.read")
        movement = _preview(user, "inventory.movement_write")
        assert read["scope_values"] == [7, 8]
        assert movement["scope_values"] == [7, 8]
        assert read["allowed"] is True
        assert movement["allowed"] is True
        # branch 8: falso positivo de scope, se deniega en helpers reales.


@pytest.mark.parametrize("role", ["ADMINISTRADOR", "SISTEMAS", "TECNICO"])
def test_p13_inventory_global_writer_keeps_global_read_and_movement(
    monkeypatch, role
):
    with Flask(__name__).test_request_context():
        user = _user(role, primary=9, branches=[])
        assert _legacy_read(user, 77, monkeypatch) is True
        assert _legacy_move(user, 77, monkeypatch) is True
        assert inventory._require_inventory_global_write() is None

        for action in (
            "inventory.read", "inventory.movement_write", "inventory.master_write"
        ):
            observed = _preview(user, action)
            assert observed["allowed"] is True
            assert observed["scope_type"] == "global"
