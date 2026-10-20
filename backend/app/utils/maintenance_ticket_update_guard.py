from __future__ import annotations

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.models.ticket_model import Ticket
from app.models.user_model import UserORM
from app.utils.pm_permissions import can_pm_execute
from app.utils.maintenance_regional_lead import (
    is_regional_maintenance_lead,
    regional_maintenance_lead_owns_ticket,
)
from app.utils.tickets_maintenance_permissions import (
    has_assigned_only_maintenance_scope,
    has_maintenance_coordination_permission,
)


MAINTENANCE_DEPARTMENT_ID = 1
GENERIC_TICKET_UPDATE_ENDPOINT = "tickets.update_ticket_status"

# Algunas rutas legacy permiten acciones a cuentas corporativas por sucursal
# principal. Compras y coordinacion no heredan ejecucion tecnica.
COMPRAS_MAINTENANCE_MUTATION_ENDPOINTS = frozenset({
    "tickets.update_ticket_status",
    "tickets.set_compromiso",
    "tickets.cierre_gerente_desde_cero",
    "tickets.cierre_solicitar",
    "tickets.cierre_rechazar_jefe",
    "tickets.cierre_aceptar_creador",
    "tickets.cierre_rechazar_creador",
    "tickets.notify_ticket",
})

# Estas rutas aceptan un ticket_id por URL y pueden mutar el ticket.
# El filtro assigned-only debe aplicarse también aquí, no solo en GET/list.
ASSIGNED_ONLY_MAINTENANCE_MUTATION_ENDPOINTS = (
    COMPRAS_MAINTENANCE_MUTATION_ENDPOINTS
    | frozenset({
        "tickets.coordinate_maintenance_ticket",
        "tickets.reassign_maintenance_ticket",
        "tickets.maintenance_mark_work_completed",
        "maintenance_planner.put_schedule",
        "mantenimiento_equipos.guardar_compromiso_estructurado",
    })
)


def assigned_only_maintenance_mutation_forbidden(user, ticket) -> bool:
    if not is_maintenance_ticket(ticket) or not has_assigned_only_maintenance_scope(user):
        return False
    return (
        str(getattr(ticket, "asignado_a", "") or "").strip().casefold()
        != str(getattr(user, "username", "") or "").strip().casefold()
    )


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
    def guard_regional_maintenance_lead_ticket_mutations():
        """La cuenta 45 no puede mutar tickets ajenos a sus sucursales."""
        endpoint = request.endpoint or ""
        if (
            request.method not in {"POST", "PUT", "PATCH", "DELETE"}
            or not (
                endpoint.startswith("tickets.")
                or endpoint == "maintenance_planner.put_schedule"
                or endpoint == "mantenimiento_equipos.guardar_compromiso_estructurado"
            )
        ):
            return None

        ticket_args = request.view_args or {}
        ticket_id = ticket_args.get("ticket_id", ticket_args.get("id"))
        if ticket_id is None:
            return None
        verify_jwt_in_request()
        actor = UserORM.get_by_id(get_jwt_identity())
        if not is_regional_maintenance_lead(actor):
            return None
        ticket = Ticket.query.get(ticket_id)
        if ticket is None:
            return None
        if not regional_maintenance_lead_owns_ticket(actor, ticket):
            return jsonify({
                "mensaje": "Ticket fuera de las sucursales autorizadas de Mantenimiento."
            }), 403
        return None

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

    @app.before_request
    def guard_assigned_only_maintenance_mutations():
        if (
            request.method not in {"POST", "PUT", "PATCH", "DELETE"}
            or request.endpoint not in ASSIGNED_ONLY_MAINTENANCE_MUTATION_ENDPOINTS
        ):
            return None

        verify_jwt_in_request()
        actor = UserORM.get_by_id(get_jwt_identity())
        if actor is None or not has_assigned_only_maintenance_scope(actor):
            return None

        route_args = request.view_args or {}
        ticket_id = route_args.get("ticket_id", route_args.get("id"))
        if ticket_id is None:
            return None

        ticket = Ticket.query.get(ticket_id)
        if ticket is None:
            return None

        if assigned_only_maintenance_mutation_forbidden(actor, ticket):
            return jsonify({
                "mensaje": (
                    "Este usuario solo puede modificar tickets de "
                    "Mantenimiento que tenga asignados."
                ),
            }), 403

        return None

    @app.before_request
    def guard_technical_commitment_changes():
        """Impedir cambios de fecha por rutas Tickets legacy sin bloquear ejecución PM.

        El Planner protege su propia ruta en schedule_ticket(). Aquí protegemos
        PUT /tickets/update y PUT /tickets/compromiso, que antes aceptaban
        cambios de compromiso de personal técnico con can_pm_execute.
        """
        if request.method != "PUT" or request.endpoint not in {
            "tickets.update_ticket_status", "tickets.set_compromiso",
        }:
            return None

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return None

        # La ruta update admite historial del cliente; no permitir inyectar
        # historial de cambios de fecha sin autoridad de coordinación.
        if request.endpoint == "tickets.update_ticket_status":
            changing_date = bool(data.get("fecha_solucion")) or bool(
                data.get("historial_fechas")
            )
        else:
            changing_date = bool(data.get("fecha_solucion"))
        if not changing_date:
            return None

        verify_jwt_in_request()
        actor = UserORM.get_by_id(get_jwt_identity())
        if actor is None or has_maintenance_coordination_permission(actor):
            return None

        ticket_id = (request.view_args or {}).get(
            "ticket_id", (request.view_args or {}).get("id")
        )
        if ticket_id is None:
            return None
        ticket = Ticket.query.get(ticket_id)
        if ticket is None or not is_maintenance_ticket(ticket):
            return None

        # Programación tradicional del jefe, solo en sus 14 sucursales.
        if regional_maintenance_lead_owns_ticket(actor, ticket):
            return None

        return jsonify({
            "mensaje": (
                "La fecha compromiso de Mantenimiento solo puede ser "
                "asignada o reprogramada por coordinación autorizada."
            ),
        }), 403

    @app.before_request
    def guard_compras_maintenance_mutations():
        if (
            request.method not in {"POST", "PUT", "PATCH", "DELETE"}
            or request.endpoint not in COMPRAS_MAINTENANCE_MUTATION_ENDPOINTS
        ):
            return None

        verify_jwt_in_request()
        actor = UserORM.get_by_id(get_jwt_identity())
        if (
            actor is None
            or str(getattr(actor, "rol", "") or "").strip().upper() not in {
                "COMPRAS", "COORDINADOR_MANTENIMIENTO"
            }
        ):
            return None

        route_args = request.view_args or {}
        ticket_id = route_args.get("ticket_id", route_args.get("id"))
        if ticket_id is None:
            return None

        ticket = Ticket.query.get(ticket_id)
        if ticket is None or not is_maintenance_ticket(ticket):
            return None

        # Excepción estrictamente para la solicitud de conformidad de
        # Mantenimiento: una coordinación explícitamente autorizada puede
        # entrar al endpoint, que vuelve a validar sucursal, estado,
        # terminación técnica y notas obligatorias.
        # El permiso PM de lectura por sí solo NO habilita escrituras.
        if (
            request.endpoint == "tickets.cierre_solicitar"
            and has_maintenance_coordination_permission(actor)
        ):
            return None

        role = str(getattr(actor, "rol", "") or "").strip().upper()
        mensaje = (
            "Compras tiene acceso de consulta a Mantenimiento; "
            "no puede ejecutar cambios, cierres ni notificaciones."
            if role == "COMPRAS"
            else (
                "La coordinación de Mantenimiento no puede ejecutar "
                "acciones técnicas, validar conformidad ni notificar por esta ruta."
            )
        )
        return jsonify({"mensaje": mensaje}), 403
