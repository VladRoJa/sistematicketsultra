# app/routes/warehouse_routes.py

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app.utils.warehouse_access import require_warehouse_operator

warehouse_bp = Blueprint('warehouse', __name__)


@warehouse_bp.route('/access', methods=['GET'])
@jwt_required()
def warehouse_access():
    forbidden = require_warehouse_operator()
    if forbidden:
        return forbidden

    return jsonify({
        "allowed": True,
        "module": "warehouse"
    }), 200