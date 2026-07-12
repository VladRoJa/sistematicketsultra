from datetime import date
import unittest
from unittest.mock import patch

from app.warehouse.services.track_forecast_service import (
    build_venta_total_forecast,
)


class TrackForecastServiceCharacterizationTest(unittest.TestCase):
    @patch(
        "app.warehouse.services.track_forecast_service._build_anchored_remaining_forecast",
        return_value={"status": "not_tested"},
    )
    @patch(
        "app.warehouse.services.track_forecast_service._build_cohort_forecast",
        return_value={"status": "not_tested"},
    )
    @patch(
        "app.warehouse.services.track_forecast_service._build_branch_drivers",
        return_value={"status": "not_tested"},
    )
    @patch(
        "app.warehouse.services.track_forecast_service._build_same_day_history",
        return_value={"status": "not_tested"},
    )
    @patch(
        "app.warehouse.services.track_forecast_service._resolve_aggregated_canonical_cutoff",
        return_value=None,
    )
    @patch(
        "app.warehouse.services.track_forecast_service._build_history_coverage",
        return_value={
            "months_count": 3,
            "first_month": "2023-07-01",
            "last_month": "2025-07-01",
            "confidence": "alta",
        },
    )
    @patch(
        "app.warehouse.services.track_forecast_service._build_historical_curve",
        return_value={
            "historical_months": 3,
            "historical_mtd_total": 300.0,
            "historical_remaining_total": 300.0,
            "historical_month_total": 600.0,
            "historical_progress_pct": 0.5,
            "confidence": "alta",
        },
    )
    @patch(
        "app.warehouse.services.track_forecast_service._resolve_goal_from_track_monthly_targets",
        return_value=(None, 0),
    )
    @patch(
        "app.warehouse.services.track_forecast_service._get_selected_mart_rows",
        return_value=[
            {
                "sucursal_canon": "TIJUANA",
                "real_mtd": 100.0,
                "ingreso_real_base_mtd": 80.0,
                "ingreso_real_agregadora_mtd": 20.0,
                "meta_faycgo_mes": None,
            }
        ],
    )
    def test_pending_goal_preserves_stable_projected_close(self, *_mocks):
        result = build_venta_total_forecast(
            track_date=date(2026, 7, 15),
            generation_mode="manual_preview",
            track_daily_version_id=1,
            scope="national",
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data_quality"]["goal_status"], "pending")

        self.assertIsNone(result["summary"]["goal_month"])
        self.assertIsNone(result["summary"]["weighted_goal_mtd"])
        self.assertIsNone(result["summary"]["gap_vs_weighted_goal"])
        self.assertIsNone(result["summary"]["gap_vs_weighted_goal_pct"])
        self.assertIsNone(result["summary"]["status_vs_goal"])

        self.assertAlmostEqual(result["summary"]["projected_close"], 200.0)
        self.assertAlmostEqual(
            result["executive_status"]["primary_metric_value"],
            200.0,
        )

        warning_codes = {warning["code"] for warning in result["warnings"]}
        self.assertIn("goal_pending", warning_codes)

        self.assertNotIn(
            "projected_close_experimental",
            result["summary"],
        )
