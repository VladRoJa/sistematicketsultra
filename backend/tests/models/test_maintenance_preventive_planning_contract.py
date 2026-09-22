import unittest

from app.models.maintenance_checklist import (
    MaintenanceChecklistItemORM,
    MaintenanceChecklistTemplateORM,
)
from app.models.maintenance_preventive import (
    MaintenanceCrewORM,
    MaintenancePersonnelORM,
    MaintenancePreventiveBatchORM,
    MaintenancePreventiveItemORM,
    MaintenancePreventiveOccurrenceORM,
    MaintenancePreventiveScheduleORM,
)


class MaintenancePreventivePlanningContractTest(unittest.TestCase):
    def test_checklist_contract(self):
        template_columns = MaintenanceChecklistTemplateORM.__table__.c
        item_columns = MaintenanceChecklistItemORM.__table__.c

        self.assertTrue(
            {
                "template_key",
                "familia_equipo_id",
                "nombre",
                "actividad_key",
                "activo",
            }.issubset(set(template_columns.keys()))
        )
        self.assertTrue(
            {
                "template_id",
                "item_key",
                "etiqueta",
                "orden",
                "requerido",
                "activo",
            }.issubset(set(item_columns.keys()))
        )

        family_fk = list(
            template_columns.familia_equipo_id.foreign_keys
        )
        self.assertEqual(len(family_fk), 1)
        self.assertEqual(
            family_fk[0].target_fullname,
            "familia_equipo.id",
        )

        template_fk = list(item_columns.template_id.foreign_keys)
        self.assertEqual(len(template_fk), 1)
        self.assertEqual(
            template_fk[0].target_fullname,
            "maintenance_checklist_templates.id",
        )

    def test_crew_and_personnel_contract(self):
        crew_columns = MaintenanceCrewORM.__table__.c
        personnel_columns = MaintenancePersonnelORM.__table__.c

        self.assertTrue(
            {"nombre", "region_id", "activo"}.issubset(
                set(crew_columns.keys())
            )
        )
        self.assertTrue(
            {"user_id", "crew_id", "activo"}.issubset(
                set(personnel_columns.keys())
            )
        )

        crew_region_fk = list(crew_columns.region_id.foreign_keys)
        self.assertEqual(len(crew_region_fk), 1)
        self.assertEqual(
            crew_region_fk[0].target_fullname,
            "suite_regions.id",
        )

        personnel_user_fk = list(personnel_columns.user_id.foreign_keys)
        self.assertEqual(len(personnel_user_fk), 1)
        self.assertEqual(
            personnel_user_fk[0].target_fullname,
            "users.id",
        )

        personnel_crew_fk = list(personnel_columns.crew_id.foreign_keys)
        self.assertEqual(len(personnel_crew_fk), 1)
        self.assertEqual(
            personnel_crew_fk[0].target_fullname,
            "maintenance_crews.id",
        )

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
                "repeat_enabled",
                "repeat_interval_workdays",
                "schedule_id",
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
        self.assertIn(
            "ck_maintenance_preventive_items_recurrence",
            constraint_names,
        )

    def test_recurrence_schedule_contract(self):
        columns = MaintenancePreventiveScheduleORM.__table__.c

        self.assertTrue(
            {
                "schedule_key",
                "target_type",
                "sucursal_id",
                "inventario_id",
                "responsable_user_id",
                "actividad",
                "observaciones",
                "repeat_interval_workdays",
                "start_date",
                "next_scheduled_date",
                "active",
                "created_by_user_id",
            }.issubset(set(columns.keys()))
        )

        constraint_names = {
            constraint.name
            for constraint in MaintenancePreventiveScheduleORM.__table__.constraints
            if constraint.name
        }

        self.assertIn(
            "ck_maintenance_preventive_schedules_target_type",
            constraint_names,
        )
        self.assertIn(
            "ck_maintenance_preventive_schedules_interval",
            constraint_names,
        )
        self.assertIn(
            "ck_maintenance_preventive_schedules_equipment_target",
            constraint_names,
        )

        expected_targets = {
            "sucursal_id": "sucursales.sucursal_id",
            "inventario_id": "inventario_general.id",
            "responsable_user_id": "users.id",
            "created_by_user_id": "users.id",
        }
        for column_name, target in expected_targets.items():
            with self.subTest(column=column_name):
                foreign_keys = list(columns[column_name].foreign_keys)
                self.assertEqual(len(foreign_keys), 1)
                self.assertEqual(foreign_keys[0].target_fullname, target)

    def test_recurrence_occurrence_contract(self):
        columns = MaintenancePreventiveOccurrenceORM.__table__.c

        self.assertTrue(
            {
                "schedule_id",
                "scheduled_date",
                "ticket_id",
                "generated_at",
            }.issubset(set(columns.keys()))
        )

        expected_targets = {
            "schedule_id": "maintenance_preventive_schedules.id",
            "ticket_id": "tickets.id",
        }
        for column_name, target in expected_targets.items():
            with self.subTest(column=column_name):
                foreign_keys = list(columns[column_name].foreign_keys)
                self.assertEqual(len(foreign_keys), 1)
                self.assertEqual(foreign_keys[0].target_fullname, target)

        constraint_names = {
            constraint.name
            for constraint in MaintenancePreventiveOccurrenceORM.__table__.constraints
            if constraint.name
        }
        self.assertIn(
            "uq_maintenance_preventive_occurrences_schedule_date",
            constraint_names,
        )
        self.assertIn(
            "uq_maintenance_preventive_occurrences_ticket_id",
            constraint_names,
        )

    def test_item_points_to_operational_entities(self):
        expected_targets = {
            "batch_id": "maintenance_preventive_batches.id",
            "sucursal_id": "sucursales.sucursal_id",
            "inventario_id": "inventario_general.id",
            "responsable_user_id": "users.id",
            "ticket_id": "tickets.id",
            "schedule_id": "maintenance_preventive_schedules.id",
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

        self.assertFalse(bool(ticket_column.index))
        self.assertFalse(bool(ticket_column.unique))
        self.assertEqual(len(unique_constraints), 1)


if __name__ == "__main__":
    unittest.main()
