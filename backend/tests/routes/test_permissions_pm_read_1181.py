"""#1178 PM lectura: check DENY sin ampliar rol, ACL o sucursal.

HTTP sintético únicamente. No modifica bitácoras, validaciones ni programación.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import pm_routes as pm


READ_URLS = (
    "/api/pm/bitacoras/31",
    "/api/pm/bitacoras",
    "/api/pm/configuraciones",
    "/api/pm/preventivo/dashboard?sucursal_id=7",
    "/api/pm/calendario?anio=2026&mes=11",
)


def client(enabled=True):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="pm-read-1181-synthetic",
        PERMISSIONS_PM_READ_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(pm.pm_bp, url_prefix="/api/pm")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


def actor(role="ADMINISTRADOR", branches=(7,), primary=7):
    return SimpleNamespace(
        id=47, username="QA", rol=role, sucursal_id=primary,
        sucursales_ids=list(branches), department_id=1,
    )


@pytest.mark.parametrize("url", READ_URLS + ("/api/pm/access",))
def test_pm_read_requires_jwt(url):
    api, _ = client()
    assert api.get(url).status_code == 401


@pytest.mark.parametrize("url", READ_URLS)
def test_pm_read_deny_403_before_query_for_five_get_handlers(url):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor(), None)), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant:
        response = api.get(url, headers=headers)
    assert response.status_code == 403
    grant.assert_called_once()
    assert grant.call_args.kwargs["action_full_key"] == "pm.read"


def test_pm_access_preserves_200_and_reflects_veto_without_affecting_execute():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor(), None)), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant:
        response = api.get("/api/pm/access", headers=headers)
    assert response.status_code == 200
    assert response.json["allowed"] is False
    assert response.json["can_view"] is False
    assert response.json["can_execute"] is True
    grant.assert_called_once()


def test_pm_allow_does_not_elevate_unauthorized_role():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor("RECEPCIONISTA"), None)), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.get("/api/pm/bitacoras", headers=headers)
    assert response.status_code == 403
    grant.assert_not_called()


def test_pm_allow_still_denies_bitacora_from_other_branch():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    user = actor("GERENTE", branches=(7,), primary=7)
    found = SimpleNamespace(sucursal_id=999)
    fake_db = SimpleNamespace(session=SimpleNamespace(get=lambda *args: found))
    with api.application.app_context(), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(user, None)), \
         patch.object(pm, "db", fake_db), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.get("/api/pm/bitacoras/31", headers=headers)
    assert response.status_code == 403
    grant.assert_called_once()


def test_pm_scoped_compras_denied_by_grant_without_bypassing_acl():
    from app.routes import permissions_catalog_routes as catalog
    from app.utils import pm_permissions
    api, headers = client()
    user = actor("COMPRAS", branches=(7, 9), primary=100)
    with api.application.app_context(), \
         patch.object(pm, "_obtener_usuario_actual_pm", return_value=(user, None)), \
         patch.object(pm_permissions, "has_scoped_maintenance_read_grant",
                      return_value=True), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant:
        response = api.get("/api/pm/access", headers=headers)
        denied = api.get("/api/pm/configuraciones", headers=headers)
    assert response.status_code == 200
    assert response.json["can_view"] is False
    assert denied.status_code == 403
    assert grant.call_count == 2


def test_pm_scoped_read_without_branches_does_not_query_grant():
    from app.routes import permissions_catalog_routes as catalog
    from app.utils import pm_permissions
    api, headers = client()
    user = actor("COORDINADOR_MANTENIMIENTO", branches=(), primary=100)
    with api.application.app_context(), \
         patch.object(pm, "_obtener_usuario_actual_pm", return_value=(user, None)), \
         patch.object(pm_permissions, "has_scoped_maintenance_read_grant",
                      return_value=True), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        response = api.get("/api/pm/access", headers=headers)
    assert response.status_code == 200
    assert response.json["can_view"] is False
    grant.assert_not_called()


def test_pm_flag_off_preserves_legacy_without_grant_query():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=False)
    with api.application.app_context(), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor(), None)), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        response = api.get("/api/pm/preventivo/dashboard", headers=headers)
    assert response.status_code == 400
    grant.assert_not_called()


def test_pm_flag_off_by_default():
    with Flask(__name__).app_context():
        assert pm.pm_read_grants_enabled() is False


@pytest.mark.parametrize("effect,branch,expected", [
    ("deny", None, False), ("deny", 7, False),
    ("allow", None, True), ("allow", 7, None),
])
def test_pm_matrix_reflects_veto_without_certifying_object(effect, branch, expected):
    from app.routes import permissions_visual_audit_routes as visual
    user = actor()
    action = SimpleNamespace(
        id=61, full_key="pm.read", name="Consultar PM", is_active=True,
        module=SimpleNamespace(id=4, key="pm", name="PM", base_action_id=61),
    )
    context = {
        "user": user, "role": user.rol, "sucursal_ids": [7],
        "pm_scoped_read": False, "warehouse_operator": None,
        "planning_operator": None, "allow_ticket_delete_all": False,
    }
    grant = SimpleNamespace(
        id=88, effect=effect, scope_type="global", starts_at=None,
        expires_at=None, reason="QA", action_id=61,
        scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None,
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_PM_READ_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(
            user, action, context, {(61, "user", 47): grant}, branch_id=branch,
        )
    assert row["legacy_allowed"] is expected
    assert row["catalog_allowed"] is expected
    assert row["catalog_source"] == "pm_read_grant_operativo"
