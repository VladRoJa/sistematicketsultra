"""M3: filtros, roll-out e informes multiaparato sin duplicar tickets."""

import unittest
from types import SimpleNamespace

from flask import Flask
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.ticket_model import Ticket
from app.models.inventario import InventarioGeneral
from app.routes import ticket_routes
from app.services import mantenimiento_report_service as report
from app.services import mantenimiento_equipos_report_service as legacy
from app.utils.ticket_aparatos_filters import (
    ticket_relacionado_con_aparato,
    ticket_relacionado_con_alguno,
)


def equipo(equipo_id, codigo, nombre):
    return SimpleNamespace(
        inventario_id=equipo_id,
        inventario=SimpleNamespace(
            id=equipo_id, codigo_interno=codigo, nombre=nombre,
        ),
    )


class TapizadoM3BackendTest(unittest.TestCase):
    def test_filtro_un_aparato_utiliza_exists_no_join(self):
        stmt = select(Ticket.id).where(ticket_relacionado_con_aparato(12))
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        self.assertIn("tickets.aparato_id =", sql)
        self.assertIn("EXISTS (SELECT 1", sql)
        self.assertIn("ticket_aparatos", sql)
        self.assertNotIn(" JOIN ", sql)

    def test_filtro_varios_aparatos_utiliza_exists_no_join(self):
        stmt = select(Ticket.id).where(ticket_relacionado_con_alguno([12, 13]))
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        self.assertIn("tickets.aparato_id IN", sql)
        self.assertIn("ticket_aparatos.inventario_id IN", sql)
        self.assertIn("EXISTS", sql)
        self.assertNotIn(" JOIN ", sql)

    def test_filtro_equipo_inventario_correlacionado(self):
        stmt = select(InventarioGeneral.id).join(
            Ticket, ticket_relacionado_con_aparato(InventarioGeneral.id)
        )
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        self.assertIn("inventario_general.id", sql)
        self.assertIn("ticket_aparatos", sql)

    def test_reporte_muestra_nombres_y_codigos_multiples(self):
        t = SimpleNamespace(
            tipo_trabajo="TAPIZADO",
            aparato_id=101,
            familia_equipo_id=None,
            aparatos_asociados=[
                equipo(101, "EQ-101", "Press"),
                equipo(102, "EQ-102", "Curl"),
            ],
        )
        self.assertIn("Press, Curl", report._subject_name(t))
        self.assertEqual(report._equipment_code(t), "EQ-101, EQ-102")

    def test_reporte_no_duplica_vinculos_repetidos(self):
        t = SimpleNamespace(
            tipo_trabajo="TAPIZADO",
            aparato_id=101,
            familia_equipo_id=None,
            aparatos_asociados=[
                equipo(101, "EQ-101", "Press"),
                equipo(101, "EQ-101", "Press"),
                equipo(102, "EQ-102", "Curl"),
            ],
        )
        self.assertEqual(len(report._equipos_tapizado(t)), 2)
        self.assertEqual(report._equipment_code(t), "EQ-101, EQ-102")

    def test_reporte_legacy_muestra_todos_los_aparatos_sin_filas_extra(self):
        t = SimpleNamespace(
            tipo_trabajo="TAPIZADO",
            aparato_id=101,
            inventario=SimpleNamespace(nombre="Press", codigo_interno="EQ-101"),
            aparatos_asociados=[
                equipo(101, "EQ-101", "Press"),
                equipo(102, "EQ-102", "Curl"),
            ],
        )
        self.assertEqual(legacy._equipment_name(t), "Press, Curl")
        self.assertEqual(legacy._equipment_code(t), "EQ-101, EQ-102")
        self.assertEqual(len(legacy._related_apparatus(t)), 2)

    def test_disponibilidad_del_backend_por_defecto_apagada(self):
        app = Flask(__name__)
        with app.app_context():
            resp, status = ticket_routes.tapizado_disponible.__wrapped__()
            self.assertEqual(status, 200)
            self.assertFalse(resp.get_json()["habilitado"])

    def test_disponibilidad_encendida_solo_con_config_backend(self):
        app = Flask(__name__)
        app.config["TICKETS_TAPIZADO_MULTI_ENABLED"] = True
        with app.app_context():
            resp, status = ticket_routes.tapizado_disponible.__wrapped__()
            self.assertEqual(status, 200)
            self.assertTrue(resp.get_json()["habilitado"])


if __name__ == "__main__":
    unittest.main()
