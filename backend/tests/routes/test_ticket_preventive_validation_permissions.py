from types import SimpleNamespace
import unittest

from app.routes.ticket_routes import _puede_validar_cierre_gerente


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


if __name__ == "__main__":
    unittest.main()
