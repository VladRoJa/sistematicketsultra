"""#1178: pm.configure es veto global para crear/actualizar programación PM.

Sólo Flask/JWT y mocks; sin escrituras productivas ni migración.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import pm_routes as pm


POST_URL = "/api/pm/configuraciones"
PUT_URL = "/api/pm/configuraciones/83"


def create_payload(*, branch=7, frequency=30):
    return {
        "inventario_id": 200,
        "sucursal_id": branch,
        "frecuencia_dias": frequency,
        "fecha_base_programacion": "2026-11-02",
    }


def actor(role="ADMINISTRADOR", branches=(7,), primary=7):
    return SimpleNamespace(
        id=47, username="QA", rol=role,
        sucursal_id=primary, sucursales_ids=list(branches),
        department_id=1,
    )


def config(branch=7):
    return SimpleNamespace(
        id=83, inventario_id=200, sucursal_id=branch,
        frecuencia_dias=30, activo=True,
        fecha_base_programacion=None,
    )


def db_for(existing_config=None):
    return SimpleNamespace(session=SimpleNamespace(
        get=Mock(return_value=existing_config),
        add=Mock(), commit=Mock(),
    ))


def client(enabled=True):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="qa-pm-configure-1181",
        PERMISSIONS_PM_CONFIGURE_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(pm.pm_bp, url_prefix="/api/pm")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("method,url,body", [
    ("post", POST_URL, create_payload()),
    ("put", PUT_URL, {"frecuencia_dias": 31}),
])
def test_pm_configure_requires_jwt(method, url, body):
    api, _ = client()
    assert getattr(api, method)(url, json=body).status_code == 401


@pytest.mark.parametrize("method,url,body", [
    ("post", POST_URL, create_payload()),
    ("put", PUT_URL, {"activo": False}),
])
def test_deny_veto_blocks_both_writes_before_scope_or_commit(method, url, body):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    fake_db = db_for(config())
    with api.application.app_context(), \
         patch.object(pm, "db", fake_db), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor(), None)), \
         patch.object(pm, "_verificar_permiso_sucursal") as scope, \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant:
        response = getattr(api, method)(url, json=body, headers=headers)
    assert response.status_code == 403
    assert response.json["detail"] == "No tienes habilitada la programación de preventivos."
    grant.assert_called_once()
    assert grant.call_args.kwargs["action_full_key"] == "pm.configure"
    scope.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.commit.assert_not_called()


@pytest.mark.parametrize("method,url,body", [
    ("post", POST_URL, create_payload()),
    ("put", PUT_URL, {"activo": False}),
])
def test_allow_does_not_elevate_unauthorized_role(method, url, body):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    fake_db = db_for(config())
    with api.application.app_context(), \
         patch.object(pm, "db", fake_db), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor("AUX_MANTENIMIENTO"), None)), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = getattr(api, method)(url, json=body, headers=headers)
    assert response.status_code == 403
    grant.assert_not_called()
    fake_db.session.commit.assert_not_called()


@pytest.mark.parametrize("method,url,body", [
    ("post", POST_URL, create_payload(branch=999)),
    ("put", PUT_URL, {"frecuencia_dias": 35}),
])
def test_allow_cannot_expand_branch_scope(method, url, body):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    fake_db = db_for(config(branch=999))
    with api.application.app_context(), \
         patch.object(pm, "db", fake_db), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor("SR_MANTENIMIENTO"), None)), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = getattr(api, method)(url, json=body, headers=headers)
    assert response.status_code == 403
    grant.assert_called_once()
    fake_db.session.commit.assert_not_called()


def test_allow_still_checks_inventario_sucursal_relation():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    relation_query = SimpleNamespace(filter_by=lambda **kw: SimpleNamespace(first=lambda: None))
    with api.application.app_context(), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor(), None)), \
         patch.object(pm.InventarioSucursal, "query", relation_query), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.post(POST_URL, json=create_payload(), headers=headers)
    assert response.status_code == 400
    assert "no pertenece" in response.json["detail"]
    grant.assert_called_once()


def test_allow_does_not_bypass_duplicate_config_guard():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    relation_query = SimpleNamespace(filter_by=lambda **kw: SimpleNamespace(
        first=lambda: SimpleNamespace(id=1)
    ))
    existing_query = SimpleNamespace(filter_by=lambda **kw: SimpleNamespace(
        first=lambda: config()
    ))
    with api.application.app_context(), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor(), None)), \
         patch.object(pm.InventarioSucursal, "query", relation_query), \
         patch.object(pm.PmPreventivoConfigORM, "query", existing_query), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.post(POST_URL, json=create_payload(), headers=headers)
    assert response.status_code == 409
    grant.assert_called_once()


def test_allow_still_validates_update_payload_before_mutation():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    fake_db = db_for(config())
    with api.application.app_context(), \
         patch.object(pm, "db", fake_db), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor(), None)), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.put(PUT_URL, json={"frecuencia_dias": 0}, headers=headers)
    assert response.status_code == 400
    assert "mayor a 0" in response.json["detail"]
    grant.assert_called_once()
    fake_db.session.commit.assert_not_called()


@pytest.mark.parametrize("method,url,body", [
    ("post", POST_URL, {"frecuencia_dias": 0}),
    ("put", PUT_URL, {"activo": False}),
])
def test_flag_off_preserves_legacy_and_skips_grant_query(method, url, body):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=False)
    fake_db = db_for(config())
    with api.application.app_context(), \
         patch.object(pm, "db", fake_db), \
         patch.object(pm, "_obtener_usuario_actual_pm",
                      return_value=(actor(), None)), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        if method == "put":
            response = api.put(url, json={"frecuencia_dias": 0}, headers=headers)
        else:
            response = api.post(url, json=body, headers=headers)
    assert response.status_code == 400
    grant.assert_not_called()
    fake_db.session.commit.assert_not_called()


def test_flag_defaults_off():
    with Flask(__name__).app_context():
        assert pm.pm_configure_grants_enabled() is False


@pytest.mark.parametrize("effect,branch,legacy,catalog_allowed", [
    ("deny", None, False, False),
    ("deny", 7, False, False),
    ("allow", None, True, True),
    ("allow", 7, None, None),
])
def test_matrix_global_veto_does_not_certify_scope(effect, branch, legacy, catalog_allowed):
    from app.routes import permissions_visual_audit_routes as visual
    user = actor()
    action = SimpleNamespace(
        id=89, full_key="pm.configure", name="Programar PM", is_active=True,
        module=SimpleNamespace(id=4, key="pm", name="PM", base_action_id=80),
    )
    context = {
        "user": user, "role": user.rol, "sucursal_ids": [7],
        "warehouse_operator": None, "planning_operator": None,
        "allow_ticket_delete_all": False, "pm_scoped_read": False,
    }
    grant = SimpleNamespace(
        id=88, effect=effect, scope_type="global", starts_at=None,
        expires_at=None, reason="QA", action_id=89,
        scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None,
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_PM_CONFIGURE_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(user, action, context,
                                   {(89, "user", 47): grant}, branch_id=branch)
    assert row["legacy_allowed"] is legacy
    assert row["catalog_allowed"] is catalog_allowed
    assert row["catalog_source"] == "pm_configure_grant_operativo"
