"""QA sintético HTTP de Tickets V1 Mantenimiento.

Estos usuarios y tickets existen únicamente en memoria dentro del test;
no utilizan el ticket #3011 ni bases de datos de producción.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy import Integer, column

from app.routes import ticket_routes
from app.services import ticket_maintenance_coordination_service as coordination


class SyntheticTicketQuery:
    def __init__(self, store):
        self.store = store

    def get(self, ticket_id):
        return self.store.get(int(ticket_id))

    def filter(self, *_expressions):
        return self

    def first(self):
        return next(iter(self.store.values()), None)


class SyntheticTicket:
    id = column("id", Integer)
    departamento_id = column("departamento_id", Integer)

    def __init__(self, ticket_id: int, mode: str):
        self.id = ticket_id
        self.departamento_id = 1
        self.sucursal_id = 8
        self.sucursal_id_destino = 8
        self.username = "QA_SOLICITANTE"
        self.estado = "en progreso"
        self.tipo_atencion = mode
        self.asignado_a = "QA_TECNICO" if mode == "INTERNA" else None
        self.estado_cierre = None
        self.fecha_finalizado = None
        self.fecha_solucion = datetime(2026, 10, 25, tzinfo=timezone.utc)
        self.costo_solucion = Decimal("275.00")
        self.notas_cierre = None
        self.historial_fechas = []
        self.motivo_rechazo_cierre = None

    def solicitar_cierre(self):
        assert self.estado == "en progreso"
        self.estado = "por_validar"
        self.estado_cierre = "pendiente_creador"
        self.fecha_finalizado = datetime.now(timezone.utc)

    def aceptar_conformidad_creador(self, commit=True):
        assert self.estado == "por_validar"
        self.estado = "finalizado"
        self.estado_cierre = None

    def to_dict(self):
        return {
            "id": self.id,
            "estado": self.estado,
            "estado_cierre": self.estado_cierre,
            "tipo_atencion": self.tipo_atencion,
            "asignado_a": self.asignado_a,
        }


@pytest.fixture
def qa_http(monkeypatch):
    users = {
        91001: SimpleNamespace(
            id=91001, username="QA_TECNICO", rol="SR_MANTENIMIENTO",
            department_id=1, sucursal_id=8, sucursales_ids=[8],
        ),
        91002: SimpleNamespace(
            id=91002, username="QA_YULIANA", rol="COMPRAS",
            department_id=6, sucursal_id=100, sucursales_ids=[8],
        ),
        91003: SimpleNamespace(
            id=91003, username="QA_GERENTE", rol="GERENTE",
            department_id=2, sucursal_id=8, sucursales_ids=[8],
        ),
        91004: SimpleNamespace(
            id=91004, username="QA_SOLICITANTE", rol="RECEPCIONISTA",
            department_id=3, sucursal_id=8, sucursales_ids=[8],
        ),
        91005: SimpleNamespace(
            id=91005, username="QA_OTRO_GERENTE", rol="GERENTE",
            department_id=2, sucursal_id=9, sucursales_ids=[9],
        ),
    }

    ticket = SyntheticTicket(990001, "INTERNA")
    query = SyntheticTicketQuery({ticket.id: ticket})
    monkeypatch.setattr(SyntheticTicket, "query", query, raising=False)
    monkeypatch.setattr(ticket_routes, "Ticket", SyntheticTicket)
    monkeypatch.setattr(coordination, "Ticket", SyntheticTicket)
    monkeypatch.setattr(
        ticket_routes.UserORM, "get_by_id", lambda ident: users.get(int(ident)),
    )
    monkeypatch.setattr(
        ticket_routes, "has_maintenance_coordination_permission",
        lambda user: user.username == "QA_YULIANA",
    )
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission",
        lambda user: user.username == "QA_YULIANA",
    )

    class ScopedQuery:
        def __init__(self, actor):
            self.actor = actor

        def filter(self, *_conditions):
            return self

        def first(self):
            return (
                ticket
                if ticket.sucursal_id_destino in self.actor.sucursales_ids
                else None
            )

    monkeypatch.setattr(
        ticket_routes, "filtrar_tickets_por_usuario",
        lambda actor: ScopedQuery(actor),
    )
    monkeypatch.setattr(coordination, "flag_modified", lambda *_args: None)
    monkeypatch.setattr(ticket_routes, "flag_modified", lambda *_args: None)
    monkeypatch.setattr(ticket_routes, "_notificar_evento_ticket", lambda **_kwargs: [])
    monkeypatch.setattr(
        ticket_routes, "schedule_ticket_attachment_retention",
        lambda **_kwargs: None,
    )

    commit = Mock()
    session = SimpleNamespace(commit=commit, rollback=Mock())
    monkeypatch.setattr(ticket_routes, "db", SimpleNamespace(session=session))

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="synthetic-maintenance-qa-only",
    )
    JWTManager(app)
    app.register_blueprint(ticket_routes.ticket_bp)

    def post(actor_id, route, payload=None):
        with app.app_context():
            token = create_access_token(identity=str(actor_id))
        return app.test_client().post(
            f"/api/tickets/{route}",
            json=payload or {},
            headers={"Authorization": f"Bearer {token}"},
        )

    return ticket, post, commit


def test_qa_flujo_interno_devolucion_revision_y_conformidad(qa_http):
    ticket, post, commit = qa_http
    close = "cierre/solicitar/990001"
    work = "maintenance/990001/work-completed"
    returned = "maintenance/990001/return-to-technician"
    approve = "cierre/aceptar-creador/990001"

    # El técnico y la coordinadora no pueden omitir la revisión técnica.
    assert post(91001, close, {"notas_cierre": "Intento técnico"}).status_code == 403
    assert post(91002, close, {"notas_cierre": "Sin técnico"}).status_code == 409

    assert post(91001, work, {"notas_trabajo": "Reparación hecha"}).status_code == 200
    assert ticket.estado == "en progreso"
    assert ticket.estado_cierre == "pendiente_revision_coord"
    assert commit.call_count == 1

    assert post(91002, returned, {"motivo": "Faltó fijar la cubierta"}).status_code == 200
    assert ticket.estado_cierre is None
    assert post(91001, work, {"notas_trabajo": "Cubierta instalada"}).status_code == 200

    response = post(91002, close, {"notas_cierre": "Trabajo revisado y correcto"})
    assert response.status_code == 200
    assert ticket.estado == "por_validar"
    assert ticket.estado_cierre == "pendiente_creador"
    assert ticket.costo_solucion == Decimal("275.00")
    assert (
        next(row for row in ticket.historial_fechas
             if row["tipo"] == "maintenance_closure_reviewed_v1")["cambiadoPor"]
        == "QA_YULIANA"
    )

    # El solicitante y el gerente de otra sucursal no validan.
    assert post(91004, approve).status_code == 403
    assert post(91005, approve).status_code == 403
    assert post(91003, approve).status_code == 200
    assert ticket.estado == "finalizado"
    assert commit.call_count == 5


def test_qa_externa_solo_coordinacion_solicita_y_gerente_valida(qa_http):
    ticket, post, commit = qa_http
    ticket.tipo_atencion = "EXTERNA"
    ticket.asignado_a = None

    assert post(
        91001, "maintenance/990001/work-completed",
        {"notas_trabajo": "Intento inválido"},
    ).status_code == 404
    assert post(
        91001, "cierre/solicitar/990001",
        {"notas_cierre": "Intento de técnico"},
    ).status_code == 403

    assert post(
        91002, "cierre/solicitar/990001",
        {"notas_cierre": "Proveedor verificó servicio"},
    ).status_code == 200
    assert ticket.estado == "por_validar"
    assert post(91003, "cierre/aceptar-creador/990001").status_code == 200
    assert ticket.estado == "finalizado"
    assert commit.call_count == 2
