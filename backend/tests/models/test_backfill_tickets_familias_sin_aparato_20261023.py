import unittest

from scripts.backfill_tickets_familias_sin_aparato_20261023 import (
    CASES,
    validation_error,
)


def sample_row(ticket_id=2150):
    case = CASES[ticket_id]
    return {
        "id": ticket_id,
        "descripcion": case["description"],
        "departamento_id": 1,
        "aparato_id": None,
        "estado": "en progreso",
        "familia_equipo_id": None,
        "falla_mantenimiento_id": None,
        "condicion_operativa": None,
    }


class AuditedHistoricalFamilyBackfillTest(unittest.TestCase):
    def test_whitelist_contains_only_reviewed_tickets(self):
        self.assertEqual(set(CASES), {2150, 2151, 2652, 2941})
        self.assertEqual(CASES[2150]["family"], "PESO_INTEGRADO")
        self.assertEqual(CASES[2151]["family"], "PESO_INTEGRADO")
        self.assertEqual(CASES[2652]["family"], "SPINNING")
        self.assertEqual(CASES[2941]["family"], "ESCALADORA")

    def test_unclassified_maintenance_ticket_without_apparatus_is_eligible(self):
        ticket = sample_row()
        self.assertIsNone(validation_error(ticket, CASES[2150]))

    def test_missing_ticket_is_rejected(self):
        self.assertEqual(validation_error(None, CASES[2150]), "TICKET_NO_EXISTE")

    def test_description_change_is_rejected(self):
        ticket = sample_row()
        ticket["descripcion"] = "Otro equipo"
        self.assertEqual(validation_error(ticket, CASES[2150]), "DESCRIPCION_CAMBIO")

    def test_ticket_with_apparatus_is_rejected(self):
        ticket = sample_row()
        ticket["aparato_id"] = 1949
        self.assertEqual(validation_error(ticket, CASES[2150]), "YA_TIENE_APARATO")

    def test_existing_family_is_not_overwritten(self):
        ticket = sample_row()
        ticket["familia_equipo_id"] = 7
        self.assertEqual(validation_error(ticket, CASES[2150]), "YA_TIENE_FAMILIA")

    def test_existing_failure_or_condition_is_not_overwritten(self):
        ticket = sample_row()
        ticket["falla_mantenimiento_id"] = 14
        self.assertEqual(validation_error(ticket, CASES[2150]), "YA_TIENE_FALLA")
        ticket = sample_row()
        ticket["condicion_operativa"] = "TRABAJA"
        self.assertEqual(validation_error(ticket, CASES[2150]), "YA_TIENE_CONDICION")

    def test_closed_ticket_is_not_updated(self):
        ticket = sample_row()
        ticket["estado"] = "finalizado"
        self.assertEqual(validation_error(ticket, CASES[2150]), "ESTADO_CAMBIO")

    def test_other_department_is_not_updated(self):
        ticket = sample_row()
        ticket["departamento_id"] = 4
        self.assertEqual(validation_error(ticket, CASES[2150]), "NO_ES_MANTENIMIENTO")


if __name__ == "__main__":
    unittest.main()
