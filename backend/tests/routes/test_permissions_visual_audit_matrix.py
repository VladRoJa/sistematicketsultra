"""Auditoría visual V1: paridad entre perspectivas, triestado y seguridad HTTP.

Los fixtures son sintéticos. No se escriben grants ni se accede a producción.
"""
from types import SimpleNamespace

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.models.user_model import UserORM
from app.routes import permissions_catalog_routes as catalog
from app.routes import permissions_visual_audit_routes as visual


def make_user(role="GERENTE", branches=(7,), username="QA_USER"):
    return SimpleNamespace(
        id=77, username=username, rol=role, sucursal_id=7,
        sucursales_ids=list(branches), department_id=1,
    )


def make_action(key, *, is_active=True):
    module_key, action_key = key.split(".", 1)
    return SimpleNamespace(
        id=12, full_key=key, key=action_key, name=key,
        is_active=is_active,
        module=SimpleNamespace(key=module_key, name=module_key, base_action_id=12),
    )


def make_context(user, *, warehouse=None, planning=None):
    return {
        "user": user, "role": user.rol.upper(),
        "sucursal_ids": sorted(set(user.sucursales_ids + [user.sucursal_id])),
        "warehouse_operator": warehouse,
        "planning_operator": planning,
        "pm_scoped_read": False,
        "allow_ticket_delete_all": False,
    }


@pytest.mark.parametrize("role,legacy,catalog_allowed,comparison", [
    ("GERENTE", True, False, "diferencia"),
    ("RECEPCIONISTA", False, False, "coincide"),
    ("ADMINISTRADOR", True, True, "coincide"),
])
def test_track_read_shared_evaluator_detects_gaps(role, legacy, catalog_allowed, comparison):
    user = make_user(role)
    row = visual.evaluate_pair(user, make_action("track.read"), make_context(user))
    assert row["legacy_allowed"] is legacy
    assert row["catalog_allowed"] is catalog_allowed
    assert row["comparison"] == comparison


@pytest.mark.parametrize("view", ["user", "module", "action"])
@pytest.mark.parametrize("branch_id", [None, 7, 15])
def test_one_pair_yields_identical_decision_from_all_views(view, branch_id):
    user = make_user("SISTEMAS")
    action = make_action("warehouse.view")
    operator = SimpleNamespace(can_view=True, can_upload=False, can_archive=False)
    context = make_context(user, warehouse=operator)
    row = visual.evaluate_pair(user, action, context, branch_id=branch_id)
    # Cada perspectiva invoca la misma función, no derivaciones de roles propias.
    assert row["legacy_allowed"] is True
    assert row["catalog_allowed"] is True
    assert row["comparison"] == "coincide"
    assert row["context"]["branch_id"] == branch_id
    assert row["scope"] == "global"


def test_warehouse_denial_and_planning_inactive_operator():
    user = make_user("GERENTE")
    context = make_context(user)
    row = visual.evaluate_pair(user, make_action("warehouse.upload"), context)
    assert row["legacy_allowed"] is False and row["status"] == "denegado"
    planning = SimpleNamespace(is_active=False, can_approve=True)
    context = make_context(user, planning=planning)
    row = visual.evaluate_pair(user, make_action("planning.approve"), context)
    assert row["legacy_allowed"] is False


def test_internal_documents_manager_difference_from_real_pure_guard():
    user = make_user("SISTEMAS", username="SISTEMAS_QA")
    row = visual.evaluate_pair(
        user, make_action("internal_documents.manage"), make_context(user),
    )
    assert row["legacy_allowed"] is True
    assert row["catalog_allowed"] is False
    assert row["comparison"] == "diferencia"


def test_document_scope_without_object_unknown_then_guard_evaluated(monkeypatch):
    user = make_user("RECEPCIONISTA")
    action = make_action("internal_documents.view")
    context = make_context(user)
    unknown = visual.evaluate_pair(user, action, context)
    assert unknown["legacy_allowed"] is None
    assert unknown["comparison"] == "no_concluyente"
    calls = []
    monkeypatch.setattr(visual, "can_view_internal_document",
                        lambda document, doc_context: calls.append(document.id) or False)
    row = visual.evaluate_pair(user, action, context, document=SimpleNamespace(id=999))
    assert calls == [999]
    assert row["legacy_allowed"] is False
    assert row["catalog_allowed"] is True
    assert row["comparison"] == "diferencia"
    assert row["scope"] == "documento"


@pytest.mark.parametrize("action_key", [
    "pm.validate", "inventory.movement_write", "tickets.delete_all", "tickets.close",
])
def test_unverified_specific_guards_remain_unknown(action_key):
    user = make_user("ADMINISTRADOR")
    row = visual.evaluate_pair(
        user, make_action(action_key), make_context(user), branch_id=7,
    )
    assert row["legacy_allowed"] is None
    assert row["status"] == "no_concluyente"
    assert row["comparison"] == "no_concluyente"


def test_catalog_unmapped_does_not_count_as_denial():
    user = make_user("ADMINISTRADOR")
    row = visual.evaluate_pair(user, make_action("custom.unknown"), make_context(user))
    assert row["catalog_allowed"] is None
    assert row["legacy_allowed"] is None
    assert row["comparison"] == "no_concluyente"


def test_scoped_or_time_bounded_grants_never_masquerade_as_enforcement():
    user = make_user("GERENTE")
    grant = SimpleNamespace(
        scope_type="branch", starts_at=None, expires_at=None,
        reason="solo sucursal 7", effect="allow",
    )
    row = visual.evaluate_pair(
        user, make_action("warehouse.view"), make_context(user),
        grants={(12, "user", user.id): grant}, branch_id=7,
    )
    assert row["legacy_allowed"] is False
    assert row["catalog_allowed"] is None
    assert row["catalog_source"] == "grant_diagnostico_no_enforcement"
    assert row["comparison"] == "no_concluyente"


@pytest.mark.parametrize("limit,offset", [(0, 0), (51, 0), (1, -1), ("x", 0)])
def test_pagination_rejects_invalid_ranges(limit, offset):
    app = Flask(__name__)
    with app.test_request_context(f"/?limit={limit}&offset={offset}"):
        with pytest.raises(ValueError):
            visual._pagination()


def test_pagination_defaults_and_positive_bounds():
    app = Flask(__name__)
    with app.test_request_context("/"):
        assert visual._pagination() == (25, 0)
    with app.test_request_context("/?limit=50&offset=75"):
        assert visual._pagination() == (50, 75)


def test_search_and_role_are_cumulative_sql_filters():
    app = Flask(__name__)
    with app.test_request_context("/?q=GER&role=GERENTE"):
        sql = str(visual._user_query().statement.compile())
    assert "upper" in sql.lower() and "ilike" in sql.lower()
    assert "users.rol" in sql.lower()


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.config["JWT_SECRET_KEY"] = "tests-only-visual-permissions"
    JWTManager(app)
    app.register_blueprint(
        visual.permissions_visual_audit_bp, url_prefix="/api/permissions/catalog/audit",
    )
    monkeypatch.setattr(
        UserORM, "get_by_id", classmethod(
            lambda cls, uid: SimpleNamespace(
                id=uid, rol="ADMINISTRADOR" if uid == 1 else "GERENTE",
            )
        ),
    )
    return app


def test_http_admin_gate_is_enforced_before_fetching_records(app):
    with app.app_context():
        client = app.test_client()
        admin_token = create_access_token(identity="1")
        ordinary_token = create_access_token(identity="2")
        path = "/api/permissions/catalog/audit/matrix?view=user"
        assert client.get(path).status_code == 401
        ordinary = client.get(path, headers={"Authorization": f"Bearer {ordinary_token}"})
        assert ordinary.status_code == 403
        admin = client.get(path, headers={"Authorization": f"Bearer {admin_token}"})
        assert admin.status_code == 400  # admin pasa guard; le falta user_id


def test_route_is_only_get_and_no_mutating_permission_endpoints(app):
    methods = {
        rule.rule: rule.methods for rule in app.url_map.iter_rules()
        if rule.rule.endswith("/audit/matrix")
    }
    assert len(methods) == 1
    assert "GET" in next(iter(methods.values()))
    assert "PUT" not in next(iter(methods.values()))
    assert "POST" not in next(iter(methods.values()))
