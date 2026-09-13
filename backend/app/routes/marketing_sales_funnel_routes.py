from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.user_model import UserORM
from app.services.marketing_access import (
    MarketingAuthorizationError,
    resolve_marketing_access,
)
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.services.marketing_inputs_service import (
    MarketingInputValidationError,
    parse_month,
)
from app.services.marketing_sales_funnel_detail_service import (
    MarketingSalesFunnelDetailValidationError,
)
from app.services.marketing_sales_funnel_drilldown_service import (
    DETAIL_EXPORT_MIMETYPE,
    build_marketing_sales_funnel_drilldown,
    build_marketing_sales_funnel_drilldown_export,
)
from app.services.marketing_sales_funnel_iventas_stage_service import (
    count_monthly_iventas_leads,
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
        month = request.args.get("month", "")
        result = build_marketing_sales_funnel(
            month=month,
            access=access,
        )
        _, branch_ids, _ = load_visible_marketing_branches(access)
        result["summary"]["leads_iventas_month"] = (
            count_monthly_iventas_leads(
                month_start=parse_month(month),
                branch_ids=branch_ids,
            )
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
        result = build_marketing_sales_funnel_drilldown(
            month=request.args.get("month", ""),
            access=access,
            metric=request.args.get("metric", ""),
            branch_id=request.args.get("branch_id"),
            origin=request.args.get("origin"),
            page=request.args.get("page"),
            page_size=request.args.get("page_size"),
            sort_by=request.args.get("sort_by"),
            sort_dir=request.args.get("sort_dir"),
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


@marketing_sales_funnel_bp.get("/sales-funnel/detail/export")
@jwt_required()
def export_marketing_sales_funnel_detail_endpoint():
    try:
        access = _resolve_request_access()
        output, filename = build_marketing_sales_funnel_drilldown_export(
            month=request.args.get("month", ""),
            access=access,
            metric=request.args.get("metric", ""),
            branch_id=request.args.get("branch_id"),
            origin=request.args.get("origin"),
            sort_by=request.args.get("sort_by"),
            sort_dir=request.args.get("sort_dir"),
        )
        return send_file(
            output,
            mimetype=DETAIL_EXPORT_MIMETYPE,
            as_attachment=True,
            download_name=filename,
        )
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
                "message": "Falló la exportación del detalle del funnel.",
            }
        ), 500
