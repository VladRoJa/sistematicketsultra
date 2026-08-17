from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app.services.ticket_validation_summary_service as service


class _Expression:
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def matches(self, row):
        return bool(self.evaluator(row))


class _Field:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return _Expression(
            lambda row: getattr(row, self.name, None) == other
        )

    def __le__(self, other):
        return _Expression(
            lambda row: (
                getattr(row, self.name, None) is not None
                and getattr(row, self.name) <= other
            )
        )

    def isnot(self, other):
        return _Expression(
            lambda row: getattr(row, self.name, None) is not other
        )


class _LowerField:
    def __init__(self, field):
        self.field = field

    def __eq__(self, other):
        expected = str(other or "").lower()

        return _Expression(
            lambda row: str(
                getattr(row, self.field.name, "") or ""
            ).lower() == expected
        )


class _FakeFunc:
    @staticmethod
    def lower(field):
        return _LowerField(field)


class _FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *conditions):
        rows = self.rows

        for condition in conditions:
            if isinstance(condition, _Expression):
                rows = [
                    row
                    for row in rows
                    if condition.matches(row)
                ]
            elif condition is False:
                rows = []
            elif condition is True:
                continue
            else:
                raise AssertionError(
                    f"Condición de prueba no soportada: {condition!r}"
                )

        return _FakeQuery(rows)

    def order_by(self, *args, **kwargs):
        return self

    def count(self):
        return len(self.rows)


class _FakeTicket:
    estado = _Field("estado")
    username = _Field("username")
    fecha_finalizado = _Field("fecha_finalizado")

    query = _FakeQuery([])


class TicketValidationSummaryCreatorScopeTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(
            2026, 8, 16, 20, 0, tzinfo=timezone.utc
        )

        self.rows = [
            SimpleNamespace(
                id=1,
                username="usuario_tienda",
                estado="por_validar",
                sucursal_id_destino=25,
                fecha_finalizado=self.now - timedelta(hours=1),
            ),
            SimpleNamespace(
                id=2,
                username="usuario_otra_sucursal",
                estado="por_validar",
                sucursal_id_destino=30,
                fecha_finalizado=self.now - timedelta(hours=1),
            ),
            SimpleNamespace(
                id=3,
                username="usuario_tienda",
                estado="finalizado",
                sucursal_id_destino=25,
                fecha_finalizado=self.now - timedelta(hours=1),
            ),
        ]

        _FakeTicket.query = _FakeQuery(self.rows)

        self.ticket_patcher = patch.object(
            service,
            "Ticket",
            _FakeTicket,
        )
        self.func_patcher = patch.object(
            service,
            "func",
            _FakeFunc(),
        )

        self.ticket_patcher.start()
        self.func_patcher.start()

    def tearDown(self):
        self.func_patcher.stop()
        self.ticket_patcher.stop()

    def test_tienda_creator_receives_only_own_pending_ticket(self):
        user = SimpleNamespace(
            username="USUARIO_TIENDA",
            rol="TIENDA",
            sucursal_id=25,
            department_id=None,
        )

        summary = service.get_ticket_validation_summary_for_user(
            user,
            now_utc=self.now,
        )

        self.assertEqual(summary.total_por_validar, 1)
        self.assertEqual(summary.mayores_48h, 0)
        self.assertEqual(summary.mayores_72h, 0)
        self.assertEqual(summary.severity, "normal")

    def test_other_tienda_same_branch_does_not_receive_foreign_pending_ticket(self):
        user = SimpleNamespace(
            username="otro_usuario_tienda",
            rol="TIENDA",
            sucursal_id=25,
            department_id=None,
        )

        summary = service.get_ticket_validation_summary_for_user(
            user,
            now_utc=self.now,
        )

        self.assertEqual(summary.total_por_validar, 0)
        self.assertEqual(summary.mayores_48h, 0)
        self.assertEqual(summary.mayores_72h, 0)
        self.assertEqual(summary.severity, "none")

    def test_gerente_preserves_existing_branch_scope(self):
        user = SimpleNamespace(
            username="gerente_sucursal",
            rol="GERENTE",
            sucursal_id=25,
            department_id=None,
        )

        gerente_scope = _FakeQuery(
            [
                row
                for row in self.rows
                if row.sucursal_id_destino == 25
            ]
        )

        with patch.object(
            service,
            "filtrar_tickets_por_usuario",
            return_value=gerente_scope,
        ) as filtro_mock:
            summary = service.get_ticket_validation_summary_for_user(
                user,
                now_utc=self.now,
            )

        filtro_mock.assert_called_once_with(user)

        self.assertEqual(summary.total_por_validar, 1)
        self.assertEqual(summary.mayores_48h, 0)
        self.assertEqual(summary.mayores_72h, 0)
        self.assertEqual(summary.severity, "normal")


if __name__ == "__main__":
    unittest.main()
