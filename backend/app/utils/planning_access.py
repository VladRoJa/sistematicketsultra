# backend/app/utils/planning_access.py

from __future__ import annotations

from flask import jsonify
from flask_jwt_extended import get_jwt_identity

from app.models import PlanningOperatorORM


def _get_current_user_id() -> int | None:
    current_user_id = get_jwt_identity()

    if current_user_id is None:
        return None

    try:
        normalized_user_id = int(current_user_id)
    except (TypeError, ValueError):
        return None

    if normalized_user_id <= 0:
        return None

    return normalized_user_id


def get_current_planning_operator() -> PlanningOperatorORM | None:
    """
    Devuelve el operador activo de Planeación Comercial para el usuario actual.

    Debe usarse dentro de rutas protegidas con @jwt_required().
    """
    current_user_id = _get_current_user_id()

    if current_user_id is None:
        return None

    return PlanningOperatorORM.query.filter_by(
        user_id=current_user_id,
        is_active=True,
    ).first()


def is_current_user_planning_operator() -> bool:
    return get_current_planning_operator() is not None


def _forbidden_response(detail: str):
    return jsonify(
        {
            "error": "Forbidden",
            "detail": detail,
        }
    ), 403


def require_planning_operator():
    """
    Valida acceso base al módulo de Planeación Comercial.

    Permite entrar si el usuario está activo en planning_operators
    y tiene can_view=True.
    """
    operator = get_current_planning_operator()

    if operator is None or not operator.can_view:
        return _forbidden_response(
            "No autorizado para acceder a Planeación Comercial."
        )

    return None


def require_planning_edit():
    operator = get_current_planning_operator()

    if operator is None or not operator.can_edit:
        return _forbidden_response(
            "No autorizado para editar Planeación Comercial."
        )

    return None


def require_planning_submit():
    operator = get_current_planning_operator()

    if operator is None or not operator.can_submit:
        return _forbidden_response(
            "No autorizado para enviar metas a revisión."
        )

    return None


def require_planning_approve():
    operator = get_current_planning_operator()

    if operator is None or not operator.can_approve:
        return _forbidden_response(
            "No autorizado para aprobar o rechazar metas."
        )

    return None


def require_planning_publish():
    operator = get_current_planning_operator()

    if operator is None or not operator.can_publish:
        return _forbidden_response(
            "No autorizado para publicar metas hacia Track."
        )

    return None


def require_planning_model_config():
    operator = get_current_planning_operator()

    if operator is None or not operator.can_configure_model:
        return _forbidden_response(
            "No autorizado para configurar modelos de Planeación Comercial."
        )

    return None

def get_current_planning_access_payload() -> dict:
    operator = get_current_planning_operator()

    if operator is None:
        return {
            "status": "ok",
            "has_access": False,
            "can_view": False,
            "can_edit": False,
            "can_submit": False,
            "can_approve": False,
            "can_publish": False,
            "can_configure_model": False,
        }

    return {
        "status": "ok",
        "has_access": bool(operator.is_active and operator.can_view),
        "can_view": bool(operator.is_active and operator.can_view),
        "can_edit": bool(operator.is_active and operator.can_edit),
        "can_submit": bool(operator.is_active and operator.can_submit),
        "can_approve": bool(operator.is_active and operator.can_approve),
        "can_publish": bool(operator.is_active and operator.can_publish),
        "can_configure_model": bool(
            operator.is_active and operator.can_configure_model
        ),
    }