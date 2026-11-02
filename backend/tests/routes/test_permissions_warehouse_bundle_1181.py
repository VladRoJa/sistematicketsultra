"""#1181: Warehouse view/upload/catalogs are vetoes after existing operator caps.

Synthetic JWT HTTP calls across shared consumers. No production data.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import warehouse_routes as wh
from app.routes import warehouse_agregadoras_routes as agg
from app.routes import warehouse_commercial_routes as commercial
from app.routes import google_ads_m6_continuity_routes as m6
from app.utils import warehouse_access as access


FLAGS = {
    "PERMISSIONS_WAREHOUSE_VIEW_GRANTS_ENABLED": True,
    "PERMISSIONS_WAREHOUSE_UPLOAD_GRANTS_ENABLED": True,
    "PERMISSIONS_WAREHOUSE_CATALOGS_GRANTS_ENABLED": True,
}


def client(**flags):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="warehouse-checks-test", **FLAGS)
    app.config.update(flags)
    JWTManager(app)
    app.register_blueprint(wh.warehouse_bp, url_prefix="/api/warehouse")
    app.register_blueprint(agg.warehouse_agregadoras_bp, url_prefix="/api/warehouse")
    app.register_blueprint(commercial.warehouse_commercial_bp, url_prefix="/api/warehouse")
    app.register_blueprint(m6.google_ads_m6_continuity_bp, url_prefix="/api/google-ads-m6")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


def operator(view=True, upload=True):
    return SimpleNamespace(can_view=view, can_upload=upload, can_archive=True)


def actor():
    return SimpleNamespace(id=47, rol="ADMINISTRADOR", username="qa")


@pytest.mark.parametrize("method,url", [
    ("get", "/api/warehouse/uploads"),
    ("post", "/api/warehouse/uploads"),
    ("get", "/api/warehouse/catalogs"),
    ("get", "/api/warehouse/agregadoras-consolidado/status"),
    ("post", "/api/warehouse/agregadoras-consolidado/generate"),
    ("get", "/api/warehouse/promotions/ranking"),
    ("post", "/api/google-ads-m6/manual/confirm"),
])
def test_routes_reject_missing_jwt(method, url):
    api, _ = client()
    assert getattr(api, method)(url).status_code == 401


@pytest.mark.parametrize("method,url,key,extra_env", [
    ("get", "/api/warehouse/uploads", "warehouse.view", None),
    ("get", "/api/warehouse/uploads/5", "warehouse.view", None),
    ("get", "/api/warehouse/uploads/5/download", "warehouse.view", None),
    ("get", "/api/warehouse/uploads/5/audit", "warehouse.view", None),
    ("get", "/api/warehouse/agregadoras-consolidado/status", "warehouse.view", None),
    ("get", "/api/warehouse/agregadoras-consolidado/download", "warehouse.view", None),
    ("get", "/api/warehouse/promotions/ranking", "warehouse.view", None),
    ("get", "/api/warehouse/promotions/summary", "warehouse.view", None),
    ("get", "/api/google-ads-m6/manual/correction-status", "warehouse.view", None),
    ("post", "/api/google-ads-m6/corrections/candidates/5/review", "warehouse.view",
     "CORRECTION_REVIEW"),
    ("get", "/api/warehouse/catalogs", "warehouse.catalogs", None),
    ("post", "/api/warehouse/uploads", "warehouse.upload", None),
    ("post", "/api/warehouse/agregadoras-consolidado/generate", "warehouse.upload", None),
    ("post", "/api/google-ads-m6/manual/confirm", "warehouse.upload", None),
    ("post", "/api/google-ads-m6/manual/ingest", "warehouse.upload",
     "GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED"),
    ("post", "/api/google-ads-m6/manual/publish", "warehouse.upload",
     "GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED"),
    ("post", "/api/google-ads-m6/corrections/raw/preview", "warehouse.upload",
     "CORRECTION_RAW"),
    ("post", "/api/google-ads-m6/corrections/raw/confirm", "warehouse.upload",
     "CORRECTION_RAW"),
    ("post", "/api/google-ads-m6/corrections/candidates/ingest", "warehouse.upload",
     "CORRECTION_CANDIDATE"),
    ("post", "/api/google-ads-m6/corrections/candidates/5/promote", "warehouse.upload",
     "CORRECTION_PROMOTION"),
])
def test_global_deny_vetoes_existing_route_before_side_effects(
    method, url, key, extra_env, monkeypatch
):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    env_key = {
        "CORRECTION_REVIEW": m6.CORRECTION_REVIEW_FLAG,
        "CORRECTION_RAW": m6.CORRECTION_RAW_FLAG,
        "CORRECTION_CANDIDATE": m6.CORRECTION_CANDIDATE_FLAG,
        "CORRECTION_PROMOTION": m6.CORRECTION_PROMOTION_FLAG,
    }.get(extra_env, extra_env)
    if env_key:
        monkeypatch.setenv(env_key, "true")
    with api.application.app_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id", return_value=actor()), \
         patch.object(m6, "require_current_admicorp", return_value=47), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant:
        response = getattr(api, method)(url, headers=headers)
    assert response.status_code == 403, (url, response.json)
    grant.assert_called_once()
    assert grant.call_args.kwargs["action_full_key"] == key


@pytest.mark.parametrize("key,gate,operator_config", [
    ("warehouse.view", access.require_warehouse_view, operator(False, True)),
    ("warehouse.upload", access.require_warehouse_upload, operator(True, False)),
    ("warehouse.catalogs", access.require_warehouse_catalogs, operator(False, False)),
    ("warehouse.catalogs", access.require_warehouse_catalogs, None),
])
def test_allow_never_bypasses_legacy_caps(key, gate, operator_config):
    from app.routes import permissions_catalog_routes as catalog
    app = Flask(__name__)
    app.config.update(FLAGS)
    with app.test_request_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator_config), \
         patch.object(access.UserORM, "get_by_id") as user, \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        resp = gate()
    assert resp[1] == 403
    user.assert_not_called()
    grant.assert_not_called()


@pytest.mark.parametrize("key,gate", [
    ("warehouse.view", access.require_warehouse_view),
    ("warehouse.upload", access.require_warehouse_upload),
    ("warehouse.catalogs", access.require_warehouse_catalogs),
])
@pytest.mark.parametrize("decision", [True, None])
def test_allow_and_inherit_preserve_legacy_permission(key, gate, decision):
    from app.routes import permissions_catalog_routes as catalog
    app = Flask(__name__)
    app.config.update(FLAGS)
    with app.test_request_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator()), \
         patch.object(access, "get_jwt_identity", return_value="47"), \
         patch.object(access.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=decision) as grant:
        assert gate() is None
    assert grant.call_args.kwargs["action_full_key"] == key


@pytest.mark.parametrize("flag,gate", [
    ("PERMISSIONS_WAREHOUSE_VIEW_GRANTS_ENABLED", access.require_warehouse_view),
    ("PERMISSIONS_WAREHOUSE_UPLOAD_GRANTS_ENABLED", access.require_warehouse_upload),
    ("PERMISSIONS_WAREHOUSE_CATALOGS_GRANTS_ENABLED", access.require_warehouse_catalogs),
])
def test_flag_off_skips_user_and_grants(flag, gate):
    from app.routes import permissions_catalog_routes as catalog
    app = Flask(__name__)
    app.config.update(FLAGS)
    app.config[flag] = False
    with app.test_request_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator()), \
         patch.object(access.UserORM, "get_by_id") as user, \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        assert gate() is None
    user.assert_not_called()
    grant.assert_not_called()


@pytest.mark.parametrize("gate", [
    access.require_warehouse_view,
    access.require_warehouse_upload,
    access.require_warehouse_catalogs,
])
def test_enabled_veto_requires_existing_user_even_with_operator(gate):
    from app.routes import permissions_catalog_routes as catalog
    app = Flask(__name__)
    app.config.update(FLAGS)
    with app.test_request_context(), \
         patch.object(access, "get_current_warehouse_operator",
                      return_value=operator()), \
         patch.object(access, "get_jwt_identity", return_value="47"), \
         patch.object(access.UserORM, "get_by_id", return_value=None), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        result = gate()
    assert result[1] == 403
    grant.assert_not_called()


def test_m6_admicorp_guard_precedes_warehouse_grant():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(m6, "require_current_admicorp",
                      side_effect=PermissionError()), \
         patch.object(access, "get_current_warehouse_operator") as warehouse, \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        response = api.post(
            "/api/google-ads-m6/manual/confirm", headers=headers
        )
    assert response.status_code == 403
    assert response.json["code"] == "FORBIDDEN"
    warehouse.assert_not_called()
    grant.assert_not_called()


def test_flags_default_off():
    with Flask(__name__).app_context():
        assert not access.warehouse_view_grants_enabled()
        assert not access.warehouse_upload_grants_enabled()
        assert not access.warehouse_catalogs_grants_enabled()


@pytest.mark.parametrize("key,caps", [
    ("warehouse.view", operator(True, False)),
    ("warehouse.upload", operator(False, True)),
    ("warehouse.catalogs", operator(False, True)),
])
@pytest.mark.parametrize("effect", ["allow", "deny"])
def test_matrix_shows_operational_global_veto(key, caps, effect):
    from app.routes import permissions_visual_audit_routes as visual
    user = SimpleNamespace(
        id=47, username="qa", rol="ADMINISTRADOR",
        sucursal_id=7, sucursales_ids=[7], department_id=1,
    )
    action = SimpleNamespace(
        id=65, full_key=key, name=key, is_active=True,
        module=SimpleNamespace(id=4, key="warehouse", name="Warehouse",
                               base_action_id=64),
    )
    ctx = {
        "user": user, "role": user.rol, "sucursal_ids": [7],
        "warehouse_operator": caps, "planning_operator": None,
        "allow_ticket_delete_all": False, "pm_scoped_read": False,
    }
    grant = SimpleNamespace(
        id=89, effect=effect, scope_type="global", action_id=65,
        starts_at=None, expires_at=None, reason="qa", scope_branch_id=None,
        scope_branch_ids=[], scope_department_id=None, scope_payload=None,
    )
    app = Flask(__name__)
    app.config.update(FLAGS)
    with app.app_context():
        result = visual.evaluate_pair(
            user, action, ctx, {(65, "user", 47): grant}, branch_id=7
        )
    expected = effect == "allow"
    assert result["legacy_allowed"] is expected
    assert result["catalog_allowed"] is expected
    assert result["catalog_source"] == "warehouse_grant_operativo"
