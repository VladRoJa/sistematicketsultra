# app/routes/warehouse_routes.py

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app.utils.warehouse_access import require_warehouse_operator
from app.models import (
    WarehouseSourceORM,
    WarehouseFamilyORM,
    WarehouseOperationalRoleORM,
    WarehouseReportTypeORM,
)


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
    
    
@warehouse_bp.route('/catalogs', methods=['GET'])
@jwt_required()
def warehouse_catalogs():
    forbidden = require_warehouse_operator()
    if forbidden:
        return forbidden

    sources = WarehouseSourceORM.query.filter_by(active=True).order_by(WarehouseSourceORM.key.asc()).all()
    families = WarehouseFamilyORM.query.filter_by(active=True).order_by(WarehouseFamilyORM.key.asc()).all()
    operational_roles = (
        WarehouseOperationalRoleORM.query
        .filter_by(active=True)
        .order_by(WarehouseOperationalRoleORM.key.asc())
        .all()
    )
    report_types = (
        WarehouseReportTypeORM.query
        .filter_by(active=True)
        .order_by(WarehouseReportTypeORM.key.asc())
        .all()
    )

    return jsonify({
        "sources": [
            {
                "id": item.id,
                "key": item.key,
                "label": item.label,
            }
            for item in sources
        ],
        "families": [
            {
                "id": item.id,
                "key": item.key,
                "label": item.label,
            }
            for item in families
        ],
        "operational_roles": [
            {
                "id": item.id,
                "key": item.key,
                "label": item.label,
            }
            for item in operational_roles
        ],
        "report_types": [
            {
                "id": item.id,
                "key": item.key,
                "label": item.label,
                "family_id": item.family_id,
                "default_source_id": item.default_source_id,
                "default_operational_role_id": item.default_operational_role_id,
                "default_period_type": item.default_period_type,
            }
            for item in report_types
        ],
    }), 200