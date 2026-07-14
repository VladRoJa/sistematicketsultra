from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app import create_app
from app.extensions import db
from app.models.routine_control import (
    RoutineAssignmentEvidenceORM,
    RoutineControlPipelineRunORM,
    RoutineControlProviderRunORM,
)
from app.models.user_model import UserORM
from app.routine_control.domain.commands import RegisterRoutineEvidenceCommand
from app.routine_control.domain.exceptions import (
    RoutineControlEvidenceIdentityConflict,
    RoutineControlEvidenceValidationError,
)
from app.routine_control.repositories.evidence_repository import (
    RoutineAssignmentEvidenceRepository,
)
from app.routine_control.services.evidence_ingestion_service import (
    register_routine_evidence,
)


class RoutineEvidenceIngestionPostgresTestCase(unittest.TestCase):
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
        test_key = uuid4().hex
        self.provider_key = f"TEST_EVIDENCE_{test_key}"
        self.pipeline_idempotency_prefix = f"test-evidence-{test_key}"
        self.observed_at = datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        db.session.rollback()
        db.session.execute(
            delete(RoutineAssignmentEvidenceORM).where(
                RoutineAssignmentEvidenceORM.provider_key == self.provider_key
            )
        )
        pipeline_ids = db.session.execute(
            select(RoutineControlPipelineRunORM.id).where(
                RoutineControlPipelineRunORM.idempotency_key.like(
                    f"{self.pipeline_idempotency_prefix}%"
                )
            )
        ).scalars().all()
        if pipeline_ids:
            db.session.execute(
                delete(RoutineControlProviderRunORM).where(
                    RoutineControlProviderRunORM.pipeline_run_id.in_(pipeline_ids)
                )
            )
            db.session.execute(
                delete(RoutineControlPipelineRunORM).where(
                    RoutineControlPipelineRunORM.id.in_(pipeline_ids)
                )
            )
        db.session.commit()

        evidence_count = db.session.execute(
            select(RoutineAssignmentEvidenceORM.id).where(
                RoutineAssignmentEvidenceORM.provider_key == self.provider_key
            )
        ).scalars().all()
        pipeline_count = db.session.execute(
            select(RoutineControlPipelineRunORM.id).where(
                RoutineControlPipelineRunORM.idempotency_key.like(
                    f"{self.pipeline_idempotency_prefix}%"
                )
            )
        ).scalars().all()
        self.assertEqual(evidence_count, [])
        self.assertEqual(pipeline_count, [])
        db.session.remove()

    def _command(
        self,
        *,
        provider_member_id: str = "provider-member-1",
        evidence_identity_key: str = "evidence-1",
        provider_run_id: int | None = None,
        payload_hash: str = "a" * 64,
        routine_count: int = 1,
        weighing_count: int = 0,
        observed_at_utc: datetime | None = None,
    ) -> RegisterRoutineEvidenceCommand:
        return RegisterRoutineEvidenceCommand(
            provider_key=self.provider_key,
            provider_member_id=provider_member_id,
            evidence_identity_key=evidence_identity_key,
            external_member_id="external-member-1",
            external_routine_id="external-routine-1",
            email_original="Member@Example.com",
            email_normalized="member@example.com",
            provider_center_key="center-1",
            provider_center_name="Centro Uno",
            sucursal_id=None,
            routine_activity_date=date(2026, 7, 14),
            instructor_name="Instructor Uno",
            instructor_name_normalized="instructor uno",
            routine_count=routine_count,
            weighing_count=weighing_count,
            provider_run_id=provider_run_id,
            payload_hash=payload_hash,
            source_metadata={"provider": "postgres-test"},
            observed_at_utc=observed_at_utc or self.observed_at,
        )

    def _get_evidence(self, evidence_id: int) -> RoutineAssignmentEvidenceORM:
        evidence = db.session.get(RoutineAssignmentEvidenceORM, evidence_id)
        self.assertIsNotNone(evidence)
        return evidence

    def _provider_run(self, suffix: str) -> RoutineControlProviderRunORM:
        pipeline = RoutineControlPipelineRunORM(
            business_date=date(2026, 7, 14),
            date_from=date(2026, 7, 14),
            date_to=date(2026, 7, 14),
            generation_mode="MANUAL",
            status="PENDING",
            idempotency_key=f"{self.pipeline_idempotency_prefix}-{suffix}",
            requested_by_user_id=None,
            trigger_source="UNIT_TEST",
        )
        provider_run = RoutineControlProviderRunORM(
            pipeline_run=pipeline,
            provider_key=self.provider_key,
            dataset_key="routine_assignments",
            status="PENDING",
            date_from=date(2026, 7, 14),
            date_to=date(2026, 7, 14),
        )
        db.session.add(provider_run)
        db.session.flush()
        return provider_run

    def test_creates_valid_evidence(self) -> None:
        result = register_routine_evidence(self._command())

        evidence = self._get_evidence(result.evidence_id)
        self.assertTrue(result.created)
        self.assertTrue(result.source_changed)
        self.assertIsNone(result.previous_payload_hash)
        self.assertEqual(result.current_payload_hash, "a" * 64)
        self.assertTrue(result.is_valid)
        self.assertEqual(evidence.first_observed_at, self.observed_at)
        self.assertEqual(evidence.last_observed_at, self.observed_at)
        self.assertIsNone(evidence.first_provider_run_id)
        self.assertIsNone(evidence.last_provider_run_id)
        self.assertIsNone(evidence.invalidated_at_utc)

    def test_identical_reexecution_is_idempotent(self) -> None:
        command = self._command()
        first = register_routine_evidence(command)
        second = register_routine_evidence(
            replace(
                command,
                observed_at_utc=self.observed_at + timedelta(hours=1),
            )
        )

        count = RoutineAssignmentEvidenceORM.query.filter_by(
            provider_key=self.provider_key
        ).count()
        self.assertEqual(second.evidence_id, first.evidence_id)
        self.assertFalse(second.created)
        self.assertFalse(second.source_changed)
        self.assertEqual(second.previous_payload_hash, "a" * 64)
        self.assertEqual(count, 1)

    def test_changed_payload_updates_only_content_fields(self) -> None:
        command = self._command()
        created = register_routine_evidence(command)
        evidence = self._get_evidence(created.evidence_id)
        original_created_at = evidence.created_at

        changed = replace(
            command,
            external_member_id="external-member-2",
            external_routine_id="external-routine-2",
            email_original="Updated@Example.com",
            email_normalized="updated@example.com",
            provider_center_key="center-2",
            provider_center_name="Centro Dos",
            routine_activity_date=date(2026, 7, 15),
            instructor_name="Instructor Dos",
            instructor_name_normalized="instructor dos",
            routine_count=2,
            weighing_count=1,
            payload_hash="b" * 64,
            source_metadata={"revision": 2},
            observed_at_utc=self.observed_at + timedelta(days=1),
        )
        result = register_routine_evidence(changed)

        evidence = self._get_evidence(created.evidence_id)
        self.assertTrue(result.source_changed)
        self.assertEqual(result.previous_payload_hash, "a" * 64)
        self.assertEqual(evidence.external_member_id, "external-member-2")
        self.assertEqual(evidence.routine_count, 2)
        self.assertEqual(evidence.weighing_count, 1)
        self.assertEqual(evidence.payload_hash, "b" * 64)
        self.assertEqual(evidence.source_metadata, {"revision": 2})
        self.assertEqual(evidence.created_at, original_created_at)

    def test_preserves_identity_and_first_observation_fields(self) -> None:
        first_run = self._provider_run("first")
        second_run = self._provider_run("second")
        command = self._command(provider_run_id=first_run.id)
        created = register_routine_evidence(command)

        register_routine_evidence(
            replace(
                command,
                provider_run_id=second_run.id,
                payload_hash="b" * 64,
                observed_at_utc=self.observed_at + timedelta(hours=1),
            )
        )

        evidence = self._get_evidence(created.evidence_id)
        self.assertEqual(evidence.provider_key, command.provider_key)
        self.assertEqual(evidence.provider_member_id, command.provider_member_id)
        self.assertEqual(
            evidence.evidence_identity_key,
            command.evidence_identity_key,
        )
        self.assertEqual(evidence.first_observed_at, self.observed_at)
        self.assertEqual(evidence.first_provider_run_id, first_run.id)
        self.assertEqual(evidence.last_provider_run_id, second_run.id)

    def test_invalidated_evidence_remains_invalidated_after_update(self) -> None:
        invalidator_id = db.session.execute(
            select(UserORM.id).order_by(UserORM.id).limit(1)
        ).scalar_one_or_none()
        self.assertIsNotNone(
            invalidator_id,
            "La prueba requiere al menos un usuario válido para la FK de auditoría.",
        )
        command = self._command()
        created = register_routine_evidence(command)
        evidence = self._get_evidence(created.evidence_id)
        invalidated_at = self.observed_at + timedelta(minutes=30)
        evidence.is_valid = False
        evidence.invalidated_at_utc = invalidated_at
        evidence.invalidated_by_user_id = invalidator_id
        evidence.invalidation_reason = "Invalidación de prueba"
        db.session.commit()

        result = register_routine_evidence(
            replace(command, payload_hash="b" * 64, routine_count=2)
        )

        evidence = self._get_evidence(created.evidence_id)
        self.assertFalse(result.is_valid)
        self.assertFalse(evidence.is_valid)
        self.assertEqual(evidence.invalidated_at_utc, invalidated_at)
        self.assertEqual(evidence.invalidated_by_user_id, invalidator_id)
        self.assertEqual(evidence.invalidation_reason, "Invalidación de prueba")
        self.assertEqual(evidence.routine_count, 2)

    def test_different_provider_member_id_raises_conflict(self) -> None:
        command = self._command()
        created = register_routine_evidence(command)

        with self.assertRaises(RoutineControlEvidenceIdentityConflict):
            register_routine_evidence(
                replace(command, provider_member_id="provider-member-2")
            )

        evidence = self._get_evidence(created.evidence_id)
        self.assertEqual(evidence.provider_member_id, "provider-member-1")

    def test_invalid_counts_raise_validation_before_write(self) -> None:
        invalid_commands = (
            replace(self._command(), routine_count=0),
            replace(self._command(), routine_count=-1),
            replace(self._command(), weighing_count=-1),
        )
        for command in invalid_commands:
            with self.subTest(command=command):
                with self.assertRaises(RoutineControlEvidenceValidationError):
                    register_routine_evidence(command)

        count = RoutineAssignmentEvidenceORM.query.filter_by(
            provider_key=self.provider_key
        ).count()
        self.assertEqual(count, 0)

    def test_naive_observed_at_raises_validation_before_write(self) -> None:
        command = replace(
            self._command(),
            observed_at_utc=datetime(2026, 7, 14, 18, 0),
        )

        with self.assertRaises(RoutineControlEvidenceValidationError):
            register_routine_evidence(command)

        count = RoutineAssignmentEvidenceORM.query.filter_by(
            provider_key=self.provider_key
        ).count()
        self.assertEqual(count, 0)

    def test_integrity_error_recovers_compatible_evidence(self) -> None:
        command = self._command()
        created = register_routine_evidence(command)
        changed = replace(command, payload_hash="b" * 64, routine_count=2)
        original_flush = db.session.flush
        flush_calls = 0

        def flaky_flush(*args, **kwargs):
            nonlocal flush_calls
            flush_calls += 1
            if flush_calls == 1:
                raise IntegrityError(
                    "forced concurrent collision",
                    {},
                    RuntimeError("simulated unique collision"),
                )
            return original_flush(*args, **kwargs)

        with patch.object(db.session, "flush", new=flaky_flush):
            result = register_routine_evidence(changed)

        evidence = self._get_evidence(created.evidence_id)
        self.assertEqual(flush_calls, 2)
        self.assertEqual(result.evidence_id, created.evidence_id)
        self.assertTrue(result.source_changed)
        self.assertEqual(evidence.routine_count, 2)
        self.assertEqual(evidence.payload_hash, "b" * 64)

    def test_injected_repository_uses_independent_session(self) -> None:
        class CloseTrackingSession(Session):
            close_called = False

            def close(self) -> None:
                self.close_called = True
                super().close()

        session_factory = sessionmaker(
            bind=db.engine,
            class_=CloseTrackingSession,
            expire_on_commit=False,
        )
        independent_session = session_factory()
        repository = RoutineAssignmentEvidenceRepository(independent_session)
        result = None

        try:
            with patch.object(db.session, "commit") as default_commit:
                result = register_routine_evidence(
                    self._command(evidence_identity_key="independent"),
                    repository=repository,
                )
                default_commit.assert_not_called()

            independent_session.expire_all()
            evidence = independent_session.get(
                RoutineAssignmentEvidenceORM,
                result.evidence_id,
            )
            self.assertIsNotNone(evidence)
            self.assertEqual(evidence.evidence_identity_key, "independent")
        finally:
            independent_session.rollback()
            if result is not None:
                independent_session.execute(
                    delete(RoutineAssignmentEvidenceORM).where(
                        RoutineAssignmentEvidenceORM.id == result.evidence_id
                    )
                )
                independent_session.commit()
            independent_session.close()

        self.assertTrue(independent_session.close_called)

    def test_unexpected_error_rolls_back_and_session_is_reusable(self) -> None:
        repository = RoutineAssignmentEvidenceRepository(db.session)
        command = self._command()
        original_rollback = db.session.rollback

        with patch.object(
            db.session,
            "rollback",
            wraps=original_rollback,
        ) as rollback, patch.object(
            db.session,
            "flush",
            side_effect=RuntimeError("unexpected flush failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpected flush failure"):
                register_routine_evidence(command, repository=repository)
            rollback.assert_called_once()

        result = register_routine_evidence(command, repository=repository)
        evidence = self._get_evidence(result.evidence_id)
        self.assertTrue(result.created)
        self.assertEqual(evidence.evidence_identity_key, "evidence-1")

    def test_earlier_backfill_preserves_last_observation_and_run(self) -> None:
        current_run = self._provider_run("current")
        older_run = self._provider_run("older")
        command = self._command(provider_run_id=current_run.id)
        created = register_routine_evidence(command)

        result = register_routine_evidence(
            replace(
                command,
                provider_run_id=older_run.id,
                observed_at_utc=self.observed_at - timedelta(days=30),
            )
        )

        evidence = self._get_evidence(created.evidence_id)
        self.assertFalse(result.source_changed)
        self.assertEqual(evidence.last_observed_at, self.observed_at)
        self.assertEqual(evidence.last_provider_run_id, current_run.id)

    def test_later_observation_updates_last_observation_and_run(self) -> None:
        first_run = self._provider_run("first")
        later_run = self._provider_run("later")
        command = self._command(provider_run_id=first_run.id)
        created = register_routine_evidence(command)
        later_observation = self.observed_at + timedelta(days=1)

        result = register_routine_evidence(
            replace(
                command,
                provider_run_id=later_run.id,
                observed_at_utc=later_observation,
            )
        )

        evidence = self._get_evidence(created.evidence_id)
        self.assertFalse(result.source_changed)
        self.assertEqual(evidence.last_observed_at, later_observation)
        self.assertEqual(evidence.last_provider_run_id, later_run.id)

    def test_repository_does_not_commit(self) -> None:
        repository = RoutineAssignmentEvidenceRepository(db.session)
        evidence = RoutineAssignmentEvidenceORM(
            provider_key=self.provider_key,
            provider_member_id="repository-member",
            evidence_identity_key="repository-evidence",
            external_member_id=None,
            external_routine_id=None,
            email_original=None,
            email_normalized=None,
            provider_center_key="repository-center",
            provider_center_name="Repository Center",
            sucursal_id=None,
            routine_activity_date=date(2026, 7, 14),
            instructor_name="Repository Instructor",
            instructor_name_normalized="repository instructor",
            routine_count=1,
            weighing_count=0,
            first_observed_at=self.observed_at,
            last_observed_at=self.observed_at,
            first_provider_run_id=None,
            last_provider_run_id=None,
            payload_hash="r" * 64,
            source_metadata=None,
            is_valid=True,
        )

        with patch.object(db.session, "commit") as commit:
            repository.acquire_identity_lock(
                provider_key=self.provider_key,
                evidence_identity_key="repository-evidence",
            )
            repository.add(evidence)
            repository.find_by_identity(
                provider_key=self.provider_key,
                evidence_identity_key="repository-evidence",
            )
            commit.assert_not_called()

        db.session.rollback()


if __name__ == "__main__":
    unittest.main()
