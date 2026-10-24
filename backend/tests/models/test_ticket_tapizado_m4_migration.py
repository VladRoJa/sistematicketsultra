"""M4 migration contract: revision sequence, nullable untouched links, audited downgrade."""

import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock, patch


FILE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions"
    / "m23c10202623_tapizado_recepcion_parcial.py"
)
spec = importlib.util.spec_from_file_location("migration_tapizado_m4", FILE)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class TapizadoM4MigrationTest(unittest.TestCase):
    def test_revision_extiende_la_cadena_existente(self):
        self.assertEqual(migration.revision, "m23c10202623")
        self.assertEqual(migration.down_revision, "v2e2a7c92623")

    def test_migracion_anade_columnas_nullable_y_constraint(self):
        with patch.object(migration, "op") as op:
            migration.upgrade()
        self.assertEqual(op.add_column.call_count, 2)
        self.assertTrue(all(
            call.args[0] == "ticket_aparatos" and call.args[1].nullable
            for call in op.add_column.call_args_list
        ))
        self.assertEqual(
            op.create_check_constraint.call_args.args[0],
            "ck_ticket_aparatos_recepcion_par",
        )

    def test_downgrade_rechaza_perder_recepciones(self):
        with patch.object(migration, "op") as op:
            op.get_bind.return_value.execute.return_value.scalar_one.return_value = 1
            with self.assertRaisesRegex(RuntimeError, "historial"):
                migration.downgrade()
            op.drop_column.assert_not_called()

    def test_downgrade_sin_recepciones_permmitido(self):
        with patch.object(migration, "op") as op:
            op.get_bind.return_value.execute.return_value.scalar_one.return_value = 0
            migration.downgrade()
            self.assertEqual(op.drop_column.call_count, 2)


if __name__ == "__main__":
    unittest.main()
