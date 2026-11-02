"""#1178: inventory.read veta consultas, sin ampliar scope de sucursales."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as inventory


# Cinco handlers; /existencias y /v2/existencias comparten uno.
READ_URLS = (
    "/api/inventario/", "/api/inventario/movimientos",
    "/api/inventario/reportes/resumen", "/api/inventario/existencias",
    "/api/inventario/v2/existencias", "/api/inventario/listar",
)


def client(enabled=True):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="read-permission-qa",
                      PERMISSIONS_INVENTORY_READ_GRANTS_ENABLED=enabled)
    JWTManager(app)
    app.register_blueprint(inventory.inventario_bp)
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


def actor(role="ADMINISTRADOR", primary=1, branches=(1, 2)):
    return SimpleNamespace(id=47, username="QA", rol=role,
                           sucursal_id=primary, sucursales_ids=list(branches))


@pytest.mark.parametrize("url", READ_URLS)
def test_inventory_read_jwt_required(url):
    api, _ = client()
    assert api.get(url).status_code == 401


@pytest.mark.parametrize("url", READ_URLS)
def test_inventory_read_deny_blocks_six_urls_before_queries(url):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant, \
         patch.object(inventory.db.session, "execute") as execute:
        response = api.get(url, headers=headers)
    assert response.status_code == 403
    grant.assert_called_once()
    assert grant.call_args.kwargs["action_full_key"] == "inventory.read"
    execute.assert_not_called()


@pytest.mark.parametrize("role,branch", [
    ("SR_MANTENIMIENTO", 99), ("AUX_MANTENIMIENTO", 2),
    ("GERENTE", 99),
])
def test_allow_never_expands_legacy_branch_scope(role, branch):
    from app.routes import permissions_catalog_routes as catalog
    api, _ = client()
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user",
                      return_value=actor(role, primary=1)), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        scope, error = inventory._resolve_inventory_read_sucursal_ids(branch)
    assert scope is None
    assert error[1] == 403
    grant.assert_not_called()


def test_sr_m2m_fallback_does_not_inherit_primary():
    from app.routes import permissions_catalog_routes as catalog
    api, _ = client()
    user = actor("SR_MANTENIMIENTO", primary=99, branches=())
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user", return_value=user), \
         patch.object(inventory, "_get_user_sucursales_scope_from_db",
                      return_value=[1, 2]) as fallback, \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        allowed, error = inventory._resolve_inventory_read_sucursal_ids(2)
        forbidden, invalid = inventory._resolve_inventory_read_sucursal_ids(99)
    assert allowed == [2] and error is None
    assert forbidden is None and invalid[1] == 403
    assert fallback.call_count == 2
    grant.assert_called_once()


def test_flag_off_preserves_scoped_legacy_without_grants():
    from app.routes import permissions_catalog_routes as catalog
    api, _ = client(enabled=False)
    with api.application.app_context(), \
         patch.object(inventory, "_get_current_inventory_user",
                      return_value=actor("AUX_MANTENIMIENTO")), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        scope, error = inventory._resolve_inventory_read_sucursal_ids(1)
    assert scope == [1] and error is None
    grant.assert_not_called()


def test_read_flag_off_by_default():
    with Flask(__name__).app_context():
        assert inventory.inventory_read_grants_enabled() is False


@pytest.mark.parametrize("effect,branch,legacy,catalog_allowed", [
    ("deny", None, False, False), ("deny", 99, False, False),
    ("allow", None, None, True), ("allow", 99, None, None),
])
def test_matrix_global_veto_not_branch_allow(effect, branch, legacy, catalog_allowed):
    from app.routes import permissions_visual_audit_routes as visual
    user = actor("GERENTE")
    action = SimpleNamespace(
        id=61, full_key="inventory.read", name="Consultar",
        is_active=True, module=SimpleNamespace(
            id=4, key="inventory", name="Inventario", base_action_id=61))
    context = {"user": user, "role": user.rol, "sucursal_ids": [1, 2],
               "warehouse_operator": None, "planning_operator": None,
               "pm_scoped_read": False, "allow_ticket_delete_all": False}
    grant = SimpleNamespace(
        id=88, effect=effect, scope_type="global", starts_at=None,
        expires_at=None, reason="QA", action_id=61,
        scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None)
    app = Flask(__name__)
    app.config["PERMISSIONS_INVENTORY_READ_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(user, action, context,
                                   {(61, "user", 47): grant}, branch_id=branch)
    assert row["legacy_allowed"] is legacy
    assert row["catalog_allowed"] is catalog_allowed
    assert row["catalog_source"] == "inventory_read_grant_operativo"
