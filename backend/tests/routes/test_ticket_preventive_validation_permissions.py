from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app import create_app

from app.routes.ticket_routes import (
    _apply_maintenance_type_filter,
    _maintenance_commitment_change_error,
    _preventive_close_requirement_error,
    _puede_validar_cierre_gerente,
    cierre_gerente_desde_cero,
)


class TicketPreventiveValidationPermissionsTest(unittest.TestCase):
    def _ticket(self, *, tipo="PREVENTIVO", creator="MANTENIMIENTO", branch=4):
        return SimpleNamespace(
            username=creator,
            tipo_mantenimiento=tipo,
            sucursal_id=branch,
            sucursal_id_destino=branch,
        )

    def test_preventive_creator_cannot_validate_own_ticket(self):
        user = SimpleNamespace(
            username="MANTENIMIENTO",
            rol="MANTENIMIENTO",
            sucursal_id=1000,
        )

        self.assertFalse(
            _puede_validar_cierre_gerente(user, self._ticket())
        )

    def test_branch_manager_can_validate_preventive(self):
        user = SimpleNamespace(
            username="GERENTE_VILLAS",
            rol="GERENTE",
            sucursal_id=4,
        )

        self.assertTrue(
            _puede_validar_cierre_gerente(user, self._ticket(branch=4))
        )

    def test_other_branch_manager_cannot_validate_preventive(self):
        user = SimpleNamespace(
            username="GERENTE_OTRA",
            rol="GERENTE",
            sucursal_id=5,
        )

        self.assertFalse(
            _puede_validar_cierre_gerente(user, self._ticket(branch=4))
        )

    def test_admin_can_validate_preventive(self):
        user = SimpleNamespace(
            username="ADMICORP",
            rol="ADMINISTRADOR",
            sucursal_id=1000,
        )

        self.assertTrue(
            _puede_validar_cierre_gerente(user, self._ticket())
        )

    def test_existing_non_preventive_creator_rule_is_preserved(self):
        user = SimpleNamespace(
            username="CREADOR",
            rol="RECEPCIONISTA",
            sucursal_id=4,
        )

        self.assertTrue(
            _puede_validar_cierre_gerente(
                user,
                self._ticket(tipo="CORRECTIVO", creator="CREADOR", branch=4),
            )
        )


class TicketMaintenanceTypeFilterTest(unittest.TestCase):
    def test_preventive_filter_applies_maintenance_scope(self):
        query = MagicMock()
        query.filter.return_value = query

        result = _apply_maintenance_type_filter(
            query,
            "preventivo",
        )

        self.assertIs(result, query)
        query.filter.assert_called_once()

        args = query.filter.call_args.args
        self.assertEqual(len(args), 2)
        self.assertIn(
            "tickets.departamento_id",
            str(args[0]),
        )
        self.assertIn(
            "tickets.tipo_mantenimiento",
            str(args[1]),
        )
        self.assertIn(
            "PREVENTIVO",
            args[1].compile().params.values(),
        )

    def test_corrective_filter_keeps_legacy_nulls_in_maintenance(self):
        query = MagicMock()
        query.filter.return_value = query

        result = _apply_maintenance_type_filter(
            query,
            "CORRECTIVO",
        )

        self.assertIs(result, query)
        query.filter.assert_called_once()

        args = query.filter.call_args.args
        self.assertEqual(len(args), 2)
        self.assertIn(
            "tickets.departamento_id",
            str(args[0]),
        )
        self.assertIn(
            "CORRECTIVO",
            args[1].compile().params.values(),
        )
        self.assertIn(
            "IS NULL",
            str(args[1]).upper(),
        )

    def test_invalid_maintenance_type_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "PREVENTIVO o CORRECTIVO",
        ):
            _apply_maintenance_type_filter(
                MagicMock(),
                "OTRO",
            )


class TicketMaintenanceCommitmentGuardTest(unittest.TestCase):
    def test_first_corrective_commitment_is_allowed(self):
        ticket = SimpleNamespace(
            departamento_id=1,
            tipo_mantenimiento="CORRECTIVO",
            fecha_solucion=None,
        )
        due = __import__("datetime").datetime(
            2026,
            9,
            20,
            14,
            0,
            tzinfo=__import__("datetime").timezone.utc,
        )

        self.assertIsNone(
            _maintenance_commitment_change_error(ticket, due)
        )

    def test_existing_corrective_commitment_requires_audited_reprogram(self):
        from datetime import datetime, timezone

        ticket = SimpleNamespace(
            departamento_id=1,
            tipo_mantenimiento="CORRECTIVO",
            fecha_solucion=datetime(
                2026,
                9,
                20,
                14,
                0,
                tzinfo=timezone.utc,
            ),
        )
        new_due = datetime(
            2026,
            9,
            27,
            14,
            0,
            tzinfo=timezone.utc,
        )

        message = _maintenance_commitment_change_error(
            ticket,
            new_due,
        )

        self.assertIn("reprogramación auditada", message)

    def test_preventive_rejects_fecha_solucion_semantics(self):
        from datetime import datetime, timezone

        ticket = SimpleNamespace(
            departamento_id=1,
            tipo_mantenimiento="PREVENTIVO",
            fecha_solucion=None,
        )

        message = _maintenance_commitment_change_error(
            ticket,
            datetime(
                2026,
                9,
                20,
                14,
                0,
                tzinfo=timezone.utc,
            ),
        )

        self.assertIn("preventivos", message.lower())


class TicketPreventiveCloseRequirementsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()

    def _ticket(self):
        return SimpleNamespace(
            id=88,
            tipo_mantenimiento="PREVENTIVO",
        )

    def _query(self, first_value):
        query = MagicMock()
        query.filter.return_value = query
        query.first.return_value = first_value
        return query

    def test_preventive_requires_bitacora(self):
        with self.app.app_context():
            with patch(
                "app.routes.ticket_routes.PmBitacoraORM.query",
                self._query(None),
            ):
                message = _preventive_close_requirement_error(
                    self._ticket()
                )

        self.assertIn("bitácora", message)

    def test_preventive_with_bitacora_is_ready_without_evidence(self):
        with self.app.app_context():
            with patch(
                "app.routes.ticket_routes.PmBitacoraORM.query",
                self._query(SimpleNamespace(id=1)),
            ):
                message = _preventive_close_requirement_error(
                    self._ticket()
                )

        self.assertIsNone(message)

    def test_preventive_with_bitacora_and_evidence_is_ready(self):
        with self.app.app_context():
            with (
                patch(
                    "app.routes.ticket_routes.PmBitacoraORM.query",
                    self._query(SimpleNamespace(id=1)),
                ),
                patch(
                    "app.routes.ticket_routes.TicketAttachmentORM.query",
                    self._query(SimpleNamespace(id=2)),
                ),
            ):
                message = _preventive_close_requirement_error(
                    self._ticket()
                )

        self.assertIsNone(message)


class TicketPreventiveCleanupCloseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()

    def test_preventive_cannot_use_manager_cleanup_close(self):
        ticket = SimpleNamespace(
            id=77,
            tipo_mantenimiento="PREVENTIVO",
            estado="abierto",
            fecha_finalizado=None,
        )
        user = SimpleNamespace(
            id=1,
            username="GERENTE",
            rol="GERENTE",
            sucursal_id=4,
        )

        with self.app.test_request_context(
            "/api/tickets/cierre/gerente-desde-cero/77",
            method="POST",
            json={"motivo": "Limpieza"},
        ):
            with (
                patch(
                    "app.routes.ticket_routes.get_jwt_identity",
                    return_value=1,
                ),
                patch(
                    "app.routes.ticket_routes.UserORM.get_by_id",
                    return_value=user,
                ),
                patch(
                    "app.routes.ticket_routes.Ticket.query_class.get",
                    return_value=ticket,
                ),
                patch(
                    "app.routes.ticket_routes._puede_cerrar_ticket_desde_cero",
                    return_value=True,
                ),
            ):
                response, status = (
                    cierre_gerente_desde_cero
                    .__wrapped__
                    .__wrapped__(77)
                )

        self.assertEqual(status, 400)
        self.assertIn(
            "preventivo",
            response.get_json()["mensaje"].lower(),
        )


if __name__ == "__main__":
    unittest.main()
