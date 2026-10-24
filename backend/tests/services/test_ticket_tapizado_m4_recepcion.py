"""M4: contrato de recepción parcial por aparato y permisos de edición."""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.ticket_tapizado_recepcion_service import (
    RecepcionTapizadoError,
    actualizar_recepcion_tapizado,
    puede_editar_recepcion_tapizado,
    resumen_recepcion_tapizado,
    validar_recepcion_completa,
)


def vinculo(equipo_id, recibido=False):
    return SimpleNamespace(
        inventario_id=equipo_id,
        recibido_en_utc=(
            datetime(2026, 10, 23, 22, 0, tzinfo=timezone.utc)
            if recibido else None
        ),
        recibido_por=("ADMICORP" if recibido else None),
        inventario=SimpleNamespace(
            id=equipo_id, nombre=f"Banco {equipo_id}",
            codigo_interno=f"EQ{equipo_id}",
        ),
    )


def ticket(cantidad=6, recibidos=0, estado="en progreso", tipo="TAPIZADO"):
    return SimpleNamespace(
        id=3209, tipo_trabajo=tipo, estado=estado, departamento_id=1,
        sucursal_id_destino=7, sucursal_id=8, asignado_a="TECNICO_A",
        historial_fechas=[],
        aparatos_asociados=[
            vinculo(i, i <= recibidos)
            for i in range(1, cantidad + 1)
        ],
    )


def actor(rol="ADMINISTRADOR", depto=1, sucursal=7, usuario="ADMICORP"):
    return SimpleNamespace(
        id=101, rol=rol, department_id=depto, sucursal_id=sucursal,
        username=usuario,
    )


class RecepcionTapizadoM4Test(unittest.TestCase):
    def test_seis_aparatos_tres_recibidos_es_parcial(self):
        avance = resumen_recepcion_tapizado(ticket(recibidos=3))
        self.assertEqual(avance["total"], 6)
        self.assertEqual(avance["recibidos"], 3)
        self.assertEqual(avance["pendientes"], 3)
        self.assertEqual(avance["porcentaje"], 50)
        self.assertTrue(avance["parcial"])
        self.assertFalse(avance["completo"])

    def test_nadie_recibido_seis_pendientes(self):
        avance = resumen_recepcion_tapizado(ticket())
        self.assertEqual((avance["recibidos"], avance["porcentaje"]), (0, 0))
        self.assertFalse(avance["completo"])

    def test_todos_recibidos_habilita_cierre(self):
        t = ticket(recibidos=6)
        self.assertTrue(resumen_recepcion_tapizado(t)["completo"])
        self.assertIsNone(validar_recepcion_completa(t))

    def test_cero_vinculos_no_permite_cerrar(self):
        with self.assertRaises(RecepcionTapizadoError):
            validar_recepcion_completa(ticket(cantidad=0))

    def test_parcial_impide_solicitar_cierre(self):
        with self.assertRaisesRegex(RecepcionTapizadoError, "3 de 6"):
            validar_recepcion_completa(ticket(recibidos=3))

    def test_ticket_legacy_conserva_cierre(self):
        self.assertIsNone(validar_recepcion_completa(ticket(tipo=None)))
        self.assertIsNone(resumen_recepcion_tapizado(ticket(tipo=None)))

    def test_registro_individual_con_historial_y_usuario(self):
        t = ticket(recibidos=2)
        guardar_historial = Mock()
        avance = actualizar_recepcion_tapizado(
            t, inventario_id=3, recibido=True, actor="ADMICORP",
            marca_historial=guardar_historial,
        )
        self.assertEqual(avance["recibidos"], 3)
        equipo = t.aparatos_asociados[2]
        self.assertIsNotNone(equipo.recibido_en_utc)
        self.assertEqual(equipo.recibido_por, "ADMICORP")
        evento = t.historial_fechas[0]
        self.assertEqual(evento["tipo"], "tapizado_recepcion_aparato_v1")
        self.assertEqual(evento["inventario_id"], 3)
        self.assertEqual(evento["codigo_interno"], "EQ3")
        self.assertFalse(evento["recibido_anterior"])
        self.assertTrue(evento["recibido_nuevo"])
        guardar_historial.assert_called_once_with(t, "historial_fechas")

    def test_reversion_con_motivo_resta_uno_y_audita(self):
        t = ticket(recibidos=3)
        avance = actualizar_recepcion_tapizado(
            t, inventario_id=3, recibido=False, actor="GERENTE",
            motivo="Se registró por error",
            marca_historial=lambda *_: None,
        )
        self.assertEqual(avance["recibidos"], 2)
        self.assertIsNone(t.aparatos_asociados[2].recibido_en_utc)
        self.assertIsNone(t.aparatos_asociados[2].recibido_por)
        self.assertEqual(t.historial_fechas[0]["motivo"], "Se registró por error")
        self.assertTrue(t.historial_fechas[0]["recibido_anterior"])
        self.assertFalse(t.historial_fechas[0]["recibido_nuevo"])

    def test_reversion_sin_motivo_no_modifica_estado(self):
        t = ticket(recibidos=3)
        with self.assertRaisesRegex(RecepcionTapizadoError, "motivo"):
            actualizar_recepcion_tapizado(
                t, inventario_id=1, recibido=False, actor="ADMICORP",
                marca_historial=lambda *_: None,
            )
        self.assertEqual(resumen_recepcion_tapizado(t)["recibidos"], 3)

    def test_no_puede_cambiar_mismo_estado(self):
        with self.assertRaisesRegex(RecepcionTapizadoError, "ya tiene"):
            actualizar_recepcion_tapizado(
                ticket(), inventario_id=2, recibido=False, actor="ADMICORP",
                marca_historial=lambda *_: None,
            )

    def test_no_admite_equipo_ajeno_al_ticket(self):
        with self.assertRaisesRegex(RecepcionTapizadoError, "no pertenece"):
            actualizar_recepcion_tapizado(
                ticket(), inventario_id=99, recibido=True, actor="ADMICORP",
                marca_historial=lambda *_: None,
            )

    def test_rechaza_tipo_no_booleano_y_nota_larga(self):
        with self.assertRaises(RecepcionTapizadoError):
            actualizar_recepcion_tapizado(
                ticket(), inventario_id=1, recibido="true", actor="ADMICORP"
            )
        with self.assertRaises(RecepcionTapizadoError):
            actualizar_recepcion_tapizado(
                ticket(), inventario_id=1, recibido=True, actor="ADMICORP",
                motivo="x" * 501,
            )

    def test_por_validar_y_finalizado_no_se_editan(self):
        for estado in ("por_validar", "finalizado"):
            t = ticket(estado=estado)
            with self.assertRaises(RecepcionTapizadoError):
                actualizar_recepcion_tapizado(
                    t, inventario_id=1, recibido=True, actor="ADMICORP",
                    marca_historial=lambda *_: None,
                )

    def test_admin_edita_y_lector_global_no(self):
        self.assertTrue(puede_editar_recepcion_tapizado(actor(), ticket()))
        self.assertFalse(puede_editar_recepcion_tapizado(
            actor(rol="LECTOR_GLOBAL"), ticket()
        ))

    def test_gerente_solo_sucursal_destino(self):
        self.assertTrue(puede_editar_recepcion_tapizado(
            actor(rol="GERENTE", sucursal=7), ticket()
        ))
        self.assertFalse(puede_editar_recepcion_tapizado(
            actor(rol="GERENTE", sucursal=8), ticket()
        ))

    def test_tecnico_solo_tickets_asignados_de_mantenimiento(self):
        self.assertTrue(puede_editar_recepcion_tapizado(
            actor(rol="TECNICO", usuario="TECNICO_A"), ticket()
        ))
        self.assertFalse(puede_editar_recepcion_tapizado(
            actor(rol="TECNICO", usuario="OTRO"), ticket()
        ))
        self.assertFalse(puede_editar_recepcion_tapizado(
            actor(rol="TECNICO", depto=7, usuario="TECNICO_A"), ticket()
        ))

    def test_coordinacion_y_jefe_regional_solo_con_scope_comprobado_en_ruta(self):
        self.assertTrue(puede_editar_recepcion_tapizado(
            actor(rol="COORDINADOR_MANTENIMIENTO"), ticket(),
            es_coordinador=True,
        ))
        self.assertTrue(puede_editar_recepcion_tapizado(
            actor(rol="MANTENIMIENTO", usuario="MANTENIMIENTO"), ticket(),
            es_jefe_regional=True,
        ))
        self.assertFalse(puede_editar_recepcion_tapizado(
            actor(rol="COORDINADOR_MANTENIMIENTO"), ticket(),
        ))

    def test_finalizado_ni_admin_puede_editar(self):
        self.assertFalse(puede_editar_recepcion_tapizado(
            actor(), ticket(estado="finalizado")
        ))


if __name__ == "__main__":
    unittest.main()
