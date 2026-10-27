"""Seguridad de CAP-V1 producción: no abre navegador, no usa credenciales."""
import unittest

from scripts.training.production_readonly import (
    PROD_ACK, PROD_ORIGIN, demo_preflight, request_allowed,
    validate_production_target,
)


class ProductionReadonlyGateTests(unittest.TestCase):
    def test_target_must_be_exact_production_with_manual_ack(self):
        self.assertEqual(
            validate_production_target(PROD_ORIGIN, PROD_ACK, 123), PROD_ORIGIN,
        )
        for url, ack, ticket in (
            ("http://suiteultragym.com", PROD_ACK, 123),
            ("https://suiteultragym.com.attacker.test", PROD_ACK, 123),
            ("https://suiteultragym.com/#/login", PROD_ACK, 123),
            ("https://suiteultragym.com/", PROD_ACK, 123),
            (PROD_ORIGIN, "SI", 123),
            (PROD_ORIGIN, PROD_ACK, 0),
        ):
            with self.subTest(url=url, ack=ack, ticket=ticket):
                with self.assertRaises(ValueError):
                    validate_production_target(url, ack, ticket)

    def test_network_only_allows_reads_and_initial_login(self):
        home = PROD_ORIGIN + "/#/main/ver-tickets"
        endpoint = PROD_ORIGIN + "/api/tickets/tapizado/123/recepciones-lote"
        self.assertTrue(request_allowed(home, "GET", login_phase=False))
        self.assertTrue(request_allowed(PROD_ORIGIN + "/api/tickets/all", "GET", login_phase=False))
        self.assertTrue(
            request_allowed(PROD_ORIGIN + "/api/auth/login", "POST", login_phase=True)
        )
        for url, method, login_phase in (
            (PROD_ORIGIN + "/api/auth/login", "POST", False),
            (endpoint, "PATCH", False),
            (PROD_ORIGIN + "/api/tickets/cierre/solicitar/123", "POST", False),
            (PROD_ORIGIN + "/api/tickets/create", "POST", True),
            (PROD_ORIGIN + "/api/tickets/123", "DELETE", True),
            (PROD_ORIGIN + "/api/auth/refresh", "POST", False),
            ("https://other.example/api/tickets/all", "GET", False),
            ("http://suiteultragym.com/api/tickets/all", "GET", False),
            ("https://suiteultragym.com.evil.com/", "GET", False),
            (PROD_ORIGIN + "/api/auth/login?unexpected=1", "POST", True),
        ):
            with self.subTest(method=method, url=url):
                self.assertFalse(request_allowed(url, method, login_phase=login_phase))

    def test_preflight_requires_account_and_ticket_in_real_demo(self):
        user = {"rol": "GERENTE", "sucursal_id": 321}
        branches = [{"sucursal_id": 321, "sucursal": "ULTRA DEMO", "is_demo": True}]
        tickets = [{
            "id": 222, "sucursal_id_destino": 321,
            "tipo_trabajo": "TAPIZADO",
            "aparatos": [{"id": 1}, {"id": 2}, {"id": 3}],
        }]
        got = demo_preflight(user, branches, tickets, 222)
        self.assertEqual(got["branch_id"], 321)
        self.assertEqual(got["aparatos"], 3)
        for changed_user, changed_branches, changed_tickets, message in (
            ({"rol": "ADMINISTRADOR", "sucursal_id": 321}, branches, tickets, "rol"),
            ({"rol": "GERENTE", "sucursal_id": 999}, branches, tickets, "ULTRA DEMO"),
            (user, [{**branches[0], "is_demo": False}], tickets, "ULTRA DEMO"),
            (user, branches, [{**tickets[0], "sucursal_id_destino": 99}], "ULTRA DEMO"),
            (user, branches, [{**tickets[0], "tipo_trabajo": None}], "Tapizado"),
            (user, branches, [{**tickets[0], "aparatos": [{"id": 1}]}], "Tapizado"),
            (user, branches, tickets + [{
                "id": 223, "sucursal_id_destino": 99,
            }], "otras sucursales"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    demo_preflight(changed_user, changed_branches, changed_tickets, 222)


if __name__ == "__main__":
    unittest.main()
