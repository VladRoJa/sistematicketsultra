import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routes import ticket_routes


class RequisitoAparatoMantenimientoTest(unittest.TestCase):
    def setUp(self):
        self.catalogo_patch = patch.object(ticket_routes, "CatalogoClasificacion")
        self.inventario_patch = patch.object(ticket_routes, "InventarioGeneral")
        self.sucursal_patch = patch.object(ticket_routes, "InventarioSucursal")
        self.catalogo = self.catalogo_patch.start()
        self.inventario = self.inventario_patch.start()
        self.sucursal = self.sucursal_patch.start()

        self.aparatos = SimpleNamespace(id=487, departamento_id=1, padre=None)
        self.edificio = SimpleNamespace(id=2, departamento_id=1, padre=None)
        self.catalogo.query.get.return_value = self.aparatos
        self.inventario.query.get.return_value = SimpleNamespace(
            id=431, tipo="aparatos"
        )
        self.sucursal.query.filter_by.return_value.first.return_value = (
            SimpleNamespace(inventario_id=431, sucursal_id=4)
        )

    def tearDown(self):
        self.sucursal_patch.stop()
        self.inventario_patch.stop()
        self.catalogo_patch.stop()

    def validar(self, aparatos_id, *, departamento_id=1, clasificacion_id=487,
                sucursal_id_destino=4):
        return ticket_routes._validar_aparato_mantenimiento_creacion(
            departamento_id, clasificacion_id, aparatos_id, sucursal_id_destino
        )

    def test_mantenimiento_aparatos_no_permite_aparato_nulo(self):
        self.assertIn("Selecciona un aparato", self.validar(None))
        self.inventario.query.get.assert_not_called()

    def test_mantenimiento_aparatos_no_permite_id_vacio(self):
        self.assertIn("Selecciona un aparato", self.validar(""))
        self.assertIn("Selecciona un aparato", self.validar("   "))

    def test_mantenimiento_aparatos_no_permite_id_cero_negativo_o_booleano(self):
        for valor in (0, "0", -3, False):
            with self.subTest(valor=valor):
                self.assertIn("Selecciona un aparato", self.validar(valor))

    def test_mantenimiento_aparatos_no_permite_id_no_numerico(self):
        self.assertIn("Selecciona un aparato", self.validar("inventario-ficticio"))

    def test_no_acepta_numeros_fraccionarios_ni_cadenas_decimales(self):
        for valor in (431.5, 431.0, "431.0"):
            with self.subTest(valor=valor):
                self.assertIn("Selecciona un aparato", self.validar(valor))

    def test_aparato_valido_y_sucursal_correcta_pasa(self):
        self.assertIsNone(self.validar(431))
        self.catalogo.query.get.assert_called_with(487)
        self.inventario.query.get.assert_called_with(431)
        self.sucursal.query.filter_by.assert_called_with(
            inventario_id=431, sucursal_id=4
        )

    def test_aparato_inexistente_es_rechazado(self):
        self.inventario.query.get.return_value = None
        self.assertIn("no existe", self.validar(99999))

    def test_no_acepta_inventario_de_dispositivos(self):
        self.inventario.query.get.return_value = SimpleNamespace(tipo="dispositivos")
        self.assertIn("Aparatos", self.validar(431))

    def test_aparato_de_otra_sucursal_es_rechazado(self):
        self.sucursal.query.filter_by.return_value.first.return_value = None
        self.assertIn("no pertenece a la sucursal destino", self.validar(431))

    def test_descendientes_de_aparatos_tambien_exigen_seleccion(self):
        hijo = SimpleNamespace(id=9001, departamento_id=1, padre=self.aparatos)
        self.catalogo.query.get.return_value = hijo
        self.assertIn("Selecciona un aparato", self.validar(None, clasificacion_id=9001))

    def test_edificio_no_exige_aparato(self):
        self.catalogo.query.get.return_value = self.edificio
        self.assertIsNone(self.validar(None, clasificacion_id=2))
        self.inventario.query.get.assert_not_called()

    def test_sistemas_conserva_flujo_independiente(self):
        self.assertIsNone(self.validar(None, departamento_id=7, clasificacion_id=487))
        self.catalogo.query.get.assert_not_called()

    def test_mantenimiento_con_aparato_explicito_sin_clasificacion_verifica_vinculo(self):
        self.assertIsNone(self.validar(431, clasificacion_id=None))
        self.sucursal.query.filter_by.assert_called_once_with(
            inventario_id=431, sucursal_id=4
        )

    def test_ciclo_anomalo_en_catalogo_no_bloquea(self):
        nodo = SimpleNamespace(id=123, departamento_id=1, padre=None)
        nodo.padre = nodo
        self.catalogo.query.get.return_value = nodo
        self.assertIsNone(self.validar(None, clasificacion_id=123))


if __name__ == "__main__":
    unittest.main()
