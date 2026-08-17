import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from app.routes import ticket_routes


def _unwrap(fn):
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


class FakeClosingTicket:
    def __init__(self):
        self.id = 137
        self.username = "creador"
        self.estado = "por_validar"
        self.estado_cierre = "pendiente_creador"

        # Esta fecha simula que el cierre fue SOLICITADO días antes.
        self.fecha_finalizado = datetime(
            2026,
            8,
            10,
            12,
            0,
            tzinfo=timezone.utc,
        )

        self.commit_argument = None

    def aceptar_conformidad_creador(
        self,
        commit: bool = True,
    ):
        self.commit_argument = commit
        self.estado = "finalizado"
        self.estado_cierre = None


class TicketCreatorCloseAttachmentRetentionTest(
    unittest.TestCase
):
    def setUp(self):
        self.app = Flask(__name__)

        self.user = SimpleNamespace(
            username="creador",
            rol="GERENTE",
            sucursal_id=7,
        )

        self.ticket = FakeClosingTicket()

        self.real_closure_at = datetime(
            2026,
            8,
            17,
            14,
            30,
            tzinfo=timezone.utc,
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

        self.mock_ticket_query = MagicMock()
        self.mock_ticket_query.get.return_value = self.ticket

        self.ticket_patch = patch.object(
            ticket_routes,
            "Ticket",
            SimpleNamespace(
                query=self.mock_ticket_query,
            ),
        )
        self.ticket_patch.start()

        self.permission_patch = patch.object(
            ticket_routes,
            "_puede_validar_cierre_gerente",
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

        self.datetime_patch = patch.object(
            ticket_routes,
            "datetime",
        )
        self.mock_datetime = self.datetime_patch.start()
        self.mock_datetime.now.return_value = (
            self.real_closure_at
        )

        self.session = MagicMock()

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
        self.datetime_patch.stop()
        self.notify_patch.stop()
        self.retention_patch.stop()
        self.permission_patch.stop()
        self.ticket_patch.stop()
        self.user_patch.stop()
        self.identity_patch.stop()

    def test_retention_starts_on_real_acceptance_time(self):
        old_requested_at = self.ticket.fecha_finalizado

        with self.app.test_request_context(
            "/api/tickets/cierre/aceptar-creador/137",
            method="POST",
        ):
            response, status = _unwrap(
                ticket_routes.cierre_aceptar_creador
            )(137)

        self.assertEqual(status, 200)

        self.assertEqual(
            self.ticket.estado,
            "finalizado",
        )

        self.assertFalse(
            self.ticket.commit_argument
        )

        # La fecha histórica del "por validar" se conserva.
        self.assertEqual(
            self.ticket.fecha_finalizado,
            old_requested_at,
        )

        # Pero NO se usa para la retención.
        self.mock_retention.assert_called_once_with(
            ticket_id=137,
            finalized_at=self.real_closure_at,
        )

        self.assertNotEqual(
            self.real_closure_at,
            old_requested_at,
        )

        self.session.commit.assert_called_once_with()
        self.session.rollback.assert_not_called()

        data = response.get_json()

        self.assertEqual(
            data["mensaje"],
            "Cierre validado por gerente; ticket finalizado",
        )


if __name__ == "__main__":
    unittest.main()
