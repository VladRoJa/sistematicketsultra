from datetime import date, datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.services import maintenance_my_program_service as service


class MaintenanceMyProgramServiceTest(unittest.TestCase):
    def test_default_week_is_sunday_to_saturday(self):
        window = service._default_window(date(2026, 9, 23))

        self.assertEqual(window.start, date(2026, 9, 20))
        self.assertEqual(window.end, date(2026, 9, 26))

    def test_active_catalog_personnel_is_required(self):
        user = SimpleNamespace(
            id=20,
            department_id=1,
            username="TECNICO_PM",
        )

        with patch.object(
            service,
            "_active_personnel",
            return_value=None,
        ):
            with self.assertRaises(
                service.MaintenanceMyProgramAuthorizationError
            ):
                service.require_my_program_access(user)

    def test_non_maintenance_user_is_rejected(self):
        user = SimpleNamespace(
            id=20,
            department_id=7,
            username="TECNICO",
        )

        with self.assertRaises(
            service.MaintenanceMyProgramAuthorizationError
        ):
            service.require_my_program_access(user)

    def test_preventive_uses_programmed_date(self):
        ticket = SimpleNamespace(
            tipo_mantenimiento="PREVENTIVO",
            fecha_programada_actual=datetime(
                2026,
                9,
                20,
                14,
                0,
                tzinfo=timezone.utc,
            ),
            fecha_solucion=datetime(
                2026,
                10,
                1,
                14,
                0,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            service._ticket_work_date(ticket),
            date(2026, 9, 20),
        )

    def test_corrective_uses_current_commitment(self):
        ticket = SimpleNamespace(
            tipo_mantenimiento="CORRECTIVO",
            fecha_programada_actual=None,
            fecha_solucion=datetime(
                2026,
                9,
                21,
                14,
                0,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            service._ticket_work_date(ticket),
            date(2026, 9, 21),
        )

    def test_recurring_projection_falls_inside_requested_week(self):
        schedule = SimpleNamespace(
            active=True,
            next_scheduled_date=date(2026, 9, 30),
            repeat_interval_workdays=5,
        )
        window = service.ProgramWindow(
            start=date(2026, 9, 27),
            end=date(2026, 10, 3),
        )

        projected = service._projection_dates(
            schedule,
            window,
            date(2026, 9, 22),
        )

        self.assertEqual(projected, [date(2026, 9, 30)])

    def test_recurring_projection_skips_historical_dates(self):
        schedule = SimpleNamespace(
            active=True,
            next_scheduled_date=date(2026, 9, 15),
            repeat_interval_workdays=5,
        )
        window = service.ProgramWindow(
            start=date(2026, 9, 13),
            end=date(2026, 9, 19),
        )

        projected = service._projection_dates(
            schedule,
            window,
            date(2026, 9, 22),
        )

        self.assertEqual(projected, [])

    def test_projection_serialization_has_no_ticket(self):
        schedule = SimpleNamespace(
            id=91,
            target_type="EQUIPO",
            sucursal_id=13,
            inventario_id=501,
            building_classification_id=None,
            actividad="Mantenimiento recurrente",
            repeat_interval_workdays=5,
            estimated_duration_minutes=45,
            sucursal=SimpleNamespace(sucursal="Papalote Tijuana"),
            inventario=SimpleNamespace(
                codigo_interno="13CESLE01",
                nombre="Escalera",
            ),
            building_classification=None,
        )

        payload = service._serialize_projection(
            schedule,
            date(2026, 9, 30),
        )

        self.assertEqual(payload["item_kind"], "RECURRENCE_PROJECTION")
        self.assertIsNone(payload["ticket_id"])
        self.assertEqual(payload["schedule_id"], 91)
        self.assertEqual(payload["fecha_trabajo"], "2026-09-30")
        self.assertEqual(payload["codigo_equipo"], "13CESLE01")
        self.assertEqual(payload["repeat_interval_workdays"], 5)
        self.assertEqual(payload["estimated_duration_minutes"], 45)


if __name__ == "__main__":
    unittest.main()
