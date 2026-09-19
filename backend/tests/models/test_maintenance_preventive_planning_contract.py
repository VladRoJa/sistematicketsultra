import unittest

from app.models.maintenance_preventive import (
    MaintenancePreventiveBatchORM,
    MaintenancePreventiveItemORM,
)


class MaintenancePreventivePlanningContractTest(unittest.TestCase):
    def test_batch_contract(self):
        columns = MaintenancePreventiveBatchORM.__table__.c

        self.assertTrue(
            {
                "batch_key",
                "nombre",
                "source_type",
                "status",
                "period_start",
                "period_end",
                "source_filename",
                "source_sha256",
                "created_by_user_id",
                "published_by_user_id",
                "published_at",
            }.issubset(set(columns.keys()))
        )

        constraint_names = {
            constraint.name
            for constraint in MaintenancePreventiveBatchORM.__table__.constraints
            if constraint.name
        }

        self.assertIn(
            "ck_maintenance_preventive_batches_source_type",
            constraint_names,
        )
        self.assertIn(
            "ck_maintenance_preventive_batches_status",
            constraint_names,
        )
        self.assertIn(
            "ck_maintenance_preventive_batches_period",
            constraint_names,
        )

    def test_item_contract(self):
        columns = MaintenancePreventiveItemORM.__table__.c

        self.assertTrue(
            {
                "batch_id",
                "source_row_number",
                "sucursal_input",
                "codigo_equipo_input",
                "responsable_input",
                "fecha_programada_input",
                "sucursal_id",
                "inventario_id",
                "responsable_user_id",
                "fecha_programada",
                "actividad",
                "observaciones",
                "validation_status",
                "validation_errors",
                "ticket_id",
            }.issubset(set(columns.keys()))
        )

        self.assertTrue(
            columns.sucursal_id.nullable
            and columns.inventario_id.nullable
            and columns.fecha_programada.nullable
            and columns.actividad.nullable
        )

        constraint_names = {
            constraint.name
            for constraint in MaintenancePreventiveItemORM.__table__.constraints
            if constraint.name
        }

        self.assertIn(
            "ck_maintenance_preventive_items_validation_status",
            constraint_names,
        )
        self.assertIn(
            "uq_maintenance_preventive_items_batch_source_row",
            constraint_names,
        )

    def test_item_points_to_operational_entities(self):
        expected_targets = {
            "batch_id": "maintenance_preventive_batches.id",
            "sucursal_id": "sucursales.sucursal_id",
            "inventario_id": "inventario_general.id",
            "responsable_user_id": "users.id",
            "ticket_id": "tickets.id",
        }

        for column_name, target in expected_targets.items():
            with self.subTest(column=column_name):
                foreign_keys = list(
                    MaintenancePreventiveItemORM.__table__.c[
                        column_name
                    ].foreign_keys
                )
                self.assertEqual(len(foreign_keys), 1)
                self.assertEqual(
                    foreign_keys[0].target_fullname,
                    target,
                )

    def test_ticket_link_is_one_to_one_from_planning_item(self):
        ticket_column = MaintenancePreventiveItemORM.__table__.c.ticket_id

        unique_constraints = [
            constraint
            for constraint in MaintenancePreventiveItemORM.__table__.constraints
            if getattr(constraint, "name", None)
            == "uq_maintenance_preventive_items_ticket_id"
        ]

        self.assertTrue(ticket_column.index)
        self.assertTrue(ticket_column.unique)
        self.assertEqual(len(unique_constraints), 1)


if __name__ == "__main__":
    unittest.main()
