from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes.track_forecast_routes import track_forecast_bp
from app.warehouse.services.track_forecast_center_service import (
    ForecastCenterAuthorizationError,
    ForecastCenterNotFoundError,
    ForecastCenterValidationError,
)


class TrackForecastCenterRoutesTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="center-route-secret")
        JWTManager(self.app)
        self.app.register_blueprint(
            track_forecast_bp,
            url_prefix="/api/track/forecast",
        )
        with self.app.app_context():
            token = create_access_token(identity="1")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = SimpleNamespace(get=self._get)
        self.user = SimpleNamespace(
            id=1,
            rol="ADMIN",
            sucursal_id=1000,
            sucursales_ids=[],
        )

    def _get(self, path: str, *, headers=None):
        with self.app.test_request_context(
            path,
            method="GET",
            headers=headers,
        ):
            return self.app.full_dispatch_request()

    @staticmethod
    def _version():
        timestamp = datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)
        return SimpleNamespace(
            id=77,
            track_date=date(2026, 7, 14),
            version_type="preview_operativo",
            status="success",
            generated_at_utc=timestamp,
        )

    @staticmethod
    def _center_payload(scope="national"):
        return {
            "status": "ok",
            "context": {
                "requested_track_date": date(2026, 7, 14),
                "resolved_track_date": date(2026, 7, 14),
                "target_month": date(2026, 7, 1),
                "generation_mode": "manual_preview",
                "scope": scope,
                "scope_id": None,
                "cohort": "all",
                "user_access_scope": {
                    "type": "global",
                    "is_global": True,
                    "authorized_branch_ids": [],
                    "authorized_branch_count": 0,
                    "fallback_used": False,
                    "fallback_reason": None,
                },
                "resolved_version": {
                    "id": 77,
                    "version_type": "preview_operativo",
                    "status": "success",
                    "generated_at_utc": datetime(
                        2026, 7, 14, 18, 0, tzinfo=timezone.utc
                    ),
                },
            },
            "summary": {
                "branch_count": 2,
                "goal_month": Decimal("100.50"),
                "real_mtd": Decimal("50.25"),
                "metric_coverage": {},
            },
            "series": {"actual": {}, "required": {}, "projected": {}},
            "breakdown": {"dimension": "cohort", "items": []},
            "quality": {"status": "partial"},
        }

    @staticmethod
    def _catalogs_payload():
        return {
            "status": "ok",
            "context": {
                "user_access_scope": {
                    "type": "assigned_branches",
                    "is_global": False,
                    "authorized_branch_ids": [1, 2],
                    "authorized_branch_count": 2,
                    "fallback_used": False,
                    "fallback_reason": None,
                },
                "default_scope": "authorized_pool",
                "default_scope_id": None,
                "default_cohort": "all",
                "default_generation_mode": "manual_preview",
            },
            "capabilities": {"can_view_national": False},
            "scopes": [{"key": "authorized_pool"}],
            "cohorts": [{"key": "all", "label": "Total Ultra"}],
            "regions": [{"region_key": "R1", "authorized_branch_count": 2}],
            "branches": [
                {"sucursal_canon": "A", "sucursal_id": 1},
                {"sucursal_canon": "B", "sucursal_id": 2},
            ],
            "generation_modes": ["manual_preview", "official_closed_day"],
        }

    def _get_center(self, query=""):
        return self.client.get(
            f"/api/track/forecast/center{query}",
            headers=self.headers,
        )

    @patch("app.routes.track_forecast_routes.build_forecast_center")
    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_global_can_query_national_and_decimal_is_serialized(
        self, current_user, resolve_version, build_center
    ):
        current_user.return_value = self.user
        resolve_version.return_value = self._version()
        build_center.return_value = self._center_payload()
        response = self._get_center("?track_date=2026-07-14&scope=national")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["summary"]["goal_month"], 100.5)
        build_center.assert_called_once()

    @patch("app.routes.track_forecast_routes.build_forecast_center")
    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_global_can_query_region(self, current_user, resolve_version, build_center):
        current_user.return_value = self.user
        resolve_version.return_value = self._version()
        build_center.return_value = self._center_payload("region")
        response = self._get_center(
            "?track_date=2026-07-14&scope=region&scope_id=R1"
        )
        self.assertEqual(response.status_code, 200)

    @patch("app.routes.track_forecast_routes.build_forecast_center")
    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_global_can_query_branch(self, current_user, resolve_version, build_center):
        current_user.return_value = self.user
        resolve_version.return_value = self._version()
        build_center.return_value = self._center_payload("branch")
        response = self._get_center(
            "?track_date=2026-07-14&scope=branch&scope_id=A"
        )
        self.assertEqual(response.status_code, 200)

    @patch("app.routes.track_forecast_routes.build_forecast_center")
    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_manager_national_is_403(self, current_user, resolve_version, build_center):
        current_user.return_value = SimpleNamespace(rol="GERENTE", sucursal_id=1)
        resolve_version.return_value = self._version()
        build_center.side_effect = ForecastCenterAuthorizationError(
            "El gerente sólo puede consultar su sucursal."
        )
        response = self._get_center("?track_date=2026-07-14&scope=national")
        self.assertEqual(response.status_code, 403)

    @patch("app.routes.track_forecast_routes.build_forecast_center")
    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_manager_other_branch_is_403(self, current_user, resolve_version, build_center):
        current_user.return_value = SimpleNamespace(rol="GERENTE", sucursal_id=1)
        resolve_version.return_value = self._version()
        build_center.side_effect = ForecastCenterAuthorizationError(
            "Sucursal fuera del alcance autorizado."
        )
        response = self._get_center(
            "?track_date=2026-07-14&scope=branch&scope_id=SECRET"
        )
        self.assertEqual(response.status_code, 403)

    @patch("app.routes.track_forecast_routes.build_forecast_center")
    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_regional_can_query_authorized_pool(
        self, current_user, resolve_version, build_center
    ):
        current_user.return_value = SimpleNamespace(
            rol="GERENTE_REGIONAL", sucursal_id=1, sucursales_ids=[1, 2]
        )
        resolve_version.return_value = self._version()
        build_center.return_value = self._center_payload("authorized_pool")
        response = self._get_center(
            "?track_date=2026-07-14&scope=authorized_pool"
        )
        self.assertEqual(response.status_code, 200)

    @patch("app.routes.track_forecast_routes.build_forecast_center")
    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_regional_scope_id_manipulation_is_403(
        self, current_user, resolve_version, build_center
    ):
        current_user.return_value = SimpleNamespace(
            rol="GERENTE_REGIONAL", sucursal_id=1, sucursales_ids=[1, 2]
        )
        resolve_version.return_value = self._version()
        build_center.side_effect = ForecastCenterAuthorizationError(
            "Sucursal fuera del alcance autorizado."
        )
        response = self._get_center(
            "?track_date=2026-07-14&scope=branch&scope_id=OUTSIDE"
        )
        self.assertEqual(response.status_code, 403)

    @patch("app.routes.track_forecast_routes.build_forecast_center")
    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_unauthorized_role_is_403(self, current_user, resolve_version, build_center):
        current_user.return_value = SimpleNamespace(rol="SISTEMAS", sucursal_id=1)
        resolve_version.return_value = self._version()
        build_center.side_effect = ForecastCenterAuthorizationError("No autorizado.")
        response = self._get_center("?track_date=2026-07-14&scope=branch&scope_id=A")
        self.assertEqual(response.status_code, 403)

    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_missing_user_is_403(self, current_user):
        current_user.side_effect = PermissionError("Usuario no encontrado.")
        response = self._get_center("?track_date=2026-07-14")
        self.assertEqual(response.status_code, 403)

    def test_missing_track_date_is_400(self):
        with patch(
            "app.routes.track_forecast_routes._get_current_forecast_center_user",
            return_value=self.user,
        ):
            response = self._get_center()
        self.assertEqual(response.status_code, 400)

    def test_invalid_generation_mode_is_400(self):
        with patch(
            "app.routes.track_forecast_routes._get_current_forecast_center_user",
            return_value=self.user,
        ):
            response = self._get_center(
                "?track_date=2026-07-14&generation_mode=mixed"
            )
        self.assertEqual(response.status_code, 400)

    def test_view_and_tab_are_rejected(self):
        for parameter in ("view=summary", "tab=pace"):
            with self.subTest(parameter=parameter):
                response = self._get_center(f"?track_date=2026-07-14&{parameter}")
                self.assertEqual(response.status_code, 400)

    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_missing_common_version_is_404(self, current_user, resolve_version):
        current_user.return_value = self.user
        resolve_version.return_value = None
        response = self._get_center("?track_date=2026-07-14")
        self.assertEqual(response.status_code, 404)

    @patch("app.routes.track_forecast_routes.build_forecast_center")
    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_unknown_scope_id_is_404(self, current_user, resolve_version, build_center):
        current_user.return_value = self.user
        resolve_version.return_value = self._version()
        build_center.side_effect = ForecastCenterNotFoundError("Región no encontrada.")
        response = self._get_center(
            "?track_date=2026-07-14&scope=region&scope_id=UNKNOWN"
        )
        self.assertEqual(response.status_code, 404)

    @patch("app.routes.track_forecast_routes.build_forecast_center")
    @patch("app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_invalid_combination_is_400(self, current_user, resolve_version, build_center):
        current_user.return_value = self.user
        resolve_version.return_value = self._version()
        response = self._get_center(
            "?track_date=2026-07-14&scope=branch&scope_id=A&breakdown=cohort"
        )
        self.assertEqual(response.status_code, 400)
        build_center.assert_not_called()

    @patch("app.routes.track_forecast_routes.build_forecast_center_catalogs")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_catalogs_return_only_service_authorized_items(self, current_user, catalogs):
        current_user.return_value = self.user
        catalogs.return_value = self._catalogs_payload()
        response = self.client.get(
            "/api/track/forecast/center/catalogs", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(
            [item["sucursal_id"] for item in body["branches"]],
            [1, 2],
        )
        self.assertNotIn("999", str(body))

    @patch("app.routes.track_forecast_routes.build_forecast_center_catalogs")
    @patch("app.routes.track_forecast_routes._get_current_forecast_center_user")
    def test_catalogs_unauthorized_role_is_403(self, current_user, catalogs):
        current_user.return_value = SimpleNamespace(rol="TIENDA", sucursal_id=1)
        catalogs.side_effect = ForecastCenterAuthorizationError("No autorizado.")
        response = self.client.get(
            "/api/track/forecast/center/catalogs", headers=self.headers
        )
        self.assertEqual(response.status_code, 403)

    def test_jwt_is_required(self):
        response = self.client.get("/api/track/forecast/center/catalogs")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
