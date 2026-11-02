"""#1178: el permiso de movimientos es un veto, nunca un scope nuevo.

Solo Flask/JWT sintéticos: sin registros productivos, cambios de stock ni email.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as inventory


def client(*, enabled=False):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="qa-inventory-movement-1181",
        PERMISSIONS_INVENTORY_MOVEMENT_WRITE_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(inventory.inventario_bp)
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def actor(role="SR_MANTENIMIENTO", primary=100, branches=(1, 2)):
    return SimpleNamespace(id=47, username="QA", rol=role,
                           sucursal_id=primary, sucursales_ids=list(branches))


def movement_query(branch=1, *, cancelled=False):
    row = SimpleNamespace(id=80, sucursal_id=branch, anulado=cancelled)
    return SimpleNamespace(
        filter_by=lambda **kw: SimpleNamespace(
            with_for_update=lambda: SimpleNamespace(first=lambda: row)
        )
    )


@pytest.mark.parametrize("path,payload", [
    ("/api/inventario/movimientos", {"sucursal_id": 1}),
    ("/api/inventario/movimientos/80/anular", {"motivo": "Motivo QA anulación"}),
])
def test_movement_operations_still_require_jwt(path, payload):
    api, _ = client(enabled=True)
    response = api.post(path, json=payload)
    assert response.status_code == 401


def test_register_movement_deny_403_before_stock_mutation():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant, \
         patch.object(inventory.db.session, "add") as add, \
         patch.object(inventory.db.session, "commit") as commit:
        r = api.post("/api/inventario/movimientos", headers=headers,
                     json={"sucursal_id": 1, "tipo_movimiento": "entrada"})
    assert r.status_code == 403
    assert grant.call_args.kwargs["action_full_key"] == "inventory.movement_write"
    add.assert_not_called()
    commit.assert_not_called()


def test_cancel_movement_deny_403_before_reverting_stock():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user", return_value=actor()), \
         patch.object(inventory.MovimientoInventario, "query", movement_query(1)), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant, \
         patch.object(inventory.db.session, "add") as add, \
         patch.object(inventory.db.session, "commit") as commit:
        r = api.post("/api/inventario/movimientos/80/anular", headers=headers,
                     json={"motivo": "Motivo QA anulación"})
    assert r.status_code == 403
    grant.assert_called_once()
    add.assert_not_called()
    commit.assert_not_called()


@pytest.mark.parametrize("role,branch", [
    ("SR_MANTENIMIENTO", 999),
    ("AUX_MANTENIMIENTO", 2),
    ("GERENTE", 1),
])
def test_allow_never_bypasses_branch_or_legacy_role(role, branch):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user",
                      return_value=actor(role, primary=1, branches=(1, 2))), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant, \
         patch.object(inventory.db.session, "add") as add:
        r = api.post("/api/inventario/movimientos", headers=headers,
                     json={"sucursal_id": branch, "tipo_movimiento": "entrada"})
    assert r.status_code == 403
    grant.assert_not_called()
    add.assert_not_called()


def test_allow_still_rejects_invalid_stock_payload():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant, \
         patch.object(inventory.db.session, "add") as add:
        r = api.post("/api/inventario/movimientos", headers=headers,
                     json={"sucursal_id": 1, "tipo_movimiento": "entrada",
                           "inventarios": []})
    assert r.status_code == 400
    grant.assert_called_once()
    add.assert_not_called()


def test_allow_does_not_skip_cancellation_double_check():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user", return_value=actor()), \
         patch.object(inventory.MovimientoInventario, "query",
                      movement_query(1, cancelled=True)), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant, \
         patch.object(inventory.db.session, "commit") as commit:
        r = api.post("/api/inventario/movimientos/80/anular", headers=headers,
                     json={"motivo": "Motivo QA anulación"})
    assert r.status_code == 409
    grant.assert_called_once()
    commit.assert_not_called()


def test_flag_off_uses_legacy_without_grants():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=False)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        r = api.post("/api/inventario/movimientos", headers=headers,
                     json={"sucursal_id": 1, "tipo_movimiento": "entrada",
                           "inventarios": []})
    assert r.status_code == 400
    grant.assert_not_called()


def test_flag_default_off():
    with Flask(__name__).app_context():
        assert inventory.inventory_movement_write_grants_enabled() is False


@pytest.mark.parametrize("effect,branch,legacy_expected,catalog_expected", [
    ("deny", None, False, False),
    ("allow", None, None, True),
    ("deny", 1, False, False),
    ("allow", 1, True, True),
    ("allow", 999, False, False),
])
def test_matrix_veto_does_not_claim_access_to_other_branches(
    effect, branch, legacy_expected, catalog_expected,
):
    from app.routes import permissions_visual_audit_routes as visual
    user = actor()
    action = SimpleNamespace(
        id=76, full_key="inventory.movement_write",
        name="Registrar movimientos", is_active=True,
        module=SimpleNamespace(id=4, key="inventory", name="Inventario",
                               base_action_id=70),
    )
    context = {
        "user": user, "role": user.rol, "sucursal_ids": [1, 2],
        "warehouse_operator": None, "planning_operator": None,
        "pm_scoped_read": False, "allow_ticket_delete_all": False,
    }
    grant = SimpleNamespace(
        id=99, action_id=76, effect=effect, scope_type="global",
        scope_branch_id=None, scope_branch_ids=[], scope_department_id=None,
        scope_payload=None, starts_at=None, expires_at=None, reason="QA",
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_INVENTORY_MOVEMENT_WRITE_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(user, action, context,
                                   {(76, "user", 47): grant}, branch_id=branch)
    assert row["legacy_allowed"] is legacy_expected
    assert row["catalog_allowed"] is catalog_expected
    assert row["catalog_source"] == "inventory_movement_write_grant_operativo"
    if branch is None and effect == "allow":
        assert row["comparison"] == "no_concluyente"
