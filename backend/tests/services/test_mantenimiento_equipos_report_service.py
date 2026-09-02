from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from openpyxl import load_workbook

from app.services import mantenimiento_equipos_report_service as report


class _Expression:
    def __init__(self, predicate):
        self.predicate = predicate

    def __or__(self, other):
        return _Expression(
            lambda row: self.predicate(row) or other.predicate(row)
        )

    def __and__(self, other):
        return _Expression(
            lambda row: self.predicate(row) and other.predicate(row)
        )


class _Column:
    def __init__(self, name):
        self.name = name

    def __eq__(self, value):
        return _Expression(lambda row: getattr(row, self.name) == value)

    def isnot(self, value):
        return _Expression(lambda row: getattr(row, self.name) is not value)

    def is_(self, value):
        return _Expression(lambda row: getattr(row, self.name) is value)

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
        if any(expression is False for expression in expressions):
            self.rows = []
            return self

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
    branch_id=10,
    branch_name="TIJUANA CENTRO",
):
    current_family = SimpleNamespace(key="PESO_LIBRE", nombre="Peso Libre")
    inventory = SimpleNamespace(
        id=apparatus_id,
        nombre="Caminadora comercial",
        codigo_interno="11CCJW21",
        familia_equipo=current_family,
        familia_equipo_id=6,
    )
    branch = SimpleNamespace(sucursal=branch_name)
    return SimpleNamespace(
        id=ticket_id,
        descripcion="Ruido durante operación",
        estado=state,
        departamento_id=1,
        aparato_id=apparatus_id,
        fecha_creacion=created_at
        or datetime(2025, 5, 1, 18, 0, tzinfo=timezone.utc),
        fecha_solucion=None,
        sucursal_id=branch_id,
        sucursal_id_destino=branch_id,
        sucursal_destino=branch,
        sucursal=None,
        inventario=inventory,
        familia_equipo_id=family_id,
        familia_equipo=family,
        falla_mantenimiento=failure,
        condicion_operativa=condition,
        historial_fechas=history or [],
    )


def _fake_ticket_model(rows):
    return SimpleNamespace(
        query=_Query(rows),
        inventario="inventario",
        familia_equipo="familia_equipo",
        falla_mantenimiento="falla_mantenimiento",
        sucursal="sucursal",
        sucursal_destino="sucursal_destino",
        departamento_id=_Column("departamento_id"),
        aparato_id=_Column("aparato_id"),
        familia_equipo_id=_Column("familia_equipo_id"),
        estado=_Column("estado"),
        sucursal_id=_Column("sucursal_id"),
        sucursal_id_destino=_Column("sucursal_id_destino"),
        id=_Column("id"),
    )


class MantenimientoEquiposReportServiceTest(unittest.TestCase):
    def test_region_resuelve_solo_ids_actuales_desde_la_fuente_oficial(self):
        region_query = MagicMock()
        region_query.filter.return_value.first.return_value = SimpleNamespace(
            id=1
        )
        assignment_query = MagicMock()
        assignment_rows = (
            assignment_query.with_entities.return_value
            .filter.return_value
            .all
        )
        assignment_rows.return_value = [
            (11,),
            (10,),
            (11,),
        ]
        region_model = SimpleNamespace(
            query=region_query,
            id=_Column("id"),
            is_active=_Column("is_active"),
        )
        assignment_model = SimpleNamespace(
            query=assignment_query,
            sucursal_id=_Column("sucursal_id"),
            region_id=_Column("region_id"),
            is_current=_Column("is_current"),
        )

        with (
            patch.object(report, "SuiteRegionORM", region_model),
            patch.object(
                report,
                "SuiteSucursalRegionAssignmentORM",
                assignment_model,
            ),
        ):
            branch_ids = report._obtener_sucursales_ids_region(1)

        self.assertEqual(branch_ids, [10, 11])

    def test_region_inexistente_se_rechaza_desde_la_fuente_oficial(self):
        region_query = MagicMock()
        region_query.filter.return_value.first.return_value = None
        region_model = SimpleNamespace(
            query=region_query,
            id=_Column("id"),
            is_active=_Column("is_active"),
        )

        with patch.object(report, "SuiteRegionORM", region_model):
            with self.assertRaisesRegex(
                report.RegionReporteNoEncontradaError,
                "no existe o está inactiva",
            ):
                report._obtener_sucursales_ids_region(999999)

    def test_consulta_incluye_activo_con_aparato_o_snapshot_historico(self):
        active_2025 = _ticket(1)

        snapshot = SimpleNamespace(
            key="PESO_INTEGRADO",
            nombre="Peso Integrado",
        )
        historical_without_apparatus = _ticket(
            2,
            apparatus_id=None,
            family=snapshot,
            family_id=6,
        )

        without_apparatus_or_snapshot = _ticket(
            3,
            apparatus_id=None,
            family=None,
            family_id=None,
        )

        finalized = _ticket(4, state="finalizado")

        other_department = _ticket(5)
        other_department.departamento_id = 7

        fake_ticket_model = _fake_ticket_model(
            [
                active_2025,
                historical_without_apparatus,
                without_apparatus_or_snapshot,
                finalized,
                other_department,
            ]
        )

        with (
            patch.object(report, "Ticket", fake_ticket_model),
            patch.object(report, "joinedload", side_effect=lambda value: value),
        ):
            selected = report.obtener_tickets_reporte()

        self.assertEqual(
            [ticket.id for ticket in selected],
            [1, 2],
        )

    def test_todo_conserva_todos_los_tickets_permitidos_en_el_xlsx(self):
        tickets = [
            _ticket(6, branch_id=10, branch_name="REGIÓN A - SUCURSAL 1"),
            _ticket(7, branch_id=20, branch_name="REGIÓN B - SUCURSAL 1"),
        ]
        user = SimpleNamespace(id=20)
        fake_ticket_model = _fake_ticket_model(tickets)

        with (
            patch.object(report, "Ticket", fake_ticket_model),
            patch.object(report, "joinedload", side_effect=lambda value: value),
            patch.object(
                report,
                "filtrar_tickets_por_usuario",
                return_value=fake_ticket_model.query,
            ) as filter_by_user,
        ):
            selected = report.obtener_tickets_reporte(user=user)

        workbook = load_workbook(report.construir_reporte_xlsx(selected))
        branch_names = {
            row[6]
            for row in list(
                workbook["Tickets"].iter_rows(values_only=True)
            )[1:]
        }

        self.assertEqual(
            branch_names,
            {"REGIÓN A - SUCURSAL 1", "REGIÓN B - SUCURSAL 1"},
        )
        filter_by_user.assert_called_once_with(user)

    def test_region_incluye_todas_sus_sucursales_en_el_xlsx(self):
        tickets = [
            _ticket(8, branch_id=10, branch_name="REGIÓN A - SUCURSAL 1"),
            _ticket(9, branch_id=11, branch_name="REGIÓN A - SUCURSAL 2"),
        ]
        user = SimpleNamespace(id=20)
        fake_ticket_model = _fake_ticket_model(tickets)

        with (
            patch.object(report, "Ticket", fake_ticket_model),
            patch.object(report, "joinedload", side_effect=lambda value: value),
            patch.object(
                report,
                "filtrar_tickets_por_usuario",
                return_value=fake_ticket_model.query,
            ),
            patch.object(
                report,
                "_obtener_sucursales_ids_region",
                return_value=[10, 11],
            ),
        ):
            selected = report.obtener_tickets_reporte(user=user, region_id=1)

        workbook = load_workbook(report.construir_reporte_xlsx(selected))
        branch_names = {
            row[6]
            for row in list(
                workbook["Tickets"].iter_rows(values_only=True)
            )[1:]
        }

        self.assertEqual(
            branch_names,
            {"REGIÓN A - SUCURSAL 1", "REGIÓN A - SUCURSAL 2"},
        )

    def test_region_excluye_tickets_de_otra_region_en_el_xlsx(self):
        tickets = [
            _ticket(40, branch_id=10, branch_name="REGIÓN A - SUCURSAL 1"),
            _ticket(41, branch_id=20, branch_name="REGIÓN B - SUCURSAL 1"),
        ]
        user = SimpleNamespace(id=20)
        fake_ticket_model = _fake_ticket_model(tickets)

        with (
            patch.object(report, "Ticket", fake_ticket_model),
            patch.object(report, "joinedload", side_effect=lambda value: value),
            patch.object(
                report,
                "filtrar_tickets_por_usuario",
                return_value=fake_ticket_model.query,
            ),
            patch.object(
                report,
                "_obtener_sucursales_ids_region",
                return_value=[10],
            ),
        ):
            selected = report.obtener_tickets_reporte(user=user, region_id=1)

        workbook = load_workbook(report.construir_reporte_xlsx(selected))
        branch_names = [
            row[6]
            for row in list(
                workbook["Tickets"].iter_rows(values_only=True)
            )[1:]
        ]

        self.assertEqual(branch_names, ["REGIÓN A - SUCURSAL 1"])

    def test_region_respeta_el_scope_previamente_autorizado_del_usuario(self):
        allowed = _ticket(
            50,
            branch_id=10,
            branch_name="REGIÓN A - SUCURSAL PERMITIDA",
        )
        denied = _ticket(
            51,
            branch_id=11,
            branch_name="REGIÓN A - SUCURSAL NO PERMITIDA",
        )
        user = SimpleNamespace(id=20)
        fake_ticket_model = _fake_ticket_model([allowed, denied])

        with (
            patch.object(report, "Ticket", fake_ticket_model),
            patch.object(report, "joinedload", side_effect=lambda value: value),
            patch.object(
                report,
                "filtrar_tickets_por_usuario",
                return_value=_Query([allowed]),
            ) as filter_by_user,
            patch.object(
                report,
                "_obtener_sucursales_ids_region",
                return_value=[10, 11],
            ),
        ):
            selected = report.obtener_tickets_reporte(user=user, region_id=1)

        workbook = load_workbook(report.construir_reporte_xlsx(selected))
        branch_names = [
            row[6]
            for row in list(
                workbook["Tickets"].iter_rows(values_only=True)
            )[1:]
        ]

        self.assertEqual(branch_names, ["REGIÓN A - SUCURSAL PERMITIDA"])
        filter_by_user.assert_called_once_with(user)

    def test_region_valida_sin_sucursales_genera_xlsx_vacio_con_headers(self):
        user = SimpleNamespace(id=20)
        fake_ticket_model = _fake_ticket_model([])

        with (
            patch.object(report, "Ticket", fake_ticket_model),
            patch.object(report, "joinedload", side_effect=lambda value: value),
            patch.object(
                report,
                "filtrar_tickets_por_usuario",
                return_value=fake_ticket_model.query,
            ),
            patch.object(
                report,
                "_obtener_sucursales_ids_region",
                return_value=[],
            ),
        ):
            selected = report.obtener_tickets_reporte(user=user, region_id=1)

        workbook = load_workbook(report.construir_reporte_xlsx(selected))

        self.assertEqual(selected, [])
        self.assertEqual(workbook["Tickets"].max_row, 1)
        self.assertEqual(
            tuple(
                cell.value
                for cell in workbook["Tickets"][1]
            ),
            report.TICKETS_HEADERS,
        )

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

    def test_resumen_muestra_sin_clasificar_y_total_cuadra(self):
        snapshot = SimpleNamespace(
            key="CAMINADORA",
            nombre="Caminadora",
        )

        classified = _ticket(
            30,
            family=snapshot,
            family_id=1,
        )
        unclassified = _ticket(
            31,
            family=None,
            family_id=None,
            failure=None,
            condition=None,
        )

        workbook = load_workbook(
            report.construir_reporte_xlsx(
                [classified, unclassified]
            )
        )

        rows = list(
            workbook["Fallas por familia"].iter_rows(values_only=True)
        )
        headers = rows[0]
        summary = rows[1]

        self.assertEqual(headers[-1], "Sin clasificar")
        self.assertEqual(summary[1], 2)
        self.assertEqual(summary[2], 1)
        self.assertEqual(summary[-1], 1)
        self.assertEqual(
            summary[1],
            sum(value or 0 for value in summary[2:]),
        )



if __name__ == "__main__":
    unittest.main()
