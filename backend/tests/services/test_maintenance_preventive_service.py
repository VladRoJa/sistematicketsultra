from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.models.maintenance_preventive import MaintenancePreventiveItemORM
from app.services import maintenance_preventive_service as service
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


class MaintenancePreventiveDraftOperationsTest(unittest.TestCase):
    def _user(self, *, role="MANTENIMIENTO", branches=None):
        return SimpleNamespace(
            id=10,
            rol=role,
            sucursal_id=1000 if role == "MANTENIMIENTO" else 4,
            sucursales_ids=list(branches or []),
        )

    def test_create_batch_starts_as_draft(self):
        fake_session = MagicMock()
        user = self._user()

        with patch.object(
            service,
            "db",
            SimpleNamespace(session=fake_session),
        ):
            batch = service.crear_lote_preventivo(
                user,
                {
                    "nombre": "Semana 39",
                    "source_type": "MANUAL",
                    "period_start": "2026-09-20",
                    "period_end": "2026-09-26",
                },
            )

        self.assertEqual(batch.status, "BORRADOR")
        self.assertEqual(batch.source_type, "MANUAL")
        self.assertEqual(batch.created_by_user_id, 10)
        fake_session.add.assert_called_once_with(batch)
        fake_session.flush.assert_called_once()

    def test_add_row_preserves_raw_values_pending_validation(self):
        fake_session = MagicMock()
        batch = SimpleNamespace(
            id=30,
            status="BORRADOR",
            items=[],
            created_by_user_id=10,
        )
        user = self._user(role="SR_MANTENIMIENTO", branches=[4])
        branch = SimpleNamespace(sucursal_id=4)

        with (
            patch.object(service, "_get_batch", return_value=batch),
            patch.object(service, "_resolve_sucursal", return_value=branch),
            patch.object(
                service,
                "db",
                SimpleNamespace(session=fake_session),
            ),
        ):
            rows = service.agregar_renglones_lote(
                30,
                user,
                [
                    {
                        "sucursal": "VILLAS DEL REY",
                        "codigo_equipo": "04CC01",
                        "responsable": "TECNICO_PM",
                        "fecha_programada": "2026-09-20",
                        "actividad": "Mantenimiento general",
                    }
                ],
            )

        self.assertEqual(len(rows), 1)
        item = rows[0]
        self.assertEqual(item.validation_status, "PENDIENTE")
        self.assertEqual(item.sucursal_input, "VILLAS DEL REY")
        self.assertEqual(item.codigo_equipo_input, "04CC01")
        self.assertIsNone(item.sucursal_id)
        self.assertIsNone(item.inventario_id)
        fake_session.add.assert_called_once_with(item)

    def test_regional_cannot_add_resolvable_row_outside_scope(self):
        fake_session = MagicMock()
        batch = SimpleNamespace(
            id=30,
            status="BORRADOR",
            items=[],
            created_by_user_id=10,
        )
        user = self._user(role="SR_MANTENIMIENTO", branches=[4])
        other_branch = SimpleNamespace(sucursal_id=5)

        with (
            patch.object(service, "_get_batch", return_value=batch),
            patch.object(
                service,
                "_resolve_sucursal",
                return_value=other_branch,
            ),
            patch.object(
                service,
                "db",
                SimpleNamespace(session=fake_session),
            ),
        ):
            with self.assertRaises(
                service.MaintenancePreventiveAuthorizationError
            ):
                service.agregar_renglones_lote(
                    30,
                    user,
                    [
                        {
                            "sucursal": "OTRA SUCURSAL",
                            "codigo_equipo": "05CC01",
                            "responsable": "TECNICO_PM",
                            "fecha_programada": "2026-09-20",
                            "actividad": "Mantenimiento general",
                        }
                    ],
                )

        fake_session.add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
