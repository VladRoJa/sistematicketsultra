"""M1: contrato de persistencia multiaparato, sin modificar flujos V1."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.ticket_aparato import TicketAparatoORM
from app.models.ticket_model import Ticket


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/k23c10202623_ticket_aparatos_multi.py"
)
spec = importlib.util.spec_from_file_location("migracion_ticket_aparatos_m1", MIGRATION)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class TicketAparatosM1SchemaTest(unittest.TestCase):
    def setUp(self):
        self.table = TicketAparatoORM.__table__

    def test_nombre_y_columnas_canonicos(self):
        self.assertEqual(self.table.name, "ticket_aparatos")
        self.assertEqual(
            {column.name for column in self.table.columns},
            {"ticket_id", "inventario_id", "vinculado_en_utc",
             "recibido_en_utc", "recibido_por"},
        )

    def test_clave_primaria_compuesta_impide_repetir_equipo(self):
        self.assertEqual(
            [c.name for c in self.table.primary_key.columns],
            ["ticket_id", "inventario_id"],
        )
        self.assertFalse(self.table.c.ticket_id.nullable)
        self.assertFalse(self.table.c.inventario_id.nullable)

    def test_vinculado_en_es_timestamp_con_timezone(self):
        column = self.table.c.vinculado_en_utc
        self.assertFalse(column.nullable)
        self.assertTrue(column.type.timezone)
        self.assertIsNotNone(column.server_default)

    def test_integridad_referencial_y_borrado_controlado(self):
        constraints = {
            constraint.name: constraint
            for constraint in self.table.constraints
            if isinstance(constraint, sa.ForeignKeyConstraint)
        }
        self.assertEqual(
            constraints["fk_ticket_aparatos_ticket"].ondelete, "CASCADE"
        )
        self.assertEqual(
            constraints["fk_ticket_aparatos_inventario"].ondelete, "RESTRICT"
        )
        self.assertEqual(
            list(constraints["fk_ticket_aparatos_ticket"].elements)[0]
            .target_fullname,
            "tickets.id",
        )
        self.assertEqual(
            list(constraints["fk_ticket_aparatos_inventario"].elements)[0]
            .target_fullname,
            "inventario_general.id",
        )

    def test_indice_historial_por_equipo(self):
        indexes = {index.name: index for index in self.table.indexes}
        self.assertEqual(
            [c.name for c in indexes["ix_ticket_aparatos_inventario_ticket"].columns],
            ["inventario_id", "ticket_id"],
        )

    def test_v1_aparato_id_y_snapshot_se_conservan(self):
        self.assertIn("aparato_id", Ticket.__table__.c)
        self.assertIn("familia_equipo_id", Ticket.__table__.c)
        self.assertIn("aparatos_asociados", Ticket.__dict__)
        self.assertEqual(Ticket.__table__.name, "tickets")

    def test_ddl_incluye_fks_y_pk(self):
        ddl = str(CreateTable(self.table).compile(dialect=postgresql.dialect()))
        self.assertIn("PRIMARY KEY (ticket_id, inventario_id)", ddl)
        self.assertIn("ON DELETE CASCADE", ddl)
        self.assertIn("ON DELETE RESTRICT", ddl)

    def test_migracion_desciende_del_head_anteriores(self):
        self.assertEqual(migration.revision, "k23c10202623")
        self.assertEqual(migration.down_revision, "j22c10202622")

    def test_upgrade_solo_crea_tabla_e_indice_no_toca_tickets(self):
        with patch.object(migration.op, "create_table") as create_table, patch.object(
            migration.op, "create_index"
        ) as create_index:
            migration.upgrade()
        self.assertEqual(create_table.call_count, 1)
        self.assertEqual(create_table.call_args.args[0], "ticket_aparatos")
        self.assertEqual(create_index.call_count, 1)
        self.assertEqual(
            create_index.call_args.args[:2],
            ("ix_ticket_aparatos_inventario_ticket", "ticket_aparatos"),
        )

    def test_downgrade_no_elimina_vinculos_historicos(self):
        with patch.object(migration.op, "get_bind") as get_bind, patch.object(
            migration.op, "drop_index"
        ) as drop_index, patch.object(
            migration.op, "drop_table"
        ) as drop_table:
            get_bind.return_value.execute.return_value.scalar_one.return_value = 3
            with self.assertRaisesRegex(RuntimeError, "vínculos históricos"):
                migration.downgrade()
            drop_index.assert_not_called()
            drop_table.assert_not_called()

    def test_downgrade_vacio_es_reversible(self):
        with patch.object(migration.op, "get_bind") as get_bind, patch.object(
            migration.op, "drop_index"
        ) as drop_index, patch.object(
            migration.op, "drop_table"
        ) as drop_table:
            get_bind.return_value.execute.return_value.scalar_one.return_value = 0
            migration.downgrade()
            drop_index.assert_called_once_with(
                "ix_ticket_aparatos_inventario_ticket", table_name="ticket_aparatos"
            )
            drop_table.assert_called_once_with("ticket_aparatos")


if __name__ == "__main__":
    unittest.main()
