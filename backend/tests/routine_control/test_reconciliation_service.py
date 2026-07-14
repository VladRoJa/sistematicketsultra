from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app import create_app
from app.extensions import db
from app.models.routine_control import (
    RoutineAssignmentEvidenceORM,
    RoutineControlDecisionORM,
    RoutineControlIncidentORM,
    RoutineControlMemberEvidenceORM,
    RoutineControlMemberORM,
)
from app.models.user_model import UserORM
from app.routine_control.domain.commands import ReconcileRoutineMemberCommand
from app.routine_control.domain.exceptions import (
    RoutineControlReconciliationNotFound,
    RoutineControlReconciliationValidationError,
)
from app.routine_control.repositories.reconciliation_repository import (
    RoutineControlReconciliationRepository,
    build_reconciliation_advisory_lock_key,
)
from app.routine_control.services.reconciliation_service import (
    reconcile_routine_member,
)


class RoutineControlReconciliationPostgresTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_app()
        cls.app_context = cls.app.app_context()
        cls.app_context.push()
        if db.engine.dialect.name != "postgresql":
            raise RuntimeError(
                "Estas pruebas requieren PostgreSQL real; SQLite no está permitido."
            )

    @classmethod
    def tearDownClass(cls) -> None:
        db.session.remove()
        cls.app_context.pop()

    def setUp(self) -> None:
        key = uuid4().hex
        self.source_system = f"TEST_RECONCILIATION_{key}"
        self.provider_key = f"TEST_RECONCILIATION_{key}"
        self.now = datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)
        self.member = RoutineControlMemberORM(
            source_system=self.source_system,
            source_record_id="record-1",
            source_identity_key="identity-1",
            external_member_id="member-1",
            external_sale_id=None,
            sucursal_id=None,
            source_branch_name=None,
            member_name="Member One",
            email_original="member@example.com",
            email_normalized="member@example.com",
            sale_date=date(2026, 7, 14),
            cohort_month=date(2026, 7, 1),
            classification_status="CLASSIFIED",
            current_status="SIN_RUTINA",
            status_version=1,
            first_seen_at=self.now,
            last_seen_at=self.now,
            source_updated_at_utc=None,
            payload_hash="m" * 64,
            source_metadata=None,
        )
        db.session.add(self.member)
        db.session.commit()

    def tearDown(self) -> None:
        db.session.rollback()
        member_ids = select(RoutineControlMemberORM.id).where(
            RoutineControlMemberORM.source_system == self.source_system
        )
        evidence_ids = select(RoutineAssignmentEvidenceORM.id).where(
            RoutineAssignmentEvidenceORM.provider_key == self.provider_key
        )
        db.session.execute(
            delete(RoutineControlDecisionORM).where(
                RoutineControlDecisionORM.member_id.in_(member_ids)
            )
        )
        db.session.execute(
            delete(RoutineControlIncidentORM).where(
                RoutineControlIncidentORM.member_id.in_(member_ids)
            )
        )
        db.session.execute(
            delete(RoutineControlMemberEvidenceORM).where(
                (RoutineControlMemberEvidenceORM.member_id.in_(member_ids))
                | (RoutineControlMemberEvidenceORM.evidence_id.in_(evidence_ids))
            )
        )
        db.session.execute(
            delete(RoutineAssignmentEvidenceORM).where(
                RoutineAssignmentEvidenceORM.provider_key == self.provider_key
            )
        )
        db.session.execute(
            delete(RoutineControlMemberORM).where(
                RoutineControlMemberORM.source_system == self.source_system
            )
        )
        db.session.commit()

        self.assertEqual(
            db.session.execute(member_ids).scalars().all(),
            [],
        )
        self.assertEqual(
            db.session.execute(evidence_ids).scalars().all(),
            [],
        )
        db.session.remove()

    def _command(
        self,
        *,
        member_id: int | None = None,
        as_of_utc: datetime | None = None,
    ) -> ReconcileRoutineMemberCommand:
        return ReconcileRoutineMemberCommand(
            member_id=member_id or self.member.id,
            as_of_utc=as_of_utc or self.now,
        )

    def _evidence(
        self,
        activity_date: date,
        instructor: str,
        *,
        active_link: bool = True,
        valid: bool = True,
    ) -> RoutineAssignmentEvidenceORM:
        suffix = uuid4().hex
        evidence = RoutineAssignmentEvidenceORM(
            provider_key=self.provider_key,
            provider_member_id=f"provider-{suffix}",
            evidence_identity_key=f"evidence-{suffix}",
            external_member_id=None,
            external_routine_id=None,
            email_original=None,
            email_normalized=None,
            provider_center_key="center-1",
            provider_center_name="Center One",
            sucursal_id=None,
            routine_activity_date=activity_date,
            instructor_name=instructor,
            instructor_name_normalized=instructor.lower(),
            routine_count=1,
            weighing_count=0,
            first_observed_at=self.now,
            last_observed_at=self.now,
            first_provider_run_id=None,
            last_provider_run_id=None,
            payload_hash=suffix + suffix,
            source_metadata=None,
            is_valid=True,
        )
        db.session.add(evidence)
        db.session.flush()
        link = RoutineControlMemberEvidenceORM(
            member_id=self.member.id,
            evidence_id=evidence.id,
            match_method="EXTERNAL_ID",
            is_active=True,
            linked_at_utc=self.now,
        )
        db.session.add(link)
        db.session.flush()
        if not active_link:
            link.is_active = False
            link.unlinked_at_utc = self.now
            link.unlink_reason = "Inactive for reconciliation test"
        if not valid:
            user_id = db.session.execute(
                select(UserORM.id).order_by(UserORM.id).limit(1)
            ).scalar_one()
            evidence.is_valid = False
            evidence.invalidated_at_utc = self.now
            evidence.invalidated_by_user_id = user_id
            evidence.invalidation_reason = "Invalid for reconciliation test"
        db.session.commit()
        return evidence

    def _decision(self, **overrides) -> RoutineControlDecisionORM:
        values = {
            "member_id": self.member.id,
            "decision_type": "NO_DESEA_RUTINA",
            "is_active": True,
            "decided_at_utc": self.now - timedelta(days=1),
            "effective_from_utc": self.now - timedelta(days=1),
            "effective_to_utc": None,
            "revoked_at_utc": None,
            "decision_reason": "Test decision",
        }
        values.update(overrides)
        decision = RoutineControlDecisionORM(**values)
        db.session.add(decision)
        db.session.commit()
        return decision

    def _incident(self, **overrides) -> RoutineControlIncidentORM:
        values = {
            "member_id": self.member.id,
            "incident_type": "EMAIL_VACIO",
            "is_blocking": True,
            "is_active": True,
            "detected_at_utc": self.now,
            "resolved_at_utc": None,
        }
        values.update(overrides)
        incident = RoutineControlIncidentORM(**values)
        db.session.add(incident)
        db.session.commit()
        return incident

    def _refresh_member(self) -> RoutineControlMemberORM:
        db.session.expire_all()
        return db.session.get(RoutineControlMemberORM, self.member.id)

    def test_without_evidence_decision_or_incident_is_sin_rutina(self) -> None:
        result = reconcile_routine_member(self._command())

        self.assertFalse(result.changed)
        self.assertEqual(result.classification_status, "CLASSIFIED")
        self.assertEqual(result.current_status, "SIN_RUTINA")
        self.assertIsNone(result.first_routine_at)
        self.assertIsNone(result.latest_routine_at)
        self.assertIsNone(result.current_instructor_name)
        self.assertIsNone(result.routine_assignment_type)

    def test_assignment_type_uses_first_activity_date(self) -> None:
        cases = (
            (date(2026, 7, 13), "PREEXISTENTE"),
            (date(2026, 7, 14), "MISMO_DIA"),
            (date(2026, 7, 15), "POSTERIOR"),
        )
        for activity_date, expected in cases:
            with self.subTest(expected=expected):
                evidence = self._evidence(activity_date, expected)
                result = reconcile_routine_member(self._command())
                self.assertEqual(result.classification_status, "CLASSIFIED")
                self.assertEqual(result.current_status, "CON_RUTINA")
                self.assertEqual(result.routine_assignment_type, expected)
                db.session.execute(
                    delete(RoutineControlMemberEvidenceORM).where(
                        RoutineControlMemberEvidenceORM.evidence_id == evidence.id
                    )
                )
                db.session.delete(evidence)
                member = self._refresh_member()
                member.classification_status = "CLASSIFIED"
                member.current_status = "SIN_RUTINA"
                member.first_routine_at = None
                member.latest_routine_at = None
                member.current_instructor_name = None
                member.routine_assignment_type = None
                db.session.commit()

    def test_multiple_evidences_derive_first_latest_and_instructor(self) -> None:
        self._evidence(date(2026, 7, 16), "Latest Instructor")
        self._evidence(date(2026, 7, 12), "First Instructor")
        self._evidence(date(2026, 7, 15), "Middle Instructor")

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.first_routine_at, date(2026, 7, 12))
        self.assertEqual(result.latest_routine_at, date(2026, 7, 16))
        self.assertEqual(result.current_instructor_name, "Latest Instructor")
        self.assertEqual(result.routine_assignment_type, "PREEXISTENTE")

    def test_same_date_tie_uses_highest_evidence_id_as_latest(self) -> None:
        first = self._evidence(date(2026, 7, 14), "Lower Id")
        second = self._evidence(date(2026, 7, 14), "Higher Id")
        self.assertLess(first.id, second.id)

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.first_routine_at, date(2026, 7, 14))
        self.assertEqual(result.latest_routine_at, date(2026, 7, 14))
        self.assertEqual(result.current_instructor_name, "Higher Id")

    def test_invalid_evidence_does_not_participate(self) -> None:
        self._evidence(date(2026, 7, 14), "Invalid", valid=False)

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.current_status, "SIN_RUTINA")
        self.assertIsNone(result.first_routine_at)

    def test_inactive_association_does_not_participate(self) -> None:
        self._evidence(date(2026, 7, 14), "Inactive", active_link=False)

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.current_status, "SIN_RUTINA")
        self.assertIsNone(result.first_routine_at)

    def test_current_no_routine_decision_applies_without_evidence(self) -> None:
        self._decision()

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.classification_status, "CLASSIFIED")
        self.assertEqual(result.current_status, "NO_DESEA_RUTINA")

    def test_future_decision_does_not_participate(self) -> None:
        self._decision(effective_from_utc=self.now + timedelta(seconds=1))

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.current_status, "SIN_RUTINA")

    def test_expired_decision_does_not_participate(self) -> None:
        self._decision(effective_to_utc=self.now - timedelta(seconds=1))

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.current_status, "SIN_RUTINA")

    def test_inactive_or_revoked_decision_does_not_participate(self) -> None:
        for revoked_at in (None, self.now - timedelta(hours=1)):
            with self.subTest(revoked=revoked_at is not None):
                decision = self._decision(
                    is_active=False,
                    revoked_at_utc=revoked_at,
                )
                result = reconcile_routine_member(self._command())
                self.assertEqual(result.current_status, "SIN_RUTINA")
                db.session.delete(decision)
                db.session.commit()

    def test_evidence_has_priority_and_decision_is_not_modified(self) -> None:
        decision = self._decision()
        self._evidence(date(2026, 7, 14), "Evidence Wins")
        before = (
            decision.is_active,
            decision.revoked_at_utc,
            decision.effective_from_utc,
            decision.effective_to_utc,
        )

        result = reconcile_routine_member(self._command())

        db.session.refresh(decision)
        self.assertEqual(result.current_status, "CON_RUTINA")
        self.assertEqual(
            (
                decision.is_active,
                decision.revoked_at_utc,
                decision.effective_from_utc,
                decision.effective_to_utc,
            ),
            before,
        )

    def test_active_blocking_incident_has_top_priority(self) -> None:
        self._decision()
        self._evidence(date(2026, 7, 14), "Preserved")
        self._incident()

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.classification_status, "INCIDENT")
        self.assertIsNone(result.current_status)
        self.assertEqual(result.first_routine_at, date(2026, 7, 14))
        self.assertEqual(result.latest_routine_at, date(2026, 7, 14))
        self.assertEqual(result.current_instructor_name, "Preserved")
        self.assertEqual(result.routine_assignment_type, "MISMO_DIA")

    def test_nonblocking_incident_variants_do_not_block(self) -> None:
        cases = (
            {"is_active": False},
            {
                "is_active": False,
                "resolved_at_utc": self.now + timedelta(hours=1),
            },
            {"is_blocking": False},
        )
        for values in cases:
            with self.subTest(values=values):
                incident = self._incident(**values)
                result = reconcile_routine_member(self._command())
                self.assertEqual(result.classification_status, "CLASSIFIED")
                self.assertEqual(result.current_status, "SIN_RUTINA")
                db.session.delete(incident)
                db.session.commit()

    def test_invalidating_only_evidence_falls_back_to_decision(self) -> None:
        decision = self._decision()
        evidence = self._evidence(date(2026, 7, 14), "Initially Valid")
        reconcile_routine_member(self._command())
        user_id = db.session.execute(
            select(UserORM.id).order_by(UserORM.id).limit(1)
        ).scalar_one()
        evidence.is_valid = False
        evidence.invalidated_at_utc = self.now
        evidence.invalidated_by_user_id = user_id
        evidence.invalidation_reason = "Invalidated after first projection"
        db.session.commit()

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.current_status, "NO_DESEA_RUTINA")
        self.assertIsNone(result.first_routine_at)
        self.assertIsNone(result.latest_routine_at)
        self.assertIsNone(result.current_instructor_name)
        self.assertIsNone(result.routine_assignment_type)
        db.session.refresh(decision)
        self.assertTrue(decision.is_active)

    def test_invalidating_only_evidence_falls_back_to_sin_rutina(self) -> None:
        evidence = self._evidence(date(2026, 7, 15), "Initially Valid")
        reconcile_routine_member(self._command())
        user_id = db.session.execute(
            select(UserORM.id).order_by(UserORM.id).limit(1)
        ).scalar_one()
        evidence.is_valid = False
        evidence.invalidated_at_utc = self.now
        evidence.invalidated_by_user_id = user_id
        evidence.invalidation_reason = "Invalidated after first projection"
        db.session.commit()

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.current_status, "SIN_RUTINA")
        self.assertIsNone(result.first_routine_at)
        self.assertIsNone(result.latest_routine_at)
        self.assertIsNone(result.current_instructor_name)
        self.assertIsNone(result.routine_assignment_type)

    def test_deactivating_only_link_removes_evidence_from_projection(self) -> None:
        evidence = self._evidence(date(2026, 7, 15), "Initially Linked")
        reconcile_routine_member(self._command())
        link = db.session.execute(
            select(RoutineControlMemberEvidenceORM).where(
                RoutineControlMemberEvidenceORM.evidence_id == evidence.id
            )
        ).scalar_one()
        link.is_active = False
        link.unlinked_at_utc = self.now
        link.unlink_reason = "Unlinked after first projection"
        db.session.commit()

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.current_status, "SIN_RUTINA")
        self.assertIsNone(result.first_routine_at)
        self.assertIsNone(result.current_instructor_name)

    def test_identical_reexecution_does_not_change_version(self) -> None:
        self._evidence(date(2026, 7, 14), "Stable")
        first = reconcile_routine_member(self._command())
        second = reconcile_routine_member(self._command())

        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(second.status_version, first.status_version)

    def test_effective_change_increments_version_exactly_once(self) -> None:
        initial_version = self.member.status_version
        self._evidence(date(2026, 7, 15), "Changed")

        result = reconcile_routine_member(self._command())

        self.assertTrue(result.changed)
        self.assertEqual(result.status_version, initial_version + 1)

    def test_multiple_field_changes_increment_version_only_once(self) -> None:
        self.member.classification_status = "INCIDENT"
        self.member.current_status = None
        self.member.first_routine_at = date(2026, 7, 1)
        self.member.latest_routine_at = date(2026, 7, 2)
        self.member.current_instructor_name = "Old Instructor"
        self.member.routine_assignment_type = "PREEXISTENTE"
        db.session.commit()
        initial_version = self.member.status_version

        result = reconcile_routine_member(self._command())

        self.assertEqual(result.classification_status, "CLASSIFIED")
        self.assertEqual(result.current_status, "SIN_RUTINA")
        self.assertIsNone(result.first_routine_at)
        self.assertEqual(result.status_version, initial_version + 1)

    def test_missing_member_raises_not_found(self) -> None:
        with self.assertRaises(RoutineControlReconciliationNotFound):
            reconcile_routine_member(
                self._command(member_id=self.member.id + 10_000_000)
            )

    def test_validates_id_and_timezone_before_lock(self) -> None:
        repository = RoutineControlReconciliationRepository(db.session)
        commands = (
            replace(self._command(), member_id=0),
            replace(self._command(), member_id=-1),
            replace(self._command(), member_id=True),
            replace(self._command(), member_id="1"),
            replace(
                self._command(),
                as_of_utc=datetime(2026, 7, 14, 18, 0),
            ),
        )
        with patch.object(repository, "acquire_member_lock") as acquire:
            for command in commands:
                with self.subTest(command=command):
                    with self.assertRaises(
                        RoutineControlReconciliationValidationError
                    ):
                        reconcile_routine_member(command, repository=repository)
            acquire.assert_not_called()

    def test_as_of_is_normalized_to_utc(self) -> None:
        repository = RoutineControlReconciliationRepository(db.session)
        offset = timezone(timedelta(hours=-7))
        local_as_of = datetime(2026, 7, 14, 11, 0, tzinfo=offset)
        original = repository.has_current_no_routine_decision

        with patch.object(
            repository,
            "has_current_no_routine_decision",
            wraps=original,
        ) as current_decision:
            reconcile_routine_member(
                self._command(as_of_utc=local_as_of),
                repository=repository,
            )

        self.assertEqual(
            current_decision.call_args.kwargs["as_of_utc"],
            self.now,
        )

    def test_injected_repository_uses_exact_independent_session(self) -> None:
        class CloseTrackingSession(Session):
            close_called = False

            def close(self) -> None:
                self.close_called = True
                super().close()

        factory = sessionmaker(
            bind=db.engine,
            class_=CloseTrackingSession,
            expire_on_commit=False,
        )
        independent_session = factory()
        repository = RoutineControlReconciliationRepository(independent_session)
        try:
            with patch.object(db.session, "commit") as default_commit:
                result = reconcile_routine_member(
                    self._command(),
                    repository=repository,
                )
                default_commit.assert_not_called()
            self.assertEqual(result.member_id, self.member.id)
        finally:
            independent_session.rollback()
            independent_session.close()
        self.assertTrue(independent_session.close_called)

    def test_unexpected_error_rolls_back_and_session_is_reusable(self) -> None:
        repository = RoutineControlReconciliationRepository(db.session)
        original_rollback = db.session.rollback
        with patch.object(
            db.session,
            "rollback",
            wraps=original_rollback,
        ) as rollback, patch.object(
            repository,
            "find_active_valid_evidences",
            side_effect=RuntimeError("unexpected reconciliation failure"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "unexpected reconciliation failure",
            ):
                reconcile_routine_member(
                    self._command(),
                    repository=repository,
                )
            rollback.assert_called_once()

        result = reconcile_routine_member(
            self._command(),
            repository=repository,
        )
        self.assertEqual(result.member_id, self.member.id)

    def test_repository_never_commits_or_rolls_back(self) -> None:
        repository = RoutineControlReconciliationRepository(db.session)
        with patch.object(db.session, "commit") as commit, patch.object(
            db.session,
            "rollback",
        ) as rollback:
            repository.acquire_member_lock(member_id=self.member.id)
            self.assertIsNotNone(
                repository.find_member_for_update(member_id=self.member.id)
            )
            repository.find_active_valid_evidences(member_id=self.member.id)
            repository.has_active_blocking_incident(member_id=self.member.id)
            repository.has_current_no_routine_decision(
                member_id=self.member.id,
                as_of_utc=self.now,
            )
            commit.assert_not_called()
            rollback.assert_not_called()
        db.session.rollback()

    def test_advisory_lock_key_is_stable_signed_bigint(self) -> None:
        first = build_reconciliation_advisory_lock_key(member_id=self.member.id)
        second = build_reconciliation_advisory_lock_key(member_id=self.member.id)

        self.assertEqual(first, second)
        self.assertGreaterEqual(first, -(2**63))
        self.assertLessEqual(first, 2**63 - 1)


if __name__ == "__main__":
    unittest.main()
