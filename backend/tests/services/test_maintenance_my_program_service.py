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


if __name__ == "__main__":
    unittest.main()
