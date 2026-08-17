import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.models.ticket_model as ticket_model


class TicketCreateTransactionModeTest(unittest.TestCase):
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

    def _create(self, **extra):
        params = dict(
            descripcion="Prueba",
            username="tester",
            sucursal_id=1,
            sucursal_id_destino=1,
            departamento_id=1,
            criticidad=1,
            clasificacion_id=None,
            categoria="General",
        )
        params.update(extra)

        return ticket_model.Ticket.create_ticket(**params)

    def test_default_behavior_still_commits(self):
        ticket = self._create()

        self.assertIsNotNone(ticket)
        self.session.add.assert_called_once_with(ticket)
        self.session.flush.assert_called_once_with()
        self.session.commit.assert_called_once_with()

    def test_commit_false_flushes_but_does_not_commit(self):
        ticket = self._create(commit=False)

        self.assertIsNotNone(ticket)
        self.session.add.assert_called_once_with(ticket)
        self.session.flush.assert_called_once_with()
        self.session.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
