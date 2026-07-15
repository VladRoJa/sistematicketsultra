from calendar import monthrange
from contextlib import ExitStack
from datetime import date, datetime, timezone
from decimal import Decimal
from copy import deepcopy
import unittest
from unittest.mock import patch

from flask import Flask
from sqlalchemy import text

from app.extensions import db
from app.models.warehouse import (
    TrackDailyMartORM,
    TrackDailyVersionORM,
    VentaTotalSnapshotORM,
)
from app.warehouse.services.track_forecast_service import (
    BranchForecastDetailConsistencyError,
    _build_branch_goal_pace_detail,
    build_branch_calendar_aligned_daily_weights,
    build_branch_current_track_daily_values,
    build_branch_forecast_detail,
    build_branch_historical_expected_daily_curve,
    build_branch_historical_daily_series,
    build_branch_projected_daily_path,
    build_venta_total_forecast,
    select_track_daily_branch_versions,
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
        self.assertNotIn("projected_daily_path", result)


class BranchForecastDetailOrchestratorTest(unittest.TestCase):
    TRACK_DATE = date(2026, 7, 12)
    TARGET_MONTH = date(2026, 7, 1)
    BRANCH = "TIJUANA"
    VERSION_ID = 987

    def _forecast(self, *, quality_issue=None, progress=0.5):
        pace_available = quality_issue is None and progress == 0.5
        return {
            "status": "ok",
            "metadata": {
                "track_date": self.TRACK_DATE.isoformat(),
                "target_month": self.TARGET_MONTH.isoformat(),
                "generation_mode": "manual_preview",
                "track_daily_version_id": self.VERSION_ID,
                "scope": "branch",
                "branch": self.BRANCH,
                "history_window": {
                    "start": "2023-01-01",
                    "end_exclusive": "2026-01-01",
                },
            },
            "forecast_cutoff": {"status": "available"},
            "same_day_history": {"status": "available"},
            "warnings": [{"code": "fixture_warning"}],
            "data_quality": {
                "goal_status": "available",
                "history_coverage": {"confidence": "alta"},
                "branch_projection_quality_issue": quality_issue,
            },
            "summary": {
                "real_mtd": 120.0,
                "real_base_mtd": 100.0,
                "real_agregadora_mtd": 20.0,
                "historical_progress_pct": progress,
                "historical_expected_mtd": (
                    100.0 if progress == 0.5 else None
                ),
                "historical_expected_month_total": (
                    200.0 if progress == 0.5 else None
                ),
                "goal_month": 300.0,
                "projected_close": 240.0 if pace_available else None,
                "weighted_goal_mtd": 150.0 if pace_available else None,
                "gap_vs_weighted_goal": -30.0 if pace_available else None,
                "gap_vs_weighted_goal_pct": -0.2 if pace_available else None,
                "confidence": "alta",
            },
        }

    def _selections(self):
        return [
            {
                "track_date": date(2026, 7, 2),
                "version_id": 100,
                "version_type": "cierre_canonico",
                "selection_reason": "current_canonical_close",
                "ingreso_real_base_mtd": Decimal("10"),
                "ingreso_real_agregadora_mtd": Decimal("2"),
                "ingreso_real_total_mtd": Decimal("12"),
            },
            {
                "track_date": self.TRACK_DATE,
                "version_id": self.VERSION_ID,
                "version_type": "preview_operativo",
                "selection_reason": "resolved_cutoff_version",
                "ingreso_real_base_mtd": Decimal("100"),
                "ingreso_real_agregadora_mtd": Decimal("20"),
                "ingreso_real_total_mtd": Decimal("120"),
            },
        ]

    def _historical_series(self):
        def available_series(year, daily_totals):
            business_month = date(year, 7, 1)
            cumulative = Decimal("0")
            points = []
            for day, raw_total in enumerate(daily_totals, start=1):
                daily_total = Decimal(raw_total)
                cumulative += daily_total
                points.append(
                    {
                        "day": day,
                        "date": business_month.replace(day=day),
                        "daily_total": daily_total,
                        "cumulative_total": cumulative,
                        "has_positive_sale_row": daily_total > 0,
                    }
                )
            return {
                "year": year,
                "business_month": business_month,
                "status": "available",
                "snapshot_id": year,
                "snapshot_business_date": business_month.replace(day=31),
                "days_in_month": 31,
                "days_with_positive_sale_row": 31,
                "first_positive_sale_date": business_month,
                "last_positive_sale_date": business_month.replace(day=31),
                "mtd_at_cutoff": points[11]["cumulative_total"],
                "full_month_total": cumulative,
                "points": points,
            }

        strong_weekday_totals = []
        for day in range(1, 32):
            weekday = date(2023, 7, day).weekday()
            strong_weekday_totals.append("5" if weekday in (0, 1) else "1")
        return [
            available_series(2023, strong_weekday_totals),
            {
                "year": 2024,
                "business_month": date(2024, 7, 1),
                "status": "no_canonical_snapshot",
                "snapshot_id": None,
                "snapshot_business_date": None,
                "days_in_month": 31,
                "days_with_positive_sale_row": 0,
                "first_positive_sale_date": None,
                "last_positive_sale_date": None,
                "mtd_at_cutoff": None,
                "full_month_total": None,
                "points": [],
            },
            available_series(2025, ["1"] * 31),
        ]

    def _expected_curve(self, *, status="available"):
        if status != "available":
            return {
                "status": status,
                "method": "fixture",
                "target_month": self.TARGET_MONTH,
                "cutoff_day": 12,
                "comparison_years_requested": [2023, 2024, 2025],
                "comparison_years_used": [],
                "comparison_years_excluded": [],
                "samples_count": 0,
                "historical_expected_month_total": None,
                "historical_progress_pct_at_cutoff": None,
                "historical_expected_mtd_at_cutoff": None,
                "points": [],
            }

        points = []
        previous_expected = Decimal("0")
        for day in range(1, 32):
            if day <= 12:
                progress = Decimal(day) / Decimal("24")
            else:
                progress = Decimal("0.5") + (
                    Decimal(day - 12) * Decimal("0.5") / Decimal("19")
                )
            if day == 31:
                progress = Decimal("1")
            expected = Decimal("200") * progress
            points.append(
                {
                    "day": day,
                    "date": date(2026, 7, day),
                    "historical_progress_pct": progress,
                    "expected_daily_total": expected - previous_expected,
                    "expected_cumulative_total": expected,
                    "sample_years": [2023, 2025],
                    "samples_count": 2,
                }
            )
            previous_expected = expected
        return {
            "status": "available",
            "method": "fixture",
            "target_month": self.TARGET_MONTH,
            "cutoff_day": 12,
            "comparison_years_requested": [2023, 2024, 2025],
            "comparison_years_used": [2023, 2025],
            "comparison_years_excluded": [
                {"year": 2024, "reason": "no_canonical_snapshot"}
            ],
            "samples_count": 2,
            "historical_expected_month_total": Decimal("200"),
            "historical_progress_pct_at_cutoff": Decimal("0.5"),
            "historical_expected_mtd_at_cutoff": Decimal("100"),
            "points": points,
        }

    def _calendar_distribution(self, *, expected_curve=None):
        expected_curve = expected_curve or self._expected_curve()
        points = []
        previous_progress = Decimal("0")
        for day in range(1, 32):
            curve_point = next(
                (
                    point
                    for point in expected_curve.get("points", [])
                    if point["day"] == day
                ),
                None,
            )
            cumulative_weight = (
                curve_point["historical_progress_pct"]
                if curve_point is not None
                else None
            )
            normalized_weight = (
                cumulative_weight - previous_progress
                if cumulative_weight is not None
                else None
            )
            target_date = self.TARGET_MONTH.replace(day=day)
            points.append(
                {
                    "day": day,
                    "date": target_date,
                    "weekday": target_date.strftime("%A").lower(),
                    "weekday_index": target_date.weekday(),
                    "weekday_ordinal": ((day - 1) // 7) + 1,
                    "alignment_key": (
                        f"{target_date.strftime('%A').lower()}:"
                        f"{((day - 1) // 7) + 1}"
                    ),
                    "raw_daily_weight": normalized_weight,
                    "normalized_daily_weight": normalized_weight,
                    "cumulative_weight": cumulative_weight,
                    "samples_count": 2 if curve_point is not None else 0,
                    "sample_years": [2023, 2025] if curve_point is not None else [],
                    "used_fallback": False,
                    "historical_samples": [],
                }
            )
            if cumulative_weight is not None:
                previous_progress = cumulative_weight
        return {
            "status": (
                "available"
                if expected_curve.get("status") == "available"
                else "no_comparable_history"
            ),
            "method": "weekday_ordinal_aligned_historical_weights",
            "target_month": self.TARGET_MONTH,
            "cutoff_day": 12,
            "historical_progress_pct_at_cutoff": expected_curve.get(
                "historical_progress_pct_at_cutoff"
            ),
            "comparison_years_requested": [2023, 2024, 2025],
            "comparison_years_used": [2023, 2025],
            "comparison_years_excluded": [
                {"year": 2024, "reason": "no_canonical_snapshot"}
            ],
            "exact_matches_count": 62,
            "fallback_matches_count": 0,
            "points": points,
        }

    def _build(self, *, forecast=None, selections=None, expected_curve=None):
        forecast = forecast or self._forecast()
        selections = selections if selections is not None else self._selections()
        with ExitStack() as stack:
            base_mock = stack.enter_context(patch(
                "app.warehouse.services.track_forecast_service.build_venta_total_forecast",
                return_value=forecast,
            ))
            select_mock = stack.enter_context(patch(
                "app.warehouse.services.track_forecast_service.select_track_daily_branch_versions",
                return_value=selections,
            ))
            history_mock = stack.enter_context(patch(
                "app.warehouse.services.track_forecast_service.build_branch_historical_daily_series",
                return_value=self._historical_series(),
            ))
            if expected_curve is not None:
                calendar_distribution = self._calendar_distribution(
                    expected_curve=expected_curve
                )
                stack.enter_context(patch(
                    "app.warehouse.services.track_forecast_service.build_branch_calendar_aligned_daily_weights",
                    return_value=calendar_distribution,
                ))
                stack.enter_context(patch(
                    "app.warehouse.services.track_forecast_service._build_branch_calendar_aligned_historical_expected_daily_curve",
                    return_value=expected_curve,
                ))
            result = build_branch_forecast_detail(
                sucursal_canon=" tijuana ",
                track_date=self.TRACK_DATE,
                generation_mode="manual_preview",
                track_daily_version_id=self.VERSION_ID,
            )
        return result, base_mock, select_mock, history_mock

    def test_complete_detail_uses_sources_and_preserves_total_projection(self):
        result, base_mock, _, _ = self._build()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metadata"]["sucursal_canon"], self.BRANCH)
        self.assertEqual(
            result["series"]["current_track"]["source_basis"],
            "track_daily_mart",
        )
        self.assertEqual(
            result["series"]["historical_years"]["source_basis"],
            "venta_total_base",
        )
        self.assertEqual(result["summary"]["projected_close"], 240.0)
        self.assertEqual(
            result["summary"]["total_projection_basis"]["metric_basis"],
            "total_mtd",
        )
        self.assertEqual(result["goal_pace"]["status"], "available")
        self.assertEqual(result["goal_pace"]["metric_basis"], "total_mtd")
        self.assertEqual(
            result["goal_pace"]["goal_expected_mtd_at_cutoff"],
            Decimal("150.0"),
        )
        self.assertEqual(
            result["goal_pace"]["projected_path"]["points"][-1][
                "projected_cumulative_total"
            ],
            Decimal("240.0"),
        )
        base_mock.assert_called_once_with(
            track_date=self.TRACK_DATE,
            generation_mode="manual_preview",
            track_daily_version_id=self.VERSION_ID,
            scope="branch",
            branch=self.BRANCH,
        )

        current_points = result["series"]["current_track"]["points"]
        self.assertEqual(
            current_points[0]["daily_value_status"],
            "missing_previous_calendar_day",
        )
        self.assertIsNone(current_points[0]["total_daily"])
        self.assertEqual(
            current_points[-1]["daily_value_method"],
            "calendar_day_mtd_delta",
        )

    def test_calendar_distribution_drives_expected_base_and_goal_pace(self):
        result, _, _, _ = self._build()
        distribution = result["calendar_aligned_distribution"]
        historical_expected = result["series"]["historical_expected"]
        goal_pace = result["goal_pace"]

        self.assertEqual(
            distribution["method"],
            "weekday_ordinal_aligned_historical_weights",
        )
        self.assertIn(
            distribution["status"],
            ("available", "available_with_fallback"),
        )
        self.assertEqual(
            historical_expected["method"],
            "weekday_ordinal_aligned_historical_weights",
        )
        self.assertTrue(historical_expected["calendar_alignment_applied"])
        self.assertEqual(
            historical_expected["distribution_status"], distribution["status"]
        )
        self.assertEqual(
            historical_expected["historical_expected_mtd_at_cutoff"],
            Decimal("100.0"),
        )
        self.assertEqual(
            historical_expected["points"][-1]["expected_cumulative_total"],
            Decimal("200.0"),
        )
        self.assertEqual(
            sum(
                (
                    point["expected_daily_total"]
                    for point in historical_expected["points"]
                ),
                Decimal("0"),
            ),
            Decimal("200.0"),
        )
        self.assertEqual(
            goal_pace["method"],
            "goal_month_by_weekday_ordinal_aligned_historical_weights",
        )
        self.assertEqual(goal_pace["goal_expected_mtd_at_cutoff"], Decimal("150.0"))
        self.assertEqual(
            goal_pace["points"][-1]["goal_expected_cumulative"],
            Decimal("300.0"),
        )

    def test_aligned_paths_keep_anchors_and_strong_weekday_shape(self):
        result, _, _, _ = self._build()
        base_path = result["series"]["comparable_base_projection"]["path"]
        total_path = result["goal_pace"]["projected_path"]

        self.assertEqual(
            base_path["points"][0]["projected_cumulative_total"],
            Decimal("100.0"),
        )
        self.assertEqual(
            base_path["points"][-1]["projected_cumulative_total"],
            Decimal("200.0"),
        )
        self.assertEqual(
            total_path["points"][0]["projected_cumulative_total"],
            Decimal("120.0"),
        )
        self.assertEqual(
            total_path["points"][-1]["projected_cumulative_total"],
            Decimal("240.0"),
        )
        base_by_day = {point["day"]: point for point in base_path["points"]}
        total_by_day = {point["day"]: point for point in total_path["points"]}
        self.assertGreater(
            base_by_day[13]["projected_daily_increment"],
            base_by_day[15]["projected_daily_increment"],
        )
        self.assertGreater(
            total_by_day[14]["projected_daily_increment"],
            total_by_day[16]["projected_daily_increment"],
        )

    def test_observed_history_and_legacy_summary_fields_are_unchanged(self):
        forecast = self._forecast()
        expected_history = self._historical_series()
        result, _, _, _ = self._build(forecast=forecast)

        self.assertEqual(
            result["series"]["historical_years"]["items"], expected_history
        )
        for field_name, expected_value in forecast["summary"].items():
            self.assertEqual(result["summary"][field_name], expected_value)

    def test_resolved_cutoff_version_and_series_order_are_exact(self):
        result, _, select_mock, _ = self._build()

        select_mock.assert_called_once_with(
            sucursal_canon=self.BRANCH,
            start_date=self.TARGET_MONTH,
            cutoff_date=self.TRACK_DATE,
            resolved_cutoff_version_id=self.VERSION_ID,
        )
        points = result["series"]["current_track"]["points"]
        self.assertEqual([point["day"] for point in points], [2, 12])
        self.assertEqual(points[-1]["selection_reason"], "resolved_cutoff_version")

    def test_dynamic_history_years_and_unavailable_year_are_preserved(self):
        result, _, _, history_mock = self._build()

        self.assertEqual(result["metadata"]["comparison_years"], [2023, 2024, 2025])
        self.assertEqual(
            history_mock.call_args.kwargs["comparison_years"],
            [2023, 2024, 2025],
        )
        unavailable = result["series"]["historical_years"]["items"][1]
        self.assertEqual(unavailable["status"], "no_canonical_snapshot")
        self.assertEqual(unavailable["points"], [])

    def test_base_projection_uses_base_and_ends_at_its_own_close(self):
        result, _, _, _ = self._build()

        projection = result["series"]["comparable_base_projection"]
        self.assertEqual(projection["status"], "available")
        self.assertEqual(projection["method"], "stable_historical_pace_base")
        self.assertEqual(projection["metric_basis"], "base_mtd")
        self.assertEqual(projection["projected_close"], Decimal("200"))
        self.assertNotEqual(projection["projected_close"], Decimal("240"))
        self.assertEqual(
            projection["path"]["points"][-1]["projected_cumulative_total"],
            Decimal("200"),
        )

    def test_forecast_quality_issue_blocks_base_path(self):
        issue = {"code": "insufficient_history", "message": "fixture"}
        forecast = self._forecast(quality_issue=issue)
        with patch(
            "app.warehouse.services.track_forecast_service.build_branch_projected_daily_path"
        ) as path_mock:
            result, _, _, _ = self._build(forecast=forecast)

        projection = result["series"]["comparable_base_projection"]
        self.assertEqual(projection["status"], "blocked_by_forecast_quality")
        self.assertEqual(projection["quality_issue"], issue)
        self.assertEqual(result["goal_pace"]["status"], "projection_unavailable")
        self.assertEqual(
            result["goal_pace"]["goal_expected_mtd_at_cutoff"],
            Decimal("150.0"),
        )
        path_mock.assert_not_called()

    def test_invalid_historical_progress_blocks_base_path(self):
        forecast = self._forecast(progress=0)
        result, _, _, _ = self._build(
            forecast=forecast,
            expected_curve=self._expected_curve(status="no_comparable_history"),
        )

        self.assertEqual(
            result["series"]["comparable_base_projection"]["status"],
            "invalid_historical_progress",
        )

    def test_missing_base_mtd_blocks_base_path(self):
        forecast = self._forecast()
        forecast["summary"]["real_base_mtd"] = None
        selections = self._selections()
        selections[-1]["ingreso_real_base_mtd"] = None

        result, _, _, _ = self._build(
            forecast=forecast,
            selections=selections,
        )

        self.assertEqual(
            result["series"]["comparable_base_projection"]["status"],
            "missing_base_mtd",
        )

    def test_unavailable_projected_path_has_explicit_status(self):
        unavailable_path = {
            "status": "expected_curve_unavailable",
            "points": [],
        }
        with patch(
            "app.warehouse.services.track_forecast_service.build_branch_projected_daily_path",
            return_value=unavailable_path,
        ):
            result, _, _, _ = self._build()

        projection = result["series"]["comparable_base_projection"]
        self.assertEqual(projection["status"], "projected_path_unavailable")
        self.assertEqual(projection["path"], unavailable_path)

    def test_missing_cutoff_point_is_explicit_inconsistency(self):
        with self.assertRaisesRegex(
            BranchForecastDetailConsistencyError,
            "día de corte",
        ):
            self._build(selections=self._selections()[:-1])

    def test_cutoff_values_must_match_forecast_summary(self):
        selections = self._selections()
        selections[-1]["ingreso_real_base_mtd"] = Decimal("99")
        with self.assertRaisesRegex(
            BranchForecastDetailConsistencyError,
            "base_mtd",
        ):
            self._build(selections=selections)

    def test_expected_curve_cutoff_progress_must_match_forecast(self):
        expected_curve = self._expected_curve()
        expected_curve["historical_progress_pct_at_cutoff"] = Decimal("0.4")
        with self.assertRaisesRegex(
            BranchForecastDetailConsistencyError,
            "progress_pct",
        ):
            self._build(expected_curve=expected_curve)

    def test_expected_curve_cutoff_expected_mtd_must_match_forecast(self):
        expected_curve = self._expected_curve()
        expected_curve["historical_expected_mtd_at_cutoff"] = Decimal("99")
        with self.assertRaisesRegex(
            BranchForecastDetailConsistencyError,
            "expected_mtd",
        ):
            self._build(expected_curve=expected_curve)

    def test_expected_curve_month_end_must_match_forecast(self):
        expected_curve = self._expected_curve()
        expected_curve["points"][-1]["expected_cumulative_total"] = Decimal("199")
        with self.assertRaisesRegex(
            BranchForecastDetailConsistencyError,
            "month_end",
        ):
            self._build(expected_curve=expected_curve)

    def test_base_forecast_payload_is_not_mutated(self):
        forecast = self._forecast()
        original = deepcopy(forecast)

        self._build(forecast=forecast)

        self.assertEqual(forecast, original)

    def test_goal_pace_does_not_depend_on_legacy_weighted_goal_fields(self):
        forecast = self._forecast()
        forecast["summary"]["weighted_goal_mtd"] = None
        forecast["summary"]["gap_vs_weighted_goal"] = None
        forecast["summary"]["gap_vs_weighted_goal_pct"] = None

        result, _, _, _ = self._build(forecast=forecast)

        self.assertEqual(result["goal_pace"]["status"], "available")
        self.assertEqual(
            result["goal_pace"]["goal_expected_mtd_at_cutoff"],
            Decimal("150.0"),
        )

    def test_goal_pace_requires_consistency_with_legacy_goal_fields(self):
        cases = (
            ("weighted_goal_mtd", "151"),
            ("gap_vs_weighted_goal", "-31"),
            ("gap_vs_weighted_goal_pct", "-0.3"),
        )
        for field_name, value in cases:
            with self.subTest(field_name=field_name):
                forecast = self._forecast()
                forecast["summary"][field_name] = value
                with self.assertRaisesRegex(
                    BranchForecastDetailConsistencyError,
                    "goal_pace",
                ):
                    self._build(forecast=forecast)

    def test_zero_goal_remains_invalid_and_consistent_with_legacy_summary(self):
        forecast = self._forecast()
        forecast["summary"].update(
            {
                "goal_month": 0.0,
                "weighted_goal_mtd": 0.0,
                "gap_vs_weighted_goal": 120.0,
                "gap_vs_weighted_goal_pct": None,
            }
        )

        result, _, _, _ = self._build(forecast=forecast)

        self.assertEqual(result["goal_pace"]["status"], "invalid_goal")
        self.assertEqual(
            result["goal_pace"]["goal_expected_mtd_at_cutoff"],
            Decimal("0.00"),
        )
        self.assertEqual(
            result["goal_pace"]["gap_vs_goal_pace"],
            Decimal("120.0"),
        )
        self.assertEqual(result["goal_pace"]["points"], [])


class BranchCurrentTrackDailyValuesTest(unittest.TestCase):
    @staticmethod
    def _point(
        point_date: date,
        *,
        base_mtd: Decimal | None,
        agregadora_mtd: Decimal | None,
        total_mtd: Decimal | None,
        version_id: int = 1,
    ):
        return {
            "day": point_date.day,
            "date": point_date,
            "version_id": version_id,
            "version_type": "cierre_canonico",
            "selection_reason": "current_canonical_close",
            "base_mtd": base_mtd,
            "agregadora_mtd": agregadora_mtd,
            "total_mtd": total_mtd,
        }

    def test_day_one_uses_zero_baseline_and_preserves_decimal_values(self):
        source = self._point(
            date(2026, 7, 1),
            base_mtd=Decimal("10.25"),
            agregadora_mtd=Decimal("0"),
            total_mtd=Decimal("10.25"),
        )

        result = build_branch_current_track_daily_values([source])
        point = result[0]

        self.assertEqual(point["base_daily"], Decimal("10.25"))
        self.assertEqual(point["agregadora_daily"], Decimal("0"))
        self.assertEqual(point["total_daily"], Decimal("10.25"))
        self.assertEqual(point["daily_value_status"], "available")
        self.assertEqual(
            point["daily_value_method"],
            "calendar_day_mtd_delta",
        )
        self.assertTrue(
            all(
                isinstance(point[field], Decimal)
                for field in ("base_daily", "agregadora_daily", "total_daily")
            )
        )

    def test_consecutive_days_calculate_each_signed_mtd_delta(self):
        points = [
            self._point(
                date(2026, 7, 1),
                base_mtd=Decimal("10"),
                agregadora_mtd=Decimal("2"),
                total_mtd=Decimal("12"),
            ),
            self._point(
                date(2026, 7, 2),
                base_mtd=Decimal("17"),
                agregadora_mtd=Decimal("5"),
                total_mtd=Decimal("22"),
            ),
        ]

        point = build_branch_current_track_daily_values(points)[1]

        self.assertEqual(point["base_daily"], Decimal("7"))
        self.assertEqual(point["agregadora_daily"], Decimal("3"))
        self.assertEqual(point["total_daily"], Decimal("10"))
        self.assertEqual(
            point["total_daily"],
            point["base_daily"] + point["agregadora_daily"],
        )
        self.assertEqual(point["daily_value_status"], "available")

    def test_missing_previous_calendar_day_does_not_bridge_gap(self):
        points = [
            self._point(
                date(2026, 7, 10),
                base_mtd=Decimal("100"),
                agregadora_mtd=Decimal("20"),
                total_mtd=Decimal("120"),
            ),
            self._point(
                date(2026, 7, 12),
                base_mtd=Decimal("130"),
                agregadora_mtd=Decimal("25"),
                total_mtd=Decimal("155"),
            ),
            self._point(
                date(2026, 7, 15),
                base_mtd=Decimal("160"),
                agregadora_mtd=Decimal("30"),
                total_mtd=Decimal("190"),
            ),
        ]

        result = build_branch_current_track_daily_values(points)

        for point in result:
            self.assertIsNone(point["base_daily"])
            self.assertIsNone(point["agregadora_daily"])
            self.assertIsNone(point["total_daily"])
            self.assertEqual(
                point["daily_value_status"],
                "missing_previous_calendar_day",
            )

    def test_negative_adjustment_is_preserved_and_marked(self):
        points = [
            self._point(
                date(2026, 7, 5),
                base_mtd=Decimal("50"),
                agregadora_mtd=Decimal("10"),
                total_mtd=Decimal("60"),
            ),
            self._point(
                date(2026, 7, 6),
                base_mtd=Decimal("45"),
                agregadora_mtd=Decimal("12"),
                total_mtd=Decimal("57"),
            ),
        ]

        point = build_branch_current_track_daily_values(points)[1]

        self.assertEqual(point["base_daily"], Decimal("-5"))
        self.assertEqual(point["agregadora_daily"], Decimal("2"))
        self.assertEqual(point["total_daily"], Decimal("-3"))
        self.assertEqual(
            point["daily_value_status"],
            "available_with_negative_adjustment",
        )

    def test_inconsistent_components_keep_independent_total_delta(self):
        points = [
            self._point(
                date(2026, 7, 5),
                base_mtd=Decimal("50"),
                agregadora_mtd=Decimal("10"),
                total_mtd=Decimal("60"),
            ),
            self._point(
                date(2026, 7, 6),
                base_mtd=Decimal("55"),
                agregadora_mtd=Decimal("12"),
                total_mtd=Decimal("70"),
            ),
        ]

        point = build_branch_current_track_daily_values(points)[1]

        self.assertEqual(point["base_daily"], Decimal("5"))
        self.assertEqual(point["agregadora_daily"], Decimal("2"))
        self.assertEqual(point["total_daily"], Decimal("10"))
        self.assertEqual(point["daily_value_status"], "inconsistent_components")

    def test_cumulative_values_are_not_changed_and_input_is_sorted(self):
        later = self._point(
            date(2026, 7, 2),
            base_mtd=Decimal("17"),
            agregadora_mtd=Decimal("5"),
            total_mtd=Decimal("22"),
            version_id=2,
        )
        first = self._point(
            date(2026, 7, 1),
            base_mtd=Decimal("10"),
            agregadora_mtd=Decimal("2"),
            total_mtd=Decimal("12"),
        )

        result = build_branch_current_track_daily_values([later, first])

        self.assertEqual(
            [point["date"] for point in result],
            [first["date"], later["date"]],
        )
        for source, point in zip((first, later), result):
            for field in ("base_mtd", "agregadora_mtd", "total_mtd"):
                self.assertEqual(point[field], source[field])

    def test_first_day_of_new_month_ignores_previous_month(self):
        points = [
            self._point(
                date(2026, 6, 30),
                base_mtd=Decimal("300"),
                agregadora_mtd=Decimal("30"),
                total_mtd=Decimal("330"),
            ),
            self._point(
                date(2026, 7, 1),
                base_mtd=Decimal("8"),
                agregadora_mtd=Decimal("0"),
                total_mtd=Decimal("8"),
            ),
        ]

        point = build_branch_current_track_daily_values(points)[1]

        self.assertEqual(point["base_daily"], Decimal("8"))
        self.assertEqual(point["agregadora_daily"], Decimal("0"))
        self.assertEqual(point["total_daily"], Decimal("8"))
        self.assertEqual(point["daily_value_status"], "available")

    def test_missing_cumulative_value_only_nulls_affected_delta(self):
        points = [
            self._point(
                date(2026, 7, 5),
                base_mtd=Decimal("50"),
                agregadora_mtd=None,
                total_mtd=Decimal("60"),
            ),
            self._point(
                date(2026, 7, 6),
                base_mtd=Decimal("55"),
                agregadora_mtd=Decimal("12"),
                total_mtd=Decimal("67"),
            ),
        ]

        point = build_branch_current_track_daily_values(points)[1]

        self.assertEqual(point["base_daily"], Decimal("5"))
        self.assertIsNone(point["agregadora_daily"])
        self.assertEqual(point["total_daily"], Decimal("7"))
        self.assertEqual(point["daily_value_status"], "missing_cumulative_value")

    def test_missing_current_cumulative_value_has_priority_over_gap(self):
        point = self._point(
            date(2026, 7, 8),
            base_mtd=None,
            agregadora_mtd=Decimal("12"),
            total_mtd=Decimal("67"),
        )

        result = build_branch_current_track_daily_values([point])[0]

        self.assertIsNone(result["base_daily"])
        self.assertIsNone(result["agregadora_daily"])
        self.assertIsNone(result["total_daily"])
        self.assertEqual(
            result["daily_value_status"],
            "missing_cumulative_value",
        )


class TrackDailyBranchVersionSelectorTest(unittest.TestCase):
    BRANCH = "TIJUANA"
    START_DATE = date(2026, 7, 1)
    CUTOFF_DATE = date(2026, 7, 10)

    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(cls.app)
        cls.app_context = cls.app.app_context()
        cls.app_context.push()
        TrackDailyVersionORM.__table__.create(db.engine)
        TrackDailyMartORM.__table__.create(db.engine)

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        TrackDailyMartORM.__table__.drop(db.engine)
        TrackDailyVersionORM.__table__.drop(db.engine)
        cls.app_context.pop()

    def setUp(self):
        db.session.query(TrackDailyMartORM).delete()
        db.session.query(TrackDailyVersionORM).delete()
        db.session.commit()

    def tearDown(self):
        db.session.rollback()

    def _add_version(
        self,
        *,
        version_id: int,
        track_date: date,
        version_type: str,
        status: str = "success",
        is_current: bool = True,
        branch: str = BRANCH,
        with_mart: bool = True,
        base_mtd: str = "100.00",
        agregadora_mtd: str = "20.00",
        total_mtd: str = "120.00",
    ) -> None:
        now_utc = datetime.now(timezone.utc)
        db.session.add(
            TrackDailyVersionORM(
                id=version_id,
                track_date=track_date,
                version_type=version_type,
                status=status,
                is_current=is_current,
                trigger_source="test",
                created_at=now_utc,
                updated_at=now_utc,
            )
        )

        if with_mart:
            db.session.add(
                TrackDailyMartORM(
                    id=version_id,
                    track_daily_version_id=version_id,
                    track_date=track_date,
                    generation_mode="official_closed_day",
                    sucursal_canon=branch,
                    target_month=track_date.replace(day=1),
                    ingreso_real_base_mtd=Decimal(base_mtd),
                    ingreso_real_agregadora_mtd=Decimal(agregadora_mtd),
                    ingreso_real_total_mtd=Decimal(total_mtd),
                    venta_tienda_real_mtd=Decimal("0.00"),
                )
            )

    def _add_cutoff(self, *, version_id: int = 900) -> int:
        self._add_version(
            version_id=version_id,
            track_date=self.CUTOFF_DATE,
            version_type="preview_operativo",
        )
        return version_id

    def _select(self, *, resolved_cutoff_version_id: int = 900):
        db.session.commit()
        return select_track_daily_branch_versions(
            sucursal_canon=self.BRANCH,
            start_date=self.START_DATE,
            cutoff_date=self.CUTOFF_DATE,
            resolved_cutoff_version_id=resolved_cutoff_version_id,
        )

    def test_previous_day_prefers_canonical_close(self):
        previous_date = date(2026, 7, 9)
        self._add_version(
            version_id=101,
            track_date=previous_date,
            version_type="preview_operativo",
        )
        self._add_version(
            version_id=102,
            track_date=previous_date,
            version_type="base_nocturna_canonica",
        )
        self._add_version(
            version_id=103,
            track_date=previous_date,
            version_type="cierre_canonico",
        )
        self._add_cutoff()

        result = self._select()

        self.assertEqual(result[0]["version_id"], 103)
        self.assertEqual(result[0]["selection_reason"], "current_canonical_close")
        self.assertIsInstance(result[0]["ingreso_real_total_mtd"], Decimal)

    def test_replaced_close_yields_to_successful_current_close(self):
        previous_date = date(2026, 7, 9)
        self._add_version(
            version_id=110,
            track_date=previous_date,
            version_type="cierre_canonico",
            status="replaced",
            is_current=False,
        )
        self._add_version(
            version_id=111,
            track_date=previous_date,
            version_type="cierre_canonico",
        )
        self._add_cutoff()

        result = self._select()

        self.assertEqual([item["version_id"] for item in result], [111, 900])

    def test_nightly_base_is_used_without_valid_close(self):
        previous_date = date(2026, 7, 9)
        self._add_version(
            version_id=120,
            track_date=previous_date,
            version_type="cierre_canonico",
            status="failed",
        )
        self._add_version(
            version_id=121,
            track_date=previous_date,
            version_type="base_nocturna_canonica",
        )
        self._add_cutoff()

        result = self._select()

        self.assertEqual(result[0]["version_id"], 121)
        self.assertEqual(result[0]["selection_reason"], "current_nightly_base")

    def test_operational_preview_is_used_without_close_or_base(self):
        previous_date = date(2026, 7, 9)
        self._add_version(
            version_id=130,
            track_date=previous_date,
            version_type="preview_operativo",
        )
        self._add_cutoff()

        result = self._select()

        self.assertEqual(result[0]["version_id"], 130)
        self.assertEqual(
            result[0]["selection_reason"],
            "current_operational_preview",
        )

    def test_cutoff_uses_exact_resolved_version(self):
        self._add_version(
            version_id=140,
            track_date=self.CUTOFF_DATE,
            version_type="cierre_canonico",
        )
        self._add_cutoff(version_id=141)

        result = self._select(resolved_cutoff_version_id=141)

        self.assertEqual([item["version_id"] for item in result], [141])
        self.assertEqual(result[0]["selection_reason"], "resolved_cutoff_version")

    def test_cutoff_without_branch_mart_row_raises(self):
        self._add_version(
            version_id=150,
            track_date=self.CUTOFF_DATE,
            version_type="preview_operativo",
            with_mart=False,
        )
        self._add_version(
            version_id=151,
            track_date=self.CUTOFF_DATE,
            version_type="cierre_canonico",
        )

        with self.assertRaisesRegex(
            ValueError,
            "versión resuelta del corte no tiene una fila TrackDailyMart",
        ):
            self._select(resolved_cutoff_version_id=150)

    def test_excludes_other_branch_and_dates_outside_range(self):
        self._add_version(
            version_id=160,
            track_date=date(2026, 6, 30),
            version_type="cierre_canonico",
        )
        self._add_version(
            version_id=161,
            track_date=date(2026, 7, 5),
            version_type="cierre_canonico",
            branch="MEXICALI",
        )
        self._add_version(
            version_id=162,
            track_date=date(2026, 7, 6),
            version_type="cierre_canonico",
        )
        self._add_version(
            version_id=163,
            track_date=date(2026, 7, 11),
            version_type="cierre_canonico",
        )
        self._add_cutoff()

        result = self._select()

        self.assertEqual([item["version_id"] for item in result], [162, 900])

    def test_result_is_chronological(self):
        self._add_version(
            version_id=170,
            track_date=date(2026, 7, 8),
            version_type="cierre_canonico",
        )
        self._add_version(
            version_id=171,
            track_date=date(2026, 7, 2),
            version_type="cierre_canonico",
        )
        self._add_version(
            version_id=172,
            track_date=date(2026, 7, 5),
            version_type="cierre_canonico",
        )
        self._add_cutoff()

        result = self._select()

        self.assertEqual(
            [item["track_date"] for item in result],
            [
                date(2026, 7, 2),
                date(2026, 7, 5),
                date(2026, 7, 8),
                self.CUTOFF_DATE,
            ],
        )

    def test_same_type_tie_uses_highest_version_id(self):
        previous_date = date(2026, 7, 9)
        self._add_version(
            version_id=180,
            track_date=previous_date,
            version_type="cierre_canonico",
        )
        self._add_version(
            version_id=181,
            track_date=previous_date,
            version_type="cierre_canonico",
        )
        self._add_cutoff()

        result = self._select()

        self.assertEqual(result[0]["version_id"], 181)

    def test_replaced_version_never_appears(self):
        self._add_version(
            version_id=190,
            track_date=date(2026, 7, 9),
            version_type="cierre_canonico",
            status="replaced",
            is_current=False,
        )
        self._add_cutoff()

        result = self._select()

        self.assertEqual([item["version_id"] for item in result], [900])


class BranchHistoricalDailySeriesTest(unittest.TestCase):
    BRANCH = "SANTA_FE"
    TARGET_MONTH = date(2025, 7, 1)

    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(cls.app)
        cls.app_context = cls.app.app_context()
        cls.app_context.push()
        VentaTotalSnapshotORM.__table__.create(db.engine)
        db.session.execute(
            text(
                """
                CREATE TABLE track_venta_total_daily_branch_agg (
                    id INTEGER PRIMARY KEY,
                    snapshot_id INTEGER NOT NULL,
                    business_month DATE NOT NULL,
                    sale_date DATE NOT NULL,
                    day_of_month INTEGER NOT NULL,
                    sucursal_canon TEXT NOT NULL,
                    total NUMERIC(18, 2) NOT NULL
                )
                """
            )
        )
        db.session.commit()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.session.execute(text("DROP TABLE track_venta_total_daily_branch_agg"))
        VentaTotalSnapshotORM.__table__.drop(db.engine)
        cls.app_context.pop()

    def setUp(self):
        db.session.execute(text("DELETE FROM track_venta_total_daily_branch_agg"))
        db.session.query(VentaTotalSnapshotORM).delete()
        db.session.commit()
        self._next_agg_id = 1

    def tearDown(self):
        db.session.rollback()

    def _add_snapshot(
        self,
        *,
        snapshot_id: int,
        business_date: date,
        captured_hour: int = 12,
        is_canonical: bool = True,
    ) -> None:
        captured_at = datetime(
            business_date.year,
            business_date.month,
            business_date.day,
            captured_hour,
            tzinfo=timezone.utc,
        )
        db.session.add(
            VentaTotalSnapshotORM(
                id=snapshot_id,
                warehouse_upload_id=snapshot_id,
                report_type_key="venta_total",
                business_date=business_date,
                captured_at=captured_at,
                snapshot_kind="daily",
                is_canonical=is_canonical,
                row_count_detected=1,
                row_count_valid=1,
                row_count_rejected=0,
                created_at=captured_at,
                updated_at=captured_at,
            )
        )

    def _add_daily_total(
        self,
        *,
        snapshot_id: int,
        sale_date: date,
        total: str,
        branch: str = BRANCH,
    ) -> None:
        db.session.execute(
            text(
                """
                INSERT INTO track_venta_total_daily_branch_agg (
                    id,
                    snapshot_id,
                    business_month,
                    sale_date,
                    day_of_month,
                    sucursal_canon,
                    total
                ) VALUES (
                    :id,
                    :snapshot_id,
                    :business_month,
                    :sale_date,
                    :day_of_month,
                    :sucursal_canon,
                    :total
                )
                """
            ),
            {
                "id": self._next_agg_id,
                "snapshot_id": snapshot_id,
                "business_month": sale_date.replace(day=1),
                "sale_date": sale_date,
                "day_of_month": sale_date.day,
                "sucursal_canon": branch,
                "total": total,
            },
        )
        self._next_agg_id += 1

    def _build(
        self,
        *,
        years: list[int] | None = None,
        cutoff_day: int = 12,
    ):
        db.session.commit()
        return build_branch_historical_daily_series(
            sucursal_canon=self.BRANCH,
            target_month=self.TARGET_MONTH,
            comparison_years=years or [2025],
            cutoff_day=cutoff_day,
        )

    def test_builds_complete_31_day_series(self):
        self._add_snapshot(snapshot_id=101, business_date=date(2025, 7, 31))
        for day in range(1, 32):
            self._add_daily_total(
                snapshot_id=101,
                sale_date=date(2025, 7, day),
                total="1.00",
            )

        item = self._build()[0]

        self.assertEqual(item["status"], "available")
        self.assertEqual(item["days_in_month"], 31)
        self.assertEqual(len(item["points"]), 31)
        self.assertEqual(item["full_month_total"], Decimal("31.00"))

    def test_days_without_rows_are_zero_and_preserve_cumulative_total(self):
        self._add_snapshot(snapshot_id=102, business_date=date(2025, 7, 31))
        self._add_daily_total(
            snapshot_id=102,
            sale_date=date(2025, 7, 1),
            total="10.00",
        )
        self._add_daily_total(
            snapshot_id=102,
            sale_date=date(2025, 7, 3),
            total="5.00",
        )

        points = self._build()[0]["points"]

        self.assertEqual(points[1]["daily_total"], Decimal("0"))
        self.assertEqual(points[1]["cumulative_total"], Decimal("10.00"))
        self.assertFalse(points[1]["has_positive_sale_row"])

    def test_multiple_years_are_ordered_and_keep_their_snapshot(self):
        self._add_snapshot(snapshot_id=203, business_date=date(2023, 7, 31))
        self._add_snapshot(snapshot_id=205, business_date=date(2025, 7, 31))
        self._add_daily_total(
            snapshot_id=203,
            sale_date=date(2023, 7, 1),
            total="3.00",
        )
        self._add_daily_total(
            snapshot_id=205,
            sale_date=date(2025, 7, 1),
            total="5.00",
        )

        result = self._build(years=[2025, 2023])

        self.assertEqual([item["year"] for item in result], [2023, 2025])
        self.assertEqual([item["snapshot_id"] for item in result], [203, 205])

    def test_uses_only_latest_canonical_snapshot_for_month(self):
        self._add_snapshot(
            snapshot_id=301,
            business_date=date(2025, 7, 31),
            captured_hour=10,
        )
        self._add_snapshot(
            snapshot_id=302,
            business_date=date(2025, 7, 31),
            captured_hour=11,
        )
        self._add_daily_total(
            snapshot_id=301,
            sale_date=date(2025, 7, 1),
            total="100.00",
        )
        self._add_daily_total(
            snapshot_id=302,
            sale_date=date(2025, 7, 1),
            total="7.00",
        )

        item = self._build()[0]

        self.assertEqual(item["snapshot_id"], 302)
        self.assertEqual(item["full_month_total"], Decimal("7.00"))

    def test_mtd_at_cutoff_matches_requested_day(self):
        self._add_snapshot(snapshot_id=401, business_date=date(2025, 7, 31))
        for day, total in ((1, "2.00"), (2, "3.00"), (3, "4.00")):
            self._add_daily_total(
                snapshot_id=401,
                sale_date=date(2025, 7, day),
                total=total,
            )

        item = self._build(cutoff_day=2)[0]

        self.assertEqual(item["mtd_at_cutoff"], Decimal("5.00"))

    def test_cutoff_after_month_end_is_clamped_without_changing_full_total(self):
        self._add_snapshot(snapshot_id=402, business_date=date(2025, 7, 31))
        self._add_daily_total(
            snapshot_id=402,
            sale_date=date(2025, 7, 31),
            total="9.00",
        )

        item = self._build(cutoff_day=40)[0]

        self.assertEqual(item["mtd_at_cutoff"], Decimal("9.00"))
        self.assertEqual(item["full_month_total"], Decimal("9.00"))

    def test_leap_year_february_has_29_points(self):
        self.TARGET_MONTH = date(2025, 2, 1)
        self.addCleanup(setattr, self, "TARGET_MONTH", date(2025, 7, 1))
        self._add_snapshot(snapshot_id=501, business_date=date(2024, 2, 29))
        self._add_daily_total(
            snapshot_id=501,
            sale_date=date(2024, 2, 29),
            total="1.00",
        )

        item = self._build(years=[2024])[0]

        self.assertEqual(item["days_in_month"], 29)
        self.assertEqual(len(item["points"]), 29)

    def test_month_without_canonical_snapshot_has_empty_points(self):
        item = self._build()[0]

        self.assertEqual(item["status"], "no_canonical_snapshot")
        self.assertEqual(item["points"], [])
        self.assertIsNone(item["snapshot_id"])

    def test_snapshot_without_branch_rows_has_empty_points(self):
        self._add_snapshot(snapshot_id=601, business_date=date(2025, 7, 31))
        self._add_daily_total(
            snapshot_id=601,
            sale_date=date(2025, 7, 1),
            total="8.00",
            branch="TIJUANA",
        )

        item = self._build()[0]

        self.assertEqual(item["status"], "no_branch_rows")
        self.assertEqual(item["points"], [])
        self.assertEqual(item["snapshot_id"], 601)

    def test_excludes_other_branches(self):
        self._add_snapshot(snapshot_id=701, business_date=date(2025, 7, 31))
        self._add_daily_total(
            snapshot_id=701,
            sale_date=date(2025, 7, 1),
            total="4.00",
        )
        self._add_daily_total(
            snapshot_id=701,
            sale_date=date(2025, 7, 1),
            total="100.00",
            branch="TIJUANA",
        )

        item = self._build()[0]

        self.assertEqual(item["full_month_total"], Decimal("4.00"))

    def test_available_totals_remain_decimal(self):
        self._add_snapshot(snapshot_id=801, business_date=date(2025, 7, 31))
        self._add_daily_total(
            snapshot_id=801,
            sale_date=date(2025, 7, 1),
            total="1.25",
        )

        item = self._build()[0]
        point = item["points"][0]

        self.assertIsInstance(point["daily_total"], Decimal)
        self.assertIsInstance(point["cumulative_total"], Decimal)
        self.assertIsInstance(item["mtd_at_cutoff"], Decimal)
        self.assertIsInstance(item["full_month_total"], Decimal)

    def test_non_canonical_snapshots_are_not_used(self):
        self._add_snapshot(
            snapshot_id=901,
            business_date=date(2025, 7, 31),
            is_canonical=False,
        )
        self._add_daily_total(
            snapshot_id=901,
            sale_date=date(2025, 7, 1),
            total="99.00",
        )

        item = self._build()[0]

        self.assertEqual(item["status"], "no_canonical_snapshot")
        self.assertEqual(item["points"], [])


class BranchCalendarAlignedDailyWeightsTest(unittest.TestCase):
    TARGET_MONTH = date(2026, 7, 1)
    CUTOFF_DAY = 12

    def _series(
        self,
        *,
        year: int,
        target_month: date | None = None,
        daily_totals: list[str] | None = None,
        status: str = "available",
        full_month_total: Decimal | None = None,
    ):
        target_month = target_month or self.TARGET_MONTH
        business_month = date(year, target_month.month, 1)
        days_in_month = monthrange(year, target_month.month)[1]
        if status != "available":
            return {
                "year": year,
                "business_month": business_month,
                "status": status,
                "snapshot_id": None,
                "snapshot_business_date": None,
                "days_in_month": days_in_month,
                "days_with_positive_sale_row": 0,
                "first_positive_sale_date": None,
                "last_positive_sale_date": None,
                "mtd_at_cutoff": None,
                "full_month_total": None,
                "points": [],
            }
        raw_totals = daily_totals or ["1"] * days_in_month
        cumulative = Decimal("0")
        points = []
        for day, raw_total in enumerate(raw_totals, start=1):
            daily_total = Decimal(raw_total)
            cumulative += daily_total
            points.append(
                {
                    "day": day,
                    "date": business_month.replace(day=day),
                    "daily_total": daily_total,
                    "cumulative_total": cumulative,
                    "has_positive_sale_row": daily_total > 0,
                }
            )
        return {
            "year": year,
            "business_month": business_month,
            "status": "available",
            "snapshot_id": year,
            "snapshot_business_date": business_month.replace(day=len(points)),
            "days_in_month": days_in_month,
            "days_with_positive_sale_row": sum(
                point["has_positive_sale_row"] for point in points
            ),
            "first_positive_sale_date": business_month,
            "last_positive_sale_date": business_month.replace(day=len(points)),
            "mtd_at_cutoff": points[min(self.CUTOFF_DAY, len(points)) - 1][
                "cumulative_total"
            ],
            "full_month_total": (
                cumulative if full_month_total is None else full_month_total
            ),
            "points": points,
        }

    def _build(
        self,
        series=None,
        *,
        target_month: date | None = None,
        cutoff_day: int | None = None,
        progress: Decimal | None = Decimal("0.4"),
    ):
        target_month = target_month or self.TARGET_MONTH
        return build_branch_calendar_aligned_daily_weights(
            historical_series=series
            if series is not None
            else [self._series(year=2025, target_month=target_month)],
            target_month=target_month,
            cutoff_day=cutoff_day or self.CUTOFF_DAY,
            historical_progress_pct_at_cutoff=progress,
        )

    def test_weekday_ordinals_cover_first_through_fifth(self):
        result = self._build()

        self.assertEqual(result["status"], "available_with_fallback")
        self.assertEqual(
            {point["weekday_ordinal"] for point in result["points"]},
            {1, 2, 3, 4, 5},
        )
        fifth_friday = result["points"][30]
        self.assertEqual(fifth_friday["weekday"], "friday")
        self.assertEqual(fifth_friday["weekday_ordinal"], 5)

    def test_second_monday_aligns_to_historical_second_monday_not_day(self):
        result = self._build()
        target_point = result["points"][12]
        sample = target_point["historical_samples"][0]

        self.assertEqual(target_point["date"], date(2026, 7, 13))
        self.assertEqual(target_point["alignment_key"], "monday:2")
        self.assertEqual(sample["source_date"], date(2025, 7, 14))
        self.assertNotEqual(sample["source_day"], target_point["day"])
        self.assertEqual(sample["alignment_kind"], "exact_ordinal_match")

    def test_fifth_weekday_uses_explicit_same_weekday_fallback(self):
        result = self._build()
        target_point = result["points"][30]
        sample = target_point["historical_samples"][0]

        self.assertEqual(sample["source_date"], date(2025, 7, 25))
        self.assertEqual(sample["source_weekday"], "friday")
        self.assertEqual(
            sample["alignment_kind"],
            "last_weekday_occurrence_fallback",
        )
        self.assertTrue(target_point["used_fallback"])

    def test_zero_sale_is_a_valid_decimal_sample(self):
        totals = ["1"] * 31
        totals[24] = "0"
        result = self._build([self._series(year=2025, daily_totals=totals)])
        sample = result["points"][30]["historical_samples"][0]

        self.assertEqual(sample["source_daily_total"], Decimal("0"))
        self.assertEqual(sample["sample_daily_share"], Decimal("0"))
        self.assertIsInstance(result["points"][0]["raw_daily_weight"], Decimal)
        self.assertIsInstance(
            result["points"][0]["normalized_daily_weight"], Decimal
        )

    def test_raw_weight_uses_monetary_aggregate_formula(self):
        totals_2024 = ["1"] * 31
        totals_2025 = ["2"] * 31
        series_2024 = self._series(year=2024, daily_totals=totals_2024)
        series_2025 = self._series(year=2025, daily_totals=totals_2025)
        result = self._build([series_2024, series_2025])
        point = result["points"][12]
        numerator = sum(
            (sample["source_daily_total"] for sample in point["historical_samples"]),
            Decimal("0"),
        )
        denominator = sum(
            (
                sample["source_full_month_total"]
                for sample in point["historical_samples"]
            ),
            Decimal("0"),
        )

        self.assertEqual(point["raw_daily_weight"], numerator / denominator)
        self.assertEqual(point["sample_years"], [2024, 2025])

    def test_segment_normalization_and_cumulative_are_exact(self):
        progress = Decimal("0.417")
        result = self._build(progress=progress)
        normalized = [
            point["normalized_daily_weight"] for point in result["points"]
        ]
        cumulative = [point["cumulative_weight"] for point in result["points"]]

        self.assertEqual(sum(normalized[:12], Decimal("0")), progress)
        self.assertEqual(
            sum(normalized[12:], Decimal("0")), Decimal("1") - progress
        )
        self.assertEqual(cumulative[-1], Decimal("1"))
        self.assertEqual(cumulative, sorted(cumulative))

    def test_records_used_years_samples_and_match_counts(self):
        result = self._build(
            [self._series(year=2024), self._series(year=2025)]
        )

        self.assertEqual(result["comparison_years_used"], [2024, 2025])
        self.assertGreater(result["exact_matches_count"], 0)
        self.assertGreater(result["fallback_matches_count"], 0)
        self.assertEqual(result["points"][0]["samples_count"], 2)

    def test_missing_sample_has_explicit_status_without_invented_weight(self):
        malformed = self._series(year=2025)
        malformed["points"] = malformed["points"][:1]
        result = self._build([malformed])

        self.assertEqual(result["status"], "missing_calendar_sample")
        missing_point = next(
            point for point in result["points"] if point["samples_count"] == 0
        )
        self.assertIsNone(missing_point["raw_daily_weight"])
        self.assertIsNone(missing_point["normalized_daily_weight"])

    def test_non_positive_segment_weight_has_explicit_status(self):
        series = self._series(
            year=2025,
            daily_totals=["0"] * 31,
            full_month_total=Decimal("1"),
        )
        result = self._build([series])

        self.assertEqual(result["status"], "non_positive_segment_weight")

    def test_missing_cutoff_progress_has_explicit_status(self):
        result = self._build(progress=None)

        self.assertEqual(result["status"], "missing_cutoff_progress")

    def test_leap_february_and_month_lengths_are_supported(self):
        for target_month, expected_days in (
            (date(2024, 2, 1), 29),
            (date(2026, 4, 1), 30),
            (date(2026, 7, 1), 31),
        ):
            with self.subTest(target_month=target_month):
                result = self._build(
                    [self._series(year=2023, target_month=target_month)],
                    target_month=target_month,
                    cutoff_day=min(12, expected_days),
                )
                self.assertEqual(len(result["points"]), expected_days)
                self.assertEqual(result["points"][-1]["cumulative_weight"], Decimal("1"))

    def test_single_comparable_year_is_available(self):
        result = self._build([self._series(year=2025)])

        self.assertIn(result["status"], ("available", "available_with_fallback"))
        self.assertEqual(result["comparison_years_used"], [2025])

    def test_unavailable_years_are_excluded(self):
        result = self._build(
            [
                self._series(year=2023, status="no_canonical_snapshot"),
                self._series(year=2024, status="no_branch_rows"),
                self._series(year=2025),
            ]
        )

        self.assertEqual(result["comparison_years_used"], [2025])
        self.assertEqual(
            result["comparison_years_excluded"],
            [
                {"year": 2023, "reason": "no_canonical_snapshot"},
                {"year": 2024, "reason": "no_branch_rows"},
            ],
        )

    def test_without_comparable_history_is_explicit(self):
        result = self._build(
            [self._series(year=2025, status="no_canonical_snapshot")]
        )

        self.assertEqual(result["status"], "no_comparable_history")
        self.assertEqual(result["comparison_years_used"], [])


class BranchHistoricalExpectedDailyCurveTest(unittest.TestCase):
    TARGET_MONTH = date(2026, 7, 1)
    CUTOFF_DAY = 15

    def _series(
        self,
        *,
        year: int,
        daily_totals: list[str],
        status: str = "available",
    ):
        business_month = date(year, self.TARGET_MONTH.month, 1)
        if status != "available":
            return {
                "year": year,
                "business_month": business_month,
                "status": status,
                "snapshot_id": None,
                "snapshot_business_date": None,
                "days_in_month": len(daily_totals),
                "days_with_positive_sale_row": 0,
                "first_positive_sale_date": None,
                "last_positive_sale_date": None,
                "mtd_at_cutoff": None,
                "full_month_total": None,
                "points": [],
            }

        cumulative_total = Decimal("0")
        points = []
        for day, raw_total in enumerate(daily_totals, start=1):
            daily_total = Decimal(raw_total)
            cumulative_total += daily_total
            points.append(
                {
                    "day": day,
                    "date": business_month.replace(day=day),
                    "daily_total": daily_total,
                    "cumulative_total": cumulative_total,
                    "has_positive_sale_row": daily_total > 0,
                }
            )

        effective_cutoff = min(self.CUTOFF_DAY, len(points))
        return {
            "year": year,
            "business_month": business_month,
            "status": "available",
            "snapshot_id": year,
            "snapshot_business_date": business_month.replace(day=len(points)),
            "days_in_month": len(points),
            "days_with_positive_sale_row": sum(
                point["has_positive_sale_row"] for point in points
            ),
            "first_positive_sale_date": None,
            "last_positive_sale_date": None,
            "mtd_at_cutoff": points[effective_cutoff - 1]["cumulative_total"],
            "full_month_total": cumulative_total,
            "points": points,
        }

    def _build(
        self,
        series,
        *,
        target_month: date | None = None,
        cutoff_day: int | None = None,
        expected_month_total: Decimal | None = Decimal("620.00"),
    ):
        return build_branch_historical_expected_daily_curve(
            historical_series=series,
            target_month=target_month or self.TARGET_MONTH,
            cutoff_day=cutoff_day or self.CUTOFF_DAY,
            historical_expected_month_total=expected_month_total,
        )

    def test_builds_31_day_curve_with_multiple_comparable_years(self):
        result = self._build(
            [
                self._series(year=2023, daily_totals=["10"] * 31),
                self._series(year=2024, daily_totals=["20"] * 31),
            ]
        )

        self.assertEqual(result["status"], "available")
        self.assertEqual(len(result["points"]), 31)
        self.assertEqual(result["comparison_years_used"], [2023, 2024])
        self.assertEqual(result["samples_count"], 2)

    def test_cutoff_matches_current_aggregate_progress_method(self):
        series = [
            self._series(year=2023, daily_totals=["10"] * 31),
            self._series(year=2024, daily_totals=["30"] * 31),
        ]
        result = self._build(series)
        legacy_progress = (
            sum((item["mtd_at_cutoff"] for item in series), Decimal("0"))
            / sum((item["full_month_total"] for item in series), Decimal("0"))
        )

        self.assertEqual(
            result["historical_progress_pct_at_cutoff"],
            legacy_progress,
        )

    def test_cutoff_expected_total_matches_current_historical_expected_mtd(self):
        series = [
            self._series(year=2023, daily_totals=["10"] * 31),
            self._series(year=2024, daily_totals=["30"] * 31),
        ]
        aggregate_month_total = sum(
            (item["full_month_total"] for item in series), Decimal("0")
        )
        expected_month_total = aggregate_month_total / Decimal(len(series))
        result = self._build(series, expected_month_total=expected_month_total)
        legacy_expected_mtd = (
            sum((item["mtd_at_cutoff"] for item in series), Decimal("0"))
            / Decimal(len(series))
        )

        self.assertEqual(
            result["historical_expected_mtd_at_cutoff"],
            legacy_expected_mtd,
        )

    def test_last_point_is_complete_and_equals_expected_close(self):
        result = self._build(
            [self._series(year=2025, daily_totals=["1"] * 31)]
        )
        last_point = result["points"][-1]

        self.assertEqual(last_point["historical_progress_pct"], Decimal("1"))
        self.assertEqual(last_point["expected_cumulative_total"], Decimal("620.00"))

    def test_daily_totals_sum_exactly_to_expected_close(self):
        result = self._build(
            [self._series(year=2025, daily_totals=["1"] * 31)]
        )

        self.assertEqual(
            sum(
                (point["expected_daily_total"] for point in result["points"]),
                Decimal("0"),
            ),
            Decimal("620.00"),
        )

    def test_curve_is_monotonic_non_decreasing(self):
        result = self._build(
            [self._series(year=2025, daily_totals=["3", "0"] * 15 + ["1"])]
        )
        cumulative = [
            point["expected_cumulative_total"] for point in result["points"]
        ]

        self.assertEqual(cumulative, sorted(cumulative))
        self.assertTrue(
            all(point["expected_daily_total"] >= 0 for point in result["points"])
        )

    def test_zero_sale_days_preserve_curve(self):
        result = self._build(
            [self._series(year=2025, daily_totals=["10", "0"] + ["1"] * 29)]
        )

        self.assertEqual(
            result["points"][1]["expected_cumulative_total"],
            result["points"][0]["expected_cumulative_total"],
        )
        self.assertEqual(result["points"][1]["expected_daily_total"], Decimal("0"))

    def test_unavailable_years_are_excluded_with_explicit_reasons(self):
        result = self._build(
            [
                self._series(
                    year=2023,
                    daily_totals=["0"] * 31,
                    status="no_canonical_snapshot",
                ),
                self._series(
                    year=2024,
                    daily_totals=["0"] * 31,
                    status="no_branch_rows",
                ),
                self._series(year=2025, daily_totals=["1"] * 31),
            ]
        )

        self.assertEqual(
            result["comparison_years_excluded"],
            [
                {"year": 2023, "reason": "no_canonical_snapshot"},
                {"year": 2024, "reason": "no_branch_rows"},
            ],
        )

    def test_zero_full_month_total_is_excluded(self):
        result = self._build(
            [
                self._series(year=2024, daily_totals=["0"] * 31),
                self._series(year=2025, daily_totals=["1"] * 31),
            ]
        )

        self.assertEqual(result["comparison_years_used"], [2025])
        self.assertEqual(
            result["comparison_years_excluded"],
            [{"year": 2024, "reason": "non_positive_full_month_total"}],
        )

    def test_without_usable_years_returns_no_comparable_history(self):
        result = self._build(
            [self._series(year=2025, daily_totals=["0"] * 31)]
        )

        self.assertEqual(result["status"], "no_comparable_history")
        self.assertEqual(result["points"], [])

    def test_missing_expected_month_total_returns_empty_curve(self):
        result = self._build(
            [self._series(year=2025, daily_totals=["1"] * 31)],
            expected_month_total=None,
        )

        self.assertEqual(result["status"], "missing_expected_month_total")
        self.assertEqual(result["points"], [])

    def test_single_year_builds_without_inventing_confidence(self):
        result = self._build(
            [self._series(year=2025, daily_totals=["1"] * 31)]
        )

        self.assertEqual(result["samples_count"], 1)
        self.assertEqual(result["points"][0]["samples_count"], 1)
        self.assertNotIn("confidence", result)

    def test_leap_and_non_leap_february_keep_both_years(self):
        self.TARGET_MONTH = date(2024, 2, 1)
        self.addCleanup(setattr, self, "TARGET_MONTH", date(2026, 7, 1))
        series = [
            self._series(year=2023, daily_totals=["1"] * 28),
            self._series(year=2024, daily_totals=["1"] * 29),
        ]
        result = self._build(
            series,
            target_month=date(2024, 2, 1),
            cutoff_day=20,
            expected_month_total=Decimal("28.5"),
        )

        self.assertEqual(len(result["points"]), 29)
        self.assertEqual(result["points"][-1]["sample_years"], [2023, 2024])
        self.assertEqual(result["points"][-1]["samples_count"], 2)
        self.assertEqual(result["points"][-1]["historical_progress_pct"], Decimal("1"))

    def test_all_numeric_curve_values_remain_decimal(self):
        result = self._build(
            [self._series(year=2025, daily_totals=["1.25"] * 31)]
        )

        self.assertIsInstance(result["historical_expected_month_total"], Decimal)
        self.assertIsInstance(result["historical_progress_pct_at_cutoff"], Decimal)
        self.assertIsInstance(result["historical_expected_mtd_at_cutoff"], Decimal)
        for point in result["points"]:
            self.assertIsInstance(point["historical_progress_pct"], Decimal)
            self.assertIsInstance(point["expected_daily_total"], Decimal)
            self.assertIsInstance(point["expected_cumulative_total"], Decimal)


class BranchGoalPaceDetailTest(unittest.TestCase):
    TARGET_MONTH = date(2026, 7, 1)
    CUTOFF_DAY = 15

    def _expected_curve(
        self,
        *,
        target_month: date | None = None,
        cutoff_day: int | None = None,
        status: str = "available",
        daily_weights: list[str] | None = None,
    ):
        target_month = target_month or self.TARGET_MONTH
        cutoff_day = cutoff_day or self.CUTOFF_DAY
        if status != "available":
            return {
                "status": status,
                "method": "fixture",
                "target_month": target_month,
                "cutoff_day": cutoff_day,
                "comparison_years_requested": [2024, 2025],
                "comparison_years_used": [],
                "comparison_years_excluded": [],
                "samples_count": 0,
                "historical_expected_month_total": None,
                "historical_progress_pct_at_cutoff": None,
                "historical_expected_mtd_at_cutoff": None,
                "points": [],
            }

        days_in_month = 31 if target_month.month == 7 else 29
        weights = [
            Decimal(value)
            for value in (daily_weights or ["1"] * days_in_month)
        ]
        month_total = sum(weights, Decimal("0"))
        cumulative = Decimal("0")
        points = []
        for day, weight in enumerate(weights, start=1):
            cumulative += weight
            progress = cumulative / month_total
            if day == len(weights):
                progress = Decimal("1")
            points.append(
                {
                    "day": day,
                    "date": target_month.replace(day=day),
                    "historical_progress_pct": progress,
                    "expected_daily_total": weight,
                    "expected_cumulative_total": cumulative,
                    "sample_years": [2024, 2025],
                    "samples_count": 2,
                }
            )
        return {
            "status": "available",
            "method": "fixture",
            "target_month": target_month,
            "cutoff_day": cutoff_day,
            "comparison_years_requested": [2024, 2025],
            "comparison_years_used": [2024, 2025],
            "comparison_years_excluded": [],
            "samples_count": 2,
            "historical_expected_month_total": month_total,
            "historical_progress_pct_at_cutoff": points[cutoff_day - 1][
                "historical_progress_pct"
            ],
            "historical_expected_mtd_at_cutoff": points[cutoff_day - 1][
                "expected_cumulative_total"
            ],
            "points": points,
        }

    def _build(
        self,
        *,
        goal_status: str = "available",
        goal_month: Decimal | None = Decimal("310"),
        real_mtd_at_cutoff: Decimal | None = Decimal("150"),
        projected_close: Decimal | None = Decimal("310"),
        target_month: date | None = None,
        cutoff_day: int | None = None,
        historical_expected=None,
    ):
        target_month = target_month or self.TARGET_MONTH
        cutoff_day = cutoff_day or self.CUTOFF_DAY
        historical_expected = historical_expected or self._expected_curve(
            target_month=target_month,
            cutoff_day=cutoff_day,
        )
        previous_progress = Decimal("0")
        distribution_points = []
        for curve_point in historical_expected["points"]:
            progress = curve_point["historical_progress_pct"]
            normalized_weight = progress - previous_progress
            point_date = curve_point["date"]
            distribution_points.append(
                {
                    "day": curve_point["day"],
                    "date": point_date,
                    "weekday": point_date.strftime("%A").lower(),
                    "weekday_index": point_date.weekday(),
                    "weekday_ordinal": ((point_date.day - 1) // 7) + 1,
                    "alignment_key": (
                        f"{point_date.strftime('%A').lower()}:"
                        f"{((point_date.day - 1) // 7) + 1}"
                    ),
                    "raw_daily_weight": normalized_weight,
                    "normalized_daily_weight": normalized_weight,
                    "cumulative_weight": progress,
                    "samples_count": curve_point["samples_count"],
                    "sample_years": curve_point["sample_years"].copy(),
                    "used_fallback": False,
                    "historical_samples": [],
                }
            )
            previous_progress = progress
        distribution = {
            "status": (
                "available"
                if historical_expected["status"] == "available"
                else "no_comparable_history"
            ),
            "method": "weekday_ordinal_aligned_historical_weights",
            "target_month": target_month,
            "cutoff_day": cutoff_day,
            "historical_progress_pct_at_cutoff": historical_expected[
                "historical_progress_pct_at_cutoff"
            ],
            "comparison_years_requested": [2024, 2025],
            "comparison_years_used": [2024, 2025],
            "comparison_years_excluded": [],
            "exact_matches_count": len(distribution_points) * 2,
            "fallback_matches_count": 0,
            "points": distribution_points,
        }
        return _build_branch_goal_pace_detail(
            goal_status=goal_status,
            goal_month=goal_month,
            real_mtd_at_cutoff=real_mtd_at_cutoff,
            projected_close=projected_close,
            target_month=target_month,
            cutoff_day=cutoff_day,
            historical_expected=historical_expected,
            calendar_aligned_distribution=distribution,
        )

    def test_available_contract_has_explicit_basis_method_and_metadata(self):
        result = self._build()

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["metric_basis"], "total_mtd")
        self.assertEqual(result["goal_metric_basis"], "total_mtd")
        self.assertEqual(result["distribution_basis"], "venta_total_base")
        self.assertEqual(
            result["method"],
            "goal_month_by_weekday_ordinal_aligned_historical_weights",
        )
        self.assertTrue(result["includes_agregadoras"])
        self.assertTrue(result["aggregadoras_assumed_same_daily_shape"])
        self.assertIn("venta base", result["comparability_note"])

    def test_no_goal_and_partial_goal_follow_precedence(self):
        no_goal = self._build(goal_status="pending", goal_month=None)
        partial = self._build(goal_status="partial", goal_month=Decimal("310"))

        self.assertEqual(no_goal["status"], "no_goal")
        self.assertEqual(partial["status"], "partial_goal")
        self.assertEqual(no_goal["points"], [])
        self.assertEqual(partial["points"], [])

    def test_zero_negative_and_non_finite_goals_are_invalid(self):
        for goal in (Decimal("0"), Decimal("-1"), Decimal("NaN")):
            with self.subTest(goal=goal):
                result = self._build(goal_month=goal)
                self.assertEqual(result["status"], "invalid_goal")
                self.assertEqual(result["points"], [])
                if not goal.is_finite():
                    self.assertIsNone(result["goal_month"])

    def test_historical_curve_unavailable_preserves_independent_metrics(self):
        curve = self._expected_curve(status="no_comparable_history")
        result = self._build(historical_expected=curve)

        self.assertEqual(result["status"], "historical_curve_unavailable")
        self.assertEqual(result["goal_month"], Decimal("310"))
        self.assertEqual(result["real_mtd_at_cutoff"], Decimal("150"))
        self.assertEqual(result["remaining_to_goal"], Decimal("160"))
        self.assertEqual(result["remaining_days"], 16)
        self.assertEqual(result["required_daily_average"], Decimal("10"))
        self.assertIsNone(result["goal_expected_mtd_at_cutoff"])
        self.assertEqual(result["points"], [])

    def test_projection_unavailable_preserves_curve_and_pace_metrics(self):
        result = self._build(projected_close=None)

        self.assertEqual(result["status"], "projection_unavailable")
        self.assertEqual(result["goal_expected_mtd_at_cutoff"], Decimal("150"))
        self.assertEqual(result["gap_vs_goal_pace"], Decimal("0"))
        self.assertEqual(len(result["points"]), 31)
        self.assertIsNone(result["projected_path"])
        self.assertIsNone(result["projected_gap_to_goal"])
        self.assertIsNone(result["projected_goal_attainment_pct"])

    def test_unavailable_projected_path_preserves_goal_curve(self):
        unavailable_path = {
            "status": "projection_below_current_mtd",
            "points": [],
        }
        with patch(
            "app.warehouse.services.track_forecast_service.build_branch_projected_daily_path",
            return_value=unavailable_path,
        ):
            result = self._build(projected_close=Decimal("149"))

        self.assertEqual(result["status"], "projection_unavailable")
        self.assertEqual(len(result["points"]), 31)
        self.assertIs(result["projected_path"], unavailable_path)
        self.assertIsNone(result["projected_gap_to_goal"])

    def test_goal_curve_ends_and_sums_exactly_to_goal(self):
        result = self._build(goal_month=Decimal("310.123456789"))

        self.assertEqual(
            result["points"][-1]["goal_expected_cumulative"],
            Decimal("310.123456789"),
        )
        self.assertEqual(
            sum(
                (point["goal_expected_daily"] for point in result["points"]),
                Decimal("0"),
            ),
            Decimal("310.123456789"),
        )

    def test_cutoff_point_gap_and_ratio_are_exact(self):
        result = self._build(real_mtd_at_cutoff=Decimal("140"))
        cutoff = result["points"][self.CUTOFF_DAY - 1]

        self.assertEqual(result["goal_expected_mtd_at_cutoff"], Decimal("150"))
        self.assertEqual(
            cutoff["goal_expected_cumulative"],
            result["goal_expected_mtd_at_cutoff"],
        )
        self.assertEqual(result["gap_vs_goal_pace"], Decimal("-10"))
        self.assertEqual(result["gap_vs_goal_pace_pct"], Decimal("-10") / Decimal("150"))

    def test_remaining_and_required_average_never_go_negative(self):
        result = self._build(real_mtd_at_cutoff=Decimal("400"), projected_close=Decimal("400"))

        self.assertEqual(result["remaining_to_goal"], Decimal("0"))
        self.assertEqual(result["required_daily_average"], Decimal("0"))

    def test_last_day_with_missing_goal_has_no_required_average(self):
        curve = self._expected_curve(cutoff_day=31)
        result = self._build(
            cutoff_day=31,
            historical_expected=curve,
            real_mtd_at_cutoff=Decimal("300"),
            projected_close=None,
        )

        self.assertEqual(result["remaining_days"], 0)
        self.assertEqual(result["remaining_to_goal"], Decimal("10"))
        self.assertIsNone(result["required_daily_average"])

    def test_projected_gap_and_attainment_ratio_are_exact(self):
        result = self._build(projected_close=Decimal("341"))

        self.assertEqual(result["projected_gap_to_goal"], Decimal("31"))
        self.assertEqual(result["projected_goal_attainment_pct"], Decimal("1.1"))

    def test_projected_path_uses_total_and_exact_anchors(self):
        curve = self._expected_curve(
            daily_weights=["1"] * 15 + [str(day) for day in range(1, 17)]
        )
        result = self._build(
            historical_expected=curve,
            projected_close=Decimal("400"),
        )
        path = result["projected_path"]

        self.assertEqual(path["metric_basis"], "total_mtd")
        self.assertEqual(
            path["points"][0]["projected_cumulative_total"],
            Decimal("150"),
        )
        self.assertEqual(
            path["points"][-1]["projected_cumulative_total"],
            Decimal("400"),
        )
        self.assertGreater(
            len({point["projected_daily_increment"] for point in path["points"][1:]}),
            1,
        )

    def test_all_numeric_goal_values_remain_decimal(self):
        result = self._build(projected_close=Decimal("341"))
        scalar_fields = (
            "goal_month",
            "goal_expected_mtd_at_cutoff",
            "real_mtd_at_cutoff",
            "gap_vs_goal_pace",
            "gap_vs_goal_pace_pct",
            "remaining_to_goal",
            "required_daily_average",
            "projected_close",
            "projected_gap_to_goal",
            "projected_goal_attainment_pct",
        )

        for field in scalar_fields:
            self.assertIsInstance(result[field], Decimal)
        for point in result["points"]:
            self.assertIsInstance(point["historical_progress_pct"], Decimal)
            self.assertIsInstance(point["goal_expected_daily"], Decimal)
            self.assertIsInstance(point["goal_expected_cumulative"], Decimal)

    def test_decreasing_historical_curve_is_explicit_inconsistency(self):
        curve = self._expected_curve()
        curve["points"][1]["historical_progress_pct"] = Decimal("0")

        with self.assertRaisesRegex(
            BranchForecastDetailConsistencyError,
            "incrementos negativos",
        ):
            self._build(historical_expected=curve)


class BranchProjectedDailyPathTest(unittest.TestCase):
    TARGET_MONTH = date(2026, 7, 1)
    CUTOFF_DAY = 15

    def _expected_curve(
        self,
        *,
        target_month: date | None = None,
        cutoff_day: int | None = None,
        daily_weights: list[str] | None = None,
        status: str = "available",
    ):
        target_month = target_month or self.TARGET_MONTH
        cutoff_day = cutoff_day or self.CUTOFF_DAY
        weights = [Decimal(value) for value in (daily_weights or ["1"] * 31)]

        if status != "available":
            return {
                "status": status,
                "method": "test_expected_curve",
                "target_month": target_month,
                "cutoff_day": cutoff_day,
                "comparison_years_requested": [2024, 2025],
                "comparison_years_used": [2024, 2025],
                "comparison_years_excluded": [],
                "samples_count": 2,
                "historical_expected_month_total": None,
                "historical_progress_pct_at_cutoff": None,
                "historical_expected_mtd_at_cutoff": None,
                "points": [],
            }

        month_total = sum(weights, Decimal("0"))
        cumulative = Decimal("0")
        points = []
        for day, weight in enumerate(weights, start=1):
            cumulative += weight
            progress = cumulative / month_total
            if day == len(weights):
                progress = Decimal("1")
            points.append(
                {
                    "day": day,
                    "date": target_month.replace(day=day),
                    "historical_progress_pct": progress,
                    "expected_daily_total": weight,
                    "expected_cumulative_total": cumulative,
                    "sample_years": [2024, 2025],
                    "samples_count": 2,
                }
            )

        return {
            "status": "available",
            "method": "test_expected_curve",
            "target_month": target_month,
            "cutoff_day": cutoff_day,
            "comparison_years_requested": [2024, 2025],
            "comparison_years_used": [2024, 2025],
            "comparison_years_excluded": [],
            "samples_count": 2,
            "historical_expected_month_total": month_total,
            "historical_progress_pct_at_cutoff": points[cutoff_day - 1][
                "historical_progress_pct"
            ],
            "historical_expected_mtd_at_cutoff": points[cutoff_day - 1][
                "expected_cumulative_total"
            ],
            "points": points,
        }

    def _build(
        self,
        *,
        expected_curve=None,
        target_month: date | None = None,
        cutoff_day: int | None = None,
        metric_basis: str = "total_mtd",
        current_mtd_at_cutoff: Decimal | None = Decimal("150"),
        projected_close: Decimal | None = Decimal("310"),
    ):
        target_month = target_month or self.TARGET_MONTH
        cutoff_day = cutoff_day or self.CUTOFF_DAY
        return build_branch_projected_daily_path(
            expected_curve=expected_curve
            or self._expected_curve(
                target_month=target_month,
                cutoff_day=cutoff_day,
            ),
            target_month=target_month,
            cutoff_day=cutoff_day,
            metric_basis=metric_basis,
            current_mtd_at_cutoff=current_mtd_at_cutoff,
            projected_close=projected_close,
        )

    def test_builds_available_31_day_path_from_cutoff_to_month_end(self):
        result = self._build()

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["method"], "historical_remaining_daily_weights")
        self.assertEqual(len(result["points"]), 17)
        self.assertEqual(result["comparison_years_used"], [2024, 2025])
        self.assertEqual(result["samples_count"], 2)

    def test_cutoff_point_is_exact_zero_increment_anchor(self):
        first = self._build()["points"][0]

        self.assertEqual(first["day"], self.CUTOFF_DAY)
        self.assertEqual(first["date"], date(2026, 7, 15))
        self.assertEqual(first["point_kind"], "cutoff_anchor")
        self.assertEqual(first["projected_cumulative_total"], Decimal("150"))
        self.assertEqual(first["projected_daily_increment"], Decimal("0"))

    def test_last_point_and_increment_sum_close_exactly(self):
        result = self._build(
            projected_close=Decimal("310.123456789"),
        )

        self.assertEqual(
            result["points"][-1]["projected_cumulative_total"],
            Decimal("310.123456789"),
        )
        self.assertEqual(
            sum(
                (
                    point["projected_daily_increment"]
                    for point in result["points"][1:]
                ),
                Decimal("0"),
            ),
            result["projected_remaining"],
        )

    def test_non_uniform_historical_weights_produce_non_linear_path(self):
        weights = ["1"] * 15 + [str(day) for day in range(1, 17)]
        result = self._build(
            expected_curve=self._expected_curve(daily_weights=weights)
        )
        future_increments = [
            point["projected_daily_increment"] for point in result["points"][1:]
        ]

        self.assertGreater(len(set(future_increments)), 1)

    def test_path_is_monotonic_and_increments_are_non_negative(self):
        weights = ["2", "0"] * 15 + ["1"]
        result = self._build(
            expected_curve=self._expected_curve(daily_weights=weights)
        )
        cumulative = [
            point["projected_cumulative_total"] for point in result["points"]
        ]

        self.assertEqual(cumulative, sorted(cumulative))
        self.assertTrue(
            all(
                point["projected_daily_increment"] >= 0
                for point in result["points"]
            )
        )

    def test_unavailable_expected_curve_returns_empty_path(self):
        result = self._build(
            expected_curve=self._expected_curve(status="no_comparable_history")
        )

        self.assertEqual(result["status"], "expected_curve_unavailable")
        self.assertEqual(result["points"], [])

    def test_missing_current_mtd_returns_empty_path(self):
        result = self._build(current_mtd_at_cutoff=None)

        self.assertEqual(result["status"], "missing_current_mtd")
        self.assertEqual(result["points"], [])

    def test_missing_projected_close_returns_empty_path(self):
        result = self._build(projected_close=None)

        self.assertEqual(result["status"], "missing_projected_close")
        self.assertEqual(result["points"], [])

    def test_projection_below_current_mtd_returns_empty_path(self):
        result = self._build(projected_close=Decimal("149.99"))

        self.assertEqual(result["status"], "projection_below_current_mtd")
        self.assertEqual(result["points"], [])

    def test_equal_month_end_projection_returns_single_anchor(self):
        target_month = date(2026, 7, 1)
        result = self._build(
            target_month=target_month,
            cutoff_day=31,
            expected_curve=self._expected_curve(cutoff_day=31),
            current_mtd_at_cutoff=Decimal("310"),
            projected_close=Decimal("310"),
        )

        self.assertEqual(result["status"], "available")
        self.assertEqual(len(result["points"]), 1)
        self.assertEqual(result["points"][0]["point_kind"], "cutoff_anchor")

    def test_different_month_end_projection_is_inconsistent(self):
        result = self._build(
            cutoff_day=31,
            expected_curve=self._expected_curve(cutoff_day=31),
            projected_close=Decimal("311"),
        )

        self.assertEqual(result["status"], "inconsistent_month_end_projection")
        self.assertEqual(result["points"], [])

    def test_curve_without_remaining_historical_progress_is_unavailable(self):
        weights = ["1"] * 15 + ["0"] * 16
        result = self._build(
            expected_curve=self._expected_curve(daily_weights=weights)
        )

        self.assertEqual(result["status"], "no_remaining_historical_progress")
        self.assertEqual(result["remaining_historical_progress"], Decimal("0"))
        self.assertEqual(result["points"], [])

    def test_metric_basis_is_preserved_without_changing_formula(self):
        results = {
            basis: self._build(metric_basis=basis)
            for basis in ("base_mtd", "total_mtd")
        }

        self.assertEqual(results["base_mtd"]["metric_basis"], "base_mtd")
        self.assertEqual(results["total_mtd"]["metric_basis"], "total_mtd")
        self.assertEqual(
            results["base_mtd"]["points"],
            results["total_mtd"]["points"],
        )

    def test_all_numeric_path_values_remain_decimal(self):
        result = self._build()

        for field in (
            "current_mtd_at_cutoff",
            "projected_close",
            "projected_remaining",
            "historical_progress_pct_at_cutoff",
            "remaining_historical_progress",
        ):
            self.assertIsInstance(result[field], Decimal)
        for point in result["points"]:
            for field in (
                "historical_progress_pct",
                "remaining_progress_share",
                "projected_daily_increment",
                "projected_cumulative_total",
            ):
                self.assertIsInstance(point[field], Decimal)

    def test_leap_february_ends_on_day_29(self):
        target_month = date(2024, 2, 1)
        curve = self._expected_curve(
            target_month=target_month,
            cutoff_day=20,
            daily_weights=["1"] * 29,
        )
        result = self._build(
            expected_curve=curve,
            target_month=target_month,
            cutoff_day=20,
            current_mtd_at_cutoff=Decimal("200"),
            projected_close=Decimal("290"),
        )

        self.assertEqual(result["points"][-1]["day"], 29)
        self.assertEqual(result["points"][-1]["date"], date(2024, 2, 29))
        self.assertEqual(
            result["points"][-1]["projected_cumulative_total"],
            Decimal("290"),
        )

    def test_zero_future_historical_weight_preserves_cumulative_total(self):
        weights = ["1"] * 15 + ["0"] + ["1"] * 15
        result = self._build(
            expected_curve=self._expected_curve(daily_weights=weights)
        )
        zero_weight_point = result["points"][1]

        self.assertEqual(zero_weight_point["day"], 16)
        self.assertEqual(zero_weight_point["projected_daily_increment"], Decimal("0"))
        self.assertEqual(
            zero_weight_point["projected_cumulative_total"],
            result["points"][0]["projected_cumulative_total"],
        )
