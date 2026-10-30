"""#1178: un check solo puede guardar una acción con guard HTTP conectado.

Pruebas exclusivamente sintéticas; nunca acceden a BD de producción.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import permissions_catalog_routes as catalog


class FakeColumn:
    def is_(self, *_): return self
    def in_(self, *_): return self
    def desc(self): return self
    def __eq__(self, _): return self


class FakeQuery:
    def __init__(self, *, first=None, rows=None):
        self.one = first
        self.rows = [] if rows is None else rows
        self.kwargs = None

    def filter(self, *_): return self
    def filter_by(self, **kwargs):
        self.kwargs = kwargs
        return self
    def order_by(self, *_): return self
    def first(self): return self.one
    def all(self): return list(self.rows)


def client():
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="synthetic-action-check",
        PERMISSIONS_TRACK_READ_GRANTS_ENABLED=True,
        PERMISSIONS_OPENINGS_READ_GRANTS_ENABLED=True,
        PERMISSIONS_OPENINGS_COMMENT_GRANTS_ENABLED=True,
        PERMISSIONS_OPENINGS_MANAGE_GRANTS_ENABLED=True,
        PERMISSIONS_TICKETS_CREATE_GRANTS_ENABLED=True,
        PERMISSIONS_TICKETS_UPDATE_STATUS_GRANTS_ENABLED=True,
    )
    JWTManager(app)
    app.register_blueprint(catalog.permissions_catalog_bp, url_prefix="/api/permissions/catalog")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


def admin_and_target(monkeypatch):
    monkeypatch.setattr(
        catalog, "_current_admin_user_or_error",
        lambda: (SimpleNamespace(id=47), None),
    )
    monkeypatch.setattr(
        catalog, "UserORM",
        SimpleNamespace(query=SimpleNamespace(get=lambda uid: SimpleNamespace(
            id=uid, username="QA", rol="GERENTE",
        ))),
    )


@pytest.mark.parametrize("full_key", [
    "tickets.close", "pm.validate", "track.run_daily_pipeline",
    "internal_documents.view",
])
def test_uncertified_action_fails_before_db_mutation(monkeypatch, full_key):
    api, headers = client()
    admin_and_target(monkeypatch)
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))
    response = api.put(
        "/api/permissions/catalog/users/12/module-access",
        headers=headers,
        json={"changes": [{
            "module_key": full_key.split(".")[0],
            "action_full_key": full_key,
            "override": "allow",
        }]},
    )
    assert response.status_code == 409
    assert response.json["action_full_key"] == full_key
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_wrong_module_for_certified_action_rejected_without_mutation(monkeypatch):
    api, headers = client()
    admin_and_target(monkeypatch)
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))
    response = api.put(
        "/api/permissions/catalog/users/12/module-access",
        headers=headers,
        json={"changes": [{
            "module_key": "openings",
            "action_full_key": "track.read",
            "override": "allow",
        }]},
    )
    assert response.status_code == 400
    session.commit.assert_not_called()


@pytest.mark.parametrize("module_key,full_key", [
    ("track", "track.read"), ("openings", "openings.read"),
    ("openings", "openings.comment"),
    ("openings", "openings.manage"),
    ("tickets", "tickets.create"),
    ("tickets", "tickets.update_status"),
])
def test_certified_action_writes_exact_action_through_existing_endpoint(
    monkeypatch, module_key, full_key,
):
    api, headers = client()
    admin_and_target(monkeypatch)
    action = SimpleNamespace(id=61, full_key=full_key, module_id=7)
    module = SimpleNamespace(
        id=7, name="QA", key=module_key, base_action=action,
    )
    module_query = FakeQuery(first=module)
    action_query = FakeQuery(first=action)
    grant_query = FakeQuery(rows=[])

    class FakeModule:
        query = module_query
        key = is_active = is_assignable = FakeColumn()

    class FakeAction:
        query = action_query

    class FakeGrant:
        query = grant_query
        is_active = deleted_at = principal_type = principal_user_id = action_id = FakeColumn()
        updated_at = id = FakeColumn()

    monkeypatch.setattr(catalog, "PermissionModuleORM", FakeModule)
    monkeypatch.setattr(catalog, "PermissionActionORM", FakeAction)
    monkeypatch.setattr(catalog, "PermissionGrantORM", FakeGrant)
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))

    # inherit con 0 grants verifica la resolución sin crear datos falsos.
    response = api.put(
        "/api/permissions/catalog/users/12/module-access",
        headers=headers,
        json={"changes": [{
            "module_key": module_key,
            "action_full_key": full_key,
            "override": "inherit",
            "reason": "QA no mutation",
        }]},
    )
    assert response.status_code == 200, response.get_json()
    assert response.json["results"][0]["action_full_key"] == full_key
    assert action_query.kwargs == {
        "full_key": full_key, "module_id": 7, "is_active": True,
    }
    session.commit.assert_called_once()
    session.add.assert_not_called()


def test_duplicate_explicit_action_does_not_mutate(monkeypatch):
    api, headers = client()
    admin_and_target(monkeypatch)
    action = SimpleNamespace(id=61, full_key="track.read", module_id=7)
    module = SimpleNamespace(id=7, name="Track", key="track", base_action=action)

    class FakeModule:
        query = FakeQuery(first=module)
        key = is_active = is_assignable = FakeColumn()

    class FakeAction:
        query = FakeQuery(first=action)

    monkeypatch.setattr(catalog, "PermissionModuleORM", FakeModule)
    monkeypatch.setattr(catalog, "PermissionActionORM", FakeAction)
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))
    response = api.put(
        "/api/permissions/catalog/users/12/module-access",
        headers=headers,
        json={"changes": [
            {"module_key": "track", "action_full_key": "track.read", "override": "allow"},
            {"module_key": "track", "action_full_key": "track.read", "override": "deny"},
        ]},
    )
    assert response.status_code == 400
    assert "duplicada" in response.json["detail"].lower()
    session.commit.assert_not_called()


def test_comment_can_be_enabled_without_openings_read_writer(monkeypatch):
    api, headers = client()
    api.application.config["PERMISSIONS_OPENINGS_READ_GRANTS_ENABLED"] = False
    admin_and_target(monkeypatch)
    action = SimpleNamespace(id=88, full_key="openings.comment", module_id=7)
    base = SimpleNamespace(id=77, full_key="openings.read", module_id=7)
    module = SimpleNamespace(id=7, name="Aperturas", key="openings", base_action=base)

    class FakeModule:
        query = FakeQuery(first=module)
        key = is_active = is_assignable = FakeColumn()

    class FakeAction:
        query = FakeQuery(first=action)

    class FakeGrant:
        query = FakeQuery(rows=[])
        is_active = deleted_at = principal_type = principal_user_id = action_id = FakeColumn()
        updated_at = id = FakeColumn()

    monkeypatch.setattr(catalog, "PermissionModuleORM", FakeModule)
    monkeypatch.setattr(catalog, "PermissionActionORM", FakeAction)
    monkeypatch.setattr(catalog, "PermissionGrantORM", FakeGrant)
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))
    result = api.put(
        "/api/permissions/catalog/users/12/module-access",
        headers=headers,
        json={"changes": [{
            "module_key": "openings",
            "action_full_key": "openings.comment",
            "override": "inherit",
            "reason": "QA solo comentario",
        }]},
    )
    assert result.status_code == 200
    assert result.json["results"][0]["action_id"] == 88
    assert result.json["results"][0]["action_full_key"] == "openings.comment"
    session.commit.assert_called_once()
    session.add.assert_not_called()


def test_comment_writer_flag_off_even_when_read_enabled(monkeypatch):
    api, headers = client()
    api.application.config["PERMISSIONS_OPENINGS_COMMENT_GRANTS_ENABLED"] = False
    admin_and_target(monkeypatch)
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))
    result = api.put(
        "/api/permissions/catalog/users/12/module-access",
        headers=headers,
        json={"changes": [{
            "module_key": "openings",
            "action_full_key": "openings.comment",
            "override": "allow",
        }]},
    )
    assert result.status_code == 409
    assert result.json["action_full_key"] == "openings.comment"
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_manage_writer_flag_off_even_if_read_and_comment_on(monkeypatch):
    api, headers = client()
    api.application.config["PERMISSIONS_OPENINGS_MANAGE_GRANTS_ENABLED"] = False
    admin_and_target(monkeypatch)
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))
    result = api.put(
        "/api/permissions/catalog/users/12/module-access",
        headers=headers,
        json={"changes": [{
            "module_key": "openings",
            "action_full_key": "openings.manage",
            "override": "allow",
        }]},
    )
    assert result.status_code == 409
    assert result.json["action_full_key"] == "openings.manage"
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_manage_can_target_its_own_action_with_read_and_comment_off(monkeypatch):
    api, headers = client()
    api.application.config["PERMISSIONS_OPENINGS_READ_GRANTS_ENABLED"] = False
    api.application.config["PERMISSIONS_OPENINGS_COMMENT_GRANTS_ENABLED"] = False
    admin_and_target(monkeypatch)
    manage_action = SimpleNamespace(id=88, full_key="openings.manage", module_id=7)
    read_action = SimpleNamespace(id=77, full_key="openings.read", module_id=7)
    module = SimpleNamespace(id=7, name="Aperturas", key="openings", base_action=read_action)

    class FakeModule:
        query = FakeQuery(first=module)
        key = is_active = is_assignable = FakeColumn()

    class FakeAction:
        query = FakeQuery(first=manage_action)

    class FakeGrant:
        query = FakeQuery(rows=[])
        is_active = deleted_at = principal_type = principal_user_id = action_id = FakeColumn()
        updated_at = id = FakeColumn()

    monkeypatch.setattr(catalog, "PermissionModuleORM", FakeModule)
    monkeypatch.setattr(catalog, "PermissionActionORM", FakeAction)
    monkeypatch.setattr(catalog, "PermissionGrantORM", FakeGrant)
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))
    result = api.put(
        "/api/permissions/catalog/users/12/module-access",
        headers=headers,
        json={"changes": [{
            "module_key": "openings",
            "action_full_key": "openings.manage",
            "override": "inherit",
            "reason": "QA isolated manage",
        }]},
    )
    assert result.status_code == 200, result.get_json()
    assert result.json["results"][0]["action_id"] == 88
    assert result.json["results"][0]["action_full_key"] == "openings.manage"
    session.commit.assert_called_once()
    session.add.assert_not_called()


def test_tickets_create_writer_flag_off_without_db_mutation(monkeypatch):
    api, headers = client()
    api.application.config["PERMISSIONS_TICKETS_CREATE_GRANTS_ENABLED"] = False
    admin_and_target(monkeypatch)
    session = Mock()
    monkeypatch.setattr(catalog, "db", SimpleNamespace(session=session))
    result = api.put(
        "/api/permissions/catalog/users/12/module-access",
        headers=headers,
        json={"changes": [{
            "module_key": "tickets",
            "action_full_key": "tickets.create",
            "override": "deny",
        }]},
    )
    assert result.status_code == 409
    assert result.json["action_full_key"] == "tickets.create"
    session.commit.assert_not_called()
    session.add.assert_not_called()
