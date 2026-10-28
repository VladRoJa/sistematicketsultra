"""B5: pruebas sintéticas de seguridad del editor beta sin grants productivos."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import permissions_b5_beta_routes as beta


def payload(**changes):
    value = {
        "principal_user_id": 89,
        "action_full_key": "internal_documents.view",
        "effect": "allow",
        "scope_type": "branch_list",
        "scope_branch_id": None,
        "scope_branch_ids": [1, 2],
        "starts_at": "2026-11-01T09:00:00-08:00",
        "expires_at": "2026-11-08T09:00:00-08:00",
        "reason": "Excepcion diagnostica de prueba B5",
    }
    value.update(changes)
    return value


def client(*, enabled=False):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="b5-fixture-jwt",
        PERMISSIONS_B5_EDITOR_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(
        beta.permissions_b5_beta_bp,
        url_prefix="/api/permissions/catalog",
    )
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


def test_b5_flag_is_off_by_default(monkeypatch):
    c, headers = client()
    monkeypatch.setattr(beta, "_current_admin_user_or_error",
                        lambda: (SimpleNamespace(id=47), None))
    response = c.get("/api/permissions/catalog/grants/beta/status", headers=headers)
    assert response.status_code == 200
    assert response.json["enabled"] is False
    assert response.json["grants_enforced"] is False
    assert response.json["object_access_certified"] is False
    assert response.json["action_full_key"] == "internal_documents.view"


@pytest.mark.parametrize("method,url", [
    ("post", "/api/permissions/catalog/grants/beta"),
    ("patch", "/api/permissions/catalog/grants/beta/1"),
    ("post", "/api/permissions/catalog/grants/beta/1/disable"),
])
def test_b5_flag_off_denies_all_write_methods_without_db(monkeypatch, method, url):
    c, headers = client()
    monkeypatch.setattr(beta, "_current_admin_user_or_error",
                        lambda: (SimpleNamespace(id=47), None))
    monkeypatch.setattr(beta, "_evaluate",
                        lambda *_args, **_kwargs: pytest.fail("No DB reads under disabled writer"))
    response = getattr(c, method)(url, headers=headers, json=payload())
    assert response.status_code == 403
    assert "deshabilitado" in response.json["detail"]


def test_b5_rejects_missing_token_before_admin_check():
    c, _ = client()
    assert c.post("/api/permissions/catalog/grants/beta", json=payload()).status_code == 401


def test_b5_rejects_non_admin_even_when_flag_true(monkeypatch):
    c, headers = client(enabled=True)
    monkeypatch.setattr(beta, "_current_admin_user_or_error",
                        lambda: (None, beta._error("No autorizado", 403)))
    response = c.post("/api/permissions/catalog/grants/beta", headers=headers, json=payload())
    assert response.status_code == 403


@pytest.mark.parametrize("changes", [
    {"action_full_key": "internal_documents.manage"},
    {"action_full_key": "tickets.maintenance.coordinate"},
    {"action_full_key": "tickets.maintenance.read_assigned_only"},
    {"action_full_key": "inventory.correction_approve"},
    {"action_full_key": "reports.read"},
    {"scope_type": "global"},
    {"scope_type": "custom"},
    {"scope_type": "department"},
    {"scope_branch_ids": [1, 1]},
    {"scope_branch_ids": []},
    {"scope_branch_ids": [True]},
    {"scope_branch_ids": [1, "2"]},
    {"starts_at": "2026-11-01T09:00:00"},
    {"expires_at": "2026-10-30T09:00:00-08:00"},
    {"principal_user_id": True},
    {"reason": "   "},
    {"scope_payload": {"sucursal_id": 1}},
])
def test_b5_invalid_scope_action_and_time_are_rejected(changes):
    with pytest.raises(ValueError):
        beta._normalize_input(payload(**changes))


def test_b5_normalizes_times_utc_and_scope():
    normalized = beta._normalize_input(payload())
    assert normalized["branches"] == [1, 2]
    assert normalized["starts_at"].isoformat() == "2026-11-01T17:00:00+00:00"


@pytest.mark.parametrize("old_start,old_end,new_start,new_end,expected", [
    (None, None, None, None, True),
    ("2026-01-01", "2026-02-01", "2026-02-01", "2026-03-01", False),
    ("2026-01-01", "2026-02-01", "2026-01-31", "2026-03-01", True),
    ("2026-02-01", "2026-03-01", "2026-01-01", "2026-02-01", False),
    ("2026-02-01", None, "2026-01-01", "2026-02-02", True),
])
def test_b5_half_open_temporal_conflicts(old_start, old_end, new_start, new_end, expected):
    def dt(x):
        return datetime.fromisoformat(x).replace(tzinfo=timezone.utc) if x else None
    assert beta._overlap_dates(
        dt(old_start), dt(old_end), dt(new_start), dt(new_end),
    ) is expected


@pytest.mark.parametrize("scope,branch,branches,expected", [
    ("branch", 7, [], {7}),
    ("branch_list", None, [7, 8], {7, 8}),
    ("branch_list", None, [], None),
    ("global", None, [], None),
    ("custom", None, [], None),
    ("branch_list", None, [7, True], None),
])
def test_b5_scope_sets_or_nonrepresentable(scope, branch, branches, expected):
    grant = SimpleNamespace(
        scope_type=scope, scope_branch_id=branch, scope_branch_ids=branches,
    )
    assert beta._record_branches(grant) == expected


def test_b5_rejects_fake_grant_id_on_create_without_db(monkeypatch):
    c, headers = client(enabled=True)
    monkeypatch.setattr(beta, "_current_admin_user_or_error",
                        lambda: (SimpleNamespace(id=47), None))
    response = c.post("/api/permissions/catalog/grants/beta", headers=headers,
                      json=payload(grant_id=12345))
    assert response.status_code == 400


def test_b5_conflict_does_not_write(monkeypatch):
    c, headers = client(enabled=True)
    monkeypatch.setattr(beta, "_current_admin_user_or_error",
                        lambda: (SimpleNamespace(id=47), None))
    session = Mock()
    monkeypatch.setattr(beta, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(beta, "_evaluate",
                        lambda *args, **kwargs: (None, beta._error("Solape", 409)))
    response = c.post("/api/permissions/catalog/grants/beta", headers=headers, json=payload())
    assert response.status_code == 409
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_b5_atomic_rollback_when_audit_fails(monkeypatch):
    c, headers = client(enabled=True)
    monkeypatch.setattr(beta, "_current_admin_user_or_error",
                        lambda: (SimpleNamespace(id=47), None))
    monkeypatch.setattr(beta, "_evaluate",
                        lambda *_args, **_kwargs: (
                            (SimpleNamespace(id=89), SimpleNamespace(id=9, module_id=3)), None
                        ))
    class DummyGrant:
        def __init__(self, **fields):
            self.id = 123
            for key, value in fields.items():
                setattr(self, key, value)
    monkeypatch.setattr(beta, "PermissionGrantORM", DummyGrant)
    monkeypatch.setattr(beta, "_audit",
                        lambda *_args: (_ for _ in ()).throw(RuntimeError("audit failure")))
    session = Mock()
    monkeypatch.setattr(beta, "db", SimpleNamespace(session=session))
    response = c.post("/api/permissions/catalog/grants/beta", headers=headers, json=payload())
    assert response.status_code == 500
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_b5_code_references_existing_doc_guard_only_in_separate_module():
    from inspect import getsource
    from app.utils import internal_documents_access as access
    assert "permission_grants" not in getsource(access.can_view_internal_document)
    assert "PermissionGrantORM" not in getsource(access.can_manage_internal_documents)
    assert beta.B5_ACTION_KEY == "internal_documents.view"


class _GrantRows:
    def __init__(self, rows):
        self.rows = rows
    def filter(self, *_args):
        return self
    def all(self):
        return self.rows


@pytest.mark.parametrize("existing,expect_conflict", [
    ({"scope_type": "branch", "scope_branch_id": 1,
      "scope_branch_ids": [], "effect": "allow"}, True),
    ({"scope_type": "branch_list", "scope_branch_id": None,
      "scope_branch_ids": [1, 4], "effect": "deny"}, True),
    ({"scope_type": "branch", "scope_branch_id": 15,
      "scope_branch_ids": [], "effect": "deny"}, False),
    ({"scope_type": "global", "scope_branch_id": None,
      "scope_branch_ids": [], "effect": "allow"}, True),
])
def test_b5_scope_collision_and_nonoverlap(monkeypatch, existing, expect_conflict):
    grant = SimpleNamespace(
        id=12, principal_type="user",
        starts_at=None, expires_at=None, **existing,
    )
    data = beta._normalize_input(payload(starts_at=None, expires_at=None))
    result = beta._conflict_with_rows(data, [grant])
    assert bool(result) is expect_conflict


def test_b5_role_grant_for_same_action_blocks(monkeypatch):
    grant = SimpleNamespace(
        id=12, principal_type="role", scope_type="branch",
        scope_branch_id=1, scope_branch_ids=[], starts_at=None, expires_at=None,
    )
    data = beta._normalize_input(payload(starts_at=None, expires_at=None))
    assert "rol" in beta._conflict_with_rows(data, [grant])


def test_b5_preview_keeps_catalog_unknown(monkeypatch):
    c, headers = client()
    monkeypatch.setattr(beta, "_current_admin_user_or_error",
                        lambda: (SimpleNamespace(id=47), None))
    monkeypatch.setattr(beta, "_evaluate",
                        lambda data, **kwargs: (
                            (SimpleNamespace(id=89), SimpleNamespace(id=9)), None
                        ))
    response = c.post("/api/permissions/catalog/grants/beta/preview",
                      headers=headers, json=payload())
    assert response.status_code == 200
    assert response.json["catalog_allowed"] is None
    assert response.json["object_access_certified"] is False
    assert response.json["http_authorization"] == "not_evaluated"


def test_b5_v1_nube_writer_is_blocked_when_gate_enabled(monkeypatch):
    from app.routes import permissions_catalog_routes as catalog
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="b5-fixture-jwt",
        PERMISSIONS_B5_EDITOR_ENABLED=True,
    )
    JWTManager(app)
    app.register_blueprint(
        catalog.permissions_catalog_bp, url_prefix="/api/permissions/catalog",
    )
    with app.app_context():
        token = create_access_token(identity="47")
    monkeypatch.setattr(catalog, "_current_admin_user_or_error",
                        lambda: (SimpleNamespace(id=47), None))
    class TargetUsers:
        @staticmethod
        def get(_id):
            return SimpleNamespace(id=99)
    monkeypatch.setattr(catalog, "UserORM",
                        SimpleNamespace(query=TargetUsers()))
    response = app.test_client().put(
        "/api/permissions/catalog/users/99/module-access",
        headers={"Authorization": "Bearer " + token},
        json={"changes": [{
            "module_key": "internal_documents", "override": "allow",
            "reason": "Intento global bloqueado por B5",
        }]},
    )
    assert response.status_code == 409
    assert response.json["module_key"] == "internal_documents"
