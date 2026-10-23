import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from scripts.reclasificar_ticket_2856_edificio_20261023 import (
    EXPECTED,
    TARGET_CATEGORY,
    error_de_clasificaciones,
    error_de_ticket,
    preparar_historial,
)


def ticket_original():
    return SimpleNamespace(**EXPECTED, historial_fechas=[{
        "tipo": "maintenance_coordination_v1",
        "fechaCambio": "2026-10-20T08:00:00+00:00",
        "motivo": "Historial original de ejemplo",
    }])


def categorias_validas():
    raiz = SimpleNamespace(id=1, nombre="Mantenimiento", departamento_id=1, activo=True)
    padre = SimpleNamespace(
        id=2, nombre="Edificio", departamento_id=1, activo=True, padre=raiz
    )
    actual = SimpleNamespace(
        id=487, nombre="Aparatos", departamento_id=1, activo=True
    )
    destino = SimpleNamespace(
        id=34,
        nombre=TARGET_CATEGORY,
        departamento_id=1,
        activo=True,
        padre=padre,
    )
    return actual, destino


class ReclasificarTicket2856Test(unittest.TestCase):
    def test_ticket_original_es_elegible(self):
        self.assertIsNone(error_de_ticket(ticket_original()))

    def test_ticket_inexistente_no_es_elegible(self):
        self.assertEqual(error_de_ticket(None), "TICKET_NO_EXISTE")

    def test_cambio_de_clasificacion_es_bloqueado(self):
        ticket = ticket_original()
        ticket.clasificacion_id = 34
        self.assertEqual(error_de_ticket(ticket), "CAMPO_CAMBIO_clasificacion_id")

    def test_cambio_de_categoria_es_bloqueado(self):
        ticket = ticket_original()
        ticket.categoria = "AC y ventilacion"
        self.assertEqual(error_de_ticket(ticket), "CAMPO_CAMBIO_categoria")

    def test_cambio_de_estado_o_responsable_es_bloqueado(self):
        ticket = ticket_original()
        ticket.estado = "en progreso"
        self.assertEqual(error_de_ticket(ticket), "CAMPO_CAMBIO_estado")
        ticket = ticket_original()
        ticket.asignado_a = "tecnico"
        self.assertEqual(error_de_ticket(ticket), "CAMPO_CAMBIO_asignado_a")

    def test_no_admite_aparato_o_diagnostico_existente(self):
        ticket = ticket_original()
        ticket.aparato_id = 15
        self.assertEqual(error_de_ticket(ticket), "CAMPO_CAMBIO_aparato_id")
        ticket = ticket_original()
        ticket.falla_mantenimiento_id = 7
        self.assertEqual(error_de_ticket(ticket), "CAMPO_CAMBIO_falla_mantenimiento_id")

    def test_cambios_descripcion_o_sucursal_se_bloquean(self):
        ticket = ticket_original()
        ticket.descripcion = ticket.descripcion.rstrip()
        self.assertEqual(error_de_ticket(ticket), "CAMPO_CAMBIO_descripcion")
        ticket = ticket_original()
        ticket.sucursal_id_destino = 5
        self.assertEqual(error_de_ticket(ticket), "CAMPO_CAMBIO_sucursal_id_destino")

    def test_clasificacion_destino_edificio_ac_es_valida(self):
        actual, destino = categorias_validas()
        self.assertIsNone(error_de_clasificaciones(actual, destino))

    def test_no_permite_destino_inactivo_u_otra_jerarquia(self):
        actual, destino = categorias_validas()
        destino.activo = False
        self.assertEqual(
            error_de_clasificaciones(actual, destino),
            "CLASIFICACION_DESTINO_CAMBIO",
        )
        actual, destino = categorias_validas()
        destino.padre.nombre = "Aparatos"
        self.assertEqual(
            error_de_clasificaciones(actual, destino),
            "JERARQUIA_EDIFICIO_CAMBIO",
        )

    def test_no_permite_origen_distinto(self):
        actual, destino = categorias_validas()
        actual.nombre = "Otro"
        self.assertEqual(
            error_de_clasificaciones(actual, destino),
            "CLASIFICACION_ACTUAL_CAMBIO",
        )

    def test_registra_antes_y_despues_sin_perder_historial(self):
        original = ticket_original().historial_fechas
        old_entry = dict(original[0])
        now = datetime(2026, 10, 23, 21, 10, tzinfo=timezone.utc)
        updated = preparar_historial(original, now)
        self.assertEqual(len(original), 1)
        self.assertEqual(len(updated), 2)
        self.assertEqual(original[0], old_entry)
        audit = next(item for item in updated if item.get("tipo") == "maintenance_reclassification_v1")
        self.assertEqual(audit["clasificacion_id_anterior"], 487)
        self.assertEqual(audit["clasificacion_id_nuevo"], 34)
        self.assertEqual(audit["categoria_nueva"], TARGET_CATEGORY)
        self.assertEqual(audit["cambiadoPor"], "script_controlado")


if __name__ == "__main__":
    unittest.main()
