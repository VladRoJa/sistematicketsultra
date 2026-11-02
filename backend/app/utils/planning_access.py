# backend/app/utils/planning_access.py

from __future__ import annotations

from flask import jsonify, current_app, has_app_context
from flask_jwt_extended import get_jwt_identity

from app.models import PlanningOperatorORM, UserORM


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


PLANNING_GRANT_FLAGS = {
    "planning.read": "PERMISSIONS_PLANNING_READ_GRANTS_ENABLED",
    "planning.edit": "PERMISSIONS_PLANNING_EDIT_GRANTS_ENABLED",
    "planning.submit": "PERMISSIONS_PLANNING_SUBMIT_GRANTS_ENABLED",
    "planning.approve": "PERMISSIONS_PLANNING_APPROVE_GRANTS_ENABLED",
    "planning.publish": "PERMISSIONS_PLANNING_PUBLISH_GRANTS_ENABLED",
    "planning.configure_model": "PERMISSIONS_PLANNING_CONFIGURE_MODEL_GRANTS_ENABLED",
}


def planning_action_grants_enabled(action_key: str) -> bool:
    flag = PLANNING_GRANT_FLAGS.get(action_key)
    return bool(
        flag and has_app_context() and current_app.config.get(flag, False) is True
    )


def _planning_action_veto(action_key: str, detail: str):
    # Solo después del operador activo y capacidad legacy del guard.
    if not planning_action_grants_enabled(action_key):
        return None
    user_id = _get_current_user_id()
    user = UserORM.get_by_id(user_id) if user_id is not None else None
    if user is None:
        return _forbidden_response(detail)
    from app.routes.permissions_catalog_routes import _simple_global_action_grant_override
    if _simple_global_action_grant_override(
        user=user, action_full_key=action_key
    ) is False:
        return _forbidden_response(detail)
    return None


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

    return _planning_action_veto("planning.read", "No tienes habilitada la consulta de Planeación Comercial.")


def require_planning_edit():
    operator = get_current_planning_operator()

    if operator is None or not operator.can_edit:
        return _forbidden_response(
            "No autorizado para editar Planeación Comercial."
        )

    return _planning_action_veto("planning.edit", "No tienes habilitada la edición de Planeación Comercial.")


def require_planning_submit():
    operator = get_current_planning_operator()

    if operator is None or not operator.can_submit:
        return _forbidden_response(
            "No autorizado para enviar metas a revisión."
        )

    return _planning_action_veto("planning.submit", "No tienes habilitado el envío de metas a revisión.")


def require_planning_approve():
    operator = get_current_planning_operator()

    if operator is None or not operator.can_approve:
        return _forbidden_response(
            "No autorizado para aprobar o rechazar metas."
        )

    return _planning_action_veto("planning.approve", "No tienes habilitada la aprobación o rechazo de metas.")


def require_planning_publish():
    operator = get_current_planning_operator()

    if operator is None or not operator.can_publish:
        return _forbidden_response(
            "No autorizado para publicar metas hacia Track."
        )

    return _planning_action_veto("planning.publish", "No tienes habilitada la publicación de metas hacia Track.")


def require_planning_model_config():
    operator = get_current_planning_operator()

    if operator is None or not operator.can_configure_model:
        return _forbidden_response(
            "No autorizado para configurar modelos de Planeación Comercial."
        )

    return _planning_action_veto("planning.configure_model", "No tienes habilitada la configuración de modelos de Planeación.")

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

    payload = {
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
    # La respuesta de capacidades de la UI no debe anunciar acciones que
    # el veto HTTP ya prohibe. El operador y sus flags siguen siendo la base.
    for action_key, capability in (
        ("planning.read", "can_view"),
        ("planning.edit", "can_edit"),
        ("planning.submit", "can_submit"),
        ("planning.approve", "can_approve"),
        ("planning.publish", "can_publish"),
        ("planning.configure_model", "can_configure_model"),
    ):
        if payload[capability] and planning_action_grants_enabled(action_key):
            payload[capability] = _planning_action_veto(
                action_key, "Acceso a Planeación restringido."
            ) is None
    payload["has_access"] = payload["can_view"]
    return payload