from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.user_model import UserORM
from app.services.marketing_access import (
    MarketingAuthorizationError,
    resolve_marketing_access,
)
from app.services.marketing_inputs_service import MarketingInputValidationError
from app.services.marketing_sales_funnel_detail_service import (
    MarketingSalesFunnelDetailValidationError,
    build_marketing_sales_funnel_detail,
)
from app.services.marketing_sales_funnel_service import (
    build_marketing_sales_funnel,
)


marketing_sales_funnel_bp = Blueprint(
    "marketing_sales_funnel",
    __name__,
)


def _resolve_request_access():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise MarketingAuthorizationError(
            "Identidad de usuario inválida."
        ) from exc

    user = UserORM.get_by_id(user_id)
    if user is None:
        raise MarketingAuthorizationError(
            "Usuario no encontrado."
        )

    return resolve_marketing_access(user)


@marketing_sales_funnel_bp.get("/sales-funnel")
@jwt_required()
def get_marketing_sales_funnel_endpoint():
    try:
        access = _resolve_request_access()
        result = build_marketing_sales_funnel(
            month=request.args.get("month", ""),
            access=access,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify(
            {"status": "error", "message": str(exc)}
        ), 403
    except MarketingInputValidationError as exc:
        return jsonify(
            {"status": "error", "message": str(exc)}
        ), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": (
                    "Falló la consulta del Funnel de Venta Total."
                ),
            }
        ), 500


@marketing_sales_funnel_bp.get("/sales-funnel/detail")
@jwt_required()
def get_marketing_sales_funnel_detail_endpoint():
    try:
        access = _resolve_request_access()
        result = build_marketing_sales_funnel_detail(
            month=request.args.get("month", ""),
            access=access,
            metric=request.args.get("metric", ""),
            branch_id=request.args.get("branch_id"),
            origin=request.args.get("origin"),
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify(
            {"status": "error", "message": str(exc)}
        ), 403
    except (
        MarketingInputValidationError,
        MarketingSalesFunnelDetailValidationError,
    ) as exc:
        return jsonify(
            {"status": "error", "message": str(exc)}
        ), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta del detalle del funnel.",
            }
        ), 500
