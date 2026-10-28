"""B3: grants V1 son configuración, no enforcement de autorizaciones.

Pruebas de alcance/tiempo/deny con grants y usuarios sintéticos.
La escritura se intercepta ANTES de tocar la sesión si hay scope complejo.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import permissions_catalog_routes as catalog


def grant(*, grant_id=5, action_id=15, effect="allow", scope_type="global",
          starts_at=None, expires_at=None, scope_branch_id=None,
          scope_branch_ids=None, scope_department_id=None, scope_payload=None):
    return SimpleNamespace(
        id=grant_id, action_id=action_id, effect=effect,
        scope_type=scope_type, starts_at=starts_at, expires_at=expires_at,
        scope_branch_id=scope_branch_id, scope_branch_ids=scope_branch_ids,
        scope_department_id=scope_department_id, scope_payload=scope_payload,
        reason="synthetic scope contract",
    )


@pytest.mark.parametrize("scoped", [
    {"scope_type": "branch", "scope_branch_id": 7},
    {"scope_type": "branch_list", "scope_branch_ids": [7, 8]},
    {"scope_type": "department", "scope_department_id": 1},
    {"scope_type": "global", "scope_branch_id": 7},
    {"scope_type": "global", "scope_payload": {"resource": "scoped"}},
    {"scope_type": "global", "starts_at": datetime.now(timezone.utc)},
    {"scope_type": "global", "expires_at": datetime.now(timezone.utc)},
])
def test_b3_global_checkbox_rejects_scoped_or_dated_grants(scoped):
    active = grant(**scoped)
    assert not catalog._is_simple_global_module_grant(active)
    assert catalog._has_complex_module_grant([active])
    assert catalog._best_module_grants_by_action([active]) == {}


def test_b3_only_perpetual_global_allow_or_deny_is_representable():
    allow = grant()
    deny = grant(effect="deny")
    assert catalog._is_simple_global_module_grant(allow)
    assert catalog._is_simple_global_module_grant(deny)
    assert not catalog._has_complex_module_grant([allow, deny])
    assert catalog._best_module_grants_by_action([allow]) == {15: allow}


def test_b3_deny_wins_among_active_duplicate_global_grants():
    newer_allow = grant(grant_id=61, effect="allow")
    older_deny = grant(grant_id=60, effect="deny")
    assert catalog._best_module_grants_by_action([newer_allow, older_deny]) == {
        15: older_deny
    }
    # Deny always wins within the same principal/target, whatever order.
    assert catalog._best_module_grants_by_action([older_deny, newer_allow]) == {
        15: older_deny
    }


def test_b3_user_override_still_precedes_role_override_by_documented_contract():
    base = {"allowed": False, "source": "legacy", "reason": "denied"}
    decision = catalog._apply_module_access_override(
        legacy_decision=base,
        user_grant=grant(grant_id=1, effect="allow"),
        role_grant=grant(grant_id=2, effect="deny"),
    )
    assert decision["effective_allowed"] is True
    assert decision["override_source"] == "user"
    assert decision["grant_id"] == 1
    # effective_allowed is CONFIGURATION preview, not HTTP authority.


class FakeColumn:
    def is_(self, *_args):
        return self

    def in_(self, *_args):
        return self

    def desc(self):
        return self

    def __eq__(self, other):
        return self


class FakeQuery:
    def __init__(self, rows=None, one=None):
        self.rows = rows or []
        self.one = one
        self.calls = 0

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        self.calls += 1
        return list(self.rows)

    def first(self):
        return self.one


class FakeGrantModel:
    is_active = deleted_at = principal_type = principal_user_id = action_id = FakeColumn()
    principal_role_key = scope_type = starts_at = expires_at = FakeColumn()
    updated_at = id = FakeColumn()

    def __init__(self, query):
        self.query = query


def _small_client():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="b3-test-fixture")
    JWTManager(app)
    app.register_blueprint(catalog.permissions_catalog_bp, url_prefix="/api/permissions/catalog")
    with app.app_context():
        token = create_access_token(identity="881")
    return app.test_client(), {"Authorization": "Bearer " + token}


def test_b3_grant_snapshot_ignores_temporary_and_branch_overrides(monkeypatch):
    now = datetime.now(timezone.utc)
    user_g = [
        grant(grant_id=71, scope_type="branch", scope_branch_id=7),
        grant(grant_id=72, starts_at=now - timedelta(days=1),
              expires_at=now + timedelta(days=1)),
        grant(grant_id=73, scope_type="global", effect="deny"),
    ]
    query = FakeQuery(rows=user_g)
    model = FakeGrantModel(query)
    monkeypatch.setattr(catalog, "PermissionGrantORM", model)
    target = SimpleNamespace(id=100, rol="")
    data = catalog._get_latest_active_grants_by_action(user=target, action_ids=[15])
    assert data["user"][15].id == 73
    assert data["role"] == {}
    assert query.calls == 1


@pytest.mark.parametrize("override", ["allow", "deny", "inherit"])
def test_b3_writer_cannot_globalize_or_disable_scoped_grant(monkeypatch, override):
    client, headers = _small_client()
    module = SimpleNamespace(
        id=7, key="tickets", name="Tickets",
        base_action=SimpleNamespace(id=15, full_key="tickets.view"),
    )
    module_query = FakeQuery(one=module)

    class ModuleModel:
        query = module_query
        key = is_active = is_assignable = FakeColumn()

    scoped = grant(scope_type="branch", scope_branch_id=7)
    grant_query = FakeQuery(rows=[scoped])
    monkeypatch.setattr(catalog, "PermissionModuleORM", ModuleModel)
    monkeypatch.setattr(catalog, "PermissionGrantORM", FakeGrantModel(grant_query))
    monkeypatch.setattr(
        catalog, "UserORM",
        SimpleNamespace(query=SimpleNamespace(get=lambda _uid: SimpleNamespace(id=99))),
    )
    monkeypatch.setattr(
        catalog, "_current_admin_user_or_error",
        lambda: (SimpleNamespace(id=881), None),
    )
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))
    response = client.put(
        "/api/permissions/catalog/users/99/module-access",
        headers=headers,
        json={"changes": [{"module_key": "tickets", "override": override,
                           "reason": "fixture safety review"}]},
    )
    assert response.status_code == 409
    assert response.get_json()["module_key"] == "tickets"
    assert scoped.scope_type == "branch"
    assert scoped.scope_branch_id == 7
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.flush.assert_not_called()


def test_b3_batch_duplicate_modules_rejected_before_any_grant_query(monkeypatch):
    client, headers = _small_client()
    monkeypatch.setattr(
        catalog, "UserORM",
        SimpleNamespace(query=SimpleNamespace(get=lambda _: SimpleNamespace(id=99))),
    )
    monkeypatch.setattr(
        catalog, "_current_admin_user_or_error",
        lambda: (SimpleNamespace(id=881), None),
    )
    module = SimpleNamespace(
        id=7, key="tickets", name="Tickets",
        base_action=SimpleNamespace(id=15, full_key="tickets.view"),
    )

    class ModuleModel:
        query = FakeQuery(one=module)
        key = is_active = is_assignable = FakeColumn()

    monkeypatch.setattr(catalog, "PermissionModuleORM", ModuleModel)
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))
    response = client.put(
        "/api/permissions/catalog/users/99/module-access",
        headers=headers,
        json={"changes": [
            {"module_key": "tickets", "override": "allow", "reason": "synthetic"},
            {"module_key": "tickets", "override": "deny", "reason": "synthetic"},
        ]},
    )
    assert response.status_code == 400
    assert "duplicado" in response.get_json()["detail"].lower()
    session.commit.assert_not_called()


def test_b3_existing_review_contract_declares_configuration_not_http_enforcement():
    from inspect import getsource
    source = getsource(catalog.get_user_module_access)
    assert '"grants_enforced": False' in source
    assert '"hard_stops_evaluated": False' in source
    assert "no una autorización efectiva HTTP" in source
