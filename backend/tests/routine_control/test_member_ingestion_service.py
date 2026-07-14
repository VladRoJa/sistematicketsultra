from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app import create_app
from app.extensions import db
from app.models.routine_control import RoutineControlMemberORM
from app.routine_control.domain.commands import UpsertRoutineMemberCommand
from app.routine_control.domain.exceptions import (
    RoutineControlMemberIdentityConflict,
)
from app.routine_control.repositories.member_repository import (
    RoutineControlMemberRepository,
)
from app.routine_control.services.member_ingestion_service import (
    upsert_routine_member,
)


class RoutineControlMemberIngestionPostgresTestCase(unittest.TestCase):
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
        self.source_system = f"TEST_ROUTINE_CONTROL_{uuid4().hex}"
        self.observed_at = datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        db.session.rollback()
        db.session.execute(
            delete(RoutineControlMemberORM).where(
                RoutineControlMemberORM.source_system == self.source_system
            )
        )
        db.session.commit()
        db.session.remove()

    def _command(
        self,
        *,
        source_record_id: str = "record-1",
        source_identity_key: str = "identity-1",
        payload_hash: str = "a" * 64,
        member_name: str = "Miembro Inicial",
        sale_date: date = date(2026, 7, 14),
        observed_at_utc: datetime | None = None,
    ) -> UpsertRoutineMemberCommand:
        return UpsertRoutineMemberCommand(
            source_system=self.source_system,
            source_record_id=source_record_id,
            source_identity_key=source_identity_key,
            external_member_id="member-1",
            external_sale_id="sale-1",
            sucursal_id=None,
            source_branch_name="Sucursal Fuente",
            member_name=member_name,
            email_original="Member@Example.com",
            email_normalized="member@example.com",
            sale_date=sale_date,
            source_updated_at_utc=datetime(
                2026,
                7,
                14,
                17,
                30,
                tzinfo=timezone.utc,
            ),
            payload_hash=payload_hash,
            source_metadata={"provider": "postgres-test"},
            observed_at_utc=observed_at_utc or self.observed_at,
        )

    def _get_member(self, member_id: int) -> RoutineControlMemberORM:
        member = db.session.get(RoutineControlMemberORM, member_id)
        self.assertIsNotNone(member)
        return member

    def test_creates_member_and_derives_cohort_month(self) -> None:
        result = upsert_routine_member(
            self._command(sale_date=date(2026, 7, 31))
        )

        member = self._get_member(result.member_id)
        self.assertTrue(result.created)
        self.assertTrue(result.source_changed)
        self.assertIsNone(result.previous_payload_hash)
        self.assertEqual(result.current_payload_hash, "a" * 64)
        self.assertEqual(member.cohort_month, date(2026, 7, 1))
        self.assertEqual(member.classification_status, "CLASSIFIED")
        self.assertEqual(member.current_status, "SIN_RUTINA")
        self.assertEqual(member.status_version, 1)
        self.assertEqual(member.first_seen_at, self.observed_at)
        self.assertEqual(member.last_seen_at, self.observed_at)

    def test_identical_reexecution_does_not_duplicate_or_mark_source_changed(self) -> None:
        command = self._command()
        first = upsert_routine_member(command)
        second_observation = self.observed_at + timedelta(hours=1)
        second = upsert_routine_member(
            replace(command, observed_at_utc=second_observation)
        )

        member_count = RoutineControlMemberORM.query.filter_by(
            source_system=self.source_system
        ).count()
        member = self._get_member(first.member_id)
        self.assertEqual(second.member_id, first.member_id)
        self.assertFalse(second.created)
        self.assertFalse(second.source_changed)
        self.assertEqual(second.previous_payload_hash, "a" * 64)
        self.assertEqual(member_count, 1)
        self.assertEqual(member.last_seen_at, second_observation)

    def test_earlier_backfill_does_not_reduce_last_seen_at(self) -> None:
        command = self._command()
        created = upsert_routine_member(command)

        result = upsert_routine_member(
            replace(
                command,
                observed_at_utc=self.observed_at - timedelta(days=30),
            )
        )

        member = self._get_member(created.member_id)
        self.assertFalse(result.created)
        self.assertFalse(result.source_changed)
        self.assertEqual(member.last_seen_at, self.observed_at)

    def test_later_observation_increases_last_seen_at(self) -> None:
        command = self._command()
        created = upsert_routine_member(command)
        later_observation = self.observed_at + timedelta(days=1)

        result = upsert_routine_member(
            replace(command, observed_at_utc=later_observation)
        )

        member = self._get_member(created.member_id)
        self.assertFalse(result.created)
        self.assertFalse(result.source_changed)
        self.assertEqual(member.last_seen_at, later_observation)

    def test_changed_payload_updates_only_allowed_source_fields(self) -> None:
        original_command = self._command()
        created = upsert_routine_member(original_command)
        member = self._get_member(created.member_id)
        original_first_seen_at = member.first_seen_at

        member.current_status = "NO_DESEA_RUTINA"
        member.status_version = 7
        member.first_routine_at = date(2026, 7, 15)
        member.latest_routine_at = date(2026, 7, 16)
        member.current_instructor_name = "Instructor Original"
        member.routine_assignment_type = "POSTERIOR"
        db.session.commit()

        changed_command = replace(
            original_command,
            external_member_id="member-updated",
            external_sale_id="sale-updated",
            source_branch_name="Sucursal Actualizada",
            member_name="Miembro Actualizado",
            email_original="Updated@Example.com",
            email_normalized="updated@example.com",
            sale_date=date(2026, 8, 2),
            source_updated_at_utc=datetime(
                2026,
                8,
                2,
                20,
                0,
                tzinfo=timezone.utc,
            ),
            payload_hash="b" * 64,
            source_metadata={"provider": "postgres-test", "revision": 2},
            observed_at_utc=self.observed_at + timedelta(days=20),
        )
        result = upsert_routine_member(changed_command)

        member = self._get_member(created.member_id)
        self.assertFalse(result.created)
        self.assertTrue(result.source_changed)
        self.assertEqual(result.previous_payload_hash, "a" * 64)
        self.assertEqual(member.external_member_id, "member-updated")
        self.assertEqual(member.cohort_month, date(2026, 8, 1))
        self.assertEqual(member.source_system, original_command.source_system)
        self.assertEqual(member.source_record_id, original_command.source_record_id)
        self.assertEqual(
            member.source_identity_key,
            original_command.source_identity_key,
        )
        self.assertEqual(member.classification_status, "CLASSIFIED")
        self.assertEqual(member.current_status, "NO_DESEA_RUTINA")
        self.assertEqual(member.status_version, 7)
        self.assertEqual(member.first_routine_at, date(2026, 7, 15))
        self.assertEqual(member.latest_routine_at, date(2026, 7, 16))
        self.assertEqual(member.current_instructor_name, "Instructor Original")
        self.assertEqual(member.routine_assignment_type, "POSTERIOR")
        self.assertEqual(member.first_seen_at, original_first_seen_at)

    def test_crossed_primary_and_secondary_identities_raise_conflict(self) -> None:
        first = upsert_routine_member(
            self._command(
                source_record_id="record-a",
                source_identity_key="identity-a",
            )
        )
        second = upsert_routine_member(
            self._command(
                source_record_id="record-b",
                source_identity_key="identity-b",
                payload_hash="b" * 64,
            )
        )

        with self.assertRaises(RoutineControlMemberIdentityConflict):
            upsert_routine_member(
                self._command(
                    source_record_id="record-a",
                    source_identity_key="identity-b",
                    payload_hash="c" * 64,
                )
            )

        first_member = self._get_member(first.member_id)
        second_member = self._get_member(second.member_id)
        self.assertEqual(first_member.source_identity_key, "identity-a")
        self.assertEqual(second_member.source_record_id, "record-b")

    def test_integrity_error_recovers_by_rereading_compatible_member(self) -> None:
        original_command = self._command()
        created = upsert_routine_member(original_command)
        changed_command = replace(
            original_command,
            member_name="Recovered Member",
            payload_hash="b" * 64,
            observed_at_utc=self.observed_at + timedelta(hours=2),
        )

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
            result = upsert_routine_member(changed_command)

        member = self._get_member(created.member_id)
        self.assertEqual(flush_calls, 2)
        self.assertEqual(result.member_id, created.member_id)
        self.assertFalse(result.created)
        self.assertTrue(result.source_changed)
        self.assertEqual(result.previous_payload_hash, "a" * 64)
        self.assertEqual(member.member_name, "Recovered Member")
        self.assertEqual(member.payload_hash, "b" * 64)

    def test_unexpected_runtime_error_rolls_back(self) -> None:
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
            with self.assertRaisesRegex(
                RuntimeError,
                "unexpected flush failure",
            ):
                upsert_routine_member(self._command())

            rollback.assert_called_once()

        member_count = RoutineControlMemberORM.query.filter_by(
            source_system=self.source_system
        ).count()
        self.assertEqual(member_count, 0)

    def test_session_is_reusable_after_unexpected_error_rollback(self) -> None:
        repository = RoutineControlMemberRepository(db.session)
        command = self._command()

        with patch.object(
            db.session,
            "flush",
            side_effect=RuntimeError("unexpected flush failure"),
        ):
            with self.assertRaises(RuntimeError):
                upsert_routine_member(command, repository=repository)

        result = upsert_routine_member(command, repository=repository)

        member = self._get_member(result.member_id)
        self.assertTrue(result.created)
        self.assertEqual(member.source_record_id, command.source_record_id)

    def test_repository_does_not_commit(self) -> None:
        repository = RoutineControlMemberRepository(db.session)
        member = RoutineControlMemberORM(
            source_system=self.source_system,
            source_record_id="repository-record",
            source_identity_key="repository-identity",
            external_member_id="repository-member",
            external_sale_id=None,
            sucursal_id=None,
            source_branch_name=None,
            member_name=None,
            email_original=None,
            email_normalized=None,
            sale_date=date(2026, 7, 14),
            cohort_month=date(2026, 7, 1),
            classification_status="CLASSIFIED",
            current_status="SIN_RUTINA",
            status_version=1,
            first_seen_at=self.observed_at,
            last_seen_at=self.observed_at,
            source_updated_at_utc=None,
            payload_hash="r" * 64,
            source_metadata=None,
        )

        with patch.object(db.session, "commit") as commit:
            repository.acquire_primary_identity_lock(
                source_system=self.source_system,
                source_record_id="repository-record",
            )
            repository.add(member)
            repository.find_by_primary_identity(
                source_system=self.source_system,
                source_record_id="repository-record",
            )
            commit.assert_not_called()

        db.session.rollback()

    def test_injected_repository_uses_and_closes_independent_session(self) -> None:
        class CloseTrackingSession(Session):
            close_called = False

            def close(self) -> None:
                self.close_called = True
                super().close()

        independent_session_factory = sessionmaker(
            bind=db.engine,
            class_=CloseTrackingSession,
            expire_on_commit=False,
        )
        independent_session = independent_session_factory()
        repository = RoutineControlMemberRepository(independent_session)
        result = None

        try:
            with patch.object(db.session, "commit") as default_session_commit:
                result = upsert_routine_member(
                    self._command(
                        source_record_id="independent-record",
                        source_identity_key="independent-identity",
                    ),
                    repository=repository,
                )
                default_session_commit.assert_not_called()

            independent_session.expire_all()
            persisted_member = independent_session.get(
                RoutineControlMemberORM,
                result.member_id,
            )
            self.assertIsNotNone(persisted_member)
            self.assertEqual(persisted_member.id, result.member_id)
            self.assertEqual(
                persisted_member.source_record_id,
                "independent-record",
            )

            independent_session.delete(persisted_member)
            independent_session.commit()
            self.assertIsNone(
                independent_session.get(
                    RoutineControlMemberORM,
                    result.member_id,
                )
            )
        finally:
            independent_session.rollback()
            if result is not None:
                independent_session.execute(
                    delete(RoutineControlMemberORM).where(
                        RoutineControlMemberORM.id == result.member_id
                    )
                )
                independent_session.commit()
            independent_session.close()

        self.assertTrue(independent_session.close_called)


if __name__ == "__main__":
    unittest.main()
