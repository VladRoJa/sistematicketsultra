from datetime import date
from types import SimpleNamespace
import unittest

from app.models.maintenance_preventive import MaintenancePreventiveItemORM
from app.services.maintenance_preventive_service import validar_item_borrador


class MaintenancePreventiveDraftValidationTest(unittest.TestCase):
    def _item(self, **overrides):
        values = {
            "sucursal_input": "VILLAS DEL REY",
            "codigo_equipo_input": "04CC01",
            "responsable_input": "TECNICO_PM",
            "fecha_programada_input": "2026-09-20",
            "actividad": "Mantenimiento general",
        }
        values.update(overrides)
        return MaintenancePreventiveItemORM(**values)

    def _validate(
        self,
        item,
        *,
        assigned=True,
        department_id=1,
        seen_keys=None,
        equipment_type="aparatos",
    ):
        branch = SimpleNamespace(sucursal_id=4)
        equipment = SimpleNamespace(id=90, tipo=equipment_type)
        responsible = SimpleNamespace(id=20, department_id=department_id)

        return validar_item_borrador(
            item,
            seen_keys=seen_keys,
            resolve_sucursal=lambda _value: branch,
            resolve_equipo=lambda _value: equipment,
            equipo_asignado=lambda _inventory_id, _branch_id: assigned,
            resolve_responsable=lambda _value: responsible,
        )

    def test_valid_row_resolves_operational_ids(self):
        item = self._item()

        errors = self._validate(item)

        self.assertEqual(errors, [])
        self.assertEqual(item.validation_status, "VALIDO")
        self.assertIsNone(item.validation_errors)
        self.assertEqual(item.sucursal_id, 4)
        self.assertEqual(item.inventario_id, 90)
        self.assertEqual(item.responsable_user_id, 20)
        self.assertEqual(item.fecha_programada, date(2026, 9, 20))

    def test_wrong_branch_is_kept_as_error(self):
        item = self._item()

        errors = self._validate(item, assigned=False)

        self.assertIn(
            "El equipo no está asignado actualmente a la sucursal indicada.",
            errors,
        )
        self.assertEqual(item.validation_status, "ERROR")
        self.assertEqual(item.inventario_id, 90)

    def test_non_maintenance_responsible_is_rejected(self):
        item = self._item()

        errors = self._validate(item, department_id=7)

        self.assertIn(
            "El responsable no pertenece al departamento de Mantenimiento.",
            errors,
        )
        self.assertIsNone(item.responsable_user_id)

    def test_invalid_date_is_preserved_as_error(self):
        item = self._item(fecha_programada_input="20/09/2026")

        errors = self._validate(item)

        self.assertIn(
            "Fecha programada inválida; se requiere formato YYYY-MM-DD.",
            errors,
        )
        self.assertIsNone(item.fecha_programada)

    def test_non_apparatus_code_is_rejected(self):
        item = self._item()

        errors = self._validate(item, equipment_type="dispositivos")

        self.assertIn(
            "El código no corresponde a un equipo de Aparatos.",
            errors,
        )

    def test_duplicate_inside_same_batch_is_rejected(self):
        seen_keys = set()
        first = self._item()
        second = self._item()

        self.assertEqual(
            self._validate(first, seen_keys=seen_keys),
            [],
        )
        errors = self._validate(second, seen_keys=seen_keys)

        self.assertIn(
            "Renglón duplicado dentro del mismo lote.",
            errors,
        )
        self.assertEqual(second.validation_status, "ERROR")


if __name__ == "__main__":
    unittest.main()
