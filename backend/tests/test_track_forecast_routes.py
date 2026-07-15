from datetime import date, datetime, timezone
from decimal import Decimal
from copy import deepcopy
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
            "goal_pace": {
                "status": "available",
                "metric_basis": "total_mtd",
                "goal_metric_basis": "total_mtd",
                "distribution_basis": "venta_total_base",
                "method": "goal_month_by_historical_progress",
                "includes_agregadoras": True,
                "aggregadoras_assumed_same_daily_shape": True,
                "comparability_note": "Distribución histórica de venta base aplicada a la meta total.",
                "goal_month": Decimal("300.00"),
                "goal_expected_mtd_at_cutoff": Decimal("150.00"),
                "real_mtd_at_cutoff": Decimal("120.00"),
                "gap_vs_goal_pace": Decimal("-30.00"),
                "gap_vs_goal_pace_pct": Decimal("-0.20"),
                "remaining_to_goal": Decimal("180.00"),
                "remaining_days": 19,
                "required_daily_average": Decimal("9.473684210526315789"),
                "projected_close": Decimal("240.00"),
                "projected_gap_to_goal": Decimal("-60.00"),
                "projected_goal_attainment_pct": Decimal("0.80"),
                "points": [
                    {
                        "day": 12,
                        "date": date(2026, 7, 12),
                        "historical_progress_pct": Decimal("0.50"),
                        "goal_expected_daily": Decimal("10.00"),
                        "goal_expected_cumulative": Decimal("150.00"),
                    }
                ],
                "projected_path": {
                    "status": "available",
                    "method": "historical_remaining_daily_weights",
                    "metric_basis": "total_mtd",
                    "points": [
                        {
                            "date": date(2026, 7, 12),
                            "projected_cumulative_total": Decimal("120.00"),
                        },
                        {
                            "date": date(2026, 7, 31),
                            "projected_cumulative_total": Decimal("240.00"),
                        },
                    ],
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
        self.assertIn("goal_pace", payload)
        self.assertEqual(payload["goal_pace"]["status"], "available")
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
        self.assertEqual(payload["goal_pace"]["goal_month"], 300.0)
        self.assertEqual(payload["goal_pace"]["points"][0]["date"], "2026-07-12")
        self.assertEqual(
            payload["goal_pace"]["projected_path"]["points"][-1][
                "projected_cumulative_total"
            ],
            240.0,
        )

    def test_branch_detail_serializes_no_goal_status(self):
        detail_payload = deepcopy(self._detail_payload())
        detail_payload["goal_pace"].update(
            {
                "status": "no_goal",
                "goal_month": None,
                "goal_expected_mtd_at_cutoff": None,
                "points": [],
                "projected_path": None,
            }
        )
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
                return_value=detail_payload,
            ),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail?track_date=2026-07-12",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["goal_pace"]["status"], "no_goal")

    def test_branch_detail_serializes_projection_unavailable_status(self):
        detail_payload = deepcopy(self._detail_payload())
        detail_payload["goal_pace"].update(
            {
                "status": "projection_unavailable",
                "projected_close": None,
                "projected_gap_to_goal": None,
                "projected_goal_attainment_pct": None,
                "projected_path": None,
            }
        )
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
                return_value=detail_payload,
            ),
        ):
            response = self.client.get(
                "/api/track/forecast/branches/tijuana/detail?track_date=2026-07-12",
                headers=self.headers,
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["goal_pace"]["status"], "projection_unavailable")
        self.assertEqual(len(payload["goal_pace"]["points"]), 1)

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
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("goal_pace", payload)
        service_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
