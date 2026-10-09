"""First-party Google Ads OAuth authorization (no Ads report queries yet).

- Only a Suite ADMINISTRADOR may initiate consent.
- Google may call back without our JWT: timed, signed state + browser-bound
  Secure/HttpOnly/SameSite cookie + PKCE bind that callback to the initiator.
- Only the encrypted refresh token is persisted, never returned to a browser.
- Feature flag defaults OFF. Never include secrets in source control.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet
from flask import Blueprint, Response, current_app, jsonify, make_response, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db
from app.models.google_ads_oauth import GoogleAdsOAuthCredentialORM
from app.models.user_model import UserORM


google_ads_oauth_bp = Blueprint("google_ads_oauth", __name__)

SCOPE = "https://www.googleapis.com/auth/adwords"
CALLBACK_URI = "https://suiteultragym.com/api/integrations/google-ads/oauth/callback"
AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
COOKIE_NAME = "__Host-suite_ga_oauth_nonce"
STATE_TTL_SECONDS = 600


@google_ads_oauth_bp.after_request
def _secure_response_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _settings():
    """Fail closed unless the operator explicitly configures all secrets."""
    if os.getenv("GOOGLE_ADS_OAUTH_ENABLED", "").strip().lower() != "true":
        return None

    client_id = os.getenv("GOOGLE_ADS_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_ADS_OAUTH_CLIENT_SECRET", "").strip()
    customer_id = os.getenv("GOOGLE_ADS_OAUTH_CUSTOMER_ID", "").replace("-", "").strip()
    key = os.getenv("GOOGLE_ADS_OAUTH_TOKEN_ENCRYPTION_KEY", "").strip()

    if not client_id or not client_secret or not re.fullmatch(r"[0-9]{10}", customer_id):
        return None
    try:
        fernet = Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError):
        return None
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "customer_id": customer_id,
        "fernet": fernet,
    }


def _admin():
    user = UserORM.get_by_id(get_jwt_identity())
    return user if user and user.es_admin() else None


def _signer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="suite-ultra-google-ads-oauth-v1",
    )


def _code_verifier(nonce):
    # Recomputed on callback; never embed a PKCE verifier in client-visible state.
    digest = hmac.new(
        current_app.config["SECRET_KEY"].encode("utf-8"),
        ("google-ads-pkce:" + nonce).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _html_response(message, status):
    # Static messages only: never reflect the authorization code, state or errors.
    page = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta name='robots' content='noindex,nofollow'>"
        "<title>Suite Ultra - Google Ads</title></head><body>"
        "<main><h1>Autorización de Google Ads</h1><p>"
        + message
        + "</p></main></body></html>"
    )
    response = make_response(Response(page, status=status, mimetype="text/html"))
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    response.delete_cookie(
        COOKIE_NAME, path="/", secure=True, httponly=True, samesite="Lax"
    )
    return response


def _save_refresh_token(settings, user_id, refresh_token):
    encrypted = settings["fernet"].encrypt(refresh_token.encode("utf-8")).decode("ascii")
    try:
        row = db.session.get(GoogleAdsOAuthCredentialORM, 1, with_for_update=True)
        if row is None:
            row = GoogleAdsOAuthCredentialORM(id=1)
            db.session.add(row)
        row.customer_id = settings["customer_id"]
        row.encrypted_refresh_token = encrypted
        row.authorized_by_user_id = int(user_id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


@google_ads_oauth_bp.post("/start")
@jwt_required()
def google_ads_oauth_start():
    if _admin() is None:
        return jsonify({"error": "Forbidden"}), 403
    settings = _settings()
    if settings is None:
        return jsonify({"error": "Google Ads OAuth no está habilitado o configurado."}), 503

    nonce = secrets.token_urlsafe(32)
    state = _signer().dumps({"nonce": nonce, "user_id": str(get_jwt_identity())})
    verifier = _code_verifier(nonce)
    query = urlencode({
        "client_id": settings["client_id"],
        "redirect_uri": CALLBACK_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": _code_challenge(verifier),
        "code_challenge_method": "S256",
    })
    response = make_response(jsonify({
        "authorization_url": AUTHORIZE_ENDPOINT + "?" + query,
        "expires_in_seconds": STATE_TTL_SECONDS,
    }))
    response.set_cookie(
        COOKIE_NAME, nonce, max_age=STATE_TTL_SECONDS, secure=True,
        httponly=True, samesite="Lax", path="/",
    )
    return response


@google_ads_oauth_bp.get("/callback")
def google_ads_oauth_callback():
    settings = _settings()
    if settings is None:
        return _html_response("La integración no está habilitada.", 503)

    raw_state = request.args.get("state", "")
    browser_nonce = request.cookies.get(COOKIE_NAME, "")
    if not raw_state or len(raw_state) > 2048 or not browser_nonce:
        return _html_response("La solicitud de autorización no es válida.", 400)
    try:
        signed_state = _signer().loads(raw_state, max_age=STATE_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return _html_response("La autorización caducó o no es válida.", 400)

    if not isinstance(signed_state, dict):
        return _html_response("La solicitud de autorización no es válida.", 400)
    nonce = signed_state.get("nonce")
    user_id = signed_state.get("user_id")
    if (
        not isinstance(nonce, str)
        or not isinstance(user_id, str)
        or not secrets.compare_digest(nonce, browser_nonce)
    ):
        return _html_response("La autorización no corresponde a este navegador.", 400)

    # A revoked or demoted Suite administrator may not establish a grant.
    user = UserORM.get_by_id(user_id)
    if not user or not user.es_admin():
        return _html_response("No tienes permisos para autorizar esta integración.", 403)

    if request.args.get("error"):
        return _html_response("La autorización fue cancelada en Google.", 400)

    code = request.args.get("code", "")
    if not code or len(code) > 4096:
        return _html_response("Google no entregó un código válido.", 400)

    try:
        reply = requests.post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": settings["client_id"],
                "client_secret": settings["client_secret"],
                "redirect_uri": CALLBACK_URI,
                "grant_type": "authorization_code",
                "code_verifier": _code_verifier(nonce),
            },
            timeout=(3, 12),
            allow_redirects=False,
        )
        if reply.status_code != 200:
            return _html_response("Google rechazó el intercambio de autorización.", 502)
        tokens = reply.json()
        if not isinstance(tokens, dict):
            return _html_response("Respuesta de Google no válida.", 502)
        granted = tokens.get("scope")
        if granted is not None and SCOPE not in str(granted).split():
            return _html_response("Google no concedió el permiso solicitado.", 400)
        refresh_token = tokens.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            return _html_response(
                "Google no entregó acceso sin conexión. Reintenta la autorización.",
                409,
            )
    except (requests.RequestException, ValueError):
        return _html_response("No se pudo completar la conexión con Google.", 502)

    try:
        _save_refresh_token(settings, user_id, refresh_token)
    except Exception:
        current_app.logger.exception("No se pudo persistir la autorización Google Ads.")
        return _html_response("No se pudo guardar la autorización.", 503)

    return _html_response(
        "Autorización almacenada de forma segura. "
        "La validación de acceso a la cuenta y la sincronización aún están pendientes.",
        200,
    )


@google_ads_oauth_bp.get("/status")
@jwt_required()
def google_ads_oauth_status():
    if _admin() is None:
        return jsonify({"error": "Forbidden"}), 403
    settings = _settings()
    if settings is None:
        return jsonify({"enabled": False, "authorized": False}), 200
    record = db.session.get(GoogleAdsOAuthCredentialORM, 1)
    return jsonify({
        "enabled": True,
        "authorized": record is not None,
        "customer_id": settings["customer_id"],
        "last_authorized_at": (
            record.updated_at.isoformat() if record and record.updated_at else None
        ),
        "account_access_verified": False,
    }), 200
