# app/routes/usuarios_routes.py
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash
from app.extensions import db
from app.models.user_model import UserORM
import re
from flask_jwt_extended import jwt_required

usuarios_bp = Blueprint('usuarios', __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
def _is_valid_email(s: str | None) -> bool:
    return bool(s and EMAIL_RE.match(s))

# ─────────────────────────────────────────────────────────────
# GET: Lista todos los usuarios
# ─────────────────────────────────────────────────────────────
@usuarios_bp.route('', methods=['GET'])
@jwt_required()  # Requiere autenticación para acceder a esta ruta
def listar_usuarios():
    usuarios = UserORM.query.all()
    return jsonify([{
        "id": u.id,
        "username": u.username,
        "rol": u.rol,
        "sucursal_id": u.sucursal_id,
        "department_id": u.department_id,
        "email": u.email,                      
    } for u in usuarios]), 200

# ─────────────────────────────────────────────────────────────
# GET: Usuario por ID
# ─────────────────────────────────────────────────────────────
@usuarios_bp.route('/<int:user_id>', methods=['GET'])
@jwt_required()  # Requiere autenticación para acceder a esta ruta
def obtener_usuario(user_id):
    u = UserORM.get_by_id(user_id)
    if not u:
        return jsonify({"error": "Usuario no encontrado"}), 404
    return jsonify({
        "id": u.id,
        "username": u.username,
        "rol": u.rol,
        "sucursal_id": u.sucursal_id,
        "department_id": u.department_id,
        "email": u.email,                        
    }), 200

# ─────────────────────────────────────────────────────────────
# POST: Crear usuario nuevo
# ─────────────────────────────────────────────────────────────
@usuarios_bp.route('', methods=['POST'])
@jwt_required()  # Requiere autenticación para acceder a esta ruta
def crear_usuario():
    data = request.json or {}
    obligatorio = ['username', 'password', 'rol', 'sucursal_id', 'department_id']
    if not all(k in data and data[k] for k in obligatorio):
        return jsonify({"error": "Faltan datos requeridos"}), 400

    if UserORM.get_by_username(data['username']):
        return jsonify({"error": "El username ya está en uso"}), 409

    email = (data.get('email') or '').strip() or None
    if email and not _is_valid_email(email):
        return jsonify({"error": "Email inválido"}), 400
    if email and UserORM.query.filter(UserORM.email == email).first():
        return jsonify({"error": "El email ya está en uso"}), 409

    nuevo = UserORM(
        username=data['username'],
        password=generate_password_hash(data['password']),
        rol=data.get('rol', 'usuario'),
        sucursal_id=data['sucursal_id'],
        department_id=data['department_id'],
        email=email                                 # 👈 guardar email (opcional)
    )
    db.session.add(nuevo)
    db.session.commit()
    return jsonify({"msg": "Usuario creado correctamente", "id": nuevo.id}), 201

# ─────────────────────────────────────────────────────────────
# PUT: Editar usuario
# ─────────────────────────────────────────────────────────────
@usuarios_bp.route('/<int:user_id>', methods=['PUT'])
@jwt_required()  # Requiere autenticación para acceder a esta ruta
def editar_usuario(user_id):
    u = UserORM.get_by_id(user_id)
    if not u:
        return jsonify({"error": "Usuario no encontrado"}), 404

    data = request.json or {}

    if 'username' in data:
        if UserORM.query.filter(UserORM.username == data['username'], UserORM.id != user_id).first():
            return jsonify({"error": "El username ya está en uso"}), 409
        u.username = data['username']

    if 'password' in data and data['password']:
        u.password = generate_password_hash(data['password'])

    if 'rol' in data:
        u.rol = data['rol']
    if 'sucursal_id' in data:
        u.sucursal_id = data['sucursal_id']
    if 'department_id' in data:
        u.department_id = data['department_id']

    if 'email' in data:                              # 👈 actualizar email
        email = (data.get('email') or '').strip() or None
        if email and not _is_valid_email(email):
            return jsonify({"error": "Email inválido"}), 400
        if email and UserORM.query.filter(UserORM.email == email, UserORM.id != user_id).first():
            return jsonify({"error": "El email ya está en uso"}), 409
        u.email = email

    db.session.commit()
    return jsonify({"msg": "Usuario actualizado correctamente"}), 200

# ─────────────────────────────────────────────────────────────
# DELETE: Eliminar usuario
# ─────────────────────────────────────────────────────────────
@usuarios_bp.route('/<int:user_id>', methods=['DELETE'])
@jwt_required()  # Requiere autenticación para acceder a esta ruta
def eliminar_usuario(user_id):
    u = UserORM.get_by_id(user_id)
    if not u:
        return jsonify({"error": "Usuario no encontrado"}), 404
    db.session.delete(u)
    db.session.commit()
    return jsonify({"msg": "Usuario eliminado correctamente"}), 200
