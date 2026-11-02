"""#1178: Warehouse archive checkbox is a veto, never an operator grant.

Synthetic HTTP + JWT only; no production Warehouse DB or file mutation.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import warehouse_routes as routes
from app.utils import warehouse_access as access

URL = "/api/warehouse/uploads/31/archive"


def actor():
    return SimpleNamespace(id=47, username="QA", rol="ADMINISTRADOR")


def operator(can_archive=True):
    return SimpleNamespace(
        user_id=47, can_view=True, can_upload=True, can_archive=can_archive,
    )


def client(enabled=True):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="synthetic-warehouse-archive",
        PERMISSIONS_WAREHOUSE_ARCHIVE_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(routes.warehouse_bp, url_prefix="/api/warehouse")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


def fake_upload_query(value):
    return SimpleNamespace(filter_by=lambda **kwargs:
        SimpleNamespace(first=lambda: value))


def test_archive_requires_jwt():
    api, _ = client()
    assert api.patch(URL).status_code == 401


@pytest.mark.parametrize("can_archive", [False, None])
def test_allow_cannot_bypass_operator_capability(can_archive):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator(False) if can_archive is False else None), \
         patch.object(access.UserORM, "get_by_id") as user_lookup, \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.patch(URL, headers=headers)
    assert response.status_code == 403
    user_lookup.assert_not_called()
    grant.assert_not_called()


def test_deny_blocks_archive_before_upload_lookup_or_commit():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant, \
         patch.object(routes.WarehouseUploadORM, "query") as query, \
         patch.object(routes.db.session, "commit") as commit, \
         patch.object(routes, "log_warehouse_audit") as audit:
        response = api.patch(URL, headers=headers)
    assert response.status_code == 403
    assert response.json["detail"] == "No tienes habilitado archivar documentos de Warehouse"
    grant.assert_called_once()
    assert grant.call_args.kwargs["action_full_key"] == "warehouse.archive"
    query.filter_by.assert_not_called()
    commit.assert_not_called()
    audit.assert_not_called()


def test_missing_user_with_flag_on_fails_closed():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id", return_value=None), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        response = api.patch(URL, headers=headers)
    assert response.status_code == 403
    grant.assert_not_called()


@pytest.mark.parametrize("decision", [True, None])
def test_allow_or_inherit_preserves_missing_upload_404(decision):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=decision) as grant, \
         patch.object(routes.WarehouseUploadORM, "query", fake_upload_query(None)), \
         patch.object(routes.db.session, "commit") as commit:
        response = api.patch(URL, headers=headers)
    assert response.status_code == 404
    grant.assert_called_once()
    commit.assert_not_called()


def test_allow_preserves_already_archived_rule_without_commit():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    upload = SimpleNamespace(id=31, status="ARCHIVED")
    with api.application.app_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant, \
         patch.object(routes.WarehouseUploadORM, "query", fake_upload_query(upload)), \
         patch.object(routes.db.session, "commit") as commit:
        response = api.patch(URL, headers=headers)
    assert response.status_code == 400
    assert upload.status == "ARCHIVED"
    grant.assert_called_once()
    commit.assert_not_called()


def test_allow_does_not_change_audit_or_archival_semantics():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    upload = SimpleNamespace(
        id=31, status="ACTIVE", original_filename="qa.xlsx",
        stored_filename="qa-stored.xlsx",
    )
    with api.application.app_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant, \
         patch.object(routes.WarehouseUploadORM, "query", fake_upload_query(upload)), \
         patch.object(routes, "log_warehouse_audit") as audit, \
         patch.object(routes.db.session, "commit") as commit:
        response = api.patch(URL, headers=headers)
    assert response.status_code == 200
    assert response.json["status"] == "ARCHIVED"
    assert upload.status == "ARCHIVED"
    audit.assert_called_once()
    assert audit.call_args.kwargs["action"] == "ARCHIVE"
    commit.assert_called_once()
    grant.assert_called_once()


def test_flag_off_skips_grants_and_user_lookup():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=False)
    with api.application.app_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id") as lookup, \
         patch.object(catalog, "_simple_global_action_grant_override") as grant, \
         patch.object(routes.WarehouseUploadORM, "query", fake_upload_query(None)):
        response = api.patch(URL, headers=headers)
    assert response.status_code == 404
    lookup.assert_not_called()
    grant.assert_not_called()


def test_flag_defaults_off():
    with Flask(__name__).app_context():
        assert access.warehouse_archive_grants_enabled() is False


@pytest.mark.parametrize("effect,has_operator,branch,expected", [
    ("deny", True, None, False),
    ("deny", True, 7, False),
    ("allow", True, None, True),
    ("allow", True, 7, True),
    ("allow", False, None, False),
])
def test_matrix_global_veto_never_grants_operator(effect, has_operator, branch, expected):
    from app.routes import permissions_visual_audit_routes as visual
    user = SimpleNamespace(
        id=47, username="QA", rol="ADMINISTRADOR",
        sucursal_id=7, sucursales_ids=[7], department_id=1,
    )
    action = SimpleNamespace(
        id=88, full_key="warehouse.archive", name="Archivar Warehouse",
        is_active=True,
        module=SimpleNamespace(id=4, key="warehouse", name="Warehouse",
                               base_action_id=80),
    )
    context = {
        "user": user, "role": user.rol, "sucursal_ids": [7],
        "warehouse_operator": operator() if has_operator else None,
        "planning_operator": None, "allow_ticket_delete_all": False,
        "pm_scoped_read": False,
    }
    grant = SimpleNamespace(
        id=99, effect=effect, scope_type="global", action_id=88,
        starts_at=None, expires_at=None, reason="QA",
        scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None,
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_WAREHOUSE_ARCHIVE_GRANTS_ENABLED"] = True
    with app.app_context():
        result = visual.evaluate_pair(user, action, context,
                                      {(88, "user", 47): grant}, branch_id=branch)
    assert result["legacy_allowed"] is expected
    assert result["catalog_allowed"] is expected
    assert result["catalog_source"] == "warehouse_archive_grant_operativo"
