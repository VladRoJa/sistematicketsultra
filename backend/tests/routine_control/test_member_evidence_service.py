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
    RoutineControlMemberEvidenceORM,
    RoutineControlMemberORM,
    RoutineControlPipelineRunORM,
    RoutineControlProviderRunORM,
)
from app.models.user_model import UserORM
from app.routine_control.domain.commands import (
    LinkRoutineMemberEvidenceCommand,
    UnlinkRoutineMemberEvidenceCommand,
)
from app.routine_control.domain.exceptions import (
    RoutineControlMemberEvidenceConflict,
    RoutineControlMemberEvidenceNotFound,
    RoutineControlMemberEvidenceValidationError,
)
from app.routine_control.repositories.member_evidence_repository import (
    RoutineControlMemberEvidenceRepository,
)
from app.routine_control.services.member_evidence_service import (
    link_routine_member_evidence,
    unlink_routine_member_evidence,
)


class RoutineControlMemberEvidencePostgresTestCase(unittest.TestCase):
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
        self.source_system = f"TEST_MEMBER_EVIDENCE_{test_key}"
        self.provider_key = f"TEST_MEMBER_EVIDENCE_{test_key}"
        self.pipeline_prefix = f"test-member-evidence-{test_key}"
        self.now = datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)
        self.member = self._new_member("member-1")
        self.evidence = self._new_evidence("evidence-1")
        db.session.add_all((self.member, self.evidence))
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
        pipeline_ids = db.session.execute(
            select(RoutineControlPipelineRunORM.id).where(
                RoutineControlPipelineRunORM.idempotency_key.like(
                    f"{self.pipeline_prefix}%"
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

        residual_links = db.session.execute(
            select(RoutineControlMemberEvidenceORM.id).where(
                (RoutineControlMemberEvidenceORM.member_id.in_(member_ids))
                | (RoutineControlMemberEvidenceORM.evidence_id.in_(evidence_ids))
            )
        ).scalars().all()
        residual_members = db.session.execute(member_ids).scalars().all()
        residual_evidences = db.session.execute(evidence_ids).scalars().all()
        residual_pipelines = db.session.execute(
            select(RoutineControlPipelineRunORM.id).where(
                RoutineControlPipelineRunORM.idempotency_key.like(
                    f"{self.pipeline_prefix}%"
                )
            )
        ).scalars().all()
        self.assertEqual(residual_links, [])
        self.assertEqual(residual_members, [])
        self.assertEqual(residual_evidences, [])
        self.assertEqual(residual_pipelines, [])
        db.session.remove()

    def _new_member(self, suffix: str) -> RoutineControlMemberORM:
        return RoutineControlMemberORM(
            source_system=self.source_system,
            source_record_id=f"record-{suffix}",
            source_identity_key=f"identity-{suffix}",
            external_member_id=f"external-{suffix}",
            external_sale_id=None,
            sucursal_id=None,
            source_branch_name=None,
            member_name=f"Member {suffix}",
            email_original=f"{suffix}@example.com",
            email_normalized=f"{suffix}@example.com",
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

    def _new_evidence(self, suffix: str) -> RoutineAssignmentEvidenceORM:
        return RoutineAssignmentEvidenceORM(
            provider_key=self.provider_key,
            provider_member_id=f"provider-{suffix}",
            evidence_identity_key=f"identity-{suffix}",
            external_member_id=f"external-{suffix}",
            external_routine_id=f"routine-{suffix}",
            email_original=f"{suffix}@example.com",
            email_normalized=f"{suffix}@example.com",
            provider_center_key="center-1",
            provider_center_name="Center One",
            sucursal_id=None,
            routine_activity_date=date(2026, 7, 14),
            instructor_name="Instructor One",
            instructor_name_normalized="instructor one",
            routine_count=1,
            weighing_count=0,
            first_observed_at=self.now,
            last_observed_at=self.now,
            first_provider_run_id=None,
            last_provider_run_id=None,
            payload_hash="e" * 64,
            source_metadata=None,
            is_valid=True,
        )

    def _link_command(
        self,
        *,
        member_id: int | None = None,
        evidence_id: int | None = None,
        match_method: str = "EXTERNAL_ID",
        provider_run_id: int | None = None,
        linked_at_utc: datetime | None = None,
    ) -> LinkRoutineMemberEvidenceCommand:
        return LinkRoutineMemberEvidenceCommand(
            member_id=member_id or self.member.id,
            evidence_id=evidence_id or self.evidence.id,
            match_method=match_method,
            provider_run_id=provider_run_id,
            linked_at_utc=linked_at_utc or self.now,
        )

    def _unlink_command(
        self,
        *,
        unlink_reason: str = "  Duplicado confirmado  ",
        provider_run_id: int | None = None,
        unlinked_at_utc: datetime | None = None,
    ) -> UnlinkRoutineMemberEvidenceCommand:
        return UnlinkRoutineMemberEvidenceCommand(
            member_id=self.member.id,
            evidence_id=self.evidence.id,
            unlink_reason=unlink_reason,
            provider_run_id=provider_run_id,
            unlinked_at_utc=unlinked_at_utc or self.now,
        )

    def _get_link(self, link_id: int) -> RoutineControlMemberEvidenceORM:
        link = db.session.get(RoutineControlMemberEvidenceORM, link_id)
        self.assertIsNotNone(link)
        return link

    def _provider_run(self) -> RoutineControlProviderRunORM:
        pipeline = RoutineControlPipelineRunORM(
            business_date=date(2026, 7, 14),
            date_from=date(2026, 7, 14),
            date_to=date(2026, 7, 14),
            generation_mode="MANUAL",
            status="PENDING",
            idempotency_key=f"{self.pipeline_prefix}-unlink",
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
        db.session.commit()
        return provider_run

    def test_creates_external_id_link(self) -> None:
        result = link_routine_member_evidence(self._link_command())

        link = self._get_link(result.link_id)
        self.assertTrue(result.created)
        self.assertTrue(result.changed)
        self.assertTrue(result.is_active)
        self.assertEqual(result.match_method, "EXTERNAL_ID")
        self.assertEqual(link.linked_at_utc, self.now)
        self.assertIsNone(link.unlinked_at_utc)
        self.assertIsNone(link.unlink_reason)

    def test_identical_link_is_idempotent_and_does_not_duplicate(self) -> None:
        first = link_routine_member_evidence(self._link_command())
        second = link_routine_member_evidence(
            replace(
                self._link_command(),
                linked_at_utc=self.now + timedelta(hours=1),
            )
        )

        link = self._get_link(first.link_id)
        count = db.session.execute(
            select(RoutineControlMemberEvidenceORM.id).where(
                RoutineControlMemberEvidenceORM.member_id == self.member.id,
                RoutineControlMemberEvidenceORM.evidence_id == self.evidence.id,
            )
        ).scalars().all()
        self.assertEqual(first.link_id, second.link_id)
        self.assertFalse(second.created)
        self.assertFalse(second.changed)
        self.assertEqual(link.linked_at_utc, self.now)
        self.assertEqual(len(count), 1)

    def test_email_link_upgrades_to_external_id_without_rewriting_audit(self) -> None:
        provider_run = self._provider_run()
        first = link_routine_member_evidence(
            self._link_command(
                match_method="EMAIL",
                provider_run_id=provider_run.id,
            )
        )
        result = link_routine_member_evidence(
            self._link_command(
                match_method="EXTERNAL_ID",
                linked_at_utc=self.now + timedelta(hours=1),
            )
        )

        link = self._get_link(first.link_id)
        self.assertFalse(result.created)
        self.assertTrue(result.changed)
        self.assertEqual(result.match_method, "EXTERNAL_ID")
        self.assertEqual(link.linked_at_utc, self.now)
        self.assertEqual(link.linked_by_provider_run_id, provider_run.id)

    def test_external_id_link_does_not_degrade_to_email(self) -> None:
        first = link_routine_member_evidence(self._link_command())
        result = link_routine_member_evidence(
            self._link_command(match_method="EMAIL")
        )

        link = self._get_link(first.link_id)
        self.assertFalse(result.created)
        self.assertFalse(result.changed)
        self.assertEqual(link.match_method, "EXTERNAL_ID")

    def test_database_enforces_unique_member_evidence_pair(self) -> None:
        created = link_routine_member_evidence(self._link_command())
        duplicate = RoutineControlMemberEvidenceORM(
            member_id=self.member.id,
            evidence_id=self.evidence.id,
            match_method="EMAIL",
            is_active=True,
            linked_at_utc=self.now,
        )
        db.session.add(duplicate)

        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()

        self.assertIsNotNone(self._get_link(created.link_id))

    def test_missing_member_raises_not_found(self) -> None:
        with self.assertRaises(RoutineControlMemberEvidenceNotFound):
            link_routine_member_evidence(
                self._link_command(member_id=self.member.id + 10_000_000)
            )

    def test_missing_evidence_raises_not_found(self) -> None:
        with self.assertRaises(RoutineControlMemberEvidenceNotFound):
            link_routine_member_evidence(
                self._link_command(evidence_id=self.evidence.id + 10_000_000)
            )

    def test_invalidated_evidence_rejects_new_link(self) -> None:
        invalidator_id = db.session.execute(
            select(UserORM.id).order_by(UserORM.id).limit(1)
        ).scalar_one_or_none()
        self.assertIsNotNone(
            invalidator_id,
            "La prueba requiere al menos un usuario válido para la FK de auditoría.",
        )
        self.evidence.is_valid = False
        self.evidence.invalidated_at_utc = self.now
        self.evidence.invalidated_by_user_id = invalidator_id
        self.evidence.invalidation_reason = "Invalidated for test"
        db.session.commit()

        with self.assertRaises(RoutineControlMemberEvidenceConflict):
            link_routine_member_evidence(self._link_command())

    def test_command_validation_happens_before_write(self) -> None:
        invalid_link_commands = (
            replace(self._link_command(), member_id=0),
            replace(self._link_command(), member_id=True),
            replace(self._link_command(), evidence_id=-1),
            replace(self._link_command(), match_method="NAME"),
            replace(
                self._link_command(),
                linked_at_utc=datetime(2026, 7, 14, 18, 0),
            ),
        )
        invalid_unlink_commands = (
            replace(self._unlink_command(), unlink_reason="   "),
            replace(
                self._unlink_command(),
                unlinked_at_utc=datetime(2026, 7, 14, 18, 0),
            ),
        )
        for command in invalid_link_commands:
            with self.subTest(command=command):
                with self.assertRaises(
                    RoutineControlMemberEvidenceValidationError
                ):
                    link_routine_member_evidence(command)
        for command in invalid_unlink_commands:
            with self.subTest(command=command):
                with self.assertRaises(
                    RoutineControlMemberEvidenceValidationError
                ):
                    unlink_routine_member_evidence(command)

        count = db.session.execute(
            select(RoutineControlMemberEvidenceORM.id).where(
                RoutineControlMemberEvidenceORM.member_id == self.member.id,
                RoutineControlMemberEvidenceORM.evidence_id == self.evidence.id,
            )
        ).scalars().all()
        self.assertEqual(count, [])

    def test_unlink_records_normalized_audit_fields(self) -> None:
        provider_run = self._provider_run()
        linked = link_routine_member_evidence(self._link_command())
        unlinked_at = self.now + timedelta(hours=2)

        result = unlink_routine_member_evidence(
            self._unlink_command(
                provider_run_id=provider_run.id,
                unlinked_at_utc=unlinked_at,
            )
        )

        link = self._get_link(linked.link_id)
        self.assertFalse(result.created)
        self.assertTrue(result.changed)
        self.assertFalse(result.is_active)
        self.assertFalse(link.is_active)
        self.assertEqual(link.unlinked_at_utc, unlinked_at)
        self.assertEqual(link.unlink_reason, "Duplicado confirmado")
        self.assertEqual(link.unlinked_by_provider_run_id, provider_run.id)

    def test_repeated_unlink_preserves_original_audit(self) -> None:
        provider_run = self._provider_run()
        linked = link_routine_member_evidence(self._link_command())
        first_at = self.now + timedelta(hours=1)
        unlink_routine_member_evidence(
            self._unlink_command(
                unlink_reason="First reason",
                provider_run_id=provider_run.id,
                unlinked_at_utc=first_at,
            )
        )

        result = unlink_routine_member_evidence(
            self._unlink_command(
                unlink_reason="Second reason",
                provider_run_id=None,
                unlinked_at_utc=first_at + timedelta(hours=1),
            )
        )

        link = self._get_link(linked.link_id)
        self.assertFalse(result.changed)
        self.assertEqual(link.unlinked_at_utc, first_at)
        self.assertEqual(link.unlink_reason, "First reason")
        self.assertEqual(link.unlinked_by_provider_run_id, provider_run.id)

    def test_inactive_link_cannot_be_reactivated(self) -> None:
        linked = link_routine_member_evidence(self._link_command())
        unlink_routine_member_evidence(self._unlink_command())

        with self.assertRaises(RoutineControlMemberEvidenceConflict):
            link_routine_member_evidence(self._link_command())

        link = self._get_link(linked.link_id)
        self.assertFalse(link.is_active)

    def test_integrity_error_recovers_compatible_active_link(self) -> None:
        linked = link_routine_member_evidence(self._link_command())
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
            result = link_routine_member_evidence(self._link_command())

        self.assertEqual(flush_calls, 2)
        self.assertEqual(result.link_id, linked.link_id)
        self.assertFalse(result.created)
        self.assertFalse(result.changed)

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
        repository = RoutineControlMemberEvidenceRepository(independent_session)
        result = None

        try:
            with patch.object(db.session, "commit") as default_commit:
                result = link_routine_member_evidence(
                    self._link_command(),
                    repository=repository,
                )
                default_commit.assert_not_called()

            independent_session.expire_all()
            link = independent_session.get(
                RoutineControlMemberEvidenceORM,
                result.link_id,
            )
            self.assertIsNotNone(link)
            self.assertEqual(link.member_id, self.member.id)
        finally:
            independent_session.rollback()
            if result is not None:
                independent_session.execute(
                    delete(RoutineControlMemberEvidenceORM).where(
                        RoutineControlMemberEvidenceORM.id == result.link_id
                    )
                )
                independent_session.commit()
            independent_session.close()

        self.assertTrue(independent_session.close_called)

    def test_unexpected_error_rolls_back_and_session_is_reusable(self) -> None:
        repository = RoutineControlMemberEvidenceRepository(db.session)
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
                link_routine_member_evidence(
                    self._link_command(),
                    repository=repository,
                )
            rollback.assert_called_once()

        result = link_routine_member_evidence(
            self._link_command(),
            repository=repository,
        )
        self.assertTrue(result.created)

    def test_repository_never_commits(self) -> None:
        repository = RoutineControlMemberEvidenceRepository(db.session)
        link = RoutineControlMemberEvidenceORM(
            member_id=self.member.id,
            evidence_id=self.evidence.id,
            match_method="EMAIL",
            is_active=True,
            linked_at_utc=self.now,
        )

        with patch.object(db.session, "commit") as commit:
            repository.acquire_pair_lock(
                member_id=self.member.id,
                evidence_id=self.evidence.id,
            )
            repository.find_member(self.member.id)
            repository.find_evidence(self.evidence.id)
            repository.find_by_pair(
                member_id=self.member.id,
                evidence_id=self.evidence.id,
            )
            repository.add(link)
            commit.assert_not_called()

        db.session.rollback()

    def test_unlink_missing_pair_raises_not_found(self) -> None:
        with self.assertRaises(RoutineControlMemberEvidenceNotFound):
            unlink_routine_member_evidence(self._unlink_command())


if __name__ == "__main__":
    unittest.main()
