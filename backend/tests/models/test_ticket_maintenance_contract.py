import unittest

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


if __name__ == "__main__":
    unittest.main()
