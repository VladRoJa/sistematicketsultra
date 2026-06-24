#   backend\app\routes\warehouse_commercial_routes.py


from decimal import Decimal

from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import jwt_required

from app.utils.warehouse_access import require_warehouse_view
from app.warehouse.services.commercial_promotions_service import (
    CommercialPromotionsService,
)


warehouse_commercial_bp = Blueprint("warehouse_commercial", __name__)


def _serialize_value(value):
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, dict):
        return {
            key: _serialize_value(inner_value)
            for key, inner_value in value.items()
        }

    if isinstance(value, list):
        return [
            _serialize_value(item)
            for item in value
        ]

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def _serialize_row(row: dict) -> dict:
    return {
        key: _serialize_value(value)
        for key, value in row.items()
    }


@warehouse_commercial_bp.route("/promotions/ranking", methods=["GET"])
@jwt_required()
def get_promotions_ranking():
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    try:
        rows = CommercialPromotionsService.get_ranking_general()
    except Exception:
        current_app.logger.exception(
            "Error obteniendo ranking general de promociones comerciales."
        )
        return jsonify({
            "error": "No se pudo obtener el ranking de promociones",
            "detail": "Ocurrió un error al consultar el análisis comercial de promociones.",
        }), 500

    return jsonify({
        "items": [
            _serialize_row(row)
            for row in rows
        ],
        "metadata": {
            "source": "venta_total",
            "scope": "sucursales_canonizadas",
            "excludes": [
                "agregadoras",
                "corporativo",
                "beca",
                "sucursal_en_linea",
                "gimnasio_prueba",
            ],
            "classification_source": "warehouse_commercial_catalog",
            "canonicality_rule": (
                "Último snapshot daily canónico por mes; "
                "solo filas activas del mismo mes; "
                "solo sucursales resueltas por aliases de Track."
            ),
        },
    }), 200
    
@warehouse_commercial_bp.route("/promotions/by-month", methods=["GET"])
@jwt_required()
def get_promotions_by_month():
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    try:
        rows = CommercialPromotionsService.get_top_by_month()
    except Exception:
        current_app.logger.exception(
            "Error obteniendo promociones comerciales por mes."
        )
        return jsonify({
            "error": "No se pudieron obtener las promociones por mes",
            "detail": "Ocurrió un error al consultar el análisis mensual de promociones.",
        }), 500

    return jsonify({
        "items": [
            _serialize_row(row)
            for row in rows
        ],
        "metadata": {
            "source": "venta_total",
            "scope": "sucursales_canonizadas",
            "excludes": [
                "agregadoras",
                "corporativo",
                "beca",
                "sucursal_en_linea",
                "gimnasio_prueba",
            ],
            "classification_source": "warehouse_commercial_catalog",
            "canonicality_rule": (
                "Último snapshot daily canónico por mes; "
                "solo filas activas del mismo mes; "
                "solo sucursales resueltas por aliases de Track."
            ),
        },
    }), 200
    
    
@warehouse_commercial_bp.route("/promotions/by-branch", methods=["GET"])
@jwt_required()
def get_promotions_by_branch():
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    try:
        rows = CommercialPromotionsService.get_top_by_branch()
    except Exception:
        current_app.logger.exception(
            "Error obteniendo promociones comerciales por sucursal."
        )
        return jsonify({
            "error": "No se pudieron obtener las promociones por sucursal",
            "detail": "Ocurrió un error al consultar el análisis por sucursal de promociones.",
        }), 500

    return jsonify({
        "items": [
            _serialize_row(row)
            for row in rows
        ],
        "metadata": {
            "source": "venta_total",
            "scope": "sucursales_canonizadas",
            "excludes": [
                "agregadoras",
                "corporativo",
                "beca",
                "sucursal_en_linea",
                "gimnasio_prueba",
            ],
            "classification_source": "warehouse_commercial_catalog",
            "canonicality_rule": (
                "Último snapshot daily canónico por mes; "
                "solo filas activas del mismo mes; "
                "solo sucursales resueltas por aliases de Track."
            ),
            "impact_rule": {
                "impacto_fuerte": ">= 5%",
                "impacto_medio": ">= 2% y < 5%",
                "impacto_bajo_no_concluyente": "< 2%",
            },
        },
    }), 200
    
@warehouse_commercial_bp.route("/promotions/unmapped", methods=["GET"])
@jwt_required()
def get_promotions_unmapped():
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    try:
        rows = CommercialPromotionsService.get_unmapped_descriptions()
    except Exception:
        current_app.logger.exception(
            "Error obteniendo descripciones comerciales sin clasificar."
        )
        return jsonify({
            "error": "No se pudieron obtener las descripciones sin clasificar",
            "detail": "Ocurrió un error al consultar promociones pendientes de clasificación.",
        }), 500

    return jsonify({
        "items": [
            _serialize_row(row)
            for row in rows
        ],
        "metadata": {
            "source": "venta_total",
            "scope": "sucursales_canonizadas",
            "classification_source": "warehouse_commercial_catalog",
            "purpose": (
                "Detectar descripciones de Venta Total que parecen promociones "
                "pero aún no están clasificadas en el catálogo comercial."
            ),
            "candidate_patterns": [
                "PROMO",
                "GRATIS",
                "50%",
                "BORRON",
                "BORRÓN",
                "PREVENTA",
                "BUEN FIN",
                "HOT SALE",
                "SAN VALENT",
                "NAVIDAD",
                "PRIMER PAGO",
                "2DO MES",
                "3 X 2",
                "DESCUENTO",
                "INSCRIP",
            ],
        },
    }), 200
    
@warehouse_commercial_bp.route("/promotions/summary", methods=["GET"])
@jwt_required()
def get_promotions_summary():
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    try:
        summary = CommercialPromotionsService.get_summary()
    except Exception:
        current_app.logger.exception(
            "Error obteniendo resumen ejecutivo de promociones comerciales."
        )
        return jsonify({
            "error": "No se pudo obtener el resumen de promociones",
            "detail": "Ocurrió un error al consultar el resumen ejecutivo de promociones.",
        }), 500

    return jsonify({
        "summary": _serialize_row(summary),
        "metadata": {
            "source": "venta_total",
            "scope": "sucursales_canonizadas",
            "excludes": [
                "agregadoras",
                "corporativo",
                "beca",
                "sucursal_en_linea",
                "gimnasio_prueba",
            ],
            "classification_source": "warehouse_commercial_catalog",
            "canonicality_rule": (
                "Último snapshot daily canónico por mes; "
                "solo filas activas del mismo mes; "
                "solo sucursales resueltas por aliases de Track."
            ),
        },
    }), 200