"""Visibility of Tickets is not a grant to perform operational transitions.

HTTP-level, synthetic JWT tests; no production services or DB writes.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import ticket_routes


def _user(role="GERENTE_REGIONAL", name="EDEMUNDO"):
    return SimpleNamespace(
        id=88, username=name, rol=role, sucursal_id=100,
        sucursales_ids=[4, 5, 21], department_id=7,
    )


def _ticket():
    return SimpleNamespace(
        id=3377, estado="abierto", departamento_id=7,
        departamento=SimpleNamespace(nombre="Sistemas"),
        username="EDEMUNDO", asignado_a="SOPORTE_SISTEMAS",
    )


class _VisibleQuery:
    def __init__(self, ticket):
        self.ticket = ticket
        self.first_called = False

    def filter(self, *_args):
        return self

    def first(self):
        self.first_called = True
        return self.ticket


def _client(*, flag=False):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="tickets-regional-qa-only",
        PERMISSIONS_TICKETS_UPDATE_STATUS_GRANTS_ENABLED=flag,
        PERMISSIONS_TICKETS_UPDATE_GRANTS_ENABLED=flag,
        PERMISSIONS_TICKETS_CLOSE_GRANTS_ENABLED=flag,
    )
    JWTManager(app)
    app.register_blueprint(ticket_routes.ticket_bp)
    with app.app_context():
        token = create_access_token(identity="88")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


OPERATIONS = [
    ("PUT", "/api/tickets/update/3377", {
        "estado": "en progreso", "fecha_solucion": "2026-11-21T12:00:00Z",
    }),
    ("PUT", "/api/tickets/compromiso/3377", {
        "fecha_solucion": "2026-11-21T12:00:00Z",
    }),
    ("POST", "/api/tickets/cierre/solicitar/3377", {
        "notas_cierre": "Trabajo completado",
    }),
    ("POST", "/api/tickets/cierre/rechazar-jefe/3377", {
        "motivo": "Devolver al solicitante",
    }),
]


@pytest.mark.parametrize("flag", (False, True))
@pytest.mark.parametrize("method,url,payload", OPERATIONS)
def test_regional_read_scope_never_grants_operational_mutation(
    flag, method, url, payload,
):
    api, headers = _client(flag=flag)
    ticket = _ticket()
    visible = _VisibleQuery(ticket)
    with api.application.app_context(), patch.object(
        ticket_routes.UserORM, "get_by_id", return_value=_user()
    ), patch.object(
        ticket_routes.Ticket, "query", SimpleNamespace(get=Mock(return_value=ticket))
    ), patch.object(
        ticket_routes, "filtrar_tickets_por_usuario", return_value=visible
    ), patch.object(
        ticket_routes, "_ticket_action_grant_denied", return_value=False
    ), patch.object(
        ticket_routes.db.session, "commit"
    ) as commit:
        res = api.open(url, method=method, headers=headers, json=payload)

    assert res.status_code == 403
    assert "regional" in res.json["mensaje"].lower()
    commit.assert_not_called()
    if url.startswith("/api/tickets/update/"):
        assert visible.first_called, "The ticket was visible; only execution is denied"


@pytest.mark.parametrize("role", ["ADMINISTRADOR", "SISTEMAS", "GERENTE"])
@pytest.mark.parametrize("method,url,payload", OPERATIONS)
def test_existing_nonregional_routes_retain_their_guards(
    role, method, url, payload,
):
    api, headers = _client()
    with api.application.app_context(), patch.object(
        ticket_routes.UserORM, "get_by_id", return_value=_user(role)
    ), patch.object(
        ticket_routes.Ticket, "query", SimpleNamespace(get=Mock(return_value=None))
    ), patch.object(
        ticket_routes, "_ticket_action_grant_denied", return_value=False
    ):
        res = api.open(url, method=method, headers=headers, json=payload)
    # The regional-only guard must not deny valid roles before normal resource checks.
    assert res.status_code == 404


def test_regional_requester_keeps_nonmaintenance_creator_conformity():
    ticket = _ticket()
    assert ticket_routes._puede_validar_cierre_gerente(_user(), ticket)
    assert not ticket_routes._es_gerente_regional(_user("ADMINISTRADOR"))
