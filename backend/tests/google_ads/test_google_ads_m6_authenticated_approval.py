"""M6 authenticated approval: JWT-only actor, route kill switch and atomics.

Uses synthetic data and fake DB transaction objects; never contacts production.
"""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import google_ads_m6_continuity_routes as routes
from app.warehouse.services import google_ads_m6_continuity_approval_service as service


@pytest.fixture()
def client_and_token():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["JWT_SECRET_KEY"] = "m6-testing-only-jwt-secret"
    JWTManager(app)
    app.register_blueprint(routes.google_ads_m6_continuity_bp, url_prefix="/api/integrations/google-ads")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), token


def _post(client, *, token=None, body=None):
    headers = {"Authorization": "Bearer " + token} if token else {}
    return client.post(
        "/api/integrations/google-ads/continuity/approve",
        json=body if body is not None else {
            "approval_reference": service.M6_REFERENCE,
            "confirmation": routes.CONFIRMATION,
        },
        headers=headers,
    )


def test_approval_requires_valid_jwt_even_when_disabled(client_and_token, monkeypatch):
    client, token = client_and_token
    monkeypatch.delenv("GOOGLE_ADS_M6_APPROVAL_ENABLED", raising=False)
    assert _post(client).status_code == 401
    assert _post(client, token="invalid.token.value").status_code != 200
    assert _post(client, token=token).status_code == 503


def test_disabled_by_default_does_not_call_service(client_and_token, monkeypatch):
    client, token = client_and_token
    monkeypatch.delenv("GOOGLE_ADS_M6_APPROVAL_ENABLED", raising=False)
    monkeypatch.setattr(routes, "approve_authenticated", lambda: pytest.fail("service called"))
    response = _post(client, token=token)
    assert response.status_code == 503
    assert response.json["code"] == "GOOGLE_ADS_M6_APPROVAL_DISABLED"
    assert response.headers["Cache-Control"] == "no-store"


def test_enabled_requires_exact_confirmation_and_rejects_spoofed_user_field(client_and_token, monkeypatch):
    client, token = client_and_token
    monkeypatch.setenv("GOOGLE_ADS_M6_APPROVAL_ENABLED", "true")
    monkeypatch.setattr(routes, "approve_authenticated", lambda: pytest.fail("service called"))
    bad = [
        {"approval_reference": service.M6_REFERENCE, "confirmation": "wrong"},
        {"approval_reference": "wrong", "confirmation": routes.CONFIRMATION},
        {
            "approval_reference": service.M6_REFERENCE,
            "confirmation": routes.CONFIRMATION, "approved_by_user_id": 47,
        },
        {},
    ]
    for body in bad:
        assert _post(client, token=token, body=body).status_code == 400


def test_route_response_for_authenticated_success_and_forbidden(client_and_token, monkeypatch):
    client, token = client_and_token
    monkeypatch.setenv("GOOGLE_ADS_M6_APPROVAL_ENABLED", "true")
    monkeypatch.setattr(routes, "approve_authenticated", lambda: {
        "action": "APPROVED", "approved_identities": 26,
    })
    response = _post(client, token=token)
    assert response.status_code == 200
    assert response.json["approved_identities"] == 26
    def deny():
        raise PermissionError("do not leak details")
    monkeypatch.setattr(routes, "approve_authenticated", deny)
    response = _post(client, token=token)
    assert response.status_code == 403
    assert response.json == {"code": "FORBIDDEN"}


class FakeResult:
    def __init__(self, row=None, scalar=None):
        self.row = row
        self.scalar = scalar

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row

    def scalar_one(self):
        return self.scalar


class FakeConnection:
    def __init__(self, username="admicorp", role="ADMINISTRADOR", *, old=False):
        self.username = username
        self.role = role
        self.old = old
        self.version_id = 77 if old else None
        self.version_actor = 47
        self.inserts = []
        self.calls = []

    def execute(self, sql, params=None):
        statement = str(sql)
        self.calls.append(statement)
        if "pg_advisory_xact_lock" in statement:
            return FakeResult()
        if "FROM users" in statement and "FOR UPDATE" in statement:
            return FakeResult(row={"id": 47, "username": self.username, "rol": self.role})
        if "INSERT INTO google_ads_branch_approval_versions" in statement:
            self.inserts.append(("version", params))
            self.version_id = 77
            return FakeResult(scalar=77)
        if "INSERT INTO google_ads_branch_approved_identities" in statement:
            self.inserts.append(("identities", params))
            return FakeResult()
        raise AssertionError("Unexpected SQL: " + statement)


class FakeEngine:
    def __init__(self, conn):
        self.conn = conn
        self.committed = False
        self.rolled_back = False

    @contextmanager
    def begin(self):
        try:
            yield self.conn
            self.committed = True
        except BaseException:
            self.rolled_back = True
            raise


def _service(monkeypatch, *, username="admicorp", role="ADMINISTRADOR", old=False, actor="47"):
    conn = FakeConnection(username=username, role=role, old=old)
    engine = FakeEngine(conn)
    monkeypatch.setattr(service, "db", SimpleNamespace(engine=engine))
    monkeypatch.setattr(service, "get_jwt_identity", lambda: actor)
    monkeypatch.setattr(service, "_load_m5", lambda: {"id": service.M5_REFERENCE})
    monkeypatch.setattr(service, "_verify_m5_raw", lambda _: None)
    monkeypatch.setattr(service, "_load_files", lambda: (object(), object()))
    monkeypatch.setattr(service, "run_on_connection", lambda *args, **kwargs: {
        "action": "CHECK_ONLY", "approved_identities": 26,
    })
    monkeypatch.setattr(service, "_triples", lambda _: [
        {"campaign_key": "name:" + format(i + 1, "064x"),
         "ad_group_key": "name:" + format(i + 100, "064x"),
         "sucursal_canon": f"BRANCH_{i}"}
        for i in range(26)
    ])
    def lookup(_, _rows):
        if conn.version_id is None:
            return None, None
        return conn.version_id, {"approved_by_user_id": conn.version_actor}
    monkeypatch.setattr(service, "_check_existing", lookup)
    return engine, conn


@pytest.mark.parametrize("username,role", [
    ("someone", "ADMINISTRADOR"),
    ("admicorp", "GERENTE"),
    ("admicorp", "SISTEMAS"),
])
def test_service_blocks_wrong_principal_before_reading_raw(monkeypatch, username, role):
    engine, conn = _service(monkeypatch, username=username, role=role)
    monkeypatch.setattr(service, "_load_files", lambda: pytest.fail("should not open RAW"))
    with pytest.raises(PermissionError, match="ADMICORP"):
        service.approve_authenticated()
    assert not conn.inserts
    assert engine.rolled_back


@pytest.mark.parametrize("identity", [None, "garbage", "-1", "0"])
def test_service_rejects_invalid_jwt_identity(monkeypatch, identity):
    engine, conn = _service(monkeypatch, actor=identity)
    with pytest.raises((RuntimeError, PermissionError)):
        service.approve_authenticated()
    assert not conn.calls
    assert not conn.inserts


def test_service_approves_exactly_once_from_authenticated_identity(monkeypatch):
    engine, conn = _service(monkeypatch)
    result = service.approve_authenticated()
    assert result["action"] == "APPROVED"
    assert result["approval_version_id"] == 77
    assert len(conn.inserts) == 2
    assert conn.inserts[0][1]["actor"] == 47
    assert len(conn.inserts[1][1]) == 26
    assert engine.committed


def test_service_idempotent_same_approver_and_never_duplicate_inserts(monkeypatch):
    engine, conn = _service(monkeypatch, old=True)
    result = service.approve_authenticated()
    assert result["action"] == "ALREADY_APPROVED"
    assert result["approved_identities"] == 26
    assert conn.inserts == []
    assert engine.committed


def test_service_rejects_other_previous_approver(monkeypatch):
    engine, conn = _service(monkeypatch, old=True)
    conn.version_actor = 999
    with pytest.raises(PermissionError, match="otro operador"):
        service.approve_authenticated()
    assert not conn.inserts
    assert engine.rolled_back
