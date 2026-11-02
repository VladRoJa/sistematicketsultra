"""#1178: pm.execute es veto de dos POST, no elevación de rol/branch.

Pruebas Flask/JWT sintéticas; no conectan a base productiva.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import pm_routes as pm


POST_PATHS = ("/api/pm/mobile/bitacoras", "/api/pm/preventivo/registrar")


def payload(*, branch=7):
    return {
        "inventario_id": 123,
        "sucursal_id": branch,
        "fecha": "2026-11-02",
        "resultado": "OK",
        "tipo_mantenimiento": "PREVENTIVO",
        "checks": {},
    }


def actor(role="ADMINISTRADOR", primary=7, branches=(7,)):
    return SimpleNamespace(
        id=47, username="QA", rol=role,
        sucursal_id=primary, sucursales_ids=list(branches),
        department_id=1,
    )


def client(enabled=True):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="synthetic-pm-execute-1181",
        PERMISSIONS_PM_EXECUTE_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(pm.pm_bp, url_prefix="/api/pm")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("path", POST_PATHS)
def test_execute_routes_require_jwt(path):
    api, _ = client()
    assert api.post(path, json=payload()).status_code == 401


@pytest.mark.parametrize("path", POST_PATHS)
def test_deny_blocks_both_execute_routes_before_inventory_and_stock(path):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(pm.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant, \
         patch.object(pm, "_verificar_permiso_sucursal") as scope:
        response = api.post(path, headers=headers, json=payload())
    assert response.status_code == 403
    assert response.json["detail"] == "No tienes habilitada la ejecución de bitácoras PM."
    grant.assert_called_once()
    assert grant.call_args.kwargs["action_full_key"] == "pm.execute"
    scope.assert_not_called()


def test_execute_denied_for_unauthorized_role_without_grant_lookup():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(pm.UserORM, "get_by_id",
                      return_value=actor("GERENTE")), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.post(POST_PATHS[0], headers=headers, json=payload())
    assert response.status_code == 403
    grant.assert_not_called()


def test_allow_does_not_bypass_branch_guard():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(pm.UserORM, "get_by_id",
                      return_value=actor("AUX_MANTENIMIENTO")), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.post(POST_PATHS[0], headers=headers, json=payload(branch=999))
    assert response.status_code == 403
    grant.assert_called_once()


def test_allow_preserves_inventario_sucursal_check():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    nonexistent_relation = SimpleNamespace(
        filter_by=lambda **kwargs: SimpleNamespace(first=lambda: None)
    )
    with api.application.app_context(), \
         patch.object(pm.UserORM, "get_by_id", return_value=actor()), \
         patch.object(pm.InventarioSucursal, "query", nonexistent_relation), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.post(POST_PATHS[1], headers=headers, json=payload())
    assert response.status_code == 400
    assert "no pertenece" in response.json["detail"]
    grant.assert_called_once()


def test_allow_does_not_bypass_duplicate_preventivo():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    existing_relation = SimpleNamespace(
        filter_by=lambda **kwargs: SimpleNamespace(
            first=lambda: SimpleNamespace(id=123)
        )
    )
    with api.application.app_context(), \
         patch.object(pm.UserORM, "get_by_id", return_value=actor()), \
         patch.object(pm.InventarioSucursal, "query", existing_relation), \
         patch.object(pm, "_buscar_bitacora_preventiva_existente",
                      return_value=SimpleNamespace(id=99)) as duplicate, \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.post(POST_PATHS[0], headers=headers, json=payload())
    assert response.status_code == 409
    assert response.json["existing_bitacora_id"] == 99
    grant.assert_called_once()
    duplicate.assert_called_once()


def test_access_reports_execute_veto_without_changing_read():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor(), None)), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant:
        response = api.get("/api/pm/access", headers=headers)
    assert response.status_code == 200
    assert response.json["can_view"] is True
    assert response.json["allowed"] is True
    assert response.json["can_execute"] is False
    grant.assert_called_once()


def test_flag_off_keeps_legacy_and_does_not_read_grants():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=False)
    no_relation = SimpleNamespace(
        filter_by=lambda **kwargs: SimpleNamespace(first=lambda: None)
    )
    with api.application.app_context(), \
         patch.object(pm.UserORM, "get_by_id", return_value=actor()), \
         patch.object(pm.InventarioSucursal, "query", no_relation), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        response = api.post(POST_PATHS[0], headers=headers, json=payload())
    assert response.status_code == 400
    grant.assert_not_called()


def test_execute_flag_default_off():
    with Flask(__name__).app_context():
        assert pm.pm_execute_grants_enabled() is False


@pytest.mark.parametrize("effect,branch,legacy,catalog_allowed", [
    ("deny", None, False, False),
    ("deny", 7, False, False),
    ("allow", None, True, True),
    ("allow", 7, None, None),
])
def test_matrix_execute_global_veto_without_claiming_branch(
    effect, branch, legacy, catalog_allowed,
):
    from app.routes import permissions_visual_audit_routes as visual
    user = actor()
    action = SimpleNamespace(
        id=84, full_key="pm.execute", name="Ejecutar PM", is_active=True,
        module=SimpleNamespace(
            id=4, key="pm", name="PM", base_action_id=80
        ),
    )
    context = {
        "user": user, "role": user.rol, "sucursal_ids": [7],
        "warehouse_operator": None, "planning_operator": None,
        "allow_ticket_delete_all": False, "pm_scoped_read": False,
    }
    grant = SimpleNamespace(
        id=88, effect=effect, scope_type="global",
        starts_at=None, expires_at=None, reason="QA", action_id=84,
        scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None,
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_PM_EXECUTE_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(
            user, action, context, {(84, "user", 47): grant}, branch_id=branch
        )
    assert row["legacy_allowed"] is legacy
    assert row["catalog_allowed"] is catalog_allowed
    assert row["catalog_source"] == "pm_execute_grant_operativo"
