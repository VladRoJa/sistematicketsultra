from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import mantenimiento_equipos_routes as routes


class MantenimientoEquiposRoutesTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="mantenimiento-equipos-routes-test",
        )
        JWTManager(self.app)
        self.app.register_blueprint(
            routes.mantenimiento_equipos_bp,
            url_prefix="/api/mantenimiento-equipos",
        )

        self.actor = SimpleNamespace(
            id=20,
            username="MANTENIMIENTO",
            rol="MANTENIMIENTO",
            department_id=1,
        )
        self.ticket = SimpleNamespace(
            id=300,
            familia_equipo_id=7,
            to_dict=lambda: {"id": 300, "familia_equipo_id": 7},
        )
        self.session = MagicMock()
        self.db_patch = patch.object(
            routes,
            "db",
            SimpleNamespace(session=self.session),
        )
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def _headers(self):
        with self.app.app_context():
            token = create_access_token(identity=str(self.actor.id))
        return {"Authorization": f"Bearer {token}"}

    def _request(self, path, *, method="GET", json=None):
        with self.app.test_request_context(
            path,
            method=method,
            headers=self._headers(),
            json=json,
        ):
            return self.app.full_dispatch_request()

    def test_compromiso_hace_un_commit_y_notifica_despues(self):
        events = []
        self.session.commit.side_effect = lambda: events.append("commit")

        with (
            patch.object(routes, "_current_user", return_value=self.actor),
            patch.object(
                routes,
                "preparar_compromiso_estructurado",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("prepare") or self.ticket
                ),
            ),
            patch.object(
                routes,
                "_notify_commitment",
                side_effect=lambda *_args: events.append("notify") or [],
            ),
        ):
            response = self._request(
                "/api/mantenimiento-equipos/tickets/300/compromiso",
                method="PUT",
                json={"fecha_solucion": "2026-09-02T14:00:00Z"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(events, ["prepare", "commit", "notify"])
        self.session.commit.assert_called_once_with()
        self.session.rollback.assert_not_called()

    def test_error_revierte_snapshot_sin_cambiar_familia_actual(self):
        inventory = SimpleNamespace(familia_equipo_id=3)
        ticket = SimpleNamespace(familia_equipo_id=3)

        def fail_after_mutation(*_args, **_kwargs):
            ticket.familia_equipo_id = 7
            raise routes.MantenimientoEquiposError(
                "Falló una parte de la operación."
            )

        def rollback():
            ticket.familia_equipo_id = 3

        self.session.rollback.side_effect = rollback

        with (
            patch.object(routes, "_current_user", return_value=self.actor),
            patch.object(
                routes,
                "preparar_compromiso_estructurado",
                side_effect=fail_after_mutation,
            ),
            patch.object(routes, "_notify_commitment") as notify,
        ):
            response = self._request(
                "/api/mantenimiento-equipos/tickets/300/compromiso",
                method="PUT",
                json={"fecha_solucion": "2026-09-02T14:00:00Z"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(inventory.familia_equipo_id, 3)
        self.assertEqual(ticket.familia_equipo_id, 3)
        self.session.commit.assert_not_called()
        self.session.rollback.assert_called_once_with()
        notify.assert_not_called()

    def test_reporte_rechaza_usuario_que_no_es_admicorp(self):
        with (
            patch.object(routes, "_current_user", return_value=self.actor),
            patch.object(routes, "construir_reporte_xlsx") as build_report,
        ):
            response = self._request("/api/mantenimiento-equipos/reporte")

        self.assertEqual(response.status_code, 403)
        build_report.assert_not_called()

    def test_reporte_admicorp_devuelve_xlsx(self):
        self.actor.username = "admicorp"
        workbook = BytesIO(b"xlsx-test")

        with (
            patch.object(routes, "_current_user", return_value=self.actor),
            patch.object(
                routes,
                "construir_reporte_xlsx",
                return_value=workbook,
            ) as build_report,
        ):
            response = self._request("/api/mantenimiento-equipos/reporte")

        self.assertEqual(response.status_code, 200)
        response.direct_passthrough = False
        self.assertEqual(response.get_data(), b"xlsx-test")
        self.assertEqual(
            response.mimetype,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        build_report.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
