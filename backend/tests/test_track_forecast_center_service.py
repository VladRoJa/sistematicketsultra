from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.warehouse.services.track_forecast_center_service import (
    BranchForecastCenterResult,
    ForecastCenterAccess,
    ForecastCenterAuthorizationError,
    ForecastCenterBranch,
    ForecastCenterUniverse,
    ForecastCenterValidationError,
    aggregate_forecast_center_results,
    aggregate_forecast_center_series,
    bulk_load_forecast_center_data,
    build_forecast_center,
    build_forecast_center_catalogs,
    calculate_compact_branch_forecast,
    resolve_forecast_center_access,
    resolve_forecast_center_universe,
    select_forecast_center_scope,
    _build_breakdown,
)


def _branch(
    canon: str,
    branch_id: int,
    *,
    cohort: str = "legacy_21",
    region: str | None = "R1",
) -> ForecastCenterBranch:
    return ForecastCenterBranch(
        sucursal_canon=canon,
        sucursal_id=branch_id,
        label=canon.title(),
        display_order=branch_id,
        operational_status="ACTIVA",
        cohort=cohort,
        region_key=region,
        region_label=region,
        region_assignment_status="available" if region else "missing",
    )


def _result(
    canon: str,
    *,
    branch_id: int = 1,
    cohort: str = "legacy_21",
    region: str | None = "R1",
    goal: Decimal | None = Decimal("100"),
    real: Decimal | None = Decimal("50"),
    expected: Decimal | None = Decimal("40"),
    projected: Decimal | None = Decimal("120"),
    remaining_days: int = 10,
    actual: list[dict] | None = None,
    required: list[dict] | None = None,
    projected_series: list[dict] | None = None,
) -> BranchForecastCenterResult:
    valid_goal = goal is not None and goal > 0
    comparable_real = real if valid_goal else None
    comparable_real_to_pace = (
        real if valid_goal and real is not None and expected is not None else None
    )
    projection_comparable = valid_goal and projected is not None and real is not None
    comparable_projected = projected if projection_comparable else None
    return BranchForecastCenterResult(
        identity={
            "sucursal_canon": canon,
            "sucursal_id": branch_id,
            "label": canon.title(),
            "cohort": cohort,
            "region_key": region,
        },
        summary={
            "goal_month": goal,
            "real_mtd": real,
            "real_mtd_comparable_to_goal": comparable_real,
            "real_mtd_comparable_to_pace": comparable_real_to_pace,
            "goal_expected_mtd_at_cutoff": expected if valid_goal else None,
            "gap_vs_goal_pace": (
                comparable_real - expected
                if comparable_real is not None and expected is not None
                else None
            ),
            "projected_close": projected,
            "projected_close_comparable_to_goal": comparable_projected,
            "goal_month_comparable_to_projection": (
                goal if projection_comparable else None
            ),
            "real_mtd_comparable_to_projection": (
                real if projection_comparable else None
            ),
            "projected_gap_to_goal": (
                comparable_projected - goal
                if comparable_projected is not None and goal is not None
                else None
            ),
            "projected_goal_attainment_pct": (
                comparable_projected / goal
                if comparable_projected is not None and goal
                else None
            ),
            "remaining_to_goal": (
                max(goal - real, Decimal("0"))
                if goal is not None and real is not None
                else None
            ),
            "remaining_days": remaining_days,
            "required_daily_average": None,
        },
        series={
            "actual": actual or [],
            "required": required or [],
            "projected": projected_series or [],
        },
        quality={
            "goal_status": "available" if valid_goal else "no_goal",
            "history_status": "available",
            "projection_status": "available" if projected is not None else "unavailable",
            "calendar_status": "available",
            "has_daily_gaps": False,
            "has_calendar_fallback": False,
            "exclusion_reasons": [],
        },
        drilldown={
            "scope": "branch",
            "scope_id": canon,
            "analytic_route": f"/warehouse/track/forecast/branches/{canon}",
        },
    )


class ForecastCenterAccessTest(unittest.TestCase):
    def test_global_roles_are_global(self):
        for role in ("ADMIN", "ADMINISTRADOR", "SUPER_ADMIN", "LECTOR_GLOBAL"):
            with self.subTest(role=role):
                access = resolve_forecast_center_access(
                    SimpleNamespace(rol=role, sucursal_id=1000)
                )
                self.assertTrue(access.is_global)
                self.assertEqual(access.type, "global")

    def test_manager_uses_only_primary_branch(self):
        access = resolve_forecast_center_access(
            SimpleNamespace(
                rol="GERENTE",
                sucursal_id=7,
                sucursales_ids=[7, 8, 9],
            )
        )
        self.assertEqual(access.authorized_branch_ids, (7,))
        self.assertEqual(access.type, "primary_branch")

    def test_regional_uses_assigned_branches(self):
        access = resolve_forecast_center_access(
            SimpleNamespace(
                rol="GERENTE_REGIONAL",
                sucursal_id=1,
                sucursales_ids=[3, 2, 3],
            )
        )
        self.assertEqual(access.authorized_branch_ids, (2, 3))
        self.assertFalse(access.fallback_used)

    def test_regional_empty_pool_uses_primary_fallback(self):
        access = resolve_forecast_center_access(
            SimpleNamespace(
                rol="GERENTE_REGIONAL",
                sucursal_id=5,
                sucursales_ids=[],
            )
        )
        self.assertEqual(access.authorized_branch_ids, (5,))
        self.assertTrue(access.fallback_used)
        self.assertEqual(
            access.fallback_reason,
            "empty_assigned_branches_used_primary_branch",
        )

    def test_unauthorized_role_is_rejected(self):
        with self.assertRaises(ForecastCenterAuthorizationError):
            resolve_forecast_center_access(
                SimpleNamespace(rol="SISTEMAS", sucursal_id=1)
            )

    def test_missing_user_is_rejected(self):
        with self.assertRaises(ForecastCenterAuthorizationError):
            resolve_forecast_center_access(None)


class ForecastCenterScopeTest(unittest.TestCase):
    def setUp(self):
        self.universe = ForecastCenterUniverse(
            branches=[
                _branch("A", 1, region="R1"),
                _branch("B", 2, region="R1"),
                _branch("C", 3, cohort="new_gyms", region="R2"),
            ],
            exclusions=[],
            unauthorized_removed=0,
            total_region_branch_counts={"R1": 2, "R2": 1},
        )

    def test_global_can_select_national(self):
        access = ForecastCenterAccess("global", True, (), 0, role="ADMIN")
        selected = select_forecast_center_scope(
            universe=self.universe,
            access=access,
            scope="national",
            scope_id=None,
            cohort="all",
        )
        self.assertEqual([item.sucursal_canon for item in selected], ["A", "B", "C"])

    def test_global_can_select_region(self):
        access = ForecastCenterAccess("global", True, (), 0, role="ADMIN")
        selected = select_forecast_center_scope(
            universe=self.universe,
            access=access,
            scope="region",
            scope_id="R1",
            cohort="all",
        )
        self.assertEqual([item.sucursal_canon for item in selected], ["A", "B"])

    def test_manager_cannot_select_national(self):
        access = ForecastCenterAccess(
            "primary_branch", False, (1,), 1, role="GERENTE"
        )
        with self.assertRaises(ForecastCenterAuthorizationError):
            select_forecast_center_scope(
                universe=self.universe,
                access=access,
                scope="national",
                scope_id=None,
                cohort="all",
            )

    def test_regional_can_select_authorized_pool(self):
        access = ForecastCenterAccess(
            "assigned_branches", False, (1, 2), 2, role="GERENTE_REGIONAL"
        )
        selected = select_forecast_center_scope(
            universe=self.universe,
            access=access,
            scope="authorized_pool",
            scope_id=None,
            cohort="all",
        )
        self.assertEqual(len(selected), 3)

    def test_cohort_filter_uses_canonical_key(self):
        access = ForecastCenterAccess("global", True, (), 0, role="ADMIN")
        selected = select_forecast_center_scope(
            universe=self.universe,
            access=access,
            scope="national",
            scope_id=None,
            cohort="new_gyms",
        )
        self.assertEqual([item.sucursal_canon for item in selected], ["C"])

    def test_unknown_scope_is_validation_error_before_any_query(self):
        user = SimpleNamespace(rol="ADMIN", sucursal_id=1000)
        version = SimpleNamespace(id=1)
        with patch(
            "app.warehouse.services.track_forecast_center_service.resolve_forecast_center_universe"
        ) as resolver:
            with self.assertRaises(ForecastCenterValidationError):
                build_forecast_center(
                    user=user,
                    requested_track_date=date(2026, 7, 14),
                    generation_mode="manual_preview",
                    resolved_version=version,
                    scope="unknown",
                    scope_id=None,
                )
        resolver.assert_not_called()


class ForecastCenterUniverseTest(unittest.TestCase):
    @staticmethod
    def _catalog(
        canon: str,
        branch_id: int | None,
        *,
        active: bool = True,
        display_order: int = 1,
    ):
        return SimpleNamespace(
            sucursal_canon=canon,
            sucursal_id=branch_id,
            track_label=canon,
            display_order=display_order,
            is_track_active=active,
        )

    @staticmethod
    def _sucursal(branch_id: int, status: str = "ACTIVA"):
        return SimpleNamespace(
            sucursal_id=branch_id,
            operational_status=status,
            sucursal=f"Sucursal {branch_id}",
        )

    def _resolve(self, rows, region_rows=None, access=None):
        query = MagicMock()
        query.outerjoin.return_value.order_by.return_value.all.return_value = rows
        access = access or ForecastCenterAccess(
            "global", True, (), 0, role="ADMIN"
        )
        with patch(
            "app.warehouse.services.track_forecast_center_service.db.session.query",
            return_value=query,
        ), patch(
            "app.warehouse.services.track_forecast_center_service._load_region_assignments",
            return_value=region_rows or {},
        ):
            return resolve_forecast_center_universe(
                access=access,
                requested_track_date=date(2026, 7, 14),
            )

    @staticmethod
    def _assignment(region_key="R1"):
        return (
            SimpleNamespace(valid_from=date(2026, 1, 1), valid_to=None),
            SimpleNamespace(region_key=region_key, region_label=region_key),
        )

    def test_only_track_active_and_operationally_active_are_included(self):
        rows = [
            (self._catalog("A", 1), self._sucursal(1)),
            (self._catalog("B", 2, active=False), self._sucursal(2)),
            (self._catalog("C", 3), self._sucursal(3, "CERRADA")),
        ]
        universe = self._resolve(
            rows,
            {1: [self._assignment()]},
        )
        self.assertEqual([item.sucursal_canon for item in universe.branches], ["A"])
        reasons = {reason for item in universe.exclusions for reason in item.reasons}
        self.assertIn("inactive_track_branch", reasons)
        self.assertIn("non_active_operational_status", reasons)

    def test_la_viga_remains_excluded(self):
        universe = self._resolve(
            [(self._catalog("LA_VIGA", 4, display_order=26), self._sucursal(4))]
        )
        self.assertEqual(universe.branches, [])
        self.assertIn("forecast_excluded_branch", universe.exclusions[0].reasons)

    def test_missing_sucursal_id_is_reported(self):
        universe = self._resolve([(self._catalog("SERRANIA", None), None)])
        self.assertEqual(universe.branches, [])
        self.assertIn("missing_sucursal_id", universe.exclusions[0].reasons)

    def test_missing_region_is_reported_but_branch_stays_national(self):
        universe = self._resolve(
            [(self._catalog("A", 1), self._sucursal(1))]
        )
        self.assertEqual(len(universe.branches), 1)
        self.assertIsNone(universe.branches[0].region_key)
        self.assertIn(
            "missing_region_assignment",
            {reason for item in universe.exclusions for reason in item.reasons},
        )

    def test_overlapping_regions_are_reported_without_arbitrary_choice(self):
        universe = self._resolve(
            [(self._catalog("A", 1), self._sucursal(1))],
            {1: [self._assignment("R1"), self._assignment("R2")]},
        )
        self.assertEqual(universe.branches[0].region_assignment_status, "overlapping")
        self.assertIsNone(universe.branches[0].region_key)
        self.assertIn(
            "overlapping_region_assignments",
            {reason for item in universe.exclusions for reason in item.reasons},
        )

    def test_existing_cohort_service_rule_is_used(self):
        universe = self._resolve(
            [
                (self._catalog("A", 1, display_order=21), self._sucursal(1)),
                (self._catalog("B", 2, display_order=22), self._sucursal(2)),
            ],
            {1: [self._assignment()], 2: [self._assignment()]},
        )
        self.assertEqual(
            [item.cohort for item in universe.branches],
            ["legacy_21", "new_gyms"],
        )

    def test_unauthorized_branch_name_is_not_exposed(self):
        access = ForecastCenterAccess(
            "primary_branch", False, (1,), 1, role="GERENTE"
        )
        universe = self._resolve(
            [(self._catalog("SECRET", 2), self._sucursal(2))],
            {2: [self._assignment()]},
            access,
        )
        self.assertEqual(universe.branches, [])
        self.assertEqual(universe.unauthorized_removed, 1)
        unauthorized = next(
            item for item in universe.exclusions if "unauthorized_branch" in item.reasons
        )
        self.assertIsNone(unauthorized.sucursal_canon)


class ForecastCenterCatalogsTest(unittest.TestCase):
    def test_global_catalogs_include_global_scopes(self):
        universe = ForecastCenterUniverse(
            branches=[_branch("A", 1)],
            exclusions=[],
            unauthorized_removed=0,
            total_region_branch_counts={"R1": 1},
        )
        user = SimpleNamespace(rol="ADMIN", sucursal_id=1000)
        with patch(
            "app.warehouse.services.track_forecast_center_service.resolve_forecast_center_universe",
            return_value=universe,
        ):
            payload = build_forecast_center_catalogs(
                user=user,
                requested_track_date=date(2026, 7, 14),
            )
        self.assertTrue(payload["capabilities"]["can_view_national"])
        self.assertEqual(
            [item["key"] for item in payload["scopes"]],
            ["national", "region", "branch"],
        )

    def test_manager_catalogs_only_include_primary_branch(self):
        universe = ForecastCenterUniverse(
            branches=[_branch("A", 1)],
            exclusions=[],
            unauthorized_removed=10,
            total_region_branch_counts={"R1": 5},
        )
        user = SimpleNamespace(rol="GERENTE", sucursal_id=1)
        with patch(
            "app.warehouse.services.track_forecast_center_service.resolve_forecast_center_universe",
            return_value=universe,
        ):
            payload = build_forecast_center_catalogs(
                user=user,
                requested_track_date=date(2026, 7, 14),
            )
        self.assertEqual(payload["scopes"], [{"key": "branch", "label": "branch"}])
        self.assertEqual([item["sucursal_id"] for item in payload["branches"]], [1])

    def test_regional_catalog_marks_partial_region_access(self):
        universe = ForecastCenterUniverse(
            branches=[_branch("A", 1)],
            exclusions=[],
            unauthorized_removed=4,
            total_region_branch_counts={"R1": 5},
        )
        user = SimpleNamespace(
            rol="GERENTE_REGIONAL", sucursal_id=1, sucursales_ids=[1]
        )
        with patch(
            "app.warehouse.services.track_forecast_center_service.resolve_forecast_center_universe",
            return_value=universe,
        ):
            payload = build_forecast_center_catalogs(
                user=user,
                requested_track_date=date(2026, 7, 14),
            )
        self.assertEqual(payload["context"]["default_scope"], "authorized_pool")
        self.assertTrue(payload["regions"][0]["is_partial_access"])


class ForecastCenterAggregationTest(unittest.TestCase):
    def test_direct_sums_and_derived_percentages_use_aggregate_sums(self):
        result = aggregate_forecast_center_results(
            [
                _result("A", goal=Decimal("100"), real=Decimal("50"), expected=Decimal("40"), projected=Decimal("120")),
                _result("B", goal=Decimal("300"), real=Decimal("150"), expected=Decimal("120"), projected=Decimal("240")),
            ]
        )
        self.assertEqual(result["goal_month"], Decimal("400"))
        self.assertEqual(result["real_mtd"], Decimal("200"))
        self.assertEqual(result["gap_vs_goal_pace"], Decimal("40"))
        self.assertEqual(result["gap_vs_goal_pace_pct"], Decimal("40") / Decimal("160"))
        self.assertEqual(result["projected_goal_attainment_pct"], Decimal("360") / Decimal("400"))
        self.assertNotEqual(result["projected_goal_attainment_pct"], Decimal("1"))

    def test_null_never_becomes_zero(self):
        result = aggregate_forecast_center_results(
            [_result("A", goal=None, real=None, expected=None, projected=None)]
        )
        self.assertIsNone(result["goal_month"])
        self.assertIsNone(result["real_mtd"])
        self.assertIsNone(result["projected_close"])

    def test_branch_without_goal_contributes_only_to_total_real(self):
        result = aggregate_forecast_center_results(
            [
                _result("A", goal=Decimal("100"), real=Decimal("50")),
                _result("B", goal=None, real=Decimal("70"), expected=None),
            ]
        )
        self.assertEqual(result["real_mtd"], Decimal("120"))
        self.assertEqual(result["real_mtd_comparable_to_goal"], Decimal("50"))
        self.assertEqual(result["goal_month"], Decimal("100"))
        self.assertEqual(result["metric_coverage"]["goal_month"]["status"], "partial")

    def test_pace_gap_uses_only_branches_in_real_expected_intersection(self):
        results = [
            _result("A", real=Decimal("50"), expected=Decimal("40")),
            _result("B", branch_id=2, real=Decimal("70"), expected=Decimal("60")),
            _result("C", branch_id=3, real=Decimal("80"), expected=None),
            _result(
                "D",
                branch_id=4,
                goal=None,
                real=Decimal("90"),
                expected=None,
                projected=None,
            ),
        ]

        result = aggregate_forecast_center_results(results)

        self.assertEqual(result["real_mtd"], Decimal("290"))
        self.assertEqual(result["real_mtd_comparable_to_pace"], Decimal("120"))
        self.assertEqual(result["goal_expected_mtd_at_cutoff"], Decimal("100"))
        self.assertEqual(result["gap_vs_goal_pace"], Decimal("20"))
        self.assertEqual(result["gap_vs_goal_pace_pct"], Decimal("0.2"))
        self.assertEqual(
            result["metric_coverage"]["real_mtd_comparable_to_pace"][
                "included_branch_count"
            ],
            2,
        )
        self.assertEqual(
            result["gap_vs_goal_pace"],
            sum(
                (
                    item.summary["gap_vs_goal_pace"]
                    for item in results
                    if item.summary["real_mtd_comparable_to_pace"] is not None
                ),
                Decimal("0"),
            ),
        )

    def test_partial_projection_uses_goal_projection_intersection(self):
        result = aggregate_forecast_center_results(
            [
                _result("A", goal=Decimal("100"), projected=Decimal("120")),
                _result("B", goal=Decimal("300"), projected=None),
            ]
        )
        self.assertEqual(result["projected_close"], Decimal("120"))
        self.assertEqual(result["projected_gap_to_goal"], Decimal("20"))
        self.assertEqual(result["projected_goal_attainment_pct"], Decimal("1.2"))
        self.assertEqual(result["metric_coverage"]["projected_close"]["status"], "partial")

    def test_partial_projection_exposes_all_comparable_amounts(self):
        results = [
            _result(
                f"B{index}",
                branch_id=index,
                goal=Decimal("100"),
                real=Decimal("50"),
                projected=Decimal("120") if index <= 21 else None,
            )
            for index in range(1, 26)
        ]

        result = aggregate_forecast_center_results(results)

        self.assertEqual(result["metric_coverage"]["projected_close"]["status"], "partial")
        self.assertEqual(
            result["goal_month_comparable_to_projection"], Decimal("2100")
        )
        self.assertEqual(
            result["real_mtd_comparable_to_projection"], Decimal("1050")
        )
        self.assertEqual(
            result["projected_close_comparable_to_goal"], Decimal("2520")
        )
        self.assertEqual(result["projected_gap_to_goal"], Decimal("420"))
        self.assertEqual(result["projected_goal_attainment_pct"], Decimal("1.2"))

    def test_projection_comparable_fields_are_null_without_projection(self):
        result = aggregate_forecast_center_results(
            [_result("NEW", projected=None)]
        )

        self.assertIsNone(result["projected_close"])
        self.assertIsNone(result["goal_month_comparable_to_projection"])
        self.assertIsNone(result["real_mtd_comparable_to_projection"])
        self.assertIsNone(result["projected_goal_attainment_pct"])

    def test_remaining_to_goal_never_negative(self):
        result = aggregate_forecast_center_results(
            [_result("A", goal=Decimal("100"), real=Decimal("120"))]
        )
        self.assertEqual(result["remaining_to_goal"], Decimal("0"))
        self.assertEqual(result["required_daily_average"], Decimal("0"))

    def test_zero_denominators_return_null(self):
        item = _result(
            "A",
            goal=Decimal("0"),
            real=Decimal("10"),
            expected=Decimal("0"),
            projected=Decimal("20"),
        )
        result = aggregate_forecast_center_results([item])
        self.assertIsNone(result["gap_vs_goal_pace_pct"])
        self.assertIsNone(result["projected_goal_attainment_pct"])

    def test_decimal_is_preserved(self):
        result = aggregate_forecast_center_results(
            [_result("A", goal=Decimal("10.25"), real=Decimal("2.10"))]
        )
        self.assertIsInstance(result["goal_month"], Decimal)
        self.assertIsInstance(result["real_mtd"], Decimal)

    def test_cohort_breakdown_sums_to_total(self):
        results = [
            _result("A", cohort="legacy_21", real=Decimal("10")),
            _result("B", branch_id=2, cohort="new_gyms", real=Decimal("20")),
        ]
        total = aggregate_forecast_center_results(results)
        breakdown = _build_breakdown(
            results=results,
            dimension="cohort",
            total_summary=total,
        )
        self.assertEqual(
            sum((item["summary"]["real_mtd"] for item in breakdown["items"]), Decimal("0")),
            total["real_mtd"],
        )
        self.assertEqual(
            breakdown["items"][0]["drilldown"],
            {"scope": "national", "cohort": "legacy_21"},
        )
        self.assertEqual(
            breakdown["items"][1]["drilldown"],
            {"scope": "national", "cohort": "new_gyms"},
        )

    def test_branch_breakdown_preserves_analytic_route(self):
        results = [_result("A")]
        total = aggregate_forecast_center_results(results)
        breakdown = _build_breakdown(
            results=results,
            dimension="branch",
            total_summary=total,
        )
        self.assertEqual(
            breakdown["items"][0]["drilldown"]["analytic_route"],
            "/warehouse/track/forecast/branches/A",
        )


class ForecastCenterSeriesTest(unittest.TestCase):
    def test_exact_date_sums_daily_and_cumulative(self):
        point_a = {"date": date(2026, 7, 1), "day": 1, "daily": Decimal("10"), "cumulative": Decimal("10"), "status": "available"}
        point_b = {"date": date(2026, 7, 1), "day": 1, "daily": Decimal("20"), "cumulative": Decimal("20"), "status": "available"}
        series = aggregate_forecast_center_series(
            [_result("A", actual=[point_a]), _result("B", actual=[point_b])],
            target_month=date(2026, 7, 1),
        )
        first = series["actual"]["points"][0]
        self.assertEqual(first["daily"], Decimal("30"))
        self.assertEqual(first["cumulative"], Decimal("30"))
        self.assertEqual(first["status"], "available")

    def test_missing_date_is_not_interpolated_and_is_partial(self):
        point = {"date": date(2026, 7, 1), "day": 1, "daily": Decimal("10"), "cumulative": Decimal("10"), "status": "available"}
        series = aggregate_forecast_center_series(
            [_result("A", actual=[point]), _result("B", actual=[])],
            target_month=date(2026, 7, 1),
        )
        first = series["actual"]["points"][0]
        self.assertEqual(first["daily"], Decimal("10"))
        self.assertEqual(first["status"], "partial")
        self.assertEqual(first["exclusion_reasons"]["missing_date"], 1)

    def test_negative_correction_is_preserved(self):
        point = {"date": date(2026, 7, 2), "day": 2, "daily": Decimal("-5"), "cumulative": Decimal("5"), "status": "available_with_negative_adjustment"}
        series = aggregate_forecast_center_series(
            [_result("A", actual=[point])],
            target_month=date(2026, 7, 1),
        )
        self.assertEqual(series["actual"]["points"][1]["daily"], Decimal("-5"))

    def test_inconsistent_components_reduce_actual_coverage(self):
        point = {"date": date(2026, 7, 1), "day": 1, "daily": Decimal("10"), "cumulative": Decimal("10"), "status": "inconsistent_components"}
        series = aggregate_forecast_center_series(
            [_result("A", actual=[point])],
            target_month=date(2026, 7, 1),
        )
        first = series["actual"]["points"][0]
        self.assertIsNone(first["daily"])
        self.assertEqual(first["status"], "unavailable")

    def test_cutoff_anchor_has_zero_projected_daily_value(self):
        anchor = {"date": date(2026, 7, 10), "day": 10, "daily": None, "cumulative": Decimal("100"), "status": "cutoff_anchor"}
        series = aggregate_forecast_center_series(
            [_result("A", projected_series=[anchor])],
            target_month=date(2026, 7, 1),
        )
        point = series["projected"]["points"][9]
        self.assertEqual(point["daily"], Decimal("0"))
        self.assertEqual(point["cumulative"], Decimal("100"))

    def test_missing_projection_only_affects_projected_series(self):
        actual = {"date": date(2026, 7, 1), "day": 1, "daily": Decimal("5"), "cumulative": Decimal("5"), "status": "available"}
        series = aggregate_forecast_center_series(
            [_result("A", actual=[actual], projected_series=[])],
            target_month=date(2026, 7, 1),
        )
        self.assertEqual(series["actual"]["points"][0]["status"], "available")
        self.assertEqual(series["projected"]["status"], "unavailable")

    def test_calendar_grid_supports_all_month_lengths(self):
        for target, expected in (
            (date(2025, 2, 1), 28),
            (date(2024, 2, 1), 29),
            (date(2026, 4, 1), 30),
            (date(2026, 7, 1), 31),
        ):
            with self.subTest(target=target):
                series = aggregate_forecast_center_series([], target_month=target)
                self.assertEqual(len(series["actual"]["points"]), expected)

    def test_projected_last_point_equals_sum_of_branch_closes(self):
        last_date = date(2026, 7, 31)
        first = {"date": last_date, "day": 31, "daily": Decimal("10"), "cumulative": Decimal("120"), "status": "available"}
        second = {"date": last_date, "day": 31, "daily": Decimal("20"), "cumulative": Decimal("230"), "status": "available"}
        series = aggregate_forecast_center_series(
            [_result("A", projected_series=[first]), _result("B", projected_series=[second])],
            target_month=date(2026, 7, 1),
        )
        self.assertEqual(series["projected"]["points"][-1]["cumulative"], Decimal("350"))

    def test_comparable_series_preserve_their_exact_branch_universes(self):
        point_date = date(2026, 7, 10)
        actual_a = {"date": point_date, "day": 10, "daily": Decimal("10"), "cumulative": Decimal("50"), "status": "available"}
        actual_b = {"date": point_date, "day": 10, "daily": Decimal("20"), "cumulative": Decimal("70"), "status": "available"}
        actual_c = {"date": point_date, "day": 10, "daily": Decimal("30"), "cumulative": Decimal("90"), "status": "available"}
        required_a = {"date": point_date, "day": 10, "daily": Decimal("8"), "cumulative": Decimal("40"), "status": "available"}
        required_b = {"date": point_date, "day": 10, "daily": Decimal("12"), "cumulative": Decimal("60"), "status": "available"}
        projected_a = {"date": point_date, "day": 10, "daily": None, "cumulative": Decimal("50"), "status": "cutoff_anchor"}
        series = aggregate_forecast_center_series(
            [
                _result("A", actual=[actual_a], required=[required_a], projected_series=[projected_a]),
                _result("B", branch_id=2, actual=[actual_b], required=[required_b], projected=None),
                _result("C", branch_id=3, actual=[actual_c], required=[], projected=None),
            ],
            target_month=date(2026, 7, 1),
        )

        point_index = 9
        self.assertEqual(series["actual"]["points"][point_index]["cumulative"], Decimal("210"))
        self.assertEqual(series["actual"]["points"][point_index]["included_branch_count"], 3)
        self.assertEqual(series["pace_actual"]["points"][point_index]["cumulative"], Decimal("120"))
        self.assertEqual(
            series["pace_actual"]["points"][point_index]["included_branch_count"],
            series["required"]["points"][point_index]["included_branch_count"],
        )
        for key in ("projection_actual", "projection_required", "projected"):
            self.assertEqual(
                series[key]["points"][point_index]["included_branch_count"], 1
            )
            self.assertEqual(series[key]["points"][point_index]["status"], "partial")
            self.assertEqual(
                series[key]["points"][point_index]["eligible_branch_count"], 3
            )
            self.assertEqual(
                series[key]["points"][point_index]["excluded_branch_count"], 2
            )


class ForecastCenterBulkLoaderTest(unittest.TestCase):
    @patch("app.warehouse.services.track_forecast_center_service._load_canonical_cutoff_bulk")
    @patch("app.warehouse.services.track_forecast_center_service._load_historical_series_bulk")
    @patch("app.warehouse.services.track_forecast_center_service._load_current_candidates_bulk")
    @patch("app.warehouse.services.track_forecast_center_service.TrackMonthlyTargetORM")
    @patch("app.warehouse.services.track_forecast_center_service.TrackDailyMartORM")
    def test_each_bulk_dataset_loader_runs_once_independent_of_branch_count(
        self,
        mart_model,
        target_model,
        current_loader,
        history_loader,
        cutoff_loader,
    ):
        mart_model.query.filter.return_value.all.return_value = []
        target_model.query.filter.return_value.all.return_value = []
        current_loader.return_value = {}
        history_loader.return_value = {}
        cutoff_loader.return_value = (None, None)
        branches = [_branch(f"B{index}", index) for index in range(1, 51)]

        bundle = bulk_load_forecast_center_data(
            branches=branches,
            track_date=date(2026, 7, 14),
            track_daily_version_id=99,
        )

        self.assertEqual(bundle.loader_invocations["mart"], 1)
        self.assertEqual(bundle.loader_invocations["targets"], 1)
        self.assertEqual(bundle.loader_invocations["current_daily_versions"], 1)
        self.assertEqual(
            bundle.loader_invocations["historical_snapshots_and_daily_totals"],
            1,
        )
        self.assertEqual(bundle.loader_invocations["canonical_cutoff"], 1)
        current_loader.assert_called_once()
        history_loader.assert_called_once()
        cutoff_loader.assert_called_once()


class ForecastCenterCompactCalculationTest(unittest.TestCase):
    def test_compact_calculation_uses_preloaded_bundle_without_queries(self):
        branch = _branch("A", 1)
        mart = SimpleNamespace(
            ingreso_real_total_mtd=Decimal("50"),
            ingreso_real_mtd=Decimal("50"),
            ingreso_real_base_mtd=Decimal("40"),
            ingreso_real_agregadora_mtd=Decimal("10"),
            meta_faycgo_mes=Decimal("100"),
        )
        historical = [
            {
                "year": year,
                "business_month": date(year, 7, 1),
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
            }
            for year in (2023, 2024, 2025)
        ]
        bundle = SimpleNamespace(
            target_month=date(2026, 7, 1),
            cutoff_day=14,
            mart_by_branch={"A": mart},
            target_by_branch={},
            current_candidates_by_branch={
                "A": [
                    {
                        "track_date": date(2026, 7, 14),
                        "version_id": 99,
                        "version_type": "preview_operativo",
                        "ingreso_real_base_mtd": Decimal("40"),
                        "ingreso_real_agregadora_mtd": Decimal("10"),
                        "ingreso_real_total_mtd": Decimal("50"),
                    }
                ]
            },
            historical_series_by_branch={"A": historical},
        )
        with patch(
            "app.warehouse.services.track_forecast_center_service.db.session.query"
        ) as query:
            result = calculate_compact_branch_forecast(
                branch=branch,
                bundle=bundle,
                track_date=date(2026, 7, 14),
                track_daily_version_id=99,
            )
        query.assert_not_called()
        self.assertEqual(result.summary["real_mtd"], Decimal("50"))
        self.assertEqual(result.summary["goal_month"], Decimal("100"))
        self.assertIsNone(result.summary["projected_close"])
        self.assertEqual(result.quality["history_status"], "missing_expected_month_total")


if __name__ == "__main__":
    unittest.main()
