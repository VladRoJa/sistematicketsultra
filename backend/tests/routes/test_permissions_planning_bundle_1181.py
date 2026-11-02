"""Planning six action checks: role/capability gate, JWT, grants and HTTP.

Fixtures only: no database writes and no actual publication to Track.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import planning_targets_routes as routes
from app.utils import planning_access as access


ACTIONS = [
    ("planning.read", "can_view", access.require_planning_operator),
    ("planning.edit", "can_edit", access.require_planning_edit),
    ("planning.submit", "can_submit", access.require_planning_submit),
    ("planning.approve", "can_approve", access.require_planning_approve),
    ("planning.publish", "can_publish", access.require_planning_publish),
    ("planning.configure_model", "can_configure_model",
     access.require_planning_model_config),
]

ROUTES = [
    ("get", "/branches", "planning.read"),
    ("get", "/branches/MEXICALI/prefill", "planning.read"),
    ("get", "/branches/MEXICALI/comparisons", "planning.read"),
    ("get", "/model-configs", "planning.read"),
    ("get", "/batches", "planning.configure_model"),
    ("get", "/batches/5", "planning.submit"),
    ("post", "/model-configs", "planning.configure_model"),
    ("post", "/batches", "planning.configure_model"),
    ("post", "/batches/5/branch-rows", "planning.configure_model"),
    ("put", "/batches/5/branch-rows/8", "planning.edit"),
    ("post", "/batches/5/submit", "planning.submit"),
    ("post", "/batches/5/approve", "planning.approve"),
    ("post", "/batches/5/reject", "planning.approve"),
    ("post", "/batches/5/publish", "planning.publish"),
]


def operator(**flags):
    defaults = {
        "is_active": True, "can_view": True, "can_edit": True,
        "can_submit": True, "can_approve": True, "can_publish": True,
        "can_configure_model": True,
    }
    defaults.update(flags)
    return SimpleNamespace(**defaults)


def actor():
    return SimpleNamespace(id=47, username="planning-qa", rol="ADMINISTRADOR")


def client(flags_enabled=True):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="planning-qa-1181")
    for name in access.PLANNING_GRANT_FLAGS.values():
        app.config[name] = flags_enabled
    JWTManager(app)
    app.register_blueprint(routes.planning_targets_bp)
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("method,url,action", ROUTES)
def test_http_denies_without_jwt(method, url, action):
    api, _ = client()
    assert getattr(api, method)("/api/planning/targets" + url).status_code == 401


@pytest.mark.parametrize("method,url,action", ROUTES)
def test_global_deny_applies_to_actual_http_guard_before_services(
    method, url, action,
):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(access, "get_current_planning_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant:
        resp = getattr(api, method)("/api/planning/targets" + url,
                                    headers=headers)
    assert resp.status_code == 403, (method, url, resp.json)
    grant.assert_called_once()
    assert grant.call_args.kwargs["action_full_key"] == action


@pytest.mark.parametrize("key,capability,guard", ACTIONS)
def test_allow_cannot_create_missing_or_inactive_operator_or_capability(
    key, capability, guard,
):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    for op in (None, operator(is_active=False), operator(**{capability: False})):
        # Inactive operators are discarded by the existing query itself.
        real_operator = None if op is None or not op.is_active else op
        with api.application.test_request_context(headers=headers), \
             patch.object(access, "get_current_planning_operator",
                          return_value=real_operator), \
             patch.object(access.UserORM, "get_by_id") as user, \
             patch.object(catalog, "_simple_global_action_grant_override",
                          return_value=True) as grant:
            result = guard()
        assert result[1] == 403
        user.assert_not_called()
        grant.assert_not_called()


@pytest.mark.parametrize("key,capability,guard", ACTIONS)
@pytest.mark.parametrize("decision", [True, None])
def test_allow_and_inherit_preserve_current_operator_capability(
    key, capability, guard, decision,
):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.test_request_context(headers=headers), \
         patch.object(access, "get_jwt_identity", return_value="47"), \
         patch.object(access, "get_current_planning_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=decision) as grant:
        assert guard() is None
    assert grant.call_args.kwargs["action_full_key"] == key


@pytest.mark.parametrize("key,capability,guard", ACTIONS)
def test_flags_off_skip_permission_lookup(key, capability, guard):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(flags_enabled=False)
    with api.application.test_request_context(headers=headers), \
         patch.object(access, "get_current_planning_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id") as lookup, \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        assert guard() is None
    lookup.assert_not_called()
    grant.assert_not_called()


def test_missing_user_fails_closed_with_active_flag():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.test_request_context(headers=headers), \
         patch.object(access, "get_current_planning_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id", return_value=None), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        result = access.require_planning_publish()
    assert result[1] == 403
    grant.assert_not_called()


def test_default_flags_off():
    with Flask(__name__).app_context():
        assert all(
            access.planning_action_grants_enabled(key) is False
            for key, _, _ in ACTIONS
        )


def test_access_payload_reflects_denied_capability_without_changing_others():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    def veto(*, user, action_full_key):
        return False if action_full_key == "planning.publish" else None
    with api.application.app_context(), \
         patch.object(access, "get_current_planning_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      side_effect=veto):
        resp = api.get("/api/planning/targets/access", headers=headers)
    assert resp.status_code == 200
    body = resp.json
    # _success wraps service result; retain the contract to the UI.
    effective = body.get("data", body)
    if "can_publish" not in effective:
        effective = effective.get("access", effective)
    assert effective["can_publish"] is False
    assert effective["can_view"] is True
    assert effective["can_approve"] is True
    assert effective["has_access"] is True


@pytest.mark.parametrize("key,capability,guard", ACTIONS)
@pytest.mark.parametrize("effect,expected", [("deny", False), ("allow", True)])
def test_visual_matrix_global_veto_matches_runtime(key, capability, guard,
                                                    effect, expected):
    from app.routes import permissions_visual_audit_routes as visual
    user = SimpleNamespace(
        id=47, username="qa", rol="ADMINISTRADOR", sucursal_id=7,
        sucursales_ids=[7], department_id=1,
    )
    action = SimpleNamespace(
        id=65, full_key=key, name=key, is_active=True,
        module=SimpleNamespace(
            id=4, key="planning", name="Planeación", base_action_id=64,
        ),
    )
    ctx = {
        "user": user, "role": user.rol, "sucursal_ids": [7],
        "warehouse_operator": None, "planning_operator": operator(),
        "allow_ticket_delete_all": False, "pm_scoped_read": False,
    }
    grant = SimpleNamespace(
        id=89, effect=effect, scope_type="global", action_id=65,
        starts_at=None, expires_at=None, reason="qa", scope_branch_id=None,
        scope_branch_ids=[], scope_department_id=None, scope_payload=None,
    )
    app = Flask(__name__)
    for name in access.PLANNING_GRANT_FLAGS.values():
        app.config[name] = True
    with app.app_context():
        result = visual.evaluate_pair(
            user, action, ctx, {(65, "user", 47): grant},
            branch_id=7,
        )
    assert result["legacy_allowed"] is expected
    assert result["catalog_allowed"] is expected
    assert result["catalog_source"] == "planning_grant_operativo"
