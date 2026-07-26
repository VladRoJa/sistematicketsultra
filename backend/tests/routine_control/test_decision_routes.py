from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from importlib.metadata import version
from uuid import uuid4

import werkzeug
from flask_jwt_extended import create_access_token
from sqlalchemy import delete, func, select

from app import create_app
from app.extensions import db
from app.models.routine_control import (
    RoutineControlDecisionORM,
    RoutineControlMemberORM,
)
from app.models.user_model import UserORM
from app.routine_control.queries.operational_repository import (
    RoutineControlOperationalRepository,
)


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = version("werkzeug")


class RoutineControlDecisionRoutesPostgresTestCase(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_app()
        cls.app_context = cls.app.app_context()
        cls.app_context.push()

        if db.engine.dialect.name != "postgresql":
            raise RuntimeError(
                "Estas pruebas requieren PostgreSQL real."
            )

    @classmethod
    def tearDownClass(cls) -> None:
        db.session.remove()
        cls.app_context.pop()

    def setUp(self) -> None:
        token = uuid4().hex
        self.source_system = (
            f"TEST_DECISION_ROUTES_{token}"
        )
        self.now = datetime(
            2026,
            7,
            26,
            22,
            0,
            tzinfo=timezone.utc,
        )

        branches = (
            RoutineControlOperationalRepository(
                db.session
            ).list_operational_branches()
        )

        if len(branches) < 2:
            raise RuntimeError(
                "Se requieren al menos dos sucursales "
                "operativas para estas pruebas."
            )

        self.branch_a_id = int(branches[0]["id"])
        self.branch_b_id = int(branches[1]["id"])

        max_user_id = db.session.execute(
            select(
                func.coalesce(
                    func.max(UserORM.id),
                    0,
                )
            )
        ).scalar_one()

        self.admin = UserORM(
            id=int(max_user_id) + 1,
            username=f"decision-admin-{token}",
            password="password-no-utilizado",
            rol="ADMINISTRADOR",
            sucursal_id=self.branch_a_id,
            department_id=1,
            email=f"admin-{token}@example.com",
        )
        self.reader = UserORM(
            id=int(max_user_id) + 2,
            username=f"decision-reader-{token}",
            password="password-no-utilizado",
            rol="LECTOR_GLOBAL",
            sucursal_id=self.branch_a_id,
            department_id=1,
            email=f"reader-{token}@example.com",
        )
        self.manager = UserORM(
            id=int(max_user_id) + 3,
            username=f"decision-manager-{token}",
            password="password-no-utilizado",
            rol="GERENTE",
            sucursal_id=self.branch_a_id,
            department_id=1,
            email=f"manager-{token}@example.com",
        )

        db.session.add_all(
            (
                self.admin,
                self.reader,
                self.manager,
            )
        )
        db.session.flush()

        self.member_a = self._member(
            branch_id=self.branch_a_id,
            suffix="a",
        )
        self.member_b = self._member(
            branch_id=self.branch_b_id,
            suffix="b",
        )

        db.session.add_all(
            (
                self.member_a,
                self.member_b,
            )
        )
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self) -> None:
        db.session.rollback()

        member_ids = select(
            RoutineControlMemberORM.id
        ).where(
            RoutineControlMemberORM.source_system
            == self.source_system
        )

        db.session.execute(
            delete(RoutineControlDecisionORM).where(
                RoutineControlDecisionORM.member_id.in_(
                    member_ids
                )
            )
        )
        db.session.execute(
            delete(RoutineControlMemberORM).where(
                RoutineControlMemberORM.source_system
                == self.source_system
            )
        )
        db.session.execute(
            delete(UserORM).where(
                UserORM.id.in_(
                    (
                        self.admin.id,
                        self.reader.id,
                        self.manager.id,
                    )
                )
            )
        )

        db.session.commit()
        db.session.remove()

    def _member(
        self,
        *,
        branch_id: int,
        suffix: str,
    ) -> RoutineControlMemberORM:
        return RoutineControlMemberORM(
            source_system=self.source_system,
            source_record_id=f"record-{suffix}",
            source_identity_key=f"identity-{suffix}",
            external_member_id=f"member-{suffix}",
            external_sale_id=f"sale-{suffix}",
            sucursal_id=branch_id,
            source_branch_name=f"Sucursal {suffix}",
            member_name=f"Socio {suffix}",
            email_original=f"{suffix}@example.com",
            email_normalized=f"{suffix}@example.com",
            sale_date=date(2026, 7, 26),
            cohort_month=date(2026, 7, 1),
            classification_status="CLASSIFIED",
            current_status="SIN_RUTINA",
            status_version=1,
            first_seen_at=self.now,
            last_seen_at=self.now,
            payload_hash=suffix * 64,
            source_metadata=None,
        )

    def _headers(self, user: UserORM) -> dict:
        token = create_access_token(
            identity=str(user.id)
        )
        return {
            "Authorization": f"Bearer {token}",
        }

    def _create_url(
        self,
        member_id: int,
    ) -> str:
        return (
            "/api/routine-control/members/"
            f"{member_id}/no-routine-decision"
        )

    def _create_payload(self) -> dict:
        return {
            "reason_code": "RUTINA_PROPIA",
            "notes": "Socio con rutina propia.",
            "confirmed": True,
        }

    def test_admin_can_create_decision(self) -> None:
        response = self.client.post(
            self._create_url(self.member_a.id),
            json=self._create_payload(),
            headers=self._headers(self.admin),
        )

        self.assertEqual(
            response.status_code,
            201,
            response.get_json(),
        )

        payload = response.get_json()

        self.assertEqual(
            payload["current_status"],
            "NO_DESEA_RUTINA",
        )
        self.assertEqual(
            payload["action"],
            "CREATED",
        )

        db.session.expire_all()
        member = db.session.get(
            RoutineControlMemberORM,
            self.member_a.id,
        )
        self.assertEqual(
            member.current_status,
            "NO_DESEA_RUTINA",
        )

    def test_requires_confirmation(self) -> None:
        payload = self._create_payload()
        payload["confirmed"] = False

        response = self.client.post(
            self._create_url(self.member_a.id),
            json=payload,
            headers=self._headers(self.admin),
        )

        self.assertEqual(
            response.status_code,
            400,
            response.get_json(),
        )

    def test_reader_cannot_create_decision(
        self,
    ) -> None:
        response = self.client.post(
            self._create_url(self.member_a.id),
            json=self._create_payload(),
            headers=self._headers(self.reader),
        )

        self.assertEqual(
            response.status_code,
            403,
            response.get_json(),
        )

    def test_manager_cannot_modify_other_branch(
        self,
    ) -> None:
        response = self.client.post(
            self._create_url(self.member_b.id),
            json=self._create_payload(),
            headers=self._headers(self.manager),
        )

        self.assertEqual(
            response.status_code,
            403,
            response.get_json(),
        )

    def test_duplicate_decision_returns_conflict(
        self,
    ) -> None:
        first = self.client.post(
            self._create_url(self.member_a.id),
            json=self._create_payload(),
            headers=self._headers(self.admin),
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            self._create_url(self.member_a.id),
            json=self._create_payload(),
            headers=self._headers(self.admin),
        )

        self.assertEqual(
            second.status_code,
            409,
            second.get_json(),
        )

    def test_admin_can_revoke_decision(self) -> None:
        created = self.client.post(
            self._create_url(self.member_a.id),
            json=self._create_payload(),
            headers=self._headers(self.admin),
        )

        self.assertEqual(created.status_code, 201)
        decision_id = created.get_json()["decision_id"]

        response = self.client.post(
            (
                self._create_url(self.member_a.id)
                + f"/{decision_id}/revoke"
            ),
            json={
                "revocation_reason": (
                    "El socio ahora requiere apoyo."
                )
            },
            headers=self._headers(self.admin),
        )

        self.assertEqual(
            response.status_code,
            200,
            response.get_json(),
        )

        payload = response.get_json()

        self.assertEqual(payload["action"], "REVOKED")
        self.assertFalse(payload["is_active"])
        self.assertEqual(
            payload["current_status"],
            "SIN_RUTINA",
        )


if __name__ == "__main__":
    unittest.main()
