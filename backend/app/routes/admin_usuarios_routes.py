from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import text
from app.extensions import db

from app.models.user_model import UserORM

admin_usuarios_bp = Blueprint("admin_usuarios", __name__)


def _get_current_user_admin():
    """Retorna (user, None) o (None, (json, status)) si no autorizado."""
    current_user_id = get_jwt_identity()
    user = UserORM.get_by_id(current_user_id)
    if not user:
        return None, (jsonify({"mensaje": "No autenticado"}), 401)
    if not user.es_admin():
        return None, (jsonify({"mensaje": "No autorizado"}), 403)
    return user, None


@admin_usuarios_bp.route("/<int:user_id>/sucursales", methods=["GET"])
@jwt_required()
def get_sucursales_usuario_admin(user_id: int):
    _, err = _get_current_user_admin()
    if err:
        return err

    target_user = UserORM.get_by_id(user_id)
    if not target_user:
        return jsonify({"mensaje": "Usuario no encontrado"}), 404

    return jsonify({
        "user_id": target_user.id,
        "sucursales_ids": target_user.sucursales_ids
    }), 200
    

@admin_usuarios_bp.route("/<int:user_id>/sucursales", methods=["PUT"])
@jwt_required()
def put_sucursales_usuario_admin(user_id: int):
    _, err = _get_current_user_admin()
    if err:
        return err

    target_user = UserORM.get_by_id(user_id)
    if not target_user:
        return jsonify({"mensaje": "Usuario no encontrado"}), 404

    data = request.get_json(silent=True) or {}
    if "sucursales_ids" not in data or not isinstance(data["sucursales_ids"], list):
        return jsonify({"mensaje": "Payload inválido", "detalle": "sucursales_ids debe ser una lista"}), 400

    # Convertir a int + deduplicar (permitimos lista vacía)
    try:
        sucursales_ids = [int(x) for x in data["sucursales_ids"]]
    except (TypeError, ValueError):
        return jsonify({"mensaje": "Payload inválido", "detalle": "sucursales_ids debe contener solo enteros"}), 400

    sucursales_ids = sorted(set(sucursales_ids))

    # Reemplazo total: DELETE + INSERT (transacción)
    try:
        db.session.execute(
            text("DELETE FROM usuario_sucursal WHERE user_id = :uid"),
            {"uid": target_user.id},
        )

        if sucursales_ids:
            db.session.execute(
                text("INSERT INTO usuario_sucursal (user_id, sucursal_id) VALUES (:uid, :sid)"),
                [{"uid": target_user.id, "sid": sid} for sid in sucursales_ids],
            )

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"mensaje": "Error al actualizar sucursales"}), 500

    return jsonify({
        "mensaje": "Sucursales actualizadas",
        "user_id": target_user.id,
        "sucursales_ids": sucursales_ids
    }), 200