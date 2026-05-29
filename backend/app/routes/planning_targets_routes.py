# backend/app/routes/planning_targets_routes.py

from __future__ import annotations

from decimal import Decimal
from typing import Any

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from app.warehouse.services.planning_targets_service import (
    AddPlanningTargetBranchRowCommand,
    ApprovePlanningTargetBatchCommand,
    CreatePlanningModelConfigCommand,
    CreatePlanningTargetBatchCommand,
    PlanningTargetsServiceError,
    PublishPlanningTargetBatchCommand,
    RejectPlanningTargetBatchCommand,
    SubmitPlanningTargetBatchCommand,
    add_branch_row_to_batch,
    approve_target_batch,
    create_model_config,
    create_target_batch,
    get_batch_detail,
    get_branch_comparisons,
    get_branch_prefill,
    list_active_track_branches,
    list_model_configs,
    list_target_batches,
    publish_approved_batch_to_track,
    reject_target_batch,
    submit_target_batch,
)

from app.utils.planning_access import (
    get_current_planning_access_payload,
    require_planning_approve,
    require_planning_edit,
    require_planning_model_config,
    require_planning_operator,
    require_planning_publish,
    require_planning_submit,
)

planning_targets_bp = Blueprint(
    "planning_targets",
    __name__,
    url_prefix="/api/planning/targets",
)


def _json_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        raise PlanningTargetsServiceError(
            "El body debe ser JSON tipo objeto."
        )

    return payload


def _current_user_id_or_none() -> int | None:
    claims = get_jwt() or {}

    for key in ("user_id", "id", "sub"):
        raw_value = claims.get(key)
        if raw_value is None:
            continue

        try:
            value = int(raw_value)
        except Exception:
            continue

        if value > 0:
            return value

    return None

def _current_username_or_none() -> str | None:
    claims = get_jwt() or {}

    for key in ("username", "sub", "user"):
        raw_value = claims.get(key)
        if raw_value is None:
            continue

        normalized = str(raw_value).strip()
        if normalized:
            return normalized

    return None

def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None

    return Decimal(str(value))


def _required_decimal(payload: dict[str, Any], key: str) -> Decimal:
    if key not in payload:
        raise PlanningTargetsServiceError(
            f"El campo {key!r} es obligatorio."
        )

    return Decimal(str(payload.get(key)))


def _success(data: dict[str, Any], *, status_code: int = 200):
    return jsonify(data), status_code


def _service_error(exc: PlanningTargetsServiceError):
    return jsonify(
        {
            "status": "error",
            "error": str(exc),
        }
    ), 400

@planning_targets_bp.route("/access", methods=["GET"])
@jwt_required()
def get_planning_access_route():
    return _success(get_current_planning_access_payload())

@planning_targets_bp.route("/branches", methods=["GET"])
@jwt_required()
def list_active_track_branches_route():
    try:
        access_error = _guard(require_planning_operator)
        if access_error:
            return access_error

        result = list_active_track_branches()
        return _success(result)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)

@planning_targets_bp.route(
    "/branches/<string:sucursal_canon>/prefill",
    methods=["GET"],
)
@jwt_required()
def get_branch_prefill_route(sucursal_canon: str):
    try:
        access_error = _guard(require_planning_operator)
        if access_error:
            return access_error

        result = get_branch_prefill(
            sucursal_canon=sucursal_canon,
            target_month=request.args.get("target_month"),
        )
        return _success(result)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)

@planning_targets_bp.route(
    "/branches/<string:sucursal_canon>/comparisons",
    methods=["GET"],
)
@jwt_required()
def get_branch_comparisons_route(sucursal_canon: str):
    try:
        access_error = _guard(require_planning_operator)
        if access_error:
            return access_error

        result = get_branch_comparisons(
            sucursal_canon=sucursal_canon,
            target_month=request.args.get("target_month"),
        )
        return _success(result)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)

def _guard(access_check):
    access_error = access_check()
    if access_error is not None:
        return access_error

    return None

@planning_targets_bp.route("/model-configs", methods=["GET"])
@jwt_required()
def list_model_configs_route():
    try:
        access_error = _guard(require_planning_operator)
        if access_error:
            return access_error

        result = list_model_configs(
            status=request.args.get("status"),
        )
        return _success(result)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)

@planning_targets_bp.route("/model-configs", methods=["POST"])
@jwt_required()
def create_model_config_route():
    try:
        access_error = _guard(require_planning_model_config)
        if access_error:
            return access_error
        payload = _json_payload()

        result = create_model_config(
            CreatePlanningModelConfigCommand(
                name=payload.get("name"),
                version=payload.get("version"),
                created_by_user_id=_current_user_id_or_none(),
                description=payload.get("description"),
                trend_window_months=payload.get("trend_window_months", 3),
                trend_closed_months_only=payload.get(
                    "trend_closed_months_only",
                    True,
                ),
                arpu_strategy=payload.get("arpu_strategy", "PROMEDIO_3M"),
                bajas_strategy=payload.get(
                    "bajas_strategy",
                    "PROMEDIO_HISTORICO_SUCURSAL",
                ),
                reactivaciones_strategy=payload.get(
                    "reactivaciones_strategy",
                    "PROMEDIO_HISTORICO_SUCURSAL",
                ),
                domiciliados_strategy=payload.get(
                    "domiciliados_strategy",
                    "PORCENTAJE_CLIENTES_NUEVOS",
                ),
                aggregators_strategy=payload.get(
                    "aggregators_strategy",
                    "SEPARADAS_SOLO_INGRESO",
                ),
                new_branch_strategy=payload.get(
                    "new_branch_strategy",
                    "PROMEDIO_REGIONAL",
                ),
                risk_rules_json=payload.get("risk_rules_json"),
                parameters_json=payload.get("parameters_json"),
                notes=payload.get("notes"),
            )
        )

        return _success(result, status_code=201)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)

@planning_targets_bp.route(
    "/batches/<int:batch_id>/approve",
    methods=["POST"],
)
@jwt_required()
def approve_target_batch_route(batch_id: int):
    access_error = _guard(require_planning_submit)
    if access_error:
        return access_error    
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}

        if not isinstance(payload, dict):
            raise PlanningTargetsServiceError(
                "El body debe ser JSON tipo objeto."
            )

        result = approve_target_batch(
            ApprovePlanningTargetBatchCommand(
                batch_id=batch_id,
                approved_by_user_id=_current_user_id_or_none(),
                actor_username_snapshot=_current_username_or_none(),
                comment=payload.get("comment"),
            )
        )

        return _success(result)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)


@planning_targets_bp.route(
    "/batches/<int:batch_id>/reject",
    methods=["POST"],
)
@jwt_required()
def reject_target_batch_route(batch_id: int):
    access_error = _guard(require_planning_submit)
    if access_error:
        return access_error    
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}

        if not isinstance(payload, dict):
            raise PlanningTargetsServiceError(
                "El body debe ser JSON tipo objeto."
            )

        result = reject_target_batch(
            RejectPlanningTargetBatchCommand(
                batch_id=batch_id,
                rejected_by_user_id=_current_user_id_or_none(),
                actor_username_snapshot=_current_username_or_none(),
                comment=payload.get("comment"),
            )
        )

        return _success(result)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)

@planning_targets_bp.route(
    "/batches/<int:batch_id>/publish",
    methods=["POST"],
)
@jwt_required()
def publish_approved_batch_to_track_route(batch_id: int):
    access_error = _guard(require_planning_submit)
    if access_error:
        return access_error
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}

        if not isinstance(payload, dict):
            raise PlanningTargetsServiceError(
                "El body debe ser JSON tipo objeto."
            )

        result = publish_approved_batch_to_track(
            PublishPlanningTargetBatchCommand(
                batch_id=batch_id,
                published_by_user_id=_current_user_id_or_none(),
                actor_username_snapshot=_current_username_or_none(),
                comment=payload.get("comment"),
            )
        )

        return _success(result)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)

@planning_targets_bp.route("/batches", methods=["GET"])
@jwt_required()
def list_target_batches_route():
    try:
        access_error = _guard(require_planning_model_config)
        if access_error:
            return access_error        
        result = list_target_batches(
            target_month=request.args.get("target_month"),
            status=request.args.get("status"),
        )
        return _success(result)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)

@planning_targets_bp.route("/batches", methods=["POST"])
@jwt_required()
def create_target_batch_route():
    access_error = _guard(require_planning_model_config)
    if access_error:
        return access_error

    try:
        payload = _json_payload()

        result = create_target_batch(
            CreatePlanningTargetBatchCommand(
                target_month=payload.get("target_month"),
                version=payload.get("version"),
                created_by_user_id=_current_user_id_or_none(),
                model_config_id=payload.get("model_config_id"),
                source_upload_id=payload.get("source_upload_id"),
                scope=payload.get("scope", "MONTHLY_BATCH"),
                source_type=payload.get("source_type", "MANUAL"),
                scenario_base=payload.get("scenario_base"),
                notes=payload.get("notes"),
            )
        )

        return _success(result, status_code=201)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)


@planning_targets_bp.route(
    "/batches/<int:batch_id>/branch-rows",
    methods=["POST"],
)
@jwt_required()
def add_branch_row_to_batch_route(batch_id: int):
    access_error = _guard(require_planning_model_config)
    if access_error:
        return access_error
    try:
        payload = _json_payload()

        result = add_branch_row_to_batch(
            AddPlanningTargetBranchRowCommand(
                batch_id=batch_id,
                sucursal_canon=payload.get("sucursal_canon"),
                m2_sin_circulaciones=_required_decimal(
                    payload,
                    "m2_sin_circulaciones",
                ),
                usuarios_inicio_mes=payload.get("usuarios_inicio_mes"),
                proyeccion_usuarios_cierre_mes=payload.get(
                    "proyeccion_usuarios_cierre_mes"
                ),
                meta_faycgo_mes=_required_decimal(
                    payload,
                    "meta_faycgo_mes",
                ),
                meta_clientes_nuevos_mes=payload.get(
                    "meta_clientes_nuevos_mes"
                ),
                meta_reactivaciones_mes=payload.get(
                    "meta_reactivaciones_mes"
                ),
                meta_bajas_mes=payload.get("meta_bajas_mes"),
                meta_nuevos_domiciliados_mes=payload.get(
                    "meta_nuevos_domiciliados_mes"
                ),
                meta_arpu_mes=_required_decimal(
                    payload,
                    "meta_arpu_mes",
                ),
                meta_venta_tienda_mes=_required_decimal(
                    payload,
                    "meta_venta_tienda_mes",
                ),
                ingreso_agregadoras_estimado=_optional_decimal(
                    payload.get("ingreso_agregadoras_estimado")
                ),
                usuarios_agregadoras_estimado=payload.get(
                    "usuarios_agregadoras_estimado"
                ),
                scenario_used=payload.get("scenario_used"),
                trend_classification=payload.get("trend_classification"),
                risk_level=payload.get("risk_level"),
                status=payload.get("status", "PROPUESTA"),
                previous_branch_row_id=payload.get("previous_branch_row_id"),
                notes=payload.get("notes"),
            )
        )

        return _success(result, status_code=201)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)

@planning_targets_bp.route(
    "/batches/<int:batch_id>/submit",
    methods=["POST"],
)
@jwt_required()
def submit_target_batch_route(batch_id: int):
    access_error = _guard(require_planning_submit)
    if access_error:
        return access_error    
    
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}

        if not isinstance(payload, dict):
            raise PlanningTargetsServiceError(
                "El body debe ser JSON tipo objeto."
            )

        result = submit_target_batch(
            SubmitPlanningTargetBatchCommand(
                batch_id=batch_id,
                submitted_by_user_id=_current_user_id_or_none(),
                actor_username_snapshot=_current_username_or_none(),
                comment=payload.get("comment"),
            )
        )

        return _success(result)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)

@planning_targets_bp.route("/batches/<int:batch_id>", methods=["GET"])
@jwt_required()
def get_batch_detail_route(batch_id: int):
    access_error = _guard(require_planning_submit)
    if access_error:
        return access_error
    try:
        result = get_batch_detail(batch_id)
        return _success(result)

    except PlanningTargetsServiceError as exc:
        return _service_error(exc)