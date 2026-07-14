from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models.routine_control import (
    RoutineControlDecisionORM,
    RoutineControlIncidentORM,
    RoutineControlMemberORM,
)


class RoutineControlIncidentDecisionModelsPostgresTestCase(unittest.TestCase):
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
        self.now = datetime(2026, 7, 14, 19, 0, tzinfo=timezone.utc)
        self.member = RoutineControlMemberORM(
            source_system=self.source_system,
            source_record_id="record-1",
            source_identity_key="identity-1",
            external_member_id="member-1",
            external_sale_id="sale-1",
            sucursal_id=None,
            source_branch_name="Sucursal Fuente",
            member_name="Miembro de prueba",
            email_original="member@example.com",
            email_normalized="member@example.com",
            sale_date=date(2026, 7, 14),
            cohort_month=date(2026, 7, 1),
            classification_status="CLASSIFIED",
            current_status="SIN_RUTINA",
            status_version=1,
            first_seen_at=self.now,
            last_seen_at=self.now,
            payload_hash="a" * 64,
            source_metadata=None,
        )
        db.session.add(self.member)
        db.session.commit()

    def tearDown(self) -> None:
        db.session.rollback()
        member_ids = select(RoutineControlMemberORM.id).where(
            RoutineControlMemberORM.source_system == self.source_system
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
            delete(RoutineControlMemberORM).where(
                RoutineControlMemberORM.source_system == self.source_system
            )
        )
        db.session.commit()
        db.session.remove()

    def _incident(self, **overrides) -> RoutineControlIncidentORM:
        values = {
            "member_id": self.member.id,
            "incident_type": "EMAIL_VACIO",
            "detected_at_utc": self.now,
        }
        values.update(overrides)
        return RoutineControlIncidentORM(**values)

    def _decision(self, **overrides) -> RoutineControlDecisionORM:
        values = {
            "member_id": self.member.id,
            "decision_type": "NO_DESEA_RUTINA",
            "decided_at_utc": self.now,
            "effective_from_utc": self.now,
        }
        values.update(overrides)
        return RoutineControlDecisionORM(**values)

    def _assert_flush_rejected(self, entity) -> None:
        db.session.add(entity)
        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()
        self.assertIsNotNone(
            db.session.get(RoutineControlMemberORM, self.member.id)
        )

    def test_creates_incident_with_defaults(self) -> None:
        incident = self._incident()
        db.session.add(incident)
        db.session.commit()

        self.assertIsNotNone(incident.id)
        self.assertTrue(incident.is_blocking)
        self.assertTrue(incident.is_active)
        self.assertIsNone(incident.resolved_at_utc)
        self.assertIsNotNone(incident.created_at_utc)
        self.assertIsNotNone(incident.updated_at_utc)
        self.assertEqual(incident.member.id, self.member.id)
        self.assertIn(incident, self.member.incidents)

    def test_rejects_unknown_incident_type(self) -> None:
        self._assert_flush_rejected(
            self._incident(incident_type="TIPO_DESCONOCIDO")
        )

    def test_rejects_active_incident_with_resolved_at(self) -> None:
        self._assert_flush_rejected(
            self._incident(resolved_at_utc=self.now + timedelta(hours=1))
        )

    def test_allows_inactive_resolved_incident(self) -> None:
        incident = self._incident(
            is_active=False,
            resolved_at_utc=self.now + timedelta(hours=1),
            resolution_note="Resuelta durante la prueba.",
        )
        db.session.add(incident)
        db.session.commit()

        self.assertFalse(incident.is_active)
        self.assertEqual(incident.resolved_at_utc, self.now + timedelta(hours=1))

    def test_prevents_duplicate_active_incident_type_for_member(self) -> None:
        db.session.add(self._incident())
        db.session.commit()

        self._assert_flush_rejected(self._incident())

    def test_allows_repeated_inactive_incident_history(self) -> None:
        db.session.add_all(
            (
                self._incident(
                    is_active=False,
                    resolved_at_utc=self.now + timedelta(hours=1),
                ),
                self._incident(
                    is_active=False,
                    detected_at_utc=self.now + timedelta(days=1),
                    resolved_at_utc=self.now + timedelta(days=1, hours=1),
                ),
            )
        )
        db.session.commit()

        count = RoutineControlIncidentORM.query.filter_by(
            member_id=self.member.id,
            incident_type="EMAIL_VACIO",
            is_active=False,
        ).count()
        self.assertEqual(count, 2)

    def test_allows_different_active_incident_types(self) -> None:
        db.session.add_all(
            (
                self._incident(incident_type="EMAIL_VACIO"),
                self._incident(incident_type="COINCIDENCIA_AMBIGUA"),
            )
        )
        db.session.commit()

        count = RoutineControlIncidentORM.query.filter_by(
            member_id=self.member.id,
            is_active=True,
        ).count()
        self.assertEqual(count, 2)

    def test_creates_no_desea_rutina_decision(self) -> None:
        decision = self._decision(decision_reason="Decisión del socio.")
        db.session.add(decision)
        db.session.commit()

        self.assertIsNotNone(decision.id)
        self.assertTrue(decision.is_active)
        self.assertIsNone(decision.effective_to_utc)
        self.assertIsNone(decision.revoked_at_utc)
        self.assertEqual(decision.member.id, self.member.id)
        self.assertIn(decision, self.member.decisions)

    def test_rejects_unknown_decision_type(self) -> None:
        self._assert_flush_rejected(
            self._decision(decision_type="DECISION_DESCONOCIDA")
        )

    def test_rejects_invalid_decision_effective_range(self) -> None:
        for effective_to in (self.now, self.now - timedelta(seconds=1)):
            with self.subTest(effective_to=effective_to):
                self._assert_flush_rejected(
                    self._decision(effective_to_utc=effective_to)
                )

    def test_rejects_active_decision_with_revoked_at(self) -> None:
        self._assert_flush_rejected(
            self._decision(revoked_at_utc=self.now + timedelta(hours=1))
        )

    def test_allows_inactive_revoked_decision(self) -> None:
        decision = self._decision(
            is_active=False,
            revoked_at_utc=self.now + timedelta(hours=1),
        )
        db.session.add(decision)
        db.session.commit()

        self.assertFalse(decision.is_active)
        self.assertEqual(decision.revoked_at_utc, self.now + timedelta(hours=1))

    def test_prevents_duplicate_active_decision_type_for_member(self) -> None:
        db.session.add(self._decision())
        db.session.commit()

        self._assert_flush_rejected(self._decision())

    def test_allows_repeated_inactive_decision_history(self) -> None:
        db.session.add_all(
            (
                self._decision(
                    is_active=False,
                    revoked_at_utc=self.now + timedelta(hours=1),
                ),
                self._decision(
                    is_active=False,
                    decided_at_utc=self.now + timedelta(days=1),
                    effective_from_utc=self.now + timedelta(days=1),
                    revoked_at_utc=self.now + timedelta(days=1, hours=1),
                ),
            )
        )
        db.session.commit()

        count = RoutineControlDecisionORM.query.filter_by(
            member_id=self.member.id,
            decision_type="NO_DESEA_RUTINA",
            is_active=False,
        ).count()
        self.assertEqual(count, 2)

    def test_persists_timezone_aware_datetimes(self) -> None:
        incident = self._incident(
            is_active=False,
            resolved_at_utc=self.now + timedelta(hours=1),
        )
        decision = self._decision(
            is_active=False,
            effective_to_utc=self.now + timedelta(hours=2),
            revoked_at_utc=self.now + timedelta(hours=1),
        )
        db.session.add_all((incident, decision))
        db.session.commit()

        values = (
            incident.detected_at_utc,
            incident.resolved_at_utc,
            incident.created_at_utc,
            incident.updated_at_utc,
            decision.decided_at_utc,
            decision.effective_from_utc,
            decision.effective_to_utc,
            decision.revoked_at_utc,
            decision.created_at_utc,
            decision.updated_at_utc,
        )
        self.assertTrue(all(value.utcoffset() is not None for value in values))

    def test_member_foreign_keys_are_restrictive(self) -> None:
        db.session.add_all((self._incident(), self._decision()))
        db.session.commit()

        with self.assertRaises(IntegrityError):
            db.session.execute(
                delete(RoutineControlMemberORM).where(
                    RoutineControlMemberORM.id == self.member.id
                )
            )
        db.session.rollback()
        self.assertIsNotNone(
            db.session.get(RoutineControlMemberORM, self.member.id)
        )

    def test_rejects_missing_member_foreign_key(self) -> None:
        self._assert_flush_rejected(
            self._incident(member_id=9_000_000_000_000_000_000)
        )

    def test_session_is_reusable_after_integrity_error(self) -> None:
        self._assert_flush_rejected(
            self._decision(decision_type="DECISION_DESCONOCIDA")
        )

        decision = self._decision()
        db.session.add(decision)
        db.session.commit()
        self.assertIsNotNone(decision.id)


if __name__ == "__main__":
    unittest.main()
