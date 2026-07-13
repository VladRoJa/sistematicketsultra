from datetime import date, datetime, timezone
from decimal import Decimal
import unittest
from unittest.mock import patch

from flask import Flask

from app.extensions import db
from app.models.warehouse import TrackDailyMartORM, TrackDailyVersionORM
from app.warehouse.services.track_forecast_service import (
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
