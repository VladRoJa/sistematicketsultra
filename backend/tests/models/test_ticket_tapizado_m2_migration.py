"""M2: control de esquema de trabajo tipificado TAPIZADO."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models.ticket_model import Ticket


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/l23c10202623_ticket_tipo_trabajo_tapizado.py"
)
spec = importlib.util.spec_from_file_location("ticket_tipo_trabajo_m2", MIGRATION)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class TicketTapizadoM2MigrationTest(unittest.TestCase):
    def test_migration_chain(self):
        self.assertEqual(migration.revision, "l23c10202623")
        self.assertEqual(migration.down_revision, "k23c10202623")

    def test_tipo_trabajo_es_nullable_para_tickets_v1(self):
        c = Ticket.__table__.c.tipo_trabajo
        self.assertTrue(c.nullable)
        self.assertEqual(c.type.length, 24)

    def test_upgrade_agrega_solo_tipo_y_check(self):
        with patch.object(migration.op, "add_column") as add_column, patch.object(
            migration.op, "create_check_constraint"
        ) as create_check:
            migration.upgrade()
        self.assertEqual(add_column.call_count, 1)
        self.assertEqual(add_column.call_args.args[0], "tickets")
        self.assertEqual(add_column.call_args.args[1].name, "tipo_trabajo")
        create_check.assert_called_once_with(
            "ck_tickets_tipo_trabajo_tapizado", "tickets",
            "tipo_trabajo IS NULL OR tipo_trabajo = 'TAPIZADO'",
        )

    def test_downgrade_no_borra_trabajos_existentes(self):
        with patch.object(migration.op, "get_bind") as get_bind, patch.object(
            migration.op, "drop_column"
        ) as drop_column:
            get_bind.return_value.execute.return_value.scalar_one.return_value = 2
            with self.assertRaises(RuntimeError):
                migration.downgrade()
            drop_column.assert_not_called()

    def test_downgrade_vacio_es_reversible(self):
        with patch.object(migration.op, "get_bind") as get_bind, patch.object(
            migration.op, "drop_constraint"
        ) as drop_constraint, patch.object(
            migration.op, "drop_column"
        ) as drop_column:
            get_bind.return_value.execute.return_value.scalar_one.return_value = 0
            migration.downgrade()
            drop_constraint.assert_called_once_with(
                "ck_tickets_tipo_trabajo_tapizado",
                "tickets", type_="check"
            )
            drop_column.assert_called_once_with("tickets", "tipo_trabajo")


if __name__ == "__main__":
    unittest.main()
