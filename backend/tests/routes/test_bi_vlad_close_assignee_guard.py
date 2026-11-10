"""BI Vlad: the requester may validate a delivered ticket, but may not work/close it."""
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.routes import ticket_routes


def _user(name="EDEMUNDO", role="GERENTE_REGIONAL", branch=100):
    return SimpleNamespace(
        username=name, rol=role, sucursal_id=branch, department_id=7
    )


def _ticket(department="BI Vlad", assigned="ADMICORP", creator="EDEMUNDO"):
    return SimpleNamespace(
        id=3381,
        username=creator,
        departamento=SimpleNamespace(nombre=department),
        departamento_id=42,
        asignado_a=assigned,
        estado="en progreso",
        costo_solucion=None,
        notas_cierre=None,
        solicitar_cierre=MagicMock(),
    )


def test_assignee_only_guard_keeps_legacy_departments_untouched():
    ticket = _ticket()
    assert not ticket_routes._puede_gestionar_bi_vlad(_user(), ticket)
    assert not ticket_routes._puede_gestionar_bi_vlad(
        _user("OTHER_ADMIN", "ADMINISTRADOR", 1000), ticket
    )
    assert ticket_routes._puede_gestionar_bi_vlad(
        _user("admicorp", "ADMINISTRADOR", 1000), ticket
    )
    ticket.asignado_a = None
    assert not ticket_routes._puede_gestionar_bi_vlad(
        _user("ADMICORP", "ADMINISTRADOR", 1000), ticket
    )
    ticket.departamento.nombre = "Sistemas"
    assert ticket_routes._puede_gestionar_bi_vlad(_user(), ticket)


@pytest.mark.parametrize("endpoint,route,method", [
    ("update_ticket_status", "/api/tickets/update/3381", "PUT"),
    ("set_compromiso", "/api/tickets/compromiso/3381", "PUT"),
    ("cierre_solicitar", "/api/tickets/cierre/solicitar/3381", "POST"),
    ("cierre_rechazar_jefe", "/api/tickets/cierre/rechazar-jefe/3381", "POST"),
    ("cierre_gerente_desde_cero", "/api/tickets/cierre/gerente-desde-cero/3381", "POST"),
])
def test_regional_cannot_manage_bi_vlad_even_by_direct_endpoint(endpoint, route, method):
    app = Flask(__name__)
    ticket = _ticket()
    payload = {
        "estado": "en progreso",
        "notas_cierre": "Pretendo cerrar antes de que se atienda",
        "fecha_solucion": "2026-11-30T09:00:00Z",
        "motivo": "Limpieza",
    }
    with app.test_request_context(route, method=method, json=payload), patch.object(
        ticket_routes.UserORM, "get_by_id", return_value=_user()
    ), patch.object(ticket_routes, "get_jwt_identity", return_value="88"), patch.object(
        ticket_routes, "Ticket"
    ) as model, patch.object(
        ticket_routes, "filtrar_tickets_por_usuario"
    ) as scope:
        model.query.get.return_value = ticket
        scope.return_value.filter.return_value.first.return_value = ticket
        result = inspect.unwrap(getattr(ticket_routes, endpoint))(3381)
        assert result[1] == 403, (endpoint, result)
        assert "responsable" in result[0].get_json()["mensaje"].lower()
        ticket.solicitar_cierre.assert_not_called()


def test_admicorp_can_request_closure_of_bi_vlad_ticket():
    app = Flask(__name__)
    ticket = _ticket()
    with app.test_request_context(
        "/api/tickets/cierre/solicitar/3381",
        method="POST",
        json={"costo_solucion": None, "notas_cierre": "Trabajo completado"},
    ), patch.object(
        ticket_routes.UserORM, "get_by_id",
        return_value=_user("ADMICORP", "ADMINISTRADOR", 1000),
    ), patch.object(
        ticket_routes, "get_jwt_identity", return_value="47",
    ), patch.object(ticket_routes, "Ticket") as model, patch.object(
        ticket_routes, "validar_recepcion_completa",
    ), patch.object(
        ticket_routes, "_notificar_evento_ticket", return_value=[],
    ):
        model.query.get.return_value = ticket
        response, status = inspect.unwrap(ticket_routes.cierre_solicitar)(3381)
        assert status == 200
        assert "pendiente" in response.get_json()["mensaje"]
        ticket.solicitar_cierre.assert_called_once()


def test_requester_still_may_approve_or_reject_conformity():
    ticket = _ticket()
    ticket.estado = "por_validar"
    ticket.estado_cierre = "pendiente_creador"
    assert ticket_routes._puede_validar_cierre_gerente(_user(), ticket)
    assert not ticket_routes._puede_gestionar_bi_vlad(_user(), ticket)
