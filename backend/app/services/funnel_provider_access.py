"""Default-deny boundary for the external Original Funnel profile."""
from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.models.user_model import UserORM
from app.utils.scope_utils import normalize_role


PROVEEDOR_FUNNEL_ORIGINAL = "PROVEEDOR_FUNNEL_ORIGINAL"
AUTH_OPERATIONS = frozenset({
    ("POST", "auth.login"),
    ("POST", "auth.refresh_session"),
    ("POST", "auth.revoke_session"),
    ("GET", "auth.session_info"),
})
FUNNEL_OPERATION = ("GET", "marketing_sales_funnel.get_marketing_sales_funnel_endpoint")
FUNNEL_PARAMETERS = frozenset({"month", "visit_mode", "branch_ids", "cutoff_date", "cutoff_policy"})


def is_funnel_provider(user):
    return normalize_role(getattr(user, "rol", None)) == PROVEEDOR_FUNNEL_ORIGINAL


def register_funnel_provider_guard(app):
    @app.before_request
    def restrict_funnel_provider():
        # Login/refresh/logout authenticate independently (password or cookie).
        operation = (request.method, request.endpoint)
        if operation in AUTH_OPERATIONS or request.method == "OPTIONS":
            return None
        if not request.headers.get("Authorization"):
            return None  # Existing route authentication still applies.
        verify_jwt_in_request()
        user = UserORM.get_by_id(get_jwt_identity())
        if user is None:
            return jsonify({"message": "Usuario no encontrado."}), 403
        if not is_funnel_provider(user):
            return None
        if (
            operation == FUNNEL_OPERATION
            and request.args.getlist("visit_mode") == ["registered_only"]
            and set(request.args).issubset(FUNNEL_PARAMETERS)
            and all(len(request.args.getlist(key)) == 1 for key in request.args)
        ):
            return None
        return jsonify({"message": "Perfil autorizado únicamente para Funnel Original."}), 403
