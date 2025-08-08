# app/routes/usuarios_routes.py

from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash
from backend.app. extensions import db
from backend.app.models.user_model import UserORM

usuarios_bp = Blueprint('usuarios', __name__)

# ─────────────────────────────────────────────────────────────
# GET: Lista todos los usuarios
# ─────────────────────────────────────────────────────────────
@usuarios_bp.route('', methods=['GET'])
def listar_usuarios():
    usuarios = UserORM.query.all()
    resultado = []
    for u in usuarios:
        resultado.append({
            "id": u.id,
            "username": u.username,
            "rol": u.rol,
            "sucursal_id": u.sucursal_id,
            "department_id": u.department_id,
        })
    return jsonify(resultado), 200

# ─────────────────────────────────────────────────────────────
# GET: Usuario por ID
# ─────────────────────────────────────────────────────────────
@usuarios_bp.route('/<int:user_id>', methods=['GET'])
def obtener_usuario(user_id):
    usuario = UserORM.get_by_id(user_id)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado"}), 404
    return jsonify({
        "id": usuario.id,
        "username": usuario.username,
        "rol": usuario.rol,
        "sucursal_id": usuario.sucursal_id,
        "department_id": usuario.department_id,
    }), 200

# ─────────────────────────────────────────────────────────────
# POST: Crear usuario nuevo
# ─────────────────────────────────────────────────────────────
@usuarios_bp.route('', methods=['POST'])
def crear_usuario():
    data = request.json
    obligatorio = ['username', 'password', 'rol', 'sucursal_id', 'department_id']
    if not all(k in data and data[k] for k in obligatorio):
        return jsonify({"error": "Faltan datos requeridos"}), 400

    if UserORM.get_by_username(data['username']):
        return jsonify({"error": "El username ya está en uso"}), 409

    hashed_password = generate_password_hash(data['password'])
    nuevo_usuario = UserORM(
        username=data['username'],
        password=hashed_password,
        rol=data.get('rol', 'usuario'),
        sucursal_id=data['sucursal_id'],
        department_id=data['department_id']
    )
    db.session.add(nuevo_usuario)
    db.session.commit()
    return jsonify({"msg": "Usuario creado correctamente", "id": nuevo_usuario.id}), 201

# ─────────────────────────────────────────────────────────────
# PUT: Editar usuario
# ─────────────────────────────────────────────────────────────
@usuarios_bp.route('/<int:user_id>', methods=['PUT'])
def editar_usuario(user_id):
    usuario = UserORM.get_by_id(user_id)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado"}), 404

    data = request.json
    if 'username' in data:
        if UserORM.query.filter(UserORM.username == data['username'], UserORM.id != user_id).first():
            return jsonify({"error": "El username ya está en uso"}), 409
        usuario.username = data['username']

    if 'password' in data and data['password']:
        usuario.password = generate_password_hash(data['password'])

    if 'rol' in data:
        usuario.rol = data['rol']
    if 'sucursal_id' in data:
        usuario.sucursal_id = data['sucursal_id']
    if 'department_id' in data:
        usuario.department_id = data['department_id']

    db.session.commit()
    return jsonify({"msg": "Usuario actualizado correctamente"}), 200

# ─────────────────────────────────────────────────────────────
# DELETE: Eliminar usuario
# ─────────────────────────────────────────────────────────────
@usuarios_bp.route('/<int:user_id>', methods=['DELETE'])
def eliminar_usuario(user_id):
    usuario = UserORM.get_by_id(user_id)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado"}), 404
    db.session.delete(usuario)
    db.session.commit()
    return jsonify({"msg": "Usuario eliminado correctamente"}), 200

