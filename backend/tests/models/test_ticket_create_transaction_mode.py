import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

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

    def _create_with_inventory(
        self, *, family_id=7, family_active=True, department_id=1, commit=True
    ):
        inventory = SimpleNamespace(
            categoria_inventario_id=None,
            familia_equipo_id=family_id,
            familia_equipo=(
                SimpleNamespace(activo=family_active)
                if family_id is not None
                else None
            ),
        )
        with patch.object(
            ticket_model.Ticket,
            "inventario",
            new_callable=PropertyMock,
            return_value=inventory,
        ):
            return self._create(
                aparato_id=1949,
                departamento_id=department_id,
                commit=commit,
            )

    def test_maintenance_ticket_snapshots_active_inventory_family(self):
        ticket = self._create_with_inventory(family_id=7)

        self.assertEqual(ticket.aparato_id, 1949)
        self.assertEqual(ticket.familia_equipo_id, 7)
        self.session.commit.assert_called_once_with()

    def test_maintenance_ticket_without_inventory_family_remains_unclassified(self):
        ticket = self._create_with_inventory(family_id=None)

        self.assertIsNone(ticket.familia_equipo_id)

    def test_inactive_inventory_family_is_not_copied(self):
        ticket = self._create_with_inventory(family_id=7, family_active=False)

        self.assertIsNone(ticket.familia_equipo_id)

    def test_non_maintenance_ticket_does_not_snapshot_family(self):
        ticket = self._create_with_inventory(department_id=7)

        self.assertIsNone(ticket.familia_equipo_id)

    def test_deferred_commit_keeps_family_in_ticket_transaction(self):
        ticket = self._create_with_inventory(family_id=7, commit=False)

        self.assertEqual(ticket.familia_equipo_id, 7)
        self.session.flush.assert_called_once_with()
        self.session.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
