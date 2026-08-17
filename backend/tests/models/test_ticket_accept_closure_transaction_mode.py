import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.models.ticket_model as ticket_model


class TicketAcceptClosureTransactionModeTest(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()

        self.db_patch = patch.object(
            ticket_model,
            "db",
            SimpleNamespace(session=self.session),
        )
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()

    def _ticket(self):
        return SimpleNamespace(
            estado_cierre="pendiente_creador",
            motivo_rechazo_cierre="algo",
            estado="por_validar",
            fecha_finalizado=None,
        )

    def test_default_behavior_still_commits(self):
        ticket = self._ticket()

        ticket_model.Ticket.aceptar_conformidad_creador(
            ticket
        )

        self.assertEqual(ticket.estado, "finalizado")
        self.assertIsNone(ticket.estado_cierre)
        self.assertIsNone(ticket.motivo_rechazo_cierre)
        self.assertIsNotNone(ticket.fecha_finalizado)

        self.session.commit.assert_called_once_with()

    def test_commit_false_does_not_commit(self):
        ticket = self._ticket()

        ticket_model.Ticket.aceptar_conformidad_creador(
            ticket,
            commit=False,
        )

        self.assertEqual(ticket.estado, "finalizado")
        self.assertIsNone(ticket.estado_cierre)
        self.assertIsNone(ticket.motivo_rechazo_cierre)
        self.assertIsNotNone(ticket.fecha_finalizado)

        self.session.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
