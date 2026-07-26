from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import delete, select

from app import create_app
from app.extensions import db
from app.models.routine_control import (
    RoutineControlDecisionORM,
    RoutineControlIncidentORM,
    RoutineControlMemberORM,
)
from app.models.user_model import UserORM
from app.routine_control.domain.commands import (
    CreateNoRoutineDecisionCommand,
    RevokeNoRoutineDecisionCommand,
)
from app.routine_control.domain.exceptions import (
    RoutineControlDecisionConflict,
    RoutineControlDecisionValidationError,
)
from app.routine_control.services.decision_service import (
    create_no_routine_decision,
    revoke_no_routine_decision,
)


class RoutineControlDecisionServicePostgresTestCase(
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
            f"TEST_DECISION_SERVICE_{token}"
        )
        self.now = datetime(
            2026,
            7,
            26,
            21,
            0,
            tzinfo=timezone.utc,
        )

        self.actor = db.session.execute(
            select(UserORM)
            .order_by(UserORM.id)
            .limit(1)
        ).scalar_one()

        self.member = RoutineControlMemberORM(
            source_system=self.source_system,
            source_record_id="record-1",
            source_identity_key="identity-1",
            external_member_id="member-1",
            external_sale_id="sale-1",
            sucursal_id=self.actor.sucursal_id,
            source_branch_name="Sucursal de prueba",
            member_name="Socio de prueba",
            email_original="member@example.com",
            email_normalized="member@example.com",
            sale_date=date(2026, 7, 26),
            cohort_month=date(2026, 7, 1),
            classification_status="CLASSIFIED",
            current_status="SIN_RUTINA",
            status_version=1,
            first_seen_at=self.now,
            last_seen_at=self.now,
            payload_hash="d" * 64,
            source_metadata=None,
        )
        db.session.add(self.member)
        db.session.commit()

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
            delete(RoutineControlIncidentORM).where(
                RoutineControlIncidentORM.member_id.in_(
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
        db.session.commit()
        db.session.remove()

    def _create_command(
        self,
        **overrides,
    ) -> CreateNoRoutineDecisionCommand:
        values = {
            "member_id": self.member.id,
            "reason_code": "RUTINA_PROPIA",
            "notes": "Socio con rutina propia.",
            "actor_user_id": self.actor.id,
            "confirmed": True,
            "decided_at_utc": self.now,
        }
        values.update(overrides)
        return CreateNoRoutineDecisionCommand(**values)

    def _create_decision(self):
        return create_no_routine_decision(
            self._create_command()
        )

    def test_create_updates_projection_and_audit(
        self,
    ) -> None:
        result = self._create_decision()

        decision = db.session.get(
            RoutineControlDecisionORM,
            result.decision_id,
        )
        member = db.session.get(
            RoutineControlMemberORM,
            self.member.id,
        )

        self.assertEqual(result.action, "CREATED")
        self.assertTrue(result.is_active)
        self.assertEqual(
            result.current_status,
            "NO_DESEA_RUTINA",
        )
        self.assertEqual(
            member.current_status,
            "NO_DESEA_RUTINA",
        )
        self.assertEqual(
            member.status_version,
            2,
        )
        self.assertEqual(
            decision.created_by_user_id,
            self.actor.id,
        )
        self.assertEqual(
            decision.created_from_sucursal_id,
            self.member.sucursal_id,
        )
        self.assertEqual(
            decision.reason_code,
            "RUTINA_PROPIA",
        )

    def test_normalizes_reason_and_notes(
        self,
    ) -> None:
        result = create_no_routine_decision(
            self._create_command(
                reason_code="  no_interesado ",
                notes="  Confirmado por el socio.  ",
            )
        )

        decision = db.session.get(
            RoutineControlDecisionORM,
            result.decision_id,
        )

        self.assertEqual(
            decision.reason_code,
            "NO_INTERESADO",
        )
        self.assertEqual(
            decision.notes,
            "Confirmado por el socio.",
        )

    def test_requires_explicit_confirmation(
        self,
    ) -> None:
        with self.assertRaises(
            RoutineControlDecisionValidationError
        ):
            create_no_routine_decision(
                self._create_command(
                    confirmed=False,
                )
            )

        self.assertEqual(
            RoutineControlDecisionORM.query.filter_by(
                member_id=self.member.id
            ).count(),
            0,
        )

    def test_other_requires_notes(self) -> None:
        with self.assertRaises(
            RoutineControlDecisionValidationError
        ):
            create_no_routine_decision(
                self._create_command(
                    reason_code="OTRO",
                    notes="   ",
                )
            )

    def test_rejects_duplicate_active_decision(
        self,
    ) -> None:
        self._create_decision()

        with self.assertRaises(
            RoutineControlDecisionConflict
        ):
            self._create_decision()

        count = (
            RoutineControlDecisionORM.query.filter_by(
                member_id=self.member.id,
                is_active=True,
            ).count()
        )
        self.assertEqual(count, 1)

    def test_rejects_blocking_incident(
        self,
    ) -> None:
        db.session.add(
            RoutineControlIncidentORM(
                member_id=self.member.id,
                incident_type="EMAIL_VACIO",
                is_blocking=True,
                is_active=True,
                detected_at_utc=self.now,
            )
        )
        db.session.commit()

        with self.assertRaises(
            RoutineControlDecisionConflict
        ):
            self._create_decision()

        self.assertEqual(
            RoutineControlDecisionORM.query.filter_by(
                member_id=self.member.id
            ).count(),
            0,
        )

    def test_revoke_returns_member_to_sin_rutina(
        self,
    ) -> None:
        created = self._create_decision()
        revoked_at = self.now + timedelta(minutes=1)

        result = revoke_no_routine_decision(
            RevokeNoRoutineDecisionCommand(
                member_id=self.member.id,
                decision_id=created.decision_id,
                actor_user_id=self.actor.id,
                revocation_reason=(
                    "El socio cambió de decisión."
                ),
                revoked_at_utc=revoked_at,
            )
        )

        decision = db.session.get(
            RoutineControlDecisionORM,
            created.decision_id,
        )
        member = db.session.get(
            RoutineControlMemberORM,
            self.member.id,
        )

        self.assertEqual(result.action, "REVOKED")
        self.assertFalse(result.is_active)
        self.assertEqual(
            result.current_status,
            "SIN_RUTINA",
        )
        self.assertEqual(
            member.current_status,
            "SIN_RUTINA",
        )
        self.assertEqual(
            member.status_version,
            3,
        )
        self.assertEqual(
            decision.revoked_by_user_id,
            self.actor.id,
        )
        self.assertEqual(
            decision.revocation_reason,
            "El socio cambió de decisión.",
        )
        self.assertEqual(
            decision.effective_to_utc,
            revoked_at,
        )

    def test_rejects_second_revocation(
        self,
    ) -> None:
        created = self._create_decision()

        command = RevokeNoRoutineDecisionCommand(
            member_id=self.member.id,
            decision_id=created.decision_id,
            actor_user_id=self.actor.id,
            revocation_reason="Primera reversión.",
            revoked_at_utc=(
                self.now + timedelta(minutes=1)
            ),
        )
        revoke_no_routine_decision(command)

        with self.assertRaises(
            RoutineControlDecisionConflict
        ):
            revoke_no_routine_decision(
                RevokeNoRoutineDecisionCommand(
                    member_id=self.member.id,
                    decision_id=created.decision_id,
                    actor_user_id=self.actor.id,
                    revocation_reason=(
                        "Segunda reversión."
                    ),
                    revoked_at_utc=(
                        self.now + timedelta(minutes=2)
                    ),
                )
            )

    def test_rolls_back_decision_when_reconciliation_fails(
        self,
    ) -> None:
        with patch(
            "app.routine_control.services."
            "decision_service.reconcile_routine_member",
            side_effect=RuntimeError(
                "fallo de reconciliación"
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "fallo de reconciliación",
            ):
                self._create_decision()

        db.session.expire_all()

        self.assertEqual(
            RoutineControlDecisionORM.query.filter_by(
                member_id=self.member.id
            ).count(),
            0,
        )

        member = db.session.get(
            RoutineControlMemberORM,
            self.member.id,
        )
        self.assertEqual(
            member.current_status,
            "SIN_RUTINA",
        )
        self.assertEqual(
            member.status_version,
            1,
        )


if __name__ == "__main__":
    unittest.main()
