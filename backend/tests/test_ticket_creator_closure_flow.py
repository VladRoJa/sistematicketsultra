from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes.ticket_routes import ticket_bp


class _FakeTicketQuery:
    def get(self, ticket_id):
        try:
            ticket_id = int(ticket_id)
        except (TypeError, ValueError):
            return None

        return _FakeTicketModel.store.get(ticket_id)


class _FakeTicketModel:
    store = {}
    next_id = 1
    query = _FakeTicketQuery()

    def __init__(self, **kwargs):
        self.id = _FakeTicketModel.next_id
        _FakeTicketModel.next_id += 1

        self.username = kwargs.get("username")
        self.sucursal_id = kwargs.get("sucursal_id")
        self.sucursal_id_destino = kwargs.get("sucursal_id_destino")
        self.departamento_id = kwargs.get("departamento_id")

        self.descripcion = kwargs.get("descripcion")
        self.criticidad = kwargs.get("criticidad")
        self.clasificacion_id = kwargs.get("clasificacion_id")

        self.estado = kwargs.get("estado") or "abierto"
        self.estado_cierre = None
        self.fecha_finalizado = None
        self.costo_solucion = None
        self.notas_cierre = None
        self.motivo_rechazo_cierre = None

    @classmethod
    def reset(cls):
        cls.store = {}
        cls.next_id = 1

    @classmethod
    def create_ticket(cls, **kwargs):
        ticket = cls(**kwargs)
        cls.store[ticket.id] = ticket
        return ticket

    def solicitar_cierre(self):
        self.estado = "por_validar"
        self.estado_cierre = "pendiente_creador"
        self.fecha_finalizado = datetime.now(timezone.utc)

    def aceptar_conformidad_creador(self, commit: bool = True):
        self.estado = "finalizado"
        self.estado_cierre = None
        self.motivo_rechazo_cierre = None

        if self.fecha_finalizado is None:
            self.fecha_finalizado = datetime.now(timezone.utc)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "sucursal_id": self.sucursal_id,
            "sucursal_id_destino": self.sucursal_id_destino,
            "departamento_id": self.departamento_id,
            "estado": self.estado,
            "estado_cierre": self.estado_cierre,
        }


class TicketCreatorClosureFlowTest(unittest.TestCase):
    def setUp(self):
        _FakeTicketModel.reset()

        self.retention_patch = patch(
            "app.routes.ticket_routes."
            "schedule_ticket_attachment_retention",
            return_value=(0, None),
        )
        self.mock_retention = self.retention_patch.start()
        self.addCleanup(self.retention_patch.stop)

        self.users = {
            101: SimpleNamespace(
                id=101,
                username="usuario_tienda",
                rol="TIENDA",
                sucursal_id=25,
                department_id=9,
            ),
            202: SimpleNamespace(
                id=202,
                username="jefe_mantenimiento",
                rol="MANTENIMIENTO",
                sucursal_id=25,
                department_id=7,
            ),
            303: SimpleNamespace(
                id=303,
                username="otro_usuario_tienda",
                rol="TIENDA",
                sucursal_id=25,
                department_id=9,
            ),
        }

        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="ticket-creator-flow-test-secret",
        )

        JWTManager(self.app)
        self.app.register_blueprint(ticket_bp)

        self.patchers = [
            patch(
                "app.routes.ticket_routes.UserORM.get_by_id",
                side_effect=self._get_user,
            ),
            patch(
                "app.routes.ticket_routes.Ticket",
                _FakeTicketModel,
            ),
            patch(
                "app.routes.ticket_routes.pick_recipients",
                return_value=[],
            ),
            patch(
                "app.routes.ticket_routes._notificar_evento_ticket",
                return_value=[],
            ),
        ]

        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()

    def _get_user(self, raw_identity):
        try:
            return self.users.get(int(raw_identity))
        except (TypeError, ValueError):
            return None

    def _headers_for(self, user_id: int):
        with self.app.app_context():
            token = create_access_token(identity=str(user_id))

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _request(self, path: str, *, method: str, headers=None, json=None):
        with self.app.test_request_context(
            path,
            method=method,
            headers=headers,
            json=json,
        ):
            return self.app.full_dispatch_request()

    def test_tienda_creator_can_complete_full_ticket_closure_flow(self):
        # 1. TIENDA crea el ticket.
        create_response = self._request(
            "/api/tickets/create",
            method="POST",
            headers=self._headers_for(101),
            json={
                "descripcion": "Equipo de tienda requiere atención",
                "departamento_id": 7,
                "criticidad": 3,
                "clasificacion_id": 99,
            },
        )

        self.assertEqual(create_response.status_code, 201)

        create_payload = create_response.get_json()
        ticket_id = create_payload["ticket_id"]

        ticket = _FakeTicketModel.store[ticket_id]

        self.assertEqual(ticket.username, "usuario_tienda")
        self.assertEqual(ticket.sucursal_id, 25)
        self.assertEqual(ticket.sucursal_id_destino, 25)
        self.assertEqual(ticket.estado, "abierto")
        self.assertIsNone(ticket.estado_cierre)

        # 2. Jefe/responsable del departamento solicita el cierre.
        closure_response = self._request(
            f"/api/tickets/cierre/solicitar/{ticket_id}",
            method="POST",
            headers=self._headers_for(202),
            json={
                "costo_solucion": 125.50,
                "notas_cierre": "Trabajo concluido y validado por mantenimiento.",
            },
        )

        self.assertEqual(closure_response.status_code, 200)
        self.assertEqual(ticket.estado, "por_validar")
        self.assertEqual(ticket.estado_cierre, "pendiente_creador")
        self.assertIsNotNone(ticket.fecha_finalizado)

        # 3. Otro usuario TIENDA NO puede validar el ticket ajeno,
        # aunque pertenezca a la misma sucursal.
        unauthorized_response = self._request(
            f"/api/tickets/cierre/aceptar-creador/{ticket_id}",
            method="POST",
            headers=self._headers_for(303),
            json={},
        )

        self.assertEqual(unauthorized_response.status_code, 403)
        self.assertEqual(ticket.estado, "por_validar")
        self.assertEqual(ticket.estado_cierre, "pendiente_creador")

        # 4. El usuario TIENDA que creó el ticket sí puede validarlo.
        creator_response = self._request(
            f"/api/tickets/cierre/aceptar-creador/{ticket_id}",
            method="POST",
            headers=self._headers_for(101),
            json={},
        )

        self.assertEqual(creator_response.status_code, 200)

        creator_payload = creator_response.get_json()

        self.assertIn("finalizado", creator_payload["mensaje"].lower())
        self.assertEqual(ticket.estado, "finalizado")
        self.assertIsNone(ticket.estado_cierre)


if __name__ == "__main__":
    unittest.main()
