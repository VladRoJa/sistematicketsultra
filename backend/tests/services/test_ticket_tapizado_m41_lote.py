"""M4.1: confirmación de lote atómico de recepciones."""

import unittest
from unittest.mock import Mock

from app.services.ticket_tapizado_recepcion_service import (
    RecepcionTapizadoError,
    actualizar_recepciones_lote_tapizado,
    resumen_recepcion_tapizado,
)
from tests.services.test_ticket_tapizado_m4_recepcion import ticket


def cambio(equipo_id, recibido, anterior=False, motivo=None):
    return {
        "inventario_id": equipo_id,
        "recibido": recibido,
        "estado_anterior": anterior,
        "motivo": motivo,
    }


class LoteTapizadoM41Test(unittest.TestCase):
    def test_tres_de_seis_se_registran_con_un_unico_envio(self):
        t = ticket()
        flag = Mock()
        avance = actualizar_recepciones_lote_tapizado(
            t,
            cambios=[cambio(i, True) for i in (1, 2, 3)],
            actor="ADMICORP",
            marca_historial=flag,
        )
        self.assertEqual((avance["recibidos"], avance["pendientes"]), (3, 3))
        self.assertEqual(len(t.historial_fechas), 3)
        self.assertTrue(all(x["cambiadoPor"] == "ADMICORP" for x in t.historial_fechas))
        self.assertEqual(flag.call_count, 3)

    def test_abierto_bloquea_lote_completo_aunque_haya_5_de_6(self):
        t = ticket(estado="abierto", recibidos=5)
        flag = Mock()
        with self.assertRaisesRegex(RecepcionTapizadoError, "En progreso"):
            actualizar_recepciones_lote_tapizado(
                t, cambios=[cambio(6, True)],
                actor="ADMICORP", marca_historial=flag,
            )
        self.assertEqual(resumen_recepcion_tapizado(t)["recibidos"], 5)
        self.assertEqual(t.historial_fechas, [])
        flag.assert_not_called()

    def test_abierto_no_puede_revertir_recepcion_anterior(self):
        t = ticket(estado="abierto", recibidos=2)
        with self.assertRaisesRegex(RecepcionTapizadoError, "En progreso"):
            actualizar_recepciones_lote_tapizado(
                t, cambios=[cambio(2, False, anterior=True, motivo="Error de registro")],
                actor="ADMICORP", marca_historial=lambda *_: None,
            )
        self.assertEqual(resumen_recepcion_tapizado(t)["recibidos"], 2)

    def test_un_cambio_invalido_no_altera_ningun_aparato(self):
        t = ticket()
        flag = Mock()
        with self.assertRaisesRegex(RecepcionTapizadoError, "no pertenece"):
            actualizar_recepciones_lote_tapizado(
                t,
                cambios=[cambio(1, True), cambio(999, True)],
                actor="ADMICORP",
                marca_historial=flag,
            )
        self.assertEqual(resumen_recepcion_tapizado(t)["recibidos"], 0)
        self.assertEqual(t.historial_fechas, [])
        flag.assert_not_called()

    def test_reversion_sin_motivo_no_procesa_otros_cambios(self):
        t = ticket(recibidos=1)
        with self.assertRaisesRegex(RecepcionTapizadoError, "motivo"):
            actualizar_recepciones_lote_tapizado(
                t,
                cambios=[cambio(2, True), cambio(1, False, anterior=True)],
                actor="ADMICORP",
                marca_historial=lambda *_: None,
            )
        self.assertEqual(resumen_recepcion_tapizado(t)["recibidos"], 1)
        self.assertFalse(t.aparatos_asociados[1].recibido_en_utc)

    def test_reversion_con_motivo_y_nueva_recepcion(self):
        t = ticket(recibidos=1)
        avance = actualizar_recepciones_lote_tapizado(
            t,
            cambios=[
                cambio(1, False, anterior=True, motivo="Llegó dañado"),
                cambio(2, True),
            ],
            actor="GERENTE",
            marca_historial=lambda *_: None,
        )
        self.assertEqual(avance["recibidos"], 1)
        self.assertEqual(len(t.historial_fechas), 2)

    def test_obsoleto_rechaza_lote_entero(self):
        t = ticket(recibidos=1)
        with self.assertRaisesRegex(RecepcionTapizadoError, "Actualiza"):
            actualizar_recepciones_lote_tapizado(
                t,
                cambios=[cambio(2, True), cambio(1, False, anterior=False, motivo="error")],
                actor="ADMICORP", marca_historial=lambda *_: None,
            )
        self.assertEqual(resumen_recepcion_tapizado(t)["recibidos"], 1)

    def test_duplicado_rechaza_lote_entero(self):
        t = ticket()
        with self.assertRaisesRegex(RecepcionTapizadoError, "repitas"):
            actualizar_recepciones_lote_tapizado(
                t,
                cambios=[cambio(1, True), cambio(1, True)],
                actor="ADMICORP", marca_historial=lambda *_: None,
            )
        self.assertEqual(resumen_recepcion_tapizado(t)["recibidos"], 0)

    def test_vacio_y_mas_de_cincuenta_rechazados(self):
        for cambios in ([], [cambio(i, True) for i in range(1, 52)]):
            with self.assertRaisesRegex(RecepcionTapizadoError, "entre 1 y 50"):
                actualizar_recepciones_lote_tapizado(
                    ticket(), cambios=cambios, actor="ADMICORP",
                )

    def test_rechaza_estado_no_booleano(self):
        for cambio_invalido in (
            {"inventario_id": 1, "recibido": "true", "estado_anterior": False},
            {"inventario_id": 1, "recibido": True, "estado_anterior": "false"},
            {"inventario_id": True, "recibido": True, "estado_anterior": False},
        ):
            with self.assertRaises(RecepcionTapizadoError):
                actualizar_recepciones_lote_tapizado(
                    ticket(), cambios=[cambio_invalido], actor="ADMICORP",
                )

    def test_no_registra_en_ticket_finalizado(self):
        with self.assertRaisesRegex(RecepcionTapizadoError, "en progreso"):
            actualizar_recepciones_lote_tapizado(
                ticket(estado="finalizado"),
                cambios=[cambio(1, True)], actor="ADMICORP",
            )


if __name__ == "__main__":
    unittest.main()
