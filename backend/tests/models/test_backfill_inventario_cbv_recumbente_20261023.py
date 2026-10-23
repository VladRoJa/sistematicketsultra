import unittest

from scripts.backfill_inventario_cbv_recumbente_20261023 import (
    INVENTARIOS,
    normalizar_nombre,
    validar_inventario,
    validar_ticket,
)


def inventario_ejemplo():
    return {
        "id": 2452,
        "codigo_interno": "06CBVLF01",
        "nombre": "Bicicleta  Vertical",
        "tipo": "aparatos",
        "familia_equipo_id": None,
    }


def ticket_ejemplo():
    return {
        "id": 2656,
        "aparato_id": 2452,
        "departamento_id": 1,
        "estado": "en progreso",
        "familia_equipo_id": None,
    }


class BackfillInventarioBicicletaVerticalTest(unittest.TestCase):
    def test_alcance_exacto_cinco_inventarios_seis_tickets(self):
        self.assertEqual(set(INVENTARIOS), {431, 1144, 1967, 2452, 3330})
        ids = [ticket_id for _, tickets in INVENTARIOS.values() for ticket_id in tickets]
        self.assertEqual(sorted(ids), [2656, 2744, 2801, 2802, 2807, 2992])

    def test_nombre_con_doble_espacio_es_bicicleta_vertical(self):
        self.assertEqual(normalizar_nombre("Bicicleta  Vertical"), "BICICLETA VERTICAL")
        row = inventario_ejemplo()
        self.assertIsNone(validar_inventario(row, 2452, "06CBVLF01"))

    def test_inventario_ausente_no_es_elegible(self):
        self.assertEqual(validar_inventario(None, 2452, "06CBVLF01"), "INVENTARIO_NO_EXISTE")

    def test_no_acepta_codigo_diferente(self):
        row = inventario_ejemplo()
        row["codigo_interno"] = "06CBVLF02"
        self.assertEqual(validar_inventario(row, 2452, "06CBVLF01"), "CODIGO_DIFERENTE")

    def test_no_acepta_nombre_diferente(self):
        row = inventario_ejemplo()
        row["nombre"] = "Bicicleta Recumbente"
        self.assertEqual(validar_inventario(row, 2452, "06CBVLF01"), "NOMBRE_NO_ES_BICICLETA_VERTICAL")

    def test_no_acepta_tipo_producto(self):
        row = inventario_ejemplo()
        row["tipo"] = "producto"
        self.assertEqual(validar_inventario(row, 2452, "06CBVLF01"), "TIPO_NO_APARATO")

    def test_no_sobrescribe_familia_existente(self):
        row = inventario_ejemplo()
        row["familia_equipo_id"] = 5
        self.assertEqual(validar_inventario(row, 2452, "06CBVLF01"), "FAMILIA_YA_ASIGNADA")

    def test_ticket_correctamente_vinculado(self):
        self.assertIsNone(validar_ticket(ticket_ejemplo(), 2452))

    def test_ticket_ausente_se_rechaza(self):
        self.assertEqual(validar_ticket(None, 2452), "TICKET_NO_EXISTE")

    def test_ticket_otro_aparato_se_rechaza(self):
        row = ticket_ejemplo()
        row["aparato_id"] = 1111
        self.assertEqual(validar_ticket(row, 2452), "VINCULO_APARATO_CAMBIO")

    def test_ticket_otro_departamento_se_rechaza(self):
        row = ticket_ejemplo()
        row["departamento_id"] = 2
        self.assertEqual(validar_ticket(row, 2452), "DEPARTAMENTO_CAMBIO")

    def test_ticket_finalizado_se_rechaza(self):
        row = ticket_ejemplo()
        row["estado"] = "finalizado"
        self.assertEqual(validar_ticket(row, 2452), "ESTADO_CAMBIO")

    def test_no_sobrescribe_ticket_ya_clasificado(self):
        row = ticket_ejemplo()
        row["familia_equipo_id"] = 5
        self.assertEqual(validar_ticket(row, 2452), "FAMILIA_TICKET_YA_ASIGNADA")


if __name__ == "__main__":
    unittest.main()
