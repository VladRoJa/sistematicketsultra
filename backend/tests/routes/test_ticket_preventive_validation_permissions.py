from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes.ticket_routes import (
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


class TicketPreventiveCleanupCloseTest(unittest.TestCase):
    def test_preventive_cannot_use_manager_cleanup_close(self):
        app = Flask(__name__)
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

        with app.test_request_context(
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
                    "app.routes.ticket_routes.Ticket.query.get",
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
