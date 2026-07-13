from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes.track_forecast_routes import track_forecast_bp
from app.warehouse.services.track_forecast_service import (
    BranchForecastDetailConsistencyError,
)


class TrackForecastRoutesTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="route-test-secret",
        )
        JWTManager(self.app)
        self.app.register_blueprint(
            track_forecast_bp,
            url_prefix="/api/track/forecast",
        )
        with self.app.app_context():
            token = create_access_token(identity="1")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = SimpleNamespace(get=self._get)

    def _get(self, path: str, *, headers=None):
        with self.app.test_request_context(
            path,
            method="GET",
            headers=headers,
        ):
            return self.app.full_dispatch_request()

    @staticmethod
    def _resolved_version():
        timestamp = datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc)
        return SimpleNamespace(
            id=987,
            version_type="preview_operativo",
            status="success",
            generated_at_utc=timestamp,
            started_at_utc=timestamp,
            finished_at_utc=timestamp,
        )

    @staticmethod
    def _detail_payload():
        return {
            "status": "ok",
            "metadata": {
                "sucursal_canon": "TIJUANA",
                "track_date": date(2026, 7, 12),
                "target_month": date(2026, 7, 1),
                "cutoff_day": 12,
                "generation_mode": "manual_preview",
                "resolved_version": {"id": 987},
                "comparison_years": [2023, 2024, 2025],
            },
            "summary": {
                "real_mtd": 120.0,
                "projected_close": 240.0,
                "total_projection_basis": {
                    "metric_basis": "total_mtd",
                    "includes_agregadoras": True,
                    "source": "existing_stable_forecast",
                },
            },
            "series": {
                "current_track": {
                    "source_basis": "track_daily_mart",
                    "points": [
                        {
                            "date": date(2026, 7, 12),
                            "base_mtd": Decimal("100.25"),
                        }
                    ],
                },
                "historical_years": {
                    "source_basis": "venta_total_base",
                    "items": [],
                },
                "historical_expected": {
                    "source_basis": "venta_total_base",
                    "points": [],
                },
                "comparable_base_projection": {
                    "status": "available",
                    "method": "stable_historical_pace_base",
                    "projected_close": Decimal("200.50"),
                    "path": {"points": []},
                },
            },
            "data_quality": {
                "forecast": {},
                "current_series": {},
                "source_comparability": {},
                "warnings": [],
            },
        }

    def test_branch_detail_returns_complete_minimum_contract(self):
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch("app.routes.track_forecast_routes._require_track_forecast_beta_user"),
            patch(
                "app.routes.track_forecast_routes._resolve_active_forecast_branch",
                return_value="TIJUANA",
            ),
            patch(
                "app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query",
                return_value=self._resolved_version(),
            ),
            patch(
                "app.routes.track_forecast_routes.build_branch_forecast_detail",
                return_value=self._detail_payload(),
            ),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail"
                "?track_date=2026-07-12&generation_mode=manual_preview",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("summary", payload)
        self.assertIn("series", payload)
        self.assertIn("data_quality", payload)
        self.assertEqual(payload["metadata"]["resolved_version"]["id"], 987)

    def test_valid_query_params_reach_service(self):
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch("app.routes.track_forecast_routes._require_track_forecast_beta_user"),
            patch(
                "app.routes.track_forecast_routes._resolve_active_forecast_branch",
                return_value="TIJUANA",
            ),
            patch(
                "app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query",
                return_value=self._resolved_version(),
            ),
            patch(
                "app.routes.track_forecast_routes.build_branch_forecast_detail",
                return_value=self._detail_payload(),
            ) as service_mock,
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail"
                "?track_date=2026-07-12&generation_mode=manual_preview",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        service_mock.assert_called_once_with(
            sucursal_canon="TIJUANA",
            track_date=date(2026, 7, 12),
            generation_mode="manual_preview",
            track_daily_version_id=987,
        )

    def test_invalid_track_date_returns_400(self):
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch("app.routes.track_forecast_routes._require_track_forecast_beta_user"),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail?track_date=not-a-date",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["status"], "error")

    def test_invalid_generation_mode_returns_400(self):
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch("app.routes.track_forecast_routes._require_track_forecast_beta_user"),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail"
                "?track_date=2026-07-12&generation_mode=invented",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("allowed_generation_modes", response.get_json())

    def test_invalid_or_excluded_branch_returns_404(self):
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch("app.routes.track_forecast_routes._require_track_forecast_beta_user"),
            patch(
                "app.routes.track_forecast_routes._resolve_active_forecast_branch",
                side_effect=LookupError("La sucursal solicitada no existe o está excluida de Track."),
            ),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/invalida/detail?track_date=2026-07-12",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 404)

    def test_unresolved_track_version_returns_404(self):
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch("app.routes.track_forecast_routes._require_track_forecast_beta_user"),
            patch(
                "app.routes.track_forecast_routes._resolve_active_forecast_branch",
                return_value="TIJUANA",
            ),
            patch(
                "app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query",
                return_value=None,
            ),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail?track_date=2026-07-12",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 404)
        self.assertIn("versión Track", response.get_json()["message"])

    def test_track_read_guard_is_not_weakened(self):
        with patch(
            "app.routes.track_forecast_routes._require_track_read_role",
            side_effect=PermissionError("No autorizado para consultar el Track."),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail?track_date=2026-07-12",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("Track", response.get_json()["message"])

    def test_forecast_beta_guard_is_not_weakened(self):
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch(
                "app.routes.track_forecast_routes._require_track_forecast_beta_user",
                side_effect=PermissionError("No autorizado para consultar Proyección y Metas."),
            ),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail?track_date=2026-07-12",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 403)

    def test_service_value_error_uses_blueprint_convention(self):
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch("app.routes.track_forecast_routes._require_track_forecast_beta_user"),
            patch(
                "app.routes.track_forecast_routes._resolve_active_forecast_branch",
                return_value="TIJUANA",
            ),
            patch(
                "app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query",
                return_value=self._resolved_version(),
            ),
            patch(
                "app.routes.track_forecast_routes.build_branch_forecast_detail",
                side_effect=ValueError("No existe fila Track para la sucursal."),
            ),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail?track_date=2026-07-12",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("fila Track", response.get_json()["message"])

    def test_internal_consistency_error_does_not_leak_detail(self):
        secret_detail = "snapshot_id=secret-internal"
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch("app.routes.track_forecast_routes._require_track_forecast_beta_user"),
            patch(
                "app.routes.track_forecast_routes._resolve_active_forecast_branch",
                return_value="TIJUANA",
            ),
            patch(
                "app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query",
                return_value=self._resolved_version(),
            ),
            patch(
                "app.routes.track_forecast_routes.build_branch_forecast_detail",
                side_effect=BranchForecastDetailConsistencyError(secret_detail),
            ),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail?track_date=2026-07-12",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 500)
        self.assertNotIn(secret_detail, response.get_data(as_text=True))

    def test_detail_json_serializes_decimal_dates_and_datetimes(self):
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch("app.routes.track_forecast_routes._require_track_forecast_beta_user"),
            patch(
                "app.routes.track_forecast_routes._resolve_active_forecast_branch",
                return_value="TIJUANA",
            ),
            patch(
                "app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query",
                return_value=self._resolved_version(),
            ),
            patch(
                "app.routes.track_forecast_routes.build_branch_forecast_detail",
                return_value=self._detail_payload(),
            ),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail?track_date=2026-07-12",
                headers=self.headers,
            )

        payload = response.get_json()
        point = payload["series"]["current_track"]["points"][0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(point["date"], "2026-07-12")
        self.assertEqual(point["base_mtd"], 100.25)
        self.assertIsInstance(point["base_mtd"], float)
        self.assertEqual(
            payload["metadata"]["resolved_version"]["generated_at_utc"],
            "2026-07-12T18:00:00+00:00",
        )

    def test_existing_venta_total_endpoint_contract_remains_available(self):
        base_payload = {"status": "ok", "metadata": {}, "summary": {}}
        with (
            patch("app.routes.track_forecast_routes._require_track_read_role"),
            patch("app.routes.track_forecast_routes._require_track_forecast_beta_user"),
            patch(
                "app.routes.track_forecast_routes._resolve_current_track_daily_version_for_query",
                return_value=self._resolved_version(),
            ),
            patch(
                "app.routes.track_forecast_routes.build_venta_total_forecast",
                return_value=base_payload,
            ) as service_mock,
        ):
            response = self.client.get(
                "/api/track/forecast/venta-total"
                "?track_date=2026-07-12&generation_mode=manual_preview",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")
        service_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
