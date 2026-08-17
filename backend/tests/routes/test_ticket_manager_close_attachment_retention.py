import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from app.routes import ticket_routes


def _unwrap(fn):
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


class TicketManagerCloseAttachmentRetentionTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

        self.user = SimpleNamespace(
            username="gerente",
            rol="GERENTE",
            sucursal_id=7,
        )

        self.ticket = SimpleNamespace(
            id=137,
            estado="abierto",
            fecha_finalizado=None,
            estado_cierre=None,
            notas_cierre=None,
        )

        self.identity_patch = patch.object(
            ticket_routes,
            "get_jwt_identity",
            return_value="user-id",
        )
        self.identity_patch.start()

        self.user_patch = patch.object(
            ticket_routes.UserORM,
            "get_by_id",
            return_value=self.user,
        )
        self.user_patch.start()

        # No parcheamos Ticket.query directamente porque es un
        # descriptor de Flask-SQLAlchemy que requiere app_context.
        self.mock_ticket_query = MagicMock()
        self.mock_ticket_query.get.return_value = self.ticket

        self.ticket_model_patch = patch.object(
            ticket_routes,
            "Ticket",
            SimpleNamespace(
                query=self.mock_ticket_query,
            ),
        )
        self.ticket_model_patch.start()

        self.permission_patch = patch.object(
            ticket_routes,
            "_puede_cerrar_ticket_desde_cero",
            return_value=True,
        )
        self.permission_patch.start()

        self.retention_patch = patch.object(
            ticket_routes,
            "schedule_ticket_attachment_retention",
        )
        self.mock_retention = self.retention_patch.start()

        self.notify_patch = patch.object(
            ticket_routes,
            "_notificar_evento_ticket",
            return_value=[],
        )
        self.notify_patch.start()

        self.session = MagicMock()

        # Igual que Ticket.query: evitamos tocar el proxy real
        # de Flask-SQLAlchemy fuera de un app_context.
        self.db_patch = patch.object(
            ticket_routes,
            "db",
            SimpleNamespace(
                session=self.session,
            ),
        )
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.notify_patch.stop()
        self.retention_patch.stop()
        self.permission_patch.stop()
        self.ticket_model_patch.stop()
        self.user_patch.stop()
        self.identity_patch.stop()

    def test_finalization_and_retention_share_one_commit(self):
        with self.app.test_request_context(
            "/api/tickets/cierre/gerente-desde-cero/137",
            method="POST",
            json={
                "motivo": "Cierre administrativo de prueba"
            },
        ):
            response, status = _unwrap(
                ticket_routes.cierre_gerente_desde_cero
            )(137)

        self.assertEqual(status, 200)

        self.mock_ticket_query.get.assert_called_once_with(137)

        self.assertEqual(
            self.ticket.estado,
            "finalizado",
        )
        self.assertIsNotNone(
            self.ticket.fecha_finalizado
        )
        self.assertEqual(
            self.ticket.estado_cierre,
            "cerrado_por_gerente_desde_cero",
        )

        self.mock_retention.assert_called_once_with(
            ticket_id=137,
            finalized_at=self.ticket.fecha_finalizado,
        )

        self.session.commit.assert_called_once_with()
        self.session.rollback.assert_not_called()

        data = response.get_json()

        self.assertEqual(
            data["ticket_id"],
            137,
        )
        self.assertEqual(
            data["estado"],
            "finalizado",
        )


if __name__ == "__main__":
    unittest.main()
