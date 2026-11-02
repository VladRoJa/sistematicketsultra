"""#1178: el check inventory.master_write veta sin elevar roles ni mutar stock."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as inventory


ROUTES = (
    ("post", "/api/inventario/"),
    ("put", "/api/inventario/40"),
    ("post", "/api/inventario/40/corregir-codigo"),
    ("get", "/api/inventario/40/historial-codigos"),
    ("delete", "/api/inventario/40"),
    ("post", "/api/inventario/importar"),
    ("get", "/api/inventario/exportar"),
)


def client(enabled=False):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="qa-inventory-master-write-1181",
        PERMISSIONS_INVENTORY_MASTER_WRITE_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(inventory.inventario_bp)
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def actor(role="ADMINISTRADOR"):
    return SimpleNamespace(
        id=47, username="QA", rol=role, sucursal_id=1, sucursales_ids=[1],
    )


@pytest.mark.parametrize("method,url", ROUTES)
def test_inventory_master_write_requires_jwt(method, url):
    api, _ = client(enabled=True)
    response = getattr(api, method)(url)
    assert response.status_code == 401


@pytest.mark.parametrize("method,url", ROUTES)
def test_inventory_master_write_deny_blocks_before_mutation(method, url):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant, \
         patch.object(inventory.db.session, "add") as add, \
         patch.object(inventory.db.session, "commit") as commit:
        response = getattr(api, method)(url, headers=headers)
    assert response.status_code == 403
    grant.assert_called_once()
    assert grant.call_args.kwargs["action_full_key"] == "inventory.master_write"
    add.assert_not_called()
    commit.assert_not_called()


def test_inventory_master_write_allow_never_elevates_role():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user",
                      return_value=actor("GERENTE")), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant, \
         patch.object(inventory.db.session, "add") as add:
        response = api.post("/api/inventario/", headers=headers, json={})
    assert response.status_code == 403
    grant.assert_not_called()
    add.assert_not_called()


def test_inventory_master_write_allow_still_validates_payload():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant, \
         patch.object(inventory.db.session, "add") as add:
        response = api.post("/api/inventario/", headers=headers, json={})
    assert response.status_code == 400
    grant.assert_called_once()
    add.assert_not_called()


def test_inventory_master_write_flag_off_keeps_legacy_without_query():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=False)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        response = api.post("/api/inventario/", headers=headers, json={})
    assert response.status_code == 400
    grant.assert_not_called()


def test_inventory_master_write_default_flag_off():
    with Flask(__name__).app_context():
        assert inventory.inventory_master_write_grants_enabled() is False


@pytest.mark.parametrize("effect,role,expected", [
    ("deny", "ADMINISTRADOR", False),
    ("allow", "ADMINISTRADOR", True),
    ("allow", "GERENTE", False),
])
def test_inventory_master_write_matrix_respects_legacy_role(effect, role, expected):
    from app.routes import permissions_visual_audit_routes as visual
    user = actor(role)
    action = SimpleNamespace(
        id=74, full_key="inventory.master_write",
        name="Administrar inventario general", is_active=True,
        module=SimpleNamespace(id=4, key="inventory", name="Inventario", base_action_id=70),
    )
    context = {
        "user": user, "role": role, "sucursal_ids": [1],
        "warehouse_operator": None, "planning_operator": None,
        "pm_scoped_read": False, "allow_ticket_delete_all": False,
    }
    grant = SimpleNamespace(
        id=99, action_id=74, effect=effect, scope_type="global",
        scope_branch_id=None, scope_branch_ids=[], scope_department_id=None,
        scope_payload=None, starts_at=None, expires_at=None, reason="QA",
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_INVENTORY_MASTER_WRITE_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(user, action, context, {(74, "user", 47): grant})
        branch = visual.evaluate_pair(
            user, action, context, {(74, "user", 47): grant}, branch_id=999,
        )
    assert row["legacy_allowed"] is expected
    assert row["catalog_allowed"] is expected
    assert row["catalog_source"] == "inventory_master_write_grant_operativo"
    assert branch["legacy_allowed"] is expected
