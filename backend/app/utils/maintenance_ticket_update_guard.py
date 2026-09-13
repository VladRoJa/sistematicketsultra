from __future__ import annotations

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.models.ticket_model import Ticket
from app.models.user_model import UserORM
from app.utils.pm_permissions import can_pm_execute


MAINTENANCE_DEPARTMENT_ID = 1
GENERIC_TICKET_UPDATE_ENDPOINT = "tickets.update_ticket_status"


def is_maintenance_ticket(ticket) -> bool:
    """Return True only for tickets owned by Mantenimiento."""

    try:
        return int(getattr(ticket, "departamento_id", 0) or 0) == MAINTENANCE_DEPARTMENT_ID
    except (TypeError, ValueError):
        return False


def generic_pm_update_is_forbidden(user, ticket) -> bool:
    """Protect PM execution semantics from the generic Tickets update route.

    Visibility and execution are intentionally different permissions in Suite Ultra.
    GERENTE / GERENTE_REGIONAL may see PM tickets in their scope, but that must not
    grant permission to change state, commitment dates or history through the generic
    ``PUT /api/tickets/update/:id`` endpoint.
    """

    return is_maintenance_ticket(ticket) and not can_pm_execute(user)


def register_maintenance_ticket_update_guard(app) -> None:
    """Register the backend authorization boundary for generic PM mutations.

    The legacy Tickets update endpoint remains available for non-PM tickets. For PM
    tickets, actors must satisfy the canonical ``can_pm_execute`` policy; the route's
    own visibility/scope validation still runs afterwards for allowed actors.
    """

    @app.before_request
    def guard_generic_maintenance_ticket_update():
        if (
            request.method != "PUT"
            or request.endpoint != GENERIC_TICKET_UPDATE_ENDPOINT
        ):
            return None

        # This guard runs before the route decorators, so establish the same JWT
        # boundary before reading the current identity.
        verify_jwt_in_request()

        actor = UserORM.get_by_id(get_jwt_identity())
        if actor is None:
            # Preserve the route's existing user-not-found behavior.
            return None

        ticket_id = (request.view_args or {}).get("id")
        if ticket_id is None:
            return None

        ticket = Ticket.query.get(ticket_id)
        if ticket is None:
            # Preserve the route's existing 404 behavior.
            return None

        if not generic_pm_update_is_forbidden(actor, ticket):
            return None

        return (
            jsonify(
                {
                    "mensaje": (
                        "No tienes permiso para ejecutar cambios operativos de "
                        "Mantenimiento. Usa el flujo autorizado de Mantenimiento."
                    )
                }
            ),
            403,
        )
