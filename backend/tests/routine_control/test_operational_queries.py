from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from app.routine_control.queries.operational_service import (
    RoutineControlAuthorizationError,
    RoutineControlOperationalService,
    RoutineControlValidationError,
)


BRANCHES = [
    {"id": 1, "name": "Centro", "region_key": "NORTE", "region_name": "Norte"},
    {"id": 2, "name": "Sur", "region_key": "SUR", "region_name": "Sur"},
]


class FakeRepository:
    def __init__(self):
        self.last_branch_ids = None
        self.last_filters = None

    def list_operational_branches(self):
        return BRANCHES

    def get_summary(self, filters, branch_ids):
        self.last_filters, self.last_branch_ids = filters, branch_ids
        return {"rows": [
            (1, "Centro", "CON_RUTINA", "MISMO_DIA", 2),
            (1, "Centro", "INCIDENT", None, 1),
        ]}

    def get_freshness(self):
        return {
            "last_successful_pipeline_at_utc": None,
            "last_gasca_success_at_utc": None,
            "last_trainingym_success_at_utc": None,
        }

    def list_members(self, filters, branch_ids, **kwargs):
        self.last_filters, self.last_branch_ids = filters, branch_ids
        member = SimpleNamespace(
            id=10, external_member_id="M-10", external_sale_id="F-10", member_name="Socio",
            email_normalized="socio@example.com", email_original=None, sucursal_id=1,
            source_branch_name="Centro", sale_date=date(2026, 7, 1), classification_status="CLASSIFIED",
            current_status="CON_RUTINA", first_routine_at=date(2026, 7, 1), latest_routine_at=date(2026, 7, 2),
            current_instructor_name="Ana", routine_assignment_type="MISMO_DIA", status_version=2,
        )
        return [(member, "Centro", 1, 2)], 1


def user(role, primary=1, assigned=()):
    return SimpleNamespace(rol=role, sucursal_id=primary, sucursales_ids=list(assigned))


class RoutineControlOperationalServiceTest(unittest.TestCase):
    def setUp(self):
        self.repository = FakeRepository()
        self.service = RoutineControlOperationalService(self.repository)

    def test_manager_scope_is_only_primary_branch(self):
        scope = self.service.resolve_scope(user("GERENTE", primary=1, assigned=(1, 2)))
        self.assertEqual(scope.allowed_branch_ids, (1,))
        self.assertEqual(scope.fixed_branch_id, 1)

    def test_manager_cannot_filter_another_branch(self):
        with self.assertRaises(RoutineControlAuthorizationError):
            self.service.members(user("GERENTE"), {"branch_id": "2"})

    def test_regional_scope_uses_assigned_pool(self):
        scope = self.service.resolve_scope(user("GERENTE_REGIONAL", assigned=(2, 1, 2)))
        self.assertEqual(scope.allowed_branch_ids, (1, 2))

    def test_regional_cannot_filter_outside_pool(self):
        with self.assertRaises(RoutineControlAuthorizationError):
            self.service.summary(user("GERENTE_REGIONAL", assigned=(1,)), {"branch_id": "2"})

    def test_global_catalog_has_all_operational_branches(self):
        result = self.service.catalogs(user("LECTOR_GLOBAL"))
        self.assertEqual([item["id"] for item in result["branches"]], [1, 2])

    def test_unauthorized_role_is_forbidden(self):
        with self.assertRaises(RoutineControlAuthorizationError):
            self.service.catalogs(user("USUARIO"))

    def test_summary_counts_incident_and_classified(self):
        result = self.service.summary(user("ADMIN"), {})
        self.assertEqual(result["total_members"], 3)
        self.assertEqual(result["classified_members"], 2)
        self.assertEqual(result["status_counts"]["INCIDENT"], 1)
        self.assertEqual(result["assignment_type_counts"]["SIN_EVIDENCIA"], 1)

    def test_region_filter_resolves_to_region_branches(self):
        self.service.summary(user("ADMIN"), {"region_key": "SUR"})
        self.assertEqual(self.repository.last_branch_ids, (2,))

    def test_crossed_branch_and_region_is_invalid(self):
        with self.assertRaises(RoutineControlValidationError):
            self.service.summary(user("ADMIN"), {"region_key": "SUR", "branch_id": "1"})

    def test_invalid_dates_are_rejected(self):
        with self.assertRaises(RoutineControlValidationError):
            self.service.summary(user("ADMIN"), {"sale_date_from": "2026-08-01", "sale_date_to": "2026-07-01"})

    def test_page_size_above_max_is_rejected(self):
        with self.assertRaises(RoutineControlValidationError):
            self.service.members(user("ADMIN"), {"page_size": "101"})

    def test_sort_allowlist_is_enforced(self):
        with self.assertRaises(RoutineControlValidationError):
            self.service.members(user("ADMIN"), {"sort": "source_metadata"})

    def test_search_and_counts_are_exposed_in_member_dto(self):
        result = self.service.members(user("ADMIN"), {"search": "Socio", "page": "1", "page_size": "25"})
        self.assertEqual(self.repository.last_filters["search"], "Socio")
        self.assertEqual(result["items"][0]["active_evidence_count"], 2)
        self.assertEqual(result["items"][0]["active_incident_count"], 1)
        self.assertNotIn("source_metadata", result["items"][0])


if __name__ == "__main__":
    unittest.main()
