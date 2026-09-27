from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask

from app.routes.pm_routes import (
    _crear_bitacora,
    _crear_validacion_pm,
)
from app.utils.pm_legacy_transition import (
    legacy_operational_block,
    tickets_preventive_v1_enabled,
    transition_state_payload,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PM_ROUTES = REPOSITORY_ROOT / "backend/app/routes/pm_routes.py"
LAYOUT = REPOSITORY_ROOT / "frontend/src/app/layout/layout.component.ts"
COMPOSE = REPOSITORY_ROOT / "docker-compose.yml"


class PmLegacyTransitionTest(unittest.TestCase):
    def _app(self, enabled):
        app = Flask(__name__)
        app.config["TICKETS_PREVENTIVE_V1_ENABLED"] = enabled
        return app

    def test_flag_off_keeps_legacy_available_for_rollback(self):
        app = self._app(False)

        with app.app_context():
            self.assertFalse(tickets_preventive_v1_enabled())
            self.assertIsNone(legacy_operational_block())

            state = transition_state_payload()

        self.assertEqual(state["source_of_truth"], "PM_LEGACY")
        self.assertTrue(
            state["legacy"]["operational_writes_enabled"]
        )

    def test_flag_on_makes_tickets_source_of_truth(self):
        app = self._app(True)

        with app.app_context():
            self.assertTrue(tickets_preventive_v1_enabled())
            block = legacy_operational_block()
            state = transition_state_payload()

        self.assertEqual(block[1], 409)
        self.assertEqual(state["source_of_truth"], "TICKETS")
        self.assertFalse(
            state["legacy"]["operational_writes_enabled"]
        )
        self.assertTrue(state["legacy"]["history_readable"])

    def test_flag_on_blocks_standalone_preventive_bitacora(self):
        app = self._app(True)

        with app.app_context():
            bitacora, error = _crear_bitacora(
                {
                    "tipo_mantenimiento": "PREVENTIVO",
                },
                user_id=20,
            )

        self.assertIsNone(bitacora)
        self.assertEqual(error[1], 409)
        self.assertIn(
            "Tickets",
            error[0]["detail"],
        )

    def test_ticket_linked_bitacora_cannot_use_legacy_validation(self):
        app = self._app(True)
        ticket_linked_bitacora = SimpleNamespace(
            id=8,
            ticket_id=501,
        )

        with app.app_context():
            with patch(
                "app.routes.pm_routes.db.session.get",
                return_value=ticket_linked_bitacora,
            ):
                validation, error = _crear_validacion_pm(
                    {
                        "bitacora_pm_id": 8,
                        "decision": "VALIDADO",
                    },
                    user_id=30,
                )

        self.assertIsNone(validation)
        self.assertEqual(error[1], 409)
        self.assertEqual(error[0]["ticket_id"], 501)


class PmLegacyTransitionContractTest(unittest.TestCase):
    def _read(self, path):
        return path.read_text(encoding="utf-8")

    def test_operational_legacy_routes_are_cutover_guarded(self):
        routes = self._read(PM_ROUTES)

        assert '"/transition-state"' in routes
        assert "legacy_operational_block()" in routes
        assert "def pm_crear_configuracion" in routes
        assert "def pm_actualizar_configuracion" in routes
        assert "def pm_preventivo_dashboard" in routes
        assert "def pm_calendario" in routes

    def test_history_routes_remain_available(self):
        routes = self._read(PM_ROUTES)

        assert '"/bitacoras/<int:bitacora_pm_id>"' in routes
        assert '"/bitacoras", methods=["GET"]' in routes
        assert "legacy_operational_block()" not in routes.split(
            'def pm_listar_bitacoras',
            1,
        )[1].split(
            '@pm_bp.route("/configuraciones"',
            1,
        )[0]

    def test_menu_keeps_only_planner_and_legacy_history_after_cutover(self):
        layout = self._read(LAYOUT)

        assert "aplicarTransicionPmLegacyEnMenu" in layout
        assert "/pm/transition-state" in layout
        assert "'/maintenance-planner'" in layout
        assert "'/pm/consulta-historial'" in layout
        assert "Historial PM legacy" in layout

    def test_compose_declares_reversible_cutover_flag(self):
        compose = self._read(COMPOSE)

        assert "TICKETS_PREVENTIVE_V1_ENABLED" in compose
        assert ":-false" in compose
        assert "maintenance-preventive-scheduler:" in compose
        assert (
            "python -m app.services."
            "maintenance_preventive_scheduler_worker"
        ) in compose
        assert compose.count("TICKETS_PREVENTIVE_V1_ENABLED") >= 2


if __name__ == "__main__":
    unittest.main()
