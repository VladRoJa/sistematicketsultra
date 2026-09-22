from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.models.maintenance_preventive import (
    MaintenancePreventiveItemORM,
    MaintenancePreventiveOccurrenceORM,
    MaintenancePreventiveScheduleORM,
)
from app.services import maintenance_preventive_service as service
from app.services.maintenance_preventive_service import validar_item_borrador


class MaintenancePreventiveWorkdayRecurrenceTest(unittest.TestCase):
    def test_add_workdays_skips_weekend(self):
        self.assertEqual(
            service.add_workdays(date(2026, 9, 18), 1),
            date(2026, 9, 21),
        )

    def test_add_five_workdays_keeps_weekday_cadence(self):
        self.assertEqual(
            service.add_workdays(date(2026, 9, 18), 5),
            date(2026, 9, 25),
        )

    def test_add_workdays_rejects_non_positive_interval(self):
        with self.assertRaises(service.MaintenancePreventiveError):
            service.add_workdays(date(2026, 9, 18), 0)


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
            validate_responsable=lambda user, branch_id=None: (
                (
                    int(getattr(user, "department_id", 0) or 0) == 1,
                    None
                    if int(getattr(user, "department_id", 0) or 0) == 1
                    else (
                        "El responsable no pertenece al departamento "
                        "de Mantenimiento."
                    ),
                )
            ),
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

    def test_recurring_row_accepts_weekday_and_positive_interval(self):
        item = self._item(
            fecha_programada_input="2026-09-21",
            repeat_enabled=True,
            repeat_interval_workdays=5,
        )

        errors = self._validate(item)

        self.assertEqual(errors, [])
        self.assertEqual(item.fecha_programada, date(2026, 9, 21))
        self.assertTrue(item.repeat_enabled)
        self.assertEqual(item.repeat_interval_workdays, 5)

    def test_recurring_row_rejects_weekend_start(self):
        item = self._item(
            fecha_programada_input="2026-09-20",
            repeat_enabled=True,
            repeat_interval_workdays=5,
        )

        errors = self._validate(item)

        self.assertIn(
            "La fecha inicial de un preventivo recurrente debe ser "
            "de lunes a viernes.",
            errors,
        )

    def test_recurring_row_requires_positive_workday_interval(self):
        item = self._item(
            fecha_programada_input="2026-09-21",
            repeat_enabled=True,
            repeat_interval_workdays=None,
        )

        errors = self._validate(item)

        self.assertIn(
            "La repetición requiere un intervalo de días hábiles "
            "mayor a cero.",
            errors,
        )

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
        item = self._item(fecha_programada_input="20/13/2026")

        errors = self._validate(item)

        self.assertIn(
            "Fecha programada inválida; usa formato DD/MM/AAAA.",
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

    def test_responsible_catalog_scope_error_is_preserved(self):
        item = self._item()
        branch = SimpleNamespace(sucursal_id=4)
        equipment = SimpleNamespace(id=90, tipo="aparatos")
        responsible = SimpleNamespace(id=20, department_id=1)

        errors = validar_item_borrador(
            item,
            resolve_sucursal=lambda _value: branch,
            resolve_equipo=lambda _value: equipment,
            equipo_asignado=lambda *_args: True,
            resolve_responsable=lambda _value: responsible,
            validate_responsable=lambda _user, branch_id=None: (
                False,
                "El responsable pertenece a una cuadrilla de otra región.",
            ),
        )

        self.assertIn(
            "El responsable pertenece a una cuadrilla de otra región.",
            errors,
        )
        self.assertIsNone(item.responsable_user_id)
        self.assertEqual(item.validation_status, "ERROR")

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
            "El equipo ya está programado para esa fecha "
            "dentro del mismo lote.",
            errors,
        )
        self.assertEqual(second.validation_status, "ERROR")

    def test_same_equipment_and_date_is_duplicate_even_if_activity_changes(self):
        seen_keys = set()
        first = self._item(actividad="Limpieza")
        second = self._item(actividad="Lubricación")

        self.assertEqual(
            self._validate(first, seen_keys=seen_keys),
            [],
        )
        errors = self._validate(second, seen_keys=seen_keys)

        self.assertIn(
            "El equipo ya está programado para esa fecha "
            "dentro del mismo lote.",
            errors,
        )

    def test_same_equipment_on_different_date_is_allowed(self):
        seen_keys = set()
        first = self._item(fecha_programada_input="27/09/2026")
        second = self._item(fecha_programada_input="04/10/2026")

        self.assertEqual(
            self._validate(first, seen_keys=seen_keys),
            [],
        )
        self.assertEqual(
            self._validate(second, seen_keys=seen_keys),
            [],
        )


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
        self.assertEqual(batch.items, [item])
        fake_session.add.assert_called_once_with(item)

    def test_add_then_validate_same_transaction_sees_new_rows(self):
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
            created = service.agregar_renglones_lote(
                30,
                user,
                [
                    {
                        "sucursal": "VILLAS DEL REY",
                        "codigo_equipo": "04CC01",
                        "responsable": "TECNICO_PM",
                        "fecha_programada": "26/09/2026",
                        "actividad": "Mantenimiento general",
                    }
                ],
            )

            with patch.object(
                service,
                "validar_item_borrador",
                return_value=[],
            ):
                summary = service.validar_lote_preventivo(
                    30,
                    user,
                )

        self.assertEqual(batch.items, created)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["validos"], 1)
        self.assertEqual(summary["errores"], 0)
        self.assertTrue(summary["publicable"])

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


class MaintenancePreventivePublishTest(unittest.TestCase):
    def _user(self):
        return SimpleNamespace(
            id=10,
            username="MANTENIMIENTO",
            rol="MANTENIMIENTO",
            sucursal_id=1000,
            sucursales_ids=[],
        )

    def _valid_item(self):
        return SimpleNamespace(
            id=1,
            validation_status="VALIDO",
            ticket_id=None,
            sucursal_id=4,
            inventario_id=90,
            responsable_user_id=20,
            fecha_programada=date(2026, 9, 20),
            repeat_enabled=False,
            repeat_interval_workdays=None,
            schedule_id=None,
            actividad="Mantenimiento general",
            observaciones=None,
        )

    def test_publish_requires_all_rows_valid(self):
        batch = SimpleNamespace(
            id=30,
            status="BORRADOR",
            created_by_user_id=10,
            items=[
                SimpleNamespace(validation_status="ERROR"),
            ],
        )

        with patch.object(service, "_get_batch", return_value=batch):
            with self.assertRaises(
                service.MaintenancePreventiveStateError
            ):
                service.publicar_lote_preventivo(
                    30,
                    self._user(),
                )

    def test_publish_creates_preventive_ticket_and_links_item(self):
        item = self._valid_item()
        batch = SimpleNamespace(
            id=30,
            status="BORRADOR",
            created_by_user_id=10,
            items=[item],
            published_by_user_id=None,
            published_at=None,
        )
        inventory = SimpleNamespace(
            id=90,
            nombre="CAMINADORA",
            familia_equipo_id=1,
        )
        responsible = SimpleNamespace(
            id=20,
            username="TECNICO_PM",
        )
        ticket = SimpleNamespace(
            id=501,
            asignado_a=None,
            familia_equipo_id=None,
        )
        fake_session = MagicMock()

        def fake_get(model, object_id):
            if model is service.InventarioGeneral:
                return inventory
            if model is service.UserORM:
                return responsible
            return None

        fake_session.get.side_effect = fake_get

        with (
            patch.object(service, "_get_batch", return_value=batch),
            patch.object(
                service,
                "_published_duplicate_exists",
                return_value=False,
            ),
            patch.object(
                service,
                "db",
                SimpleNamespace(session=fake_session),
            ),
            patch.object(
                service.Ticket,
                "create_ticket",
                return_value=ticket,
            ) as create_ticket,
        ):
            tickets = service.publicar_lote_preventivo(
                30,
                self._user(),
            )

        self.assertEqual(tickets, [ticket])
        self.assertEqual(item.ticket_id, 501)
        self.assertEqual(ticket.asignado_a, "TECNICO_PM")
        self.assertEqual(ticket.familia_equipo_id, 1)
        self.assertEqual(batch.status, "PUBLICADO")
        self.assertEqual(batch.published_by_user_id, 10)

        kwargs = create_ticket.call_args.kwargs
        self.assertEqual(kwargs["tipo_mantenimiento"], "PREVENTIVO")
        self.assertEqual(kwargs["sucursal_id_destino"], 4)
        self.assertEqual(kwargs["aparato_id"], 90)
        self.assertFalse(kwargs["commit"])
        self.assertEqual(
            kwargs["fecha_programada_original"],
            kwargs["fecha_programada_actual"],
        )

    def test_publish_recurring_item_creates_schedule_and_first_occurrence(self):
        item = self._valid_item()
        item.fecha_programada = date(2026, 9, 21)
        item.repeat_enabled = True
        item.repeat_interval_workdays = 5

        batch = SimpleNamespace(
            id=30,
            status="BORRADOR",
            created_by_user_id=10,
            items=[item],
            published_by_user_id=None,
            published_at=None,
        )
        inventory = SimpleNamespace(
            id=90,
            nombre="CAMINADORA",
            familia_equipo_id=1,
        )
        responsible = SimpleNamespace(
            id=20,
            username="TECNICO_PM",
        )
        ticket = SimpleNamespace(
            id=501,
            asignado_a=None,
            familia_equipo_id=None,
        )
        fake_session = MagicMock()

        def fake_get(model, object_id):
            if model is service.InventarioGeneral:
                return inventory
            if model is service.UserORM:
                return responsible
            return None

        fake_session.get.side_effect = fake_get

        with (
            patch.object(service, "_get_batch", return_value=batch),
            patch.object(
                service,
                "_published_duplicate_exists",
                return_value=False,
            ),
            patch.object(
                service,
                "db",
                SimpleNamespace(session=fake_session),
            ),
            patch.object(
                service.Ticket,
                "create_ticket",
                return_value=ticket,
            ),
        ):
            tickets = service.publicar_lote_preventivo(
                30,
                self._user(),
            )

        self.assertEqual(tickets, [ticket])
        self.assertIsInstance(
            item.schedule,
            MaintenancePreventiveScheduleORM,
        )
        self.assertEqual(item.schedule.start_date, date(2026, 9, 21))
        self.assertEqual(
            item.schedule.next_scheduled_date,
            date(2026, 9, 28),
        )
        self.assertEqual(item.schedule.repeat_interval_workdays, 5)

        added = [
            call.args[0]
            for call in fake_session.add.call_args_list
            if call.args
        ]
        occurrences = [
            value
            for value in added
            if isinstance(value, MaintenancePreventiveOccurrenceORM)
        ]
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(
            occurrences[0].scheduled_date,
            date(2026, 9, 21),
        )
        self.assertEqual(occurrences[0].ticket_id, 501)
        self.assertIs(occurrences[0].schedule, item.schedule)

    def test_published_batch_cannot_publish_again(self):
        batch = SimpleNamespace(
            id=30,
            status="PUBLICADO",
            created_by_user_id=10,
            items=[self._valid_item()],
        )

        with patch.object(service, "_get_batch", return_value=batch):
            with self.assertRaisesRegex(
                service.MaintenancePreventiveStateError,
                "BORRADOR",
            ):
                service.publicar_lote_preventivo(
                    30,
                    self._user(),
                )


if __name__ == "__main__":
    unittest.main()
