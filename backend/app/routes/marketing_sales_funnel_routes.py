from __future__ import annotations

from time import perf_counter

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.suite_governance import (
    SuiteRegionORM,
    SuiteSucursalRegionAssignmentORM,
)
from app.models.user_model import UserORM
from app.services.marketing_access import (
    MarketingAccess,
    MarketingAuthorizationError,
    resolve_marketing_access,
)
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.services.marketing_inputs_service import (
    MarketingInputValidationError,
    parse_month,
)
from app.services.marketing_sales_funnel_cutoff_detail_service import (
    build_marketing_sales_funnel_cutoff_detail,
    build_marketing_sales_funnel_cutoff_export,
)
from app.services.marketing_sales_funnel_cutoff_service import (
    build_marketing_sales_funnel_at_cutoff,
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
    build_monthly_iventas_leads_detail,
    build_monthly_iventas_leads_export,
)
from app.services.marketing_visit_conversion_service import (
    VISIT_CONVERSION_METRICS,
    build_visit_conversion_detail,
    build_visit_conversion_export,
    build_visit_conversion_summary_from_loaded_data,
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


def _parse_requested_branch_ids(raw_value: str | None) -> tuple[int, ...] | None:
    raw = str(raw_value or "").strip()
    if not raw:
        return None

    result: list[int] = []
    seen: set[int] = set()
    for token in raw.split(","):
        normalized = token.strip()
        if not normalized:
            continue
        try:
            branch_id = int(normalized)
        except (TypeError, ValueError) as exc:
            raise MarketingSalesFunnelDetailValidationError(
                "branch_ids contiene una sucursal inválida."
            ) from exc
        if branch_id <= 0:
            raise MarketingSalesFunnelDetailValidationError(
                "branch_ids contiene una sucursal inválida."
            )
        if branch_id not in seen:
            seen.add(branch_id)
            result.append(branch_id)

    if not result:
        raise MarketingSalesFunnelDetailValidationError(
            "branch_ids no contiene sucursales válidas."
        )
    return tuple(result)


def _narrow_access(
    access: MarketingAccess,
    requested_branch_ids: tuple[int, ...] | None,
) -> MarketingAccess:
    if requested_branch_ids is None:
        return access

    _, visible_branch_ids, _ = load_visible_marketing_branches(access)
    allowed = set(visible_branch_ids)
    unauthorized = [
        branch_id
        for branch_id in requested_branch_ids
        if branch_id not in allowed
    ]
    if unauthorized:
        raise MarketingAuthorizationError(
            "El alcance solicitado contiene sucursales no autorizadas."
        )

    return MarketingAccess(
        type="FILTERED_BRANCHES",
        is_global=False,
        branch_ids=requested_branch_ids,
        role=access.role,
        can_edit_inputs=access.can_edit_inputs,
        can_view_reactivation=access.can_view_reactivation,
        fallback_used=access.fallback_used,
    )


def _resolve_scoped_access() -> tuple[MarketingAccess, MarketingAccess]:
    base_access = _resolve_request_access()
    requested_branch_ids = _parse_requested_branch_ids(
        request.args.get("branch_ids")
    )
    return base_access, _narrow_access(base_access, requested_branch_ids)


def _load_scope_options(access: MarketingAccess) -> list[dict[str, object]]:
    branches, branch_ids, _ = load_visible_marketing_branches(access)
    if not branch_ids:
        return []

    assignments = (
        SuiteSucursalRegionAssignmentORM.query
        .join(
            SuiteRegionORM,
            SuiteRegionORM.id == SuiteSucursalRegionAssignmentORM.region_id,
        )
        .filter(
            SuiteSucursalRegionAssignmentORM.sucursal_id.in_(branch_ids),
            SuiteSucursalRegionAssignmentORM.is_current.is_(True),
            SuiteRegionORM.is_active.is_(True),
        )
        .all()
    )
    region_by_branch = {
        int(assignment.sucursal_id): {
            "region_id": int(assignment.region_id),
            "region": str(assignment.region.region_label).strip(),
        }
        for assignment in assignments
        if assignment.region is not None
    }

    return [
        {
            "sucursal_id": int(branch.sucursal_id),
            "sucursal": str(branch.name),
            "region_id": region_by_branch.get(branch.sucursal_id, {}).get(
                "region_id"
            ),
            "region": region_by_branch.get(branch.sucursal_id, {}).get(
                "region"
            ),
        }
        for branch in branches
    ]


@marketing_sales_funnel_bp.get("/sales-funnel")
@jwt_required()
def get_marketing_sales_funnel_endpoint():
    request_started = perf_counter()
    try:
        stage_started = perf_counter()
        base_access, access = _resolve_scoped_access()
        month = request.args.get("month", "")
        parse_month(month)
        access_ms = (perf_counter() - stage_started) * 1000

        stage_started = perf_counter()
        funnel_build = build_marketing_sales_funnel_at_cutoff(
            month=month,
            access=access,
            cutoff_date=request.args.get("cutoff_date"),
        )
        result = funnel_build.payload
        funnel_ms = (perf_counter() - stage_started) * 1000

        stage_started = perf_counter()
        branch_scope_ms = (perf_counter() - stage_started) * 1000

        # El builder de corte ya toma la población exacta del run iVentas
        # seleccionado. No se vuelve a sobrescribir con el canónico mensual.
        leads_ms = 0.0

        stage_started = perf_counter()
        visit_conversion = build_visit_conversion_summary_from_loaded_data(
            loaded=funnel_build.loaded,
        )
        conversion_ms = (perf_counter() - stage_started) * 1000

        result["summary"].update(visit_conversion["summary"])
        conversion_by_branch = visit_conversion["branches"]
        for branch_payload in result["branches"]:
            branch_payload.update(
                conversion_by_branch.get(
                    int(branch_payload["sucursal_id"]),
                    {},
                )
            )
        result["data_quality"].update(
            visit_conversion["data_quality"]
        )
        if not visit_conversion["data_quality"][
            "visit_conversion_cohort_complete"
        ]:
            result["data_quality"]["limitations"].append(
                "La conversión de visitas sigue abierta: una visita del mes "
                "puede comprar hasta 30 días después."
            )

        stage_started = perf_counter()
        result["scope_options"] = _load_scope_options(base_access)
        scope_options_ms = (perf_counter() - stage_started) * 1000

        response = jsonify(result)
        total_ms = (perf_counter() - request_started) * 1000
        response.headers["Server-Timing"] = ", ".join(
            (
                f"access;dur={access_ms:.1f}",
                f"funnel;dur={funnel_ms:.1f}",
                f"branch_scope;dur={branch_scope_ms:.1f}",
                f"leads;dur={leads_ms:.1f}",
                f"visit_conversion;dur={conversion_ms:.1f}",
                f"scope_options;dur={scope_options_ms:.1f}",
                f"total;dur={total_ms:.1f}",
            )
        )
        return response, 200
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
                "message": (
                    "Falló la consulta del Funnel de Venta Total."
                ),
            }
        ), 500


@marketing_sales_funnel_bp.get("/sales-funnel/detail")
@jwt_required()
def get_marketing_sales_funnel_detail_endpoint():
    try:
        _, access = _resolve_scoped_access()
        month = request.args.get("month", "")
        cutoff_date = request.args.get("cutoff_date")
        metric = request.args.get("metric", "")

        if cutoff_date:
            result = build_marketing_sales_funnel_cutoff_detail(
                month=month,
                cutoff_date=cutoff_date,
                access=access,
                metric=metric,
                branch_id=request.args.get("branch_id"),
                origin=request.args.get("origin"),
                page=request.args.get("page"),
                page_size=request.args.get("page_size"),
                sort_by=request.args.get("sort_by"),
                sort_dir=request.args.get("sort_dir"),
            )
        elif metric == "leads_iventas":
            result = build_monthly_iventas_leads_detail(
                month=month,
                access=access,
                branch_id=request.args.get("branch_id"),
                page=request.args.get("page"),
                page_size=request.args.get("page_size"),
                sort_by=request.args.get("sort_by"),
                sort_dir=request.args.get("sort_dir"),
            )
        elif metric in VISIT_CONVERSION_METRICS:
            result = build_visit_conversion_detail(
                month=month,
                access=access,
                metric=metric,
                branch_id=request.args.get("branch_id"),
                page=request.args.get("page"),
                page_size=request.args.get("page_size"),
                sort_by=request.args.get("sort_by"),
                sort_dir=request.args.get("sort_dir"),
            )
        else:
            result = build_marketing_sales_funnel_drilldown(
                month=month,
                access=access,
                metric=metric,
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
        _, access = _resolve_scoped_access()
        month = request.args.get("month", "")
        cutoff_date = request.args.get("cutoff_date")
        metric = request.args.get("metric", "")

        if cutoff_date:
            output, filename = build_marketing_sales_funnel_cutoff_export(
                month=month,
                cutoff_date=cutoff_date,
                access=access,
                metric=metric,
                branch_id=request.args.get("branch_id"),
                origin=request.args.get("origin"),
                sort_by=request.args.get("sort_by"),
                sort_dir=request.args.get("sort_dir"),
            )
        elif metric == "leads_iventas":
            output, filename = build_monthly_iventas_leads_export(
                month=month,
                access=access,
                branch_id=request.args.get("branch_id"),
                sort_by=request.args.get("sort_by"),
                sort_dir=request.args.get("sort_dir"),
            )
        elif metric in VISIT_CONVERSION_METRICS:
            output, filename = build_visit_conversion_export(
                month=month,
                access=access,
                metric=metric,
                branch_id=request.args.get("branch_id"),
                sort_by=request.args.get("sort_by"),
                sort_dir=request.args.get("sort_dir"),
            )
        else:
            output, filename = build_marketing_sales_funnel_drilldown_export(
                month=month,
                access=access,
                metric=metric,
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
