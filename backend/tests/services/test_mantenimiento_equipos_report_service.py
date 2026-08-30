from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from app.services import mantenimiento_equipos_report_service as report


class _Expression:
    def __init__(self, predicate):
        self.predicate = predicate


class _Column:
    def __init__(self, name):
        self.name = name

    def __eq__(self, value):
        return _Expression(lambda row: getattr(row, self.name) == value)

    def isnot(self, value):
        return _Expression(lambda row: getattr(row, self.name) is not value)

    def in_(self, values):
        return _Expression(lambda row: getattr(row, self.name) in values)

    def asc(self):
        return self


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def options(self, *_args):
        return self

    def filter(self, *expressions):
        self.rows = [
            row
            for row in self.rows
            if all(expression.predicate(row) for expression in expressions)
        ]
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


def _ticket(
    ticket_id,
    *,
    family=None,
    family_id=None,
    failure=None,
    condition="TRABAJA",
    state="abierto",
    apparatus_id=90,
    created_at=None,
    history=None,
):
    current_family = SimpleNamespace(key="PESO_LIBRE", nombre="Peso Libre")
    inventory = SimpleNamespace(
        id=apparatus_id,
        nombre="Caminadora comercial",
        codigo_interno="11CCJW21",
        familia_equipo=current_family,
        familia_equipo_id=6,
    )
    branch = SimpleNamespace(sucursal="TIJUANA CENTRO")
    return SimpleNamespace(
        id=ticket_id,
        descripcion="Ruido durante operación",
        estado=state,
        departamento_id=1,
        aparato_id=apparatus_id,
        fecha_creacion=created_at
        or datetime(2025, 5, 1, 18, 0, tzinfo=timezone.utc),
        fecha_solucion=None,
        sucursal_id_destino=10,
        sucursal_destino=branch,
        sucursal=None,
        inventario=inventory,
        familia_equipo_id=family_id,
        familia_equipo=family,
        falla_mantenimiento=failure,
        condicion_operativa=condition,
        historial_fechas=history or [],
    )


class MantenimientoEquiposReportServiceTest(unittest.TestCase):
    def test_consulta_incluye_activo_2025_y_excluye_finalizado_y_sin_aparato(self):
        active_2025 = _ticket(1)
        finalized = _ticket(2, state="finalizado")
        without_apparatus = _ticket(3, apparatus_id=None)
        other_department = _ticket(4)
        other_department.departamento_id = 7

        fake_ticket_model = SimpleNamespace(
            query=_Query(
                [active_2025, finalized, without_apparatus, other_department]
            ),
            inventario="inventario",
            familia_equipo="familia_equipo",
            falla_mantenimiento="falla_mantenimiento",
            sucursal="sucursal",
            sucursal_destino="sucursal_destino",
            departamento_id=_Column("departamento_id"),
            aparato_id=_Column("aparato_id"),
            estado=_Column("estado"),
            sucursal_id_destino=_Column("sucursal_id_destino"),
            id=_Column("id"),
        )

        with (
            patch.object(report, "Ticket", fake_ticket_model),
            patch.object(report, "joinedload", side_effect=lambda value: value),
        ):
            selected = report.obtener_tickets_reporte()

        self.assertEqual([ticket.id for ticket in selected], [1])
        self.assertEqual(selected[0].fecha_creacion.year, 2025)

    def test_reporte_usa_snapshot_y_no_familia_actual_del_aparato(self):
        snapshot = SimpleNamespace(key="CAMINADORA", nombre="Caminadora")
        failure = SimpleNamespace(nombre="Banda desgastada")
        ticket = _ticket(
            10,
            family=snapshot,
            family_id=1,
            failure=failure,
        )

        workbook = load_workbook(report.construir_reporte_xlsx([ticket]))

        tickets_row = list(workbook["Tickets"].iter_rows(values_only=True))[1]
        self.assertEqual(tickets_row[7], "Caminadora")
        self.assertEqual(workbook["Caminadoras"].max_row, 2)
        self.assertEqual(workbook["Peso Libre"].max_row, 1)

    def test_ticket_legacy_se_muestra_sin_clasificar_historico(self):
        ticket = _ticket(
            11,
            family=None,
            family_id=None,
            failure=None,
            condition=None,
        )

        workbook = load_workbook(report.construir_reporte_xlsx([ticket]))
        row = list(workbook["Tickets"].iter_rows(values_only=True))[1]

        self.assertEqual(row[7], report.LEGACY_UNCLASSIFIED_FAMILY)
        self.assertEqual(row[8], report.PENDING_CAPTURE)
        self.assertEqual(row[9], report.PENDING_CAPTURE)
        self.assertEqual(row[10], report.NO_COMMITMENT)

    def test_plan_excluye_rechazo_y_ordena_compromisos(self):
        snapshot = SimpleNamespace(key="CAMINADORA", nombre="Caminadora")
        history = [
            {
                "fechaCambio": "2026-01-03T10:00:00Z",
                "motivo": "Segundo compromiso",
            },
            {
                "fechaCambio": "2026-01-02T10:00:00Z",
                "motivo": "No aceptado por gerente",
                "tipo": "rechazo_cierre_gerente",
            },
            {
                "fechaCambio": "2026-01-01T10:00:00Z",
                "motivo": "Primer compromiso",
            },
        ]
        ticket = _ticket(12, family=snapshot, family_id=1, history=history)

        workbook = load_workbook(report.construir_reporte_xlsx([ticket]))
        row = list(workbook["Tickets"].iter_rows(values_only=True))[1]

        self.assertEqual(
            row[11],
            "Primer compromiso\nSegundo compromiso",
        )

    def test_mismo_aparato_con_dos_tickets_cuenta_dos_fallas(self):
        snapshot = SimpleNamespace(key="CAMINADORA", nombre="Caminadora")
        tickets = [
            _ticket(20, family=snapshot, family_id=1),
            _ticket(21, family=snapshot, family_id=1),
        ]

        workbook = load_workbook(report.construir_reporte_xlsx(tickets))
        summary_row = list(
            workbook["Fallas por familia"].iter_rows(values_only=True)
        )[1]

        self.assertEqual(summary_row[1], 2)
        self.assertEqual(summary_row[2], 2)
        self.assertEqual(workbook["Caminadoras"].max_row, 3)


if __name__ == "__main__":
    unittest.main()
