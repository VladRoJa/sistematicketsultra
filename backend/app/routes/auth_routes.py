#app\routes\auth_routes.py


# -------------------------------------------------------------------------------
# BLUEPRINT: AUTENTICACIÓN (LOGIN, SESIÓN)
# -------------------------------------------------------------------------------

from flask import Blueprint, request, jsonify, make_response, Response, current_app
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from datetime import timedelta
from app.models.user_model import UserORM
import logging
from app.config import Config
import json
from app. utils.error_handler import manejar_error
from app.services.auth_refresh_service import (
    RefreshDenied, issue_refresh, rotate_refresh, revoke_refresh,
)


# Configurar logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

auth_bp = Blueprint('auth', __name__)


def _refresh_enabled():
    return bool(current_app.config.get("AUTH_REFRESH_ENABLED", False))


def _origin_allowed():
    origin = request.headers.get("Origin", "")
    allowed = current_app.config.get("CORS_ORIGINS", [])
    if origin not in allowed:
        return False
    # Never send session cookies to insecure public origins.
    return origin.startswith("https://") or origin.startswith(
        ("http://localhost", "http://127.0.0.1")
    )


def _set_refresh_cookie(response, value):
    response.set_cookie(
        current_app.config.get("AUTH_REFRESH_COOKIE_NAME", "suite_refresh"),
        value,
        max_age=int(current_app.config.get("AUTH_REFRESH_ABSOLUTE_HOURS", 12)) * 3600,
        httponly=True,
        secure=True,
        samesite="Strict",
        path="/api/auth",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _clear_refresh_cookie(response):
    response.delete_cookie(
        current_app.config.get("AUTH_REFRESH_COOKIE_NAME", "suite_refresh"),
        path="/api/auth",
        secure=True,
        httponly=True,
        samesite="Strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _claims_for(user, session_id=None):
    claims = {
        "rol": user.rol,
        "sucursal_id": user.sucursal_id,
        "sucursales_ids": user.sucursales_ids,
        "department_id": user.department_id,
    }
    if session_id is not None:
        claims["sid"] = session_id
    return claims


def _user_response(user):
    return {
        "id": user.id,
        "username": user.username,
        "rol": user.rol,
        "sucursal_id": user.sucursal_id,
        "sucursales_ids": user.sucursales_ids,
        "department_id": user.department_id,
    }

# -------------------------------------------------------------------------------
# RUTA: LOGIN (Generar token JWT)
# -------------------------------------------------------------------------------

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json(force=True)
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')

        user = UserORM.get_by_username(username)
        if user:
            if user.verify_password(password):
                refresh_cookie = None
                session_id = None
                if _refresh_enabled() and "Origin" in request.headers:
                    # Browser origins must be allowlisted before a refresh
                    # cookie is created. Clients without Origin retain the
                    # legacy JWT-only contract, never a refresh session.
                    if not _origin_allowed():
                        return jsonify({"error": "INVALID_ORIGIN"}), 403
                    refresh_cookie, session_id = issue_refresh(user.id)

                token = create_access_token(
                    identity=str(user.id),
                    additional_claims=_claims_for(user, session_id),
                )
                logger.info("Inicio de sesión exitoso para usuario id=%s", user.id)

                response = jsonify({
                    "message": "Login exitoso",
                    "token": token,
                    "user": _user_response(user),
                })
                response.headers["Cache-Control"] = "no-store"
                if refresh_cookie:
                    _set_refresh_cookie(response, refresh_cookie)
                return response, 200
            else:
                logger.warning(f"Intento de login fallido: contraseña incorrecta para usuario '{username}'.")
        else:
            logger.warning(f"Intento de login fallido: usuario '{username}' no encontrado.")

        return jsonify({"message": "Credenciales incorrectas"}), 401

    except Exception as e:
        return manejar_error(e, "login")




@auth_bp.route("/refresh", methods=["POST"])
def refresh_session():
    """Rotate a browser cookie, never accept raw refresh secrets in JSON."""
    if not _refresh_enabled():
        return jsonify({"error": "REFRESH_DISABLED"}), 404
    if not _origin_allowed():
        return jsonify({"error": "INVALID_ORIGIN"}), 403

    raw_cookie = request.cookies.get(
        current_app.config.get("AUTH_REFRESH_COOKIE_NAME", "suite_refresh")
    )
    try:
        user, rotated_cookie, session_id = rotate_refresh(raw_cookie)
    except RefreshDenied as exc:
        return _clear_refresh_cookie(
            jsonify({"error": exc.code})
        ), 401

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims=_claims_for(user, session_id),
    )
    response = jsonify({
        "token": access_token,
        "user": _user_response(user),
    })
    return _set_refresh_cookie(response, rotated_cookie), 200


@auth_bp.route("/logout", methods=["POST"])
def revoke_session():
    """Revoke only this browser session; login with password is unchanged."""
    if not _refresh_enabled():
        return jsonify({"error": "REFRESH_DISABLED"}), 404
    if not _origin_allowed():
        return jsonify({"error": "INVALID_ORIGIN"}), 403
    revoke_refresh(
        request.cookies.get(
            current_app.config.get("AUTH_REFRESH_COOKIE_NAME", "suite_refresh")
        )
    )
    return _clear_refresh_cookie(jsonify({"status": "logged_out"})), 200

# -------------------------------------------------------------------------------
# RUTA: OBTENER INFORMACIÓN DE SESIÓN ACTIVA
# -------------------------------------------------------------------------------

@auth_bp.route('/session-info', methods=['GET', 'OPTIONS'])
@jwt_required()
def session_info():
    from flask_jwt_extended import get_jwt
    import datetime

    # 📅 Depuración: ver cuándo expira el token
    jwt_data = get_jwt()
    exp_timestamp = jwt_data.get("exp")
    exp_datetime = datetime.datetime.fromtimestamp(exp_timestamp)
    logger.info(f"🕒 Token expira en: {exp_datetime} (timestamp: {exp_timestamp})")

    origin = request.headers.get('Origin') or '*'
    logger.info(f"🛡 Origin recibido en session-info: {origin}")

    if request.method == 'OPTIONS':
        response = make_response('', 204)
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    try:
        current_user_id = get_jwt_identity()
        logger.info(f"🔐 JWT recibido para ID de usuario: {current_user_id}")

        user = UserORM.get_by_id(current_user_id)
        if not user:
            logger.warning(f"⚠️ Usuario no encontrado para ID: {current_user_id}")
            return jsonify({"message": "Usuario no encontrado"}), 404

        response = jsonify({
            "user": {
                "id": user.id,
                "username": user.username,
                "rol": user.rol,
                "sucursal_id": user.sucursal_id,
                "sucursales_ids": user.sucursales_ids,
                "department_id": user.department_id,
            }
        })
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 200

    except Exception as e:
        return manejar_error(e, "session-info")
