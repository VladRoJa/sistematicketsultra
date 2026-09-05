from __future__ import annotations

from datetime import date
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)

from app.extensions import db
from app.models.user_model import UserORM
from app.services.marketing_access import (
    MarketingAuthorizationError,
    resolve_marketing_access,
)
from app.services.marketing_dashboard_service import (
    build_marketing_attribution_detail,
    build_marketing_dashboard,
    build_marketing_investment_detail,
    build_marketing_visitors_detail,
    load_visible_marketing_branches,
)
from app.services.marketing_inputs_service import (
    MarketingInputConflictError,
    MarketingInputValidationError,
    list_marketing_inputs,
    parse_month,
    serialize_marketing_input,
    upsert_marketing_input,
    validate_input_payload,
)
from app.services.marketing_leads_detail_service import (
    build_marketing_leads_detail,
)
from app.services.marketing_reactivation_service import (
    MarketingReactivationConflictError,
    MarketingReactivationInvalidTransitionError,
    MarketingReactivationNotFoundError,
    MarketingReactivationValidationError,
    build_marketing_reactivation_candidate_summary,
    build_marketing_reactivation_candidates,
    create_marketing_reactivation_campaign,
    export_marketing_reactivation_campaign,
    get_marketing_reactivation_campaign,
    list_marketing_reactivation_campaigns,
    list_marketing_reactivation_sources,
    list_marketing_reactivation_tariffs,
    mark_marketing_reactivation_campaign_sent,
    preview_marketing_reactivation_campaign,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


marketing_bp = Blueprint("marketing", __name__)


def _get_current_marketing_user() -> UserORM:
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
    return user


def _resolve_request_access():
    user = _get_current_marketing_user()
    access = resolve_marketing_access(user)
    return user, access


def _require_campaign_management(access) -> None:
    if not access.can_edit_inputs:
        raise MarketingAuthorizationError(
            "No autorizado para gestionar campañas de Reactivación."
        )


def _reactivation_allowed_sucursal_keys(access) -> tuple[str, ...] | None:
    if access.is_global:
        return None
    visible_branches, _, _ = load_visible_marketing_branches(access)
    keys = tuple(
        sorted(
            {
                key
                for key in (
                    normalize_socios_vencidos_branch_key(branch.name)
                    for branch in visible_branches
                )
                if key is not None
            }
        )
    )
    if not keys:
        raise MarketingAuthorizationError(
            "No hay sucursales de Reactivación dentro del alcance del usuario."
        )
    return keys


def _parse_campaign_payload(*, require_name: bool) -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise MarketingReactivationValidationError(
            "El payload JSON debe ser un objeto."
        )
    allowed_fields = {
        "date_from",
        "date_to",
        "filters",
        "campaign_cooldown_days",
    }
    if require_name:
        allowed_fields.update({"name", "notes"})
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise MarketingReactivationValidationError(
            "Campos no permitidos: " + ", ".join(unknown_fields) + "."
        )
    return payload


def _parse_optional_branch_id() -> int | None:
    raw_value = request.args.get("sucursal_id")
    if raw_value is None or not raw_value.strip():
        return None

    try:
        branch_id = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise MarketingInputValidationError(
            "sucursal_id debe ser un entero válido."
        ) from exc

    if branch_id <= 0:
        raise MarketingInputValidationError(
            "sucursal_id debe ser mayor a cero."
        )

    return branch_id


def _parse_required_positive_int(parameter_name: str) -> int:
    raw_value = request.args.get(parameter_name)
    if raw_value is None or not raw_value.strip():
        raise MarketingInputValidationError(
            f"{parameter_name} es obligatorio."
        )

    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise MarketingInputValidationError(
            f"{parameter_name} debe ser un entero válido."
        ) from exc

    if value <= 0:
        raise MarketingInputValidationError(
            f"{parameter_name} debe ser mayor a cero."
        )

    return value


def _parse_required_text(parameter_name: str) -> str:
    raw_value = request.args.get(parameter_name)
    if raw_value is None or not raw_value.strip():
        raise MarketingInputValidationError(
            f"{parameter_name} es obligatorio."
        )
    return raw_value.strip()


def _parse_required_iso_date(parameter_name: str) -> date:
    raw_value = _parse_required_text(parameter_name)
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise MarketingInputValidationError(
            f"{parameter_name} debe ser una fecha ISO válida (YYYY-MM-DD)."
        ) from exc


@marketing_bp.get("/reactivation/sources")
@jwt_required()
def get_marketing_reactivation_sources_endpoint():
    try:
        _, access = _resolve_request_access()
        result = list_marketing_reactivation_sources(
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        result["permissions"] = {
            "can_manage_campaigns": bool(access.can_edit_inputs),
        }
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify(
            {"status": "error", "message": str(exc)}
        ), 403
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": (
                    "Falló la consulta de fuentes de reactivación."
                ),
            }
        ), 500


@marketing_bp.get("/reactivation/tariffs")
@jwt_required()
def get_marketing_reactivation_tariffs_endpoint():
    try:
        _, access = _resolve_request_access()
        result = list_marketing_reactivation_tariffs(
            date_from=_parse_required_iso_date("date_from"),
            date_to=_parse_required_iso_date("date_to"),
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except (MarketingInputValidationError, MarketingReactivationValidationError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {"status": "error", "message": "Falló la consulta de tarifas."}
        ), 500


@marketing_bp.get("/reactivation/candidates")
@jwt_required()
def get_marketing_reactivation_candidates_endpoint():
    try:
        _, access = _resolve_request_access()
        date_from = _parse_required_iso_date("date_from")
        date_to = _parse_required_iso_date("date_to")
        if date_from > date_to:
            raise MarketingInputValidationError(
                "date_from no puede ser posterior a date_to."
            )
        iventas_period_key = _parse_required_text(
            "iventas_period_key"
        )
        result = build_marketing_reactivation_candidates(
            date_from=date_from,
            date_to=date_to,
            iventas_period_key=iventas_period_key,
            page=request.args.get("page", "1"),
            page_size=request.args.get("page_size", "50"),
            sucursal=request.args.get("sucursal"),
            tarifa=request.args.get("tarifa"),
            tariff_group=request.args.get("tariff_group"),
            operational_status=request.args.get(
                "operational_status", "ALL"
            ),
            search=request.args.get("search"),
            sort=request.args.get("sort", "fecha_vencimiento"),
            direction=request.args.get("direction", "desc"),
            cursor=request.args.get("cursor"),
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify(
            {"status": "error", "message": str(exc)}
        ), 403
    except (
        MarketingInputValidationError,
        MarketingReactivationValidationError,
    ) as exc:
        return jsonify(
            {"status": "error", "message": str(exc)}
        ), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": (
                    "Falló la consulta de candidatos de reactivación."
                ),
            }
        ), 500


@marketing_bp.get("/reactivation/candidates/summary")
@jwt_required()
def get_marketing_reactivation_candidate_summary_endpoint():
    try:
        _, access = _resolve_request_access()
        date_from = _parse_required_iso_date("date_from")
        date_to = _parse_required_iso_date("date_to")
        if date_from > date_to:
            raise MarketingInputValidationError(
                "date_from no puede ser posterior a date_to."
            )
        result = build_marketing_reactivation_candidate_summary(
            date_from=date_from,
            date_to=date_to,
            iventas_period_key=_parse_required_text("iventas_period_key"),
            sucursal=request.args.get("sucursal"),
            tarifa=request.args.get("tarifa"),
            tariff_group=request.args.get("tariff_group"),
            operational_status=request.args.get(
                "operational_status", "ALL"
            ),
            search=request.args.get("search"),
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except (
        MarketingInputValidationError,
        MarketingReactivationValidationError,
    ) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": "Falló el resumen de candidatos de reactivación.",
            }
        ), 500


@marketing_bp.post("/reactivation/campaigns/preview")
@jwt_required()
def preview_marketing_reactivation_campaign_endpoint():
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        payload = _parse_campaign_payload(require_name=False)
        result = preview_marketing_reactivation_campaign(
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            filters=payload.get("filters"),
            campaign_cooldown_days=payload.get("campaign_cooldown_days"),
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingReactivationValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {"status": "error", "message": "Falló el preview de la campaña."}
        ), 500


@marketing_bp.post("/reactivation/campaigns")
@jwt_required()
def create_marketing_reactivation_campaign_endpoint():
    try:
        user, access = _resolve_request_access()
        _require_campaign_management(access)
        payload = _parse_campaign_payload(require_name=True)
        result = create_marketing_reactivation_campaign(
            name=payload.get("name"),
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            filters=payload.get("filters"),
            notes=payload.get("notes"),
            created_by_user_id=int(user.id),
            campaign_cooldown_days=payload.get("campaign_cooldown_days"),
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        return jsonify({"campaign": result}), 201
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingReactivationValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except MarketingReactivationConflictError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409
    except Exception:
        db.session.rollback()
        return jsonify(
            {"status": "error", "message": "Falló la creación de la campaña."}
        ), 500


@marketing_bp.get("/reactivation/campaigns")
@jwt_required()
def list_marketing_reactivation_campaigns_endpoint():
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        raw_limit = request.args.get("limit", "50")
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise MarketingReactivationValidationError(
                "limit debe ser un entero."
            ) from exc
        return jsonify(
            list_marketing_reactivation_campaigns(
                limit=limit,
                session=db.session,
            )
        ), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingReactivationValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {"status": "error", "message": "Falló el historial de campañas."}
        ), 500


@marketing_bp.get("/reactivation/campaigns/<int:campaign_id>")
@jwt_required()
def get_marketing_reactivation_campaign_endpoint(campaign_id: int):
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        return jsonify(
            {
                "campaign": get_marketing_reactivation_campaign(
                    campaign_id=campaign_id,
                    session=db.session,
                )
            }
        ), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingReactivationNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except MarketingReactivationValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        return jsonify(
            {"status": "error", "message": "Falló el detalle de la campaña."}
        ), 500


@marketing_bp.get("/reactivation/campaigns/<int:campaign_id>/export")
@jwt_required()
def export_marketing_reactivation_campaign_endpoint(campaign_id: int):
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        file_bytes, filename = export_marketing_reactivation_campaign(
            campaign_id=campaign_id,
            allowed_sucursal_keys=_reactivation_allowed_sucursal_keys(access),
            session=db.session,
        )
        return send_file(
            BytesIO(file_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingReactivationNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except (
        MarketingReactivationConflictError,
        MarketingReactivationInvalidTransitionError,
    ) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409
    except MarketingReactivationValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        db.session.rollback()
        return jsonify(
            {"status": "error", "message": "Falló la exportación de la campaña."}
        ), 500


@marketing_bp.post("/reactivation/campaigns/<int:campaign_id>/mark-sent")
@jwt_required()
def mark_marketing_reactivation_campaign_sent_endpoint(campaign_id: int):
    try:
        _, access = _resolve_request_access()
        _require_campaign_management(access)
        result = mark_marketing_reactivation_campaign_sent(
            campaign_id=campaign_id,
            session=db.session,
        )
        return jsonify({"campaign": result}), 200
    except MarketingAuthorizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 403
    except MarketingReactivationNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except MarketingReactivationInvalidTransitionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409
    except MarketingReactivationValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        db.session.rollback()
        return jsonify(
            {"status": "error", "message": "Falló el cambio de estado de la campaña."}
        ), 500


@marketing_bp.get("/dashboard")
@jwt_required()
def get_marketing_dashboard_endpoint():
    try:
        _, access = _resolve_request_access()
        result = build_marketing_dashboard(
            month=request.args.get("month", ""),
            access=access,
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403
    except MarketingInputValidationError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": (
                    "Falló la consulta del dashboard "
                    "de Marketing y Conversión."
                ),
            }
        ), 500


@marketing_bp.get("/attributions")
@jwt_required()
def get_marketing_attributions_endpoint():
    try:
        _, access = _resolve_request_access()
        result = build_marketing_attribution_detail(
            month=request.args.get("month", ""),
            access=access,
            sucursal_id=_parse_optional_branch_id(),
        )
        return jsonify(result), 200
    except MarketingAuthorizationError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403
    except MarketingInputValidationError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": (
                    "Falló la consulta del detalle "
                    "de ventas atribuidas."
                ),
            }
        ), 500


@marketing_bp.get("/investment-detail")
@jwt_required()
def get_marketing_investment_detail_endpoint():
    try:
        _, access = _resolve_request_access()
        result = build_marketing_investment_detail(
            month=request.args.get("month", ""),
            access=access,
            sucursal_id=_parse_optional_branch_id(),
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
                    "Falló la consulta del detalle de inversión."
                ),
            }
        ), 500


@marketing_bp.get("/leads-detail")
@jwt_required()
def get_marketing_leads_detail_endpoint():
    try:
        _, access = _resolve_request_access()
        result = build_marketing_leads_detail(
            month=request.args.get("month", ""),
            access=access,
            sucursal_id=_parse_optional_branch_id(),
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
                "message": "Falló la consulta del detalle de leads.",
            }
        ), 500


@marketing_bp.get("/visitors-detail")
@jwt_required()
def get_marketing_visitors_detail_endpoint():
    try:
        _, access = _resolve_request_access()
        result = build_marketing_visitors_detail(
            month=request.args.get("month", ""),
            access=access,
            sucursal_id=_parse_optional_branch_id(),
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
                    "Falló la consulta del detalle de visitantes."
                ),
            }
        ), 500


@marketing_bp.get("/inputs")
@jwt_required()
def get_marketing_inputs_endpoint():
    try:
        _, access = _resolve_request_access()
        month_start = parse_month(
            request.args.get("month", "")
        )
        (
            _,
            branch_ids,
            scope,
        ) = load_visible_marketing_branches(access)
        rows = list_marketing_inputs(
            month_start=month_start,
            branch_ids=branch_ids,
        )
        return jsonify(
            {
                "month": month_start.strftime(
                    "%Y-%m"
                ),
                "scope": scope,
                "permissions": {
                    "can_edit_inputs": (
                        access.can_edit_inputs
                    ),
                },
                "inputs": [
                    serialize_marketing_input(row)
                    for row in rows
                ],
            }
        ), 200
    except MarketingAuthorizationError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403
    except MarketingInputValidationError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": (
                    "Falló la consulta de inputs "
                    "de Marketing."
                ),
            }
        ), 500


@marketing_bp.put("/inputs/<int:sucursal_id>")
@jwt_required()
def put_marketing_input_endpoint(
    sucursal_id: int,
):
    try:
        user, access = _resolve_request_access()
        if not access.can_edit_inputs:
            raise MarketingAuthorizationError(
                "No autorizado para editar inputs de Marketing."
            )

        (
            _,
            branch_ids,
            _,
        ) = load_visible_marketing_branches(access)
        if sucursal_id not in set(branch_ids):
            raise MarketingAuthorizationError(
                "La sucursal está fuera del alcance editable."
            )

        validated = validate_input_payload(
            request.get_json(silent=True)
        )
        row, created = upsert_marketing_input(
            sucursal_id=sucursal_id,
            user_id=int(user.id),
            **validated,
        )
        return jsonify(
            {
                "status": (
                    "created"
                    if created
                    else "updated"
                ),
                "input": serialize_marketing_input(
                    row
                ),
            }
        ), 201 if created else 200
    except MarketingAuthorizationError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403
    except MarketingInputValidationError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400
    except MarketingInputConflictError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 409
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": (
                    "Falló la escritura del input "
                    "de Marketing."
                ),
            }
        ), 500
