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
        return [
            {
                "year": 2023,
                "business_month": date(2023, 7, 1),
                "status": "available",
                "snapshot_id": 10,
                "snapshot_business_date": date(2023, 7, 31),
                "days_in_month": 31,
                "days_with_positive_sale_row": 31,
                "first_positive_sale_date": date(2023, 7, 1),
                "last_positive_sale_date": date(2023, 7, 31),
                "mtd_at_cutoff": Decimal("50"),
                "full_month_total": Decimal("100"),
                "points": [],
            },
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

    def _build(self, *, forecast=None, selections=None, expected_curve=None):
        forecast = forecast or self._forecast()
        selections = selections if selections is not None else self._selections()
        expected_curve = expected_curve or self._expected_curve()
        with (
            patch(
                "app.warehouse.services.track_forecast_service.build_venta_total_forecast",
                return_value=forecast,
            ) as base_mock,
            patch(
                "app.warehouse.services.track_forecast_service.select_track_daily_branch_versions",
                return_value=selections,
            ) as select_mock,
            patch(
                "app.warehouse.services.track_forecast_service.build_branch_historical_daily_series",
                return_value=self._historical_series(),
            ) as history_mock,
            patch(
                "app.warehouse.services.track_forecast_service.build_branch_historical_expected_daily_curve",
                return_value=expected_curve,
            ),
        ):
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
        return _build_branch_goal_pace_detail(
            goal_status=goal_status,
            goal_month=goal_month,
            real_mtd_at_cutoff=real_mtd_at_cutoff,
            projected_close=projected_close,
            target_month=target_month,
            cutoff_day=cutoff_day,
            historical_expected=historical_expected
            or self._expected_curve(
                target_month=target_month,
                cutoff_day=cutoff_day,
            ),
        )

    def test_available_contract_has_explicit_basis_method_and_metadata(self):
        result = self._build()

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["metric_basis"], "total_mtd")
        self.assertEqual(result["goal_metric_basis"], "total_mtd")
        self.assertEqual(result["distribution_basis"], "venta_total_base")
        self.assertEqual(result["method"], "goal_month_by_historical_progress")
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
