"""Integration contract for opt-in rotating sessions (Flask test client).

Runs on isolated SQLite; no production database, credentials or timers.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager

from app.extensions import db
from app.models.auth_refresh_session import AuthRefreshSessionORM
from app.routes.auth_routes import auth_bp
from app.services.auth_refresh_service import is_access_revoked

TRUSTED = "https://suiteultragym.com"
LOGIN_JSON = {
    "username": "usuario_contrato",
    "password": "password-solo-prueba",
}


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        JWT_SECRET_KEY="refresh-cookie-contract-test-only",
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=45),
        CORS_ORIGINS=[TRUSTED],
        AUTH_REFRESH_ENABLED=True,
        AUTH_REFRESH_IDLE_MINUTES=45,
        AUTH_REFRESH_ABSOLUTE_HOURS=12,
        AUTH_REFRESH_COOKIE_NAME="suite_refresh",
    )
    db.init_app(app)
    manager = JWTManager(app)
    manager.token_in_blocklist_loader(is_access_revoked)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    with app.app_context():
        AuthRefreshSessionORM.__table__.create(db.engine)
        yield app
        db.session.remove()


@pytest.fixture
def fake_user():
    return SimpleNamespace(
        id=47,
        username="usuario_contrato",
        rol="ADMINISTRADOR",
        sucursal_id=1000,
        sucursales_ids=[1000],
        department_id=1000,
        verify_password=lambda value: value == "password-solo-prueba",
    )


def _post(client, path, **kwargs):
    headers = {"Origin": TRUSTED, **kwargs.pop("headers", {})}
    return client.post(
        path, base_url=TRUSTED, headers=headers, **kwargs
    )


def _login(client, user):
    with patch(
        "app.routes.auth_routes.UserORM.get_by_username",
        return_value=user,
    ):
        return _post(client, "/api/auth/login", json=LOGIN_JSON)


def _cookie(response):
    return next(
        (
            header.split(";", 1)[0]
            for header in response.headers.getlist("Set-Cookie")
            if header.startswith("suite_refresh=")
        ),
        None,
    )


def test_login_emite_cookie_refresh_segura_sin_romper_respuesta_actual(app, fake_user):
    response = _login(app.test_client(), fake_user)
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload.get("token"), str) and payload["token"]
    assert payload["user"]["id"] == 47
    assert "refresh_token" not in payload

    refresh_cookie = next(
        header for header in response.headers.getlist("Set-Cookie")
        if header.startswith("suite_refresh=")
    )
    attributes = {part.strip().lower()
                  for part in refresh_cookie.split(";")[1:]}
    assert "httponly" in attributes
    assert "secure" in attributes
    assert "samesite=strict" in attributes
    assert "path=/api/auth" in attributes
    assert response.headers["Cache-Control"] == "no-store"

    with app.app_context():
        row = db.session.get(AuthRefreshSessionORM, _cookie(response).split("=")[1].split(".")[0])
        assert row is not None
        assert row.refresh_hash not in refresh_cookie
        assert row.rotation_count == 0


def test_refresh_rota_y_replay_revoca_sesion(app, fake_user):
    client = app.test_client(use_cookies=False)
    first = _login(client, fake_user)
    old_cookie = _cookie(first)
    assert old_cookie

    with patch(
        "app.services.auth_refresh_service.UserORM.get_by_id",
        return_value=fake_user,
    ):
        second = _post(
            client, "/api/auth/refresh",
            headers={"Cookie": old_cookie},
        )
        assert second.status_code == 200
        new_cookie = _cookie(second)
        assert new_cookie and new_cookie != old_cookie
        assert second.get_json()["user"]["id"] == 47
        assert "refresh_token" not in second.get_json()

        replay = _post(
            client, "/api/auth/refresh",
            headers={"Cookie": old_cookie},
        )
        assert replay.status_code == 401
        assert replay.get_json()["error"] == "SESSION_REPLAYED"

        rejected = _post(
            client, "/api/auth/refresh",
            headers={"Cookie": new_cookie},
        )
        assert rejected.status_code == 401

    with app.app_context():
        row = AuthRefreshSessionORM.query.one()
        assert row.rotation_count == 1
        assert row.revoke_reason == "REPLAY"


@pytest.mark.parametrize("expired_column", ["idle_expires_at", "absolute_expires_at"])
def test_refresh_no_resucita_sesiones_caducadas(app, fake_user, expired_column):
    client = app.test_client(use_cookies=False)
    first = _login(client, fake_user)
    with app.app_context():
        row = AuthRefreshSessionORM.query.one()
        setattr(row, expired_column, datetime.now(timezone.utc) - timedelta(seconds=1))
        db.session.commit()
    with patch(
        "app.services.auth_refresh_service.UserORM.get_by_id",
        return_value=fake_user,
    ):
        response = _post(
            client, "/api/auth/refresh",
            headers={"Cookie": _cookie(first)},
        )
    assert response.status_code == 401
    assert response.get_json()["error"] == "SESSION_EXPIRED"


def test_logout_revoca_refresh_y_jwt_access(app, fake_user):
    client = app.test_client(use_cookies=False)
    first = _login(client, fake_user)
    cookie = _cookie(first)
    access_token = first.get_json()["token"]
    result = _post(client, "/api/auth/logout", headers={"Cookie": cookie})
    assert result.status_code == 200
    assert "max-age=0" in result.headers["Set-Cookie"].lower()

    refresh = _post(client, "/api/auth/refresh", headers={"Cookie": cookie})
    assert refresh.status_code == 401
    auth = client.get(
        "/api/auth/session-info",
        base_url=TRUSTED,
        headers={"Authorization": "Bearer " + access_token},
    )
    assert auth.status_code == 401


def test_origin_ajeno_no_puede_rotar_ni_revocar(app, fake_user):
    client = app.test_client(use_cookies=False)
    first = _login(client, fake_user)
    cookie = _cookie(first)
    bad_origin = {"Origin": "https://evil.invalid", "Cookie": cookie}
    assert client.post(
        "/api/auth/refresh", base_url=TRUSTED, headers=bad_origin
    ).status_code == 403
    assert client.post(
        "/api/auth/logout", base_url=TRUSTED, headers=bad_origin
    ).status_code == 403
    with patch(
        "app.services.auth_refresh_service.UserORM.get_by_id",
        return_value=fake_user,
    ):
        valid = _post(client, "/api/auth/refresh", headers={"Cookie": cookie})
    assert valid.status_code == 200


def test_credential_solo_en_json_no_es_aceptada(app, fake_user):
    client = app.test_client(use_cookies=False)
    login = _login(client, fake_user)
    refresh = _post(
        client, "/api/auth/refresh",
        json={"refresh_token": _cookie(login)},
    )
    assert refresh.status_code == 401


def test_legacy_mode_no_cambia_login_ni_usa_tabla(app, fake_user):
    app.config["AUTH_REFRESH_ENABLED"] = False
    first = _login(app.test_client(), fake_user)
    assert first.status_code == 200
    assert first.get_json()["token"]
    assert not first.headers.getlist("Set-Cookie")
    with app.app_context():
        assert AuthRefreshSessionORM.query.count() == 0
