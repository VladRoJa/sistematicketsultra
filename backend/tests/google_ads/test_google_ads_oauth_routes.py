"""OAuth backend contract: fail closed, admin-only, browser-bound, encrypted."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import google_ads_oauth_routes as oauth


class FakeUser:
    def __init__(self, admin=True):
        self.id = 7
        self._admin = admin

    def es_admin(self):
        return self._admin


@pytest.fixture
def oauth_client(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="secret-for-oauth-test-only",
        JWT_SECRET_KEY="secret-for-jwt-test-only",
    )
    JWTManager(app)
    app.register_blueprint(oauth.google_ads_oauth_bp, url_prefix="/oauth")

    users = {"7": FakeUser()}
    monkeypatch.setattr(
        oauth.UserORM,
        "get_by_id",
        staticmethod(lambda user_id: users.get(str(user_id))),
    )
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_CLIENT_ID", "unit-test-client-id")
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_CLIENT_SECRET", "unit-test-client-secret")
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_CUSTOMER_ID", "2739125201")
    monkeypatch.setenv(
        "GOOGLE_ADS_OAUTH_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii")
    )

    with app.app_context():
        jwt = create_access_token(identity="7")

    return SimpleNamespace(
        app=app,
        client=app.test_client(),
        headers={"Authorization": "Bearer " + jwt},
        users=users,
    )


def _start(context):
    response = context.client.post(
        "/oauth/start",
        headers=context.headers,
        base_url="https://suiteultragym.com",
    )
    assert response.status_code == 200
    query = parse_qs(urlparse(response.json["authorization_url"]).query)
    return response, query


def test_requires_suite_admin_jwt(oauth_client):
    context = oauth_client
    response = context.client.post("/oauth/start")
    assert response.status_code == 401

    context.users["7"] = FakeUser(admin=False)
    response = context.client.post("/oauth/start", headers=context.headers)
    assert response.status_code == 403


def test_disabled_by_default(monkeypatch, oauth_client):
    monkeypatch.delenv("GOOGLE_ADS_OAUTH_ENABLED")
    response = oauth_client.client.post(
        "/oauth/start", headers=oauth_client.headers
    )
    assert response.status_code == 503
    assert "authorization_url" not in response.json


def test_bad_configuration_fails_closed(monkeypatch, oauth_client):
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_TOKEN_ENCRYPTION_KEY", "not-a-key")
    response = oauth_client.client.post(
        "/oauth/start", headers=oauth_client.headers
    )
    assert response.status_code == 503


def test_consent_url_uses_google_ads_offline_pkce_and_secure_cookie(oauth_client):
    response, params = _start(oauth_client)
    assert urlparse(response.json["authorization_url"]).hostname == "accounts.google.com"
    assert params["scope"] == [oauth.SCOPE]
    assert params["redirect_uri"] == [oauth.CALLBACK_URI]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["code_challenge_method"] == ["S256"]
    assert len(params["code_challenge"][0]) == 43
    assert params["state"][0]
    cookie = response.headers["Set-Cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert response.headers["Cache-Control"] == "no-store"


def test_callback_rejects_missing_or_tampered_state(oauth_client):
    response, params = _start(oauth_client)
    no_state = oauth_client.client.get(
        "/oauth/callback",
        query_string={"code": "anything"},
        base_url="https://suiteultragym.com",
    )
    assert no_state.status_code == 400

    _, fresh_params = _start(oauth_client)
    tampered = oauth_client.client.get(
        "/oauth/callback",
        query_string={"code": "anything", "state": fresh_params["state"][0] + "x"},
        base_url="https://suiteultragym.com",
    )
    assert tampered.status_code == 400


def test_callback_does_not_exchange_without_original_browser_cookie(
    oauth_client, monkeypatch
):
    _, params = _start(oauth_client)
    calls = []
    monkeypatch.setattr(oauth.requests, "post", lambda *a, **k: calls.append(1))
    different_browser = oauth_client.app.test_client()
    result = different_browser.get(
        "/oauth/callback",
        query_string={"code": "code", "state": params["state"][0]},
        base_url="https://suiteultragym.com",
    )
    assert result.status_code == 400
    assert calls == []


def test_callback_respects_role_revocation(oauth_client, monkeypatch):
    _, params = _start(oauth_client)
    oauth_client.users["7"] = FakeUser(admin=False)
    monkeypatch.setattr(oauth.requests, "post", lambda *args, **kwargs: None)
    result = oauth_client.client.get(
        "/oauth/callback",
        query_string={"code": "code", "state": params["state"][0]},
        base_url="https://suiteultragym.com",
    )
    assert result.status_code == 403


def test_callback_exchanges_and_saves_refresh_token_without_exposing_it(
    oauth_client, monkeypatch
):
    _, params = _start(oauth_client)
    recorded = []

    class FakeReply:
        status_code = 200

        def json(self):
            return {
                "refresh_token": "sensitive-test-refresh-token",
                "scope": oauth.SCOPE,
                "access_token": "short-lived-token",
            }

    def fake_post(url, **kwargs):
        assert url == oauth.TOKEN_ENDPOINT
        assert kwargs["allow_redirects"] is False
        assert kwargs["data"]["redirect_uri"] == oauth.CALLBACK_URI
        assert kwargs["data"]["code_verifier"]
        recorded.append("exchange")
        return FakeReply()

    monkeypatch.setattr(oauth.requests, "post", fake_post)
    monkeypatch.setattr(
        oauth, "_save_refresh_token",
        lambda settings, user_id, refresh_token: recorded.append(
            (user_id, refresh_token)
        )
    )
    response = oauth_client.client.get(
        "/oauth/callback",
        query_string={"code": "one-time-code", "state": params["state"][0]},
        base_url="https://suiteultragym.com",
    )
    assert response.status_code == 200
    assert recorded == ["exchange", ("7", "sensitive-test-refresh-token")]
    assert b"sensitive-test-refresh-token" not in response.data
    assert b"short-lived-token" not in response.data
    assert b"one-time-code" not in response.data
    assert response.headers["Cache-Control"] == "no-store"
    assert "Max-Age=0" in response.headers["Set-Cookie"]

    replay = oauth_client.client.get(
        "/oauth/callback",
        query_string={"code": "other-code", "state": params["state"][0]},
        base_url="https://suiteultragym.com",
    )
    assert replay.status_code == 400
    assert len(recorded) == 2


def test_callback_missing_refresh_token_does_not_replace_existing_grant(
    oauth_client, monkeypatch
):
    _, params = _start(oauth_client)

    class NoRefreshReply:
        status_code = 200

        def json(self):
            return {"access_token": "temporary", "scope": oauth.SCOPE}

    saved = []
    monkeypatch.setattr(oauth.requests, "post", lambda *a, **k: NoRefreshReply())
    monkeypatch.setattr(oauth, "_save_refresh_token", lambda *a: saved.append(1))
    response = oauth_client.client.get(
        "/oauth/callback",
        query_string={"code": "one-time-code", "state": params["state"][0]},
        base_url="https://suiteultragym.com",
    )
    assert response.status_code == 409
    assert saved == []


def test_refresh_token_ciphertext_is_not_plaintext(monkeypatch, oauth_client):
    class MemorySession:
        def __init__(self):
            self.saved = None
            self.commits = 0

        def get(self, model, identifier, **kwargs):
            return self.saved

        def add(self, row):
            self.saved = row

        def commit(self):
            self.commits += 1

        def rollback(self):
            raise AssertionError("unexpected rollback")

    session = MemorySession()
    monkeypatch.setattr(oauth, "db", SimpleNamespace(session=session))
    settings = oauth._settings()
    oauth._save_refresh_token(settings, 7, "secret-refresh-value")
    assert session.commits == 1
    assert session.saved.authorized_by_user_id == 7
    assert session.saved.customer_id == "2739125201"
    assert "secret-refresh-value" not in session.saved.encrypted_refresh_token
    assert (
        settings["fernet"]
        .decrypt(session.saved.encrypted_refresh_token.encode("ascii"))
        .decode("utf-8")
        == "secret-refresh-value"
    )
