from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from app import create_app
from app.extensions import db
from app.routine_control.queries.operational_repository import (
    RoutineControlOperationalRepository,
)
from app.routine_control.queries.operational_service import (
    RoutineControlOperationalService,
)


class StubOperationalRepository:
    def __init__(self) -> None:
        self.instructor_calls: list[dict] = []

    def list_operational_branches(self) -> list[dict]:
        return [
            {
                "id": 10,
                "name": "VILLAS DEL REY",
                "region_key": "MEXICALI",
                "region_name": "Mexicali",
            },
            {
                "id": 20,
                "name": "VILLA VERDE",
                "region_key": "MEXICALI",
                "region_name": "Mexicali",
            },
            {
                "id": 30,
                "name": "MISIÓN ENSENADA",
                "region_key": "ENSENADA",
                "region_name": "Ensenada",
            },
        ]

    def list_instructor_catalog(
        self,
        branch_ids: tuple[int, ...],
        *,
        sale_date_from: date | None = None,
        sale_date_to: date | None = None,
    ) -> list[dict]:
        self.instructor_calls.append({
            "branch_ids": branch_ids,
            "sale_date_from": sale_date_from,
            "sale_date_to": sale_date_to,
        })

        all_items = [
            {
                "name": "Ana López",
                "branch_ids": [10],
            },
            {
                "name": "Carlos Ruiz",
                "branch_ids": [10, 20],
            },
            {
                "name": "María Soto",
                "branch_ids": [30],
            },
        ]

        allowed = set(branch_ids)

        return [
            {
                "name": item["name"],
                "branch_ids": [
                    branch_id
                    for branch_id in item["branch_ids"]
                    if branch_id in allowed
                ],
            }
            for item in all_items
            if allowed.intersection(item["branch_ids"])
        ]


class RoutineControlInstructorCatalogTestCase(
    unittest.TestCase
):
    def test_manager_catalog_only_requests_own_branch(
        self,
    ) -> None:
        repository = StubOperationalRepository()
        service = RoutineControlOperationalService(
            repository
        )

        user = SimpleNamespace(
            rol="GERENTE",
            sucursal_id=10,
            sucursales_ids=None,
        )

        result = service.catalogs(user)

        self.assertEqual(
            repository.instructor_calls,
            [{
                "branch_ids": (10,),
                "sale_date_from": None,
                "sale_date_to": None,
            }],
        )
        self.assertEqual(
            result["instructors"],
            [
                {
                    "name": "Ana López",
                    "branch_ids": [10],
                },
                {
                    "name": "Carlos Ruiz",
                    "branch_ids": [10],
                },
            ],
        )
        self.assertEqual(
            result["scope"]["fixed_branch_id"],
            10,
        )

    def test_global_catalog_requests_all_operational_branches(
        self,
    ) -> None:
        repository = StubOperationalRepository()
        service = RoutineControlOperationalService(
            repository
        )

        user = SimpleNamespace(
            rol="ADMINISTRADOR",
            sucursal_id=None,
            sucursales_ids=None,
        )

        result = service.catalogs(user)

        self.assertEqual(
            repository.instructor_calls,
            [{
                "branch_ids": (10, 20, 30),
                "sale_date_from": None,
                "sale_date_to": None,
            }],
        )
        self.assertEqual(
            len(result["instructors"]),
            3,
        )

    def test_catalog_applies_branch_and_date_filters(
        self,
    ) -> None:
        repository = StubOperationalRepository()
        service = RoutineControlOperationalService(
            repository
        )

        user = SimpleNamespace(
            rol="ADMINISTRADOR",
            sucursal_id=None,
            sucursales_ids=None,
        )

        result = service.catalogs(
            user,
            {
                "region_key": "MEXICALI",
                "branch_id": "20",
                "sale_date_from": "2026-08-01",
                "sale_date_to": "2026-08-02",
            },
        )

        self.assertEqual(
            repository.instructor_calls,
            [{
                "branch_ids": (20,),
                "sale_date_from": date(
                    2026,
                    8,
                    1,
                ),
                "sale_date_to": date(
                    2026,
                    8,
                    2,
                ),
            }],
        )
        self.assertEqual(
            result["instructors"],
            [{
                "name": "Carlos Ruiz",
                "branch_ids": [20],
            }],
        )

    def test_member_filters_do_not_reload_instructor_catalog(
        self,
    ) -> None:
        repository = StubOperationalRepository()
        service = RoutineControlOperationalService(
            repository
        )

        user = SimpleNamespace(
            rol="GERENTE",
            sucursal_id=10,
            sucursales_ids=None,
        )

        _, filters = service._filters(
            user,
            {},
            listing=False,
        )

        self.assertEqual(
            repository.instructor_calls,
            [],
        )
        self.assertEqual(
            filters["effective_branch_ids"],
            (10,),
        )


class RoutineControlInstructorCatalogPostgresTestCase(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_app()
        cls.app_context = cls.app.app_context()
        cls.app_context.push()

        if db.engine.dialect.name != "postgresql":
            raise RuntimeError(
                "Esta prueba requiere PostgreSQL real."
            )

    @classmethod
    def tearDownClass(cls) -> None:
        db.session.remove()
        cls.app_context.pop()

    def tearDown(self) -> None:
        db.session.rollback()
        db.session.remove()

    def test_repository_query_executes_on_postgresql(
        self,
    ) -> None:
        repository = RoutineControlOperationalRepository(
            db.session
        )

        branch_ids = tuple(
            int(branch["id"])
            for branch in repository
            .list_operational_branches()
        )

        result = repository.list_instructor_catalog(
            branch_ids
        )

        self.assertIsInstance(result, list)

        for instructor in result:
            self.assertIsInstance(
                instructor["name"],
                str,
            )
            self.assertTrue(
                instructor["name"].strip(),
            )
            self.assertIsInstance(
                instructor["branch_ids"],
                list,
            )
            self.assertTrue(
                all(
                    isinstance(branch_id, int)
                    for branch_id
                    in instructor["branch_ids"]
                )
            )


if __name__ == "__main__":
    unittest.main()
