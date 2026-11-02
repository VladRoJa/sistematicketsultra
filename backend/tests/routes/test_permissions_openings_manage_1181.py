"""Aperturas: el check manage gobierna las 11 rutas admin sin tocar read/comment.

Fixtures sintéticos JWT. Rechazos se ejecutan antes de toda consulta o mutación.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import openings_routes as openings


ADMIN_URLS = [
    ("POST", "/api/openings"),
    ("PATCH", "/api/openings/1"),
    ("POST", "/api/openings/1/phases"),
    ("PATCH", "/api/openings/1/phases/2"),
    ("POST", "/api/openings/1/tasks"),
    ("PATCH", "/api/openings/1/tasks/2"),
    ("POST", "/api/openings/1/tasks/2/dependencies"),
    ("DELETE", "/api/openings/1/task-dependencies/3"),
    ("POST", "/api/openings/1/tasks/2/blockers"),
    ("PATCH", "/api/openings/1/task-blockers/3/resolve"),
    ("POST", "/api/openings/1/tasks/2/documents/upload"),
]


def client(*, manage=False, read=False, comment=False):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="synthetic-openings-manage-1181",
        PERMISSIONS_OPENINGS_MANAGE_GRANTS_ENABLED=manage,
        PERMISSIONS_OPENINGS_READ_GRANTS_ENABLED=read,
        PERMISSIONS_OPENINGS_COMMENT_GRANTS_ENABLED=comment,
    )
    JWTManager(app)
    app.register_blueprint(openings.openings_bp, url_prefix="/api/openings")
    with app.app_context():
        token = create_access_token(identity="77")
    return app.test_client(), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("method,url", ADMIN_URLS)
def test_manage_deny_blocks_every_admin_route_before_db(method, url):
    api, auth = client(manage=True)
    with patch.object(openings, "_openings_manage_override", return_value=False), \
         patch.object(openings, "_current_role", return_value="APERTURAS_ADMIN"), \
         patch.object(openings.db.session, "get") as read_db, \
         patch.object(openings.db.session, "add") as write_db:
        response = api.open(url, method=method, headers=auth, json={})
    assert response.status_code == 403, (method, url, response.get_json())
    read_db.assert_not_called()
    write_db.assert_not_called()


@pytest.mark.parametrize("method,url", ADMIN_URLS)
def test_admin_routes_still_require_jwt_even_with_manage_allow(method, url):
    api, _ = client(manage=True)
    with patch.object(openings, "_openings_manage_override", return_value=True):
        response = api.open(url, method=method, json={})
    assert response.status_code == 401, (method, url)


@pytest.mark.parametrize("role,override,allowed", [
    ("APERTURAS_ADMIN", None, True),
    ("RECEPCIONISTA", None, False),
    ("APERTURAS_ADMIN", False, False),
    ("RECEPCIONISTA", True, True),
])
def test_manage_guard_honors_global_action_override(role, override, allowed):
    app = Flask(__name__)
    with app.app_context(), \
         patch.object(openings, "_openings_manage_override", return_value=override), \
         patch.object(openings, "_current_role", return_value=role):
        result = openings._require_openings_admin()
    assert (result is None) is allowed
    if result is not None:
        assert result[1] == 403


def test_manage_allow_does_not_grant_read_or_comment():
    api, _ = client(manage=True)
    with api.application.app_context(), \
         patch.object(openings, "_current_role", return_value="RECEPCIONISTA"), \
         patch.object(openings, "_openings_manage_override", return_value=True):
        assert openings._require_openings_admin() is None
        assert openings._require_openings_read()[1] == 403
        assert openings._require_openings_comment()[1] == 403


def test_manage_flag_off_does_not_query_user_orm():
    api, _ = client(manage=False)
    with api.application.test_request_context("/api/openings", method="POST"), \
         patch.object(openings.UserORM, "get_by_id") as lookup:
        assert openings._openings_manage_override() is None
        lookup.assert_not_called()


def test_manage_override_resolves_jwt_actor_and_exact_action():
    from app.routes import permissions_catalog_routes as catalog
    api, auth = client(manage=True)
    seen = {}

    def fake_override(*, user, action_full_key):
        seen["user_id"] = user.id
        seen["action"] = action_full_key
        return True

    with api.application.test_request_context(
        "/api/openings", method="POST", headers=auth,
    ):
        from flask_jwt_extended import verify_jwt_in_request
        verify_jwt_in_request()
        with patch.object(
            openings.UserORM, "get_by_id",
            return_value=SimpleNamespace(id=77, rol="RECEPCIONISTA"),
        ), patch.object(catalog, "_simple_global_action_grant_override",
                        side_effect=fake_override):
            assert openings._openings_manage_override() is True
    assert seen == {"user_id": 77, "action": "openings.manage"}


@pytest.mark.parametrize("role,effect,enabled,expected", [
    ("APERTURAS_ADMIN", "deny", True, False),
    ("RECEPCIONISTA", "allow", True, True),
    ("APERTURAS_ADMIN", "deny", False, True),
])
def test_matrix_manage_matches_flag_and_guard(role, effect, enabled, expected):
    from app.routes import permissions_visual_audit_routes as visual

    user = SimpleNamespace(
        id=77, username="QA_MANAGE", rol=role,
        sucursal_id=1, sucursales_ids=[1], department_id=1,
    )
    action = SimpleNamespace(
        id=29, full_key="openings.manage", name="Gestionar aperturas",
        is_active=True,
        module=SimpleNamespace(id=5, key="openings", name="Aperturas", base_action_id=12),
    )
    context = {
        "user": user, "role": role, "sucursal_ids": [1],
        "warehouse_operator": None, "planning_operator": None,
        "allow_ticket_delete_all": False, "pm_scoped_read": False,
    }
    grant = SimpleNamespace(
        id=200, action_id=29, effect=effect, scope_type="global",
        scope_branch_id=None, scope_branch_ids=[], scope_department_id=None,
        scope_payload=None, starts_at=None, expires_at=None, reason="QA manage",
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_OPENINGS_MANAGE_GRANTS_ENABLED"] = enabled
    with app.app_context():
        row = visual.evaluate_pair(
            user, action, context, {(29, "user", 77): grant},
        )
    assert row["legacy_allowed"] is expected
    if enabled:
        assert row["catalog_allowed"] is expected
        assert row["catalog_source"] == "openings_manage_grant_operativo"
        assert row["comparison"] == "coincide"
    else:
        assert row["legacy_source"] == "openings._require_openings_admin"


def test_manage_allow_reaches_real_patch_resource_validation_without_mutation():
    api, auth = client(manage=True, read=False, comment=False)
    with patch.object(openings, "_openings_manage_override", return_value=True), \
         patch.object(openings, "_current_role", return_value="RECEPCIONISTA"), \
         patch.object(openings.db.session, "get", return_value=None) as read_db, \
         patch.object(openings.db.session, "add") as write_db, \
         patch.object(openings.db.session, "commit") as commit_db:
        response = api.patch(
            "/api/openings/1",
            headers=auth,
            json={"name": "QA no resource"},
        )
    # Grant de gestión permite llegar hasta las reglas de existencia del
    # objeto, NO crea ni edita una apertura inexistente.
    assert response.status_code == 404
    read_db.assert_called_once()
    write_db.assert_not_called()
    commit_db.assert_not_called()
