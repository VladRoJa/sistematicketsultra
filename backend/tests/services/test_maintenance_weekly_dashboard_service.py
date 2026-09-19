from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from app.services import maintenance_weekly_dashboard_service as service


class MaintenanceWeeklyDashboardServiceTest(unittest.TestCase):
    def _ticket(
        self,
        *,
        ticket_id,
        maintenance_type,
        created,
        original_program=None,
        current_program=None,
        original_due=None,
        current_due=None,
        validated=None,
        finalized=None,
    ):
        return SimpleNamespace(
            id=ticket_id,
            tipo_mantenimiento=maintenance_type,
            fecha_creacion=created,
            fecha_programada_original=original_program,
            fecha_programada_actual=current_program,
            fecha_compromiso_original=original_due,
            fecha_solucion=current_due,
            fecha_validacion_cierre=validated,
            fecha_finalizado=finalized,
            historial_fechas=[],
            origen_correctivo="REACTIVO",
        )

    def _dt(self, day):
        return datetime(
            2026,
            9,
            day,
            18,
            0,
            tzinfo=timezone.utc,
        )

    def test_week_is_sunday_to_saturday(self):
        windows = service._week_windows(
            service.date(2026, 9, 23),
            1,
        )

        self.assertEqual(
            windows[0].start,
            service.date(2026, 9, 20),
        )
        self.assertEqual(
            windows[0].end,
            service.date(2026, 9, 26),
        )

    def test_preventive_requires_manager_validation_for_strict_compliance(self):
        week = service.WeekWindow(
            start=service.date(2026, 9, 20),
            end=service.date(2026, 9, 26),
        )
        executed_not_validated = self._ticket(
            ticket_id=1,
            maintenance_type="PREVENTIVO",
            created=self._dt(18),
            original_program=self._dt(21),
            current_program=self._dt(21),
            validated=None,
            finalized=self._dt(21),
        )
        validated_late = self._ticket(
            ticket_id=2,
            maintenance_type="PREVENTIVO",
            created=self._dt(18),
            original_program=self._dt(22),
            current_program=self._dt(29),
            validated=self._dt(29),
            finalized=self._dt(22),
        )
        validated_on_time = self._ticket(
            ticket_id=3,
            maintenance_type="PREVENTIVO",
            created=self._dt(18),
            original_program=self._dt(23),
            current_program=self._dt(23),
            validated=self._dt(24),
            finalized=self._dt(23),
        )

        card = service._build_week_card(
            week,
            [
                executed_not_validated,
                validated_late,
                validated_on_time,
            ],
            [],
        )

        self.assertEqual(card["preventive"]["programmed"]["count"], 3)
        self.assertEqual(
            card["preventive"]["validated_on_time"]["ticket_ids"],
            [3],
        )
        self.assertEqual(
            card["preventive"]["eventually_validated"]["count"],
            2,
        )
        self.assertEqual(
            card["preventive"]["reprogrammed"]["ticket_ids"],
            [2],
        )
        self.assertEqual(
            card["preventive"]["missed"]["ticket_ids"],
            [1],
        )
        self.assertEqual(
            (
                card["preventive"]["validated_on_time"]["count"]
                + card["preventive"]["reprogrammed"]["count"]
                + card["preventive"]["missed"]["count"]
            ),
            card["preventive"]["programmed"]["count"],
        )
        self.assertEqual(
            card["preventive"]["pending_now"]["ticket_ids"],
            [1],
        )
        self.assertEqual(
            card["preventive"]["strict_compliance_percent"],
            33.33,
        )
        self.assertEqual(
            card["preventive"]["current_progress_percent"],
            66.67,
        )

    def test_corrective_uses_exact_original_commitment_and_tracks_demand(self):
        week = service.WeekWindow(
            start=service.date(2026, 9, 20),
            end=service.date(2026, 9, 26),
        )
        reprogrammed_but_late = self._ticket(
            ticket_id=10,
            maintenance_type="CORRECTIVO",
            created=self._dt(20),
            original_due=self._dt(22),
            current_due=self._dt(29),
            validated=self._dt(25),
        )
        demand_not_due_this_week = self._ticket(
            ticket_id=11,
            maintenance_type="CORRECTIVO",
            created=self._dt(23),
            original_due=self._dt(30),
            current_due=self._dt(30),
            validated=None,
        )
        fulfilled_on_commitment = self._ticket(
            ticket_id=12,
            maintenance_type="CORRECTIVO",
            created=self._dt(21),
            original_due=self._dt(24),
            current_due=self._dt(24),
            validated=self._dt(24),
        )

        card = service._build_week_card(
            week,
            [],
            [
                reprogrammed_but_late,
                demand_not_due_this_week,
                fulfilled_on_commitment,
            ],
        )

        self.assertEqual(
            set(card["corrective"]["due"]["ticket_ids"]),
            {10, 12},
        )
        self.assertEqual(
            card["corrective"]["validated_on_time"]["ticket_ids"],
            [12],
        )
        self.assertEqual(
            card["corrective"]["reprogrammed"]["ticket_ids"],
            [10],
        )
        self.assertEqual(
            card["corrective"]["missed"]["ticket_ids"],
            [],
        )
        self.assertEqual(
            (
                card["corrective"]["validated_on_time"]["count"]
                + card["corrective"]["reprogrammed"]["count"]
                + card["corrective"]["missed"]["count"]
            ),
            card["corrective"]["due"]["count"],
        )
        self.assertEqual(
            set(card["corrective"]["demand"]["ticket_ids"]),
            {10, 11, 12},
        )
        self.assertEqual(
            card["corrective"]["fulfillment_percent"],
            50.0,
        )

    def test_manager_rejection_without_date_change_is_not_reprogramming(self):
        original = self._dt(22)
        ticket = self._ticket(
            ticket_id=14,
            maintenance_type="CORRECTIVO",
            created=self._dt(20),
            original_due=original,
            current_due=original,
            validated=None,
        )
        ticket.historial_fechas = [
            {
                "evento": "rechazo_cierre_gerente",
                "fecha": original.isoformat(),
                "fechaCambio": self._dt(23).isoformat(),
                "motivo": "Corregir evidencia",
            }
        ]

        self.assertFalse(
            service._ticket_was_reprogrammed(
                ticket,
                service._corrective_original_due(ticket),
                service._corrective_current_due(ticket),
            )
        )
        self.assertEqual(
            service._serialize_reprogram_history(ticket),
            [],
        )

    def test_reprogrammed_history_does_not_disappear_if_date_returns_to_original(self):
        original = self._dt(22)
        ticket = self._ticket(
            ticket_id=13,
            maintenance_type="CORRECTIVO",
            created=self._dt(20),
            original_due=original,
            current_due=original,
            validated=None,
        )
        ticket.historial_fechas = [
            {
                "evento": "reprogramacion_mantenimiento",
                "fecha_anterior": original.isoformat(),
                "fecha": self._dt(24).isoformat(),
                "fechaCambio": self._dt(21).isoformat(),
            },
            {
                "evento": "reprogramacion_mantenimiento",
                "fecha_anterior": self._dt(24).isoformat(),
                "fecha": original.isoformat(),
                "fechaCambio": self._dt(22).isoformat(),
            },
        ]

        self.assertTrue(
            service._ticket_was_reprogrammed(
                ticket,
                service._corrective_original_due(ticket),
                service._corrective_current_due(ticket),
            )
        )

    def test_backlog_is_historical_at_start_and_end_of_week(self):
        week = service.WeekWindow(
            start=service.date(2026, 9, 20),
            end=service.date(2026, 9, 26),
        )
        carried_and_still_open = self._ticket(
            ticket_id=20,
            maintenance_type="CORRECTIVO",
            created=self._dt(18),
            original_due=self._dt(19),
            current_due=self._dt(19),
            validated=None,
        )
        carried_closed_midweek = self._ticket(
            ticket_id=21,
            maintenance_type="CORRECTIVO",
            created=self._dt(18),
            original_due=self._dt(20),
            current_due=self._dt(20),
            validated=self._dt(22),
        )
        new_open = self._ticket(
            ticket_id=22,
            maintenance_type="CORRECTIVO",
            created=self._dt(23),
            original_due=self._dt(24),
            current_due=self._dt(24),
            validated=None,
        )

        card = service._build_week_card(
            week,
            [],
            [
                carried_and_still_open,
                carried_closed_midweek,
                new_open,
            ],
        )

        self.assertEqual(
            set(card["backlog"]["start"]["ticket_ids"]),
            {20, 21},
        )
        self.assertEqual(
            set(card["backlog"]["end"]["ticket_ids"]),
            {20, 22},
        )
        self.assertEqual(card["backlog"]["delta"], 0)


    def test_due_as_of_uses_only_reprogramming_known_by_that_week(self):
        ticket = self._ticket(
            ticket_id=30,
            maintenance_type="CORRECTIVO",
            created=self._dt(10),
            original_due=self._dt(21),
            current_due=self._dt(30),
            validated=None,
        )
        ticket.historial_fechas = [
            {
                "fecha": self._dt(30).isoformat(),
                "fechaCambio": self._dt(25).isoformat(),
                "motivo": "Refacción pendiente",
            }
        ]

        self.assertEqual(
            service._corrective_due_as_of(
                ticket,
                service.date(2026, 9, 23),
            ),
            service.date(2026, 9, 21),
        )
        self.assertEqual(
            service._corrective_due_as_of(
                ticket,
                service.date(2026, 9, 26),
            ),
            service.date(2026, 9, 30),
        )

    def test_overdue_backlog_and_origin_segmentation(self):
        week = service.WeekWindow(
            start=service.date(2026, 9, 20),
            end=service.date(2026, 9, 26),
        )

        reactive = self._ticket(
            ticket_id=40,
            maintenance_type="CORRECTIVO",
            created=self._dt(20),
            original_due=self._dt(21),
            current_due=self._dt(21),
            validated=None,
        )
        detected = self._ticket(
            ticket_id=41,
            maintenance_type="CORRECTIVO",
            created=self._dt(21),
            original_due=self._dt(22),
            current_due=self._dt(22),
            validated=None,
        )
        detected.origen_correctivo = "DETECTADO_EN_PREVENTIVO"

        card = service._build_week_card(
            week,
            [],
            [reactive, detected],
        )

        self.assertEqual(
            card["corrective"]["demand_reactive"]["ticket_ids"],
            [40],
        )
        self.assertEqual(
            card["corrective"]["demand_detected_preventive"]["ticket_ids"],
            [41],
        )
        self.assertEqual(
            set(card["backlog"]["overdue_end"]["ticket_ids"]),
            {40, 41},
        )

    def test_reprogram_history_serializer_exposes_reason_and_new_date(self):
        ticket = self._ticket(
            ticket_id=50,
            maintenance_type="CORRECTIVO",
            created=self._dt(20),
            original_due=self._dt(22),
            current_due=self._dt(29),
            validated=None,
        )
        ticket.historial_fechas = [
            {
                "evento": "reprogramacion_mantenimiento",
                "fecha_anterior": self._dt(22).isoformat(),
                "fecha": self._dt(29).isoformat(),
                "motivo_key": "FALTA_TECNICO",
                "motivo": "Falta de técnico",
                "comentario": "Cobertura",
                "cambiadoPor": "MANT_BOSS",
                "fechaCambio": self._dt(21).isoformat(),
            }
        ]

        rows = service._serialize_reprogram_history(ticket)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["motivo"], "Falta de técnico")
        self.assertEqual(rows[0]["comentario"], "Cobertura")
        self.assertEqual(rows[0]["actor"], "MANT_BOSS")
        self.assertIn("2026-09-29", rows[0]["fecha_nueva"])

    def test_aging_bucket_contract(self):
        self.assertEqual(service._aging_bucket(1), "1_7")
        self.assertEqual(service._aging_bucket(7), "1_7")
        self.assertEqual(service._aging_bucket(8), "8_14")
        self.assertEqual(service._aging_bucket(15), "15_30")
        self.assertEqual(service._aging_bucket(31), "31_PLUS")


if __name__ == "__main__":
    unittest.main()
