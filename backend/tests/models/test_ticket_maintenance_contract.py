import unittest
from unittest.mock import patch

from app.models.ticket_model import Ticket


class TicketMaintenanceContractTest(unittest.TestCase):
    def test_ticket_exposes_canonical_maintenance_fields(self):
        columns = Ticket.__table__.c

        expected = {
            "tipo_mantenimiento",
            "origen_correctivo",
            "fecha_compromiso_original",
            "fecha_programada_original",
            "fecha_programada_actual",
            "fecha_validacion_cierre",
            "ticket_preventivo_origen_id",
        }

        self.assertTrue(expected.issubset(set(columns.keys())))

    def test_ticket_maintenance_checks_are_declared(self):
        constraint_names = {
            constraint.name
            for constraint in Ticket.__table__.constraints
            if constraint.name
        }

        self.assertIn(
            "ck_tickets_tipo_mantenimiento",
            constraint_names,
        )
        self.assertIn(
            "ck_tickets_origen_correctivo",
            constraint_names,
        )

    def test_preventive_origin_points_to_ticket(self):
        foreign_keys = list(
            Ticket.__table__.c.ticket_preventivo_origen_id.foreign_keys
        )

        self.assertEqual(len(foreign_keys), 1)
        self.assertEqual(
            foreign_keys[0].target_fullname,
            "tickets.id",
        )

    def test_maintenance_indexes_are_declared(self):
        index_names = {
            index.name
            for index in Ticket.__table__.indexes
        }

        self.assertTrue(
            {
                "ix_tickets_tipo_mantenimiento",
                "ix_tickets_fecha_compromiso_original",
                "ix_tickets_fecha_programada_actual",
                "ix_tickets_fecha_validacion_cierre",
                "ix_tickets_ticket_preventivo_origen_id",
            }.issubset(index_names)
        )

    def test_first_corrective_commitment_is_frozen(self):
        from datetime import datetime, timezone

        first = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
        second = datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)

        ticket = Ticket(
            descripcion="Prueba",
            username="tester",
            sucursal_id=1,
            sucursal_id_destino=1,
            departamento_id=1,
            criticidad=1,
            estado="abierto",
        )

        ticket.asignar_fecha_compromiso(first)
        ticket.asignar_fecha_compromiso(second)

        self.assertEqual(ticket.tipo_mantenimiento, "CORRECTIVO")
        self.assertEqual(ticket.origen_correctivo, "REACTIVO")
        self.assertEqual(ticket.fecha_compromiso_original, first)
        self.assertEqual(ticket.fecha_solucion, second)

    def test_legacy_current_commitment_is_preserved_before_reprogramming(self):
        from datetime import datetime, timezone

        previous = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
        new_due = datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)

        ticket = Ticket(
            descripcion="Legacy",
            username="tester",
            sucursal_id=1,
            sucursal_id_destino=1,
            departamento_id=1,
            criticidad=1,
            estado="en progreso",
            fecha_solucion=previous,
            tipo_mantenimiento="CORRECTIVO",
            origen_correctivo="REACTIVO",
        )

        ticket.asignar_fecha_compromiso(new_due)

        self.assertEqual(ticket.fecha_compromiso_original, previous)
        self.assertEqual(ticket.fecha_solucion, new_due)

    def test_rejection_helper_preserves_preventive_original_when_date_is_supplied(self):
        from datetime import datetime, timezone

        original = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
        current = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)
        new_due = datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)

        ticket = Ticket(
            descripcion="Preventivo",
            username="mantenimiento",
            sucursal_id=1000,
            sucursal_id_destino=4,
            departamento_id=1,
            criticidad=1,
            estado="por_validar",
            estado_cierre="pendiente_creador",
            tipo_mantenimiento="PREVENTIVO",
            fecha_programada_original=original,
            fecha_programada_actual=current,
            fecha_solucion=None,
            historial_fechas=[],
        )

        with patch("app.models.ticket_model.db.session.commit"):
            ticket.rechazar_conformidad_creador(
                motivo="Repetir lubricación",
                nueva_fecha_compromiso=new_due,
                actor_username="ADMIN_TEST",
            )

        self.assertEqual(ticket.fecha_programada_original, original)
        self.assertEqual(ticket.fecha_programada_actual, new_due)
        self.assertIsNone(ticket.fecha_solucion)
        self.assertEqual(ticket.estado, "en progreso")
        self.assertEqual(ticket.estado_cierre, "rechazado_por_gerente")

    def test_preventive_commitment_helper_does_not_reclassify(self):
        from datetime import datetime, timezone

        due = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)

        ticket = Ticket(
            descripcion="Prueba PM",
            username="tester",
            sucursal_id=1,
            sucursal_id_destino=1,
            departamento_id=1,
            criticidad=1,
            estado="abierto",
            tipo_mantenimiento="PREVENTIVO",
        )

        ticket.asignar_fecha_compromiso(due)

        self.assertEqual(ticket.tipo_mantenimiento, "PREVENTIVO")
        self.assertIsNone(ticket.origen_correctivo)
        self.assertIsNone(ticket.fecha_compromiso_original)
        self.assertEqual(ticket.fecha_solucion, due)


if __name__ == "__main__":
    unittest.main()
