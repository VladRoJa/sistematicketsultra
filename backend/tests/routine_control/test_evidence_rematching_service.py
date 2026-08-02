from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import delete, select

from app import create_app
from app.extensions import db
from app.models.routine_control import (
    RoutineAssignmentEvidenceORM,
    RoutineControlMemberEvidenceORM,
    RoutineControlMemberORM,
)
from app.routine_control.pipeline.matching_policy import (
    MATCHED,
    TEMPORALLY_INVALID,
    EvidenceMatchInput,
    MemberMatchCandidate,
    select_evidence_match,
)
from app.routine_control.repositories.member_evidence_repository import (
    RoutineControlMemberEvidenceRepository,
)
from app.routine_control.services.evidence_rematching_service import (
    REACTIVATION_REQUIRED,
    _proposed_actions,
    rematch_routine_evidences,
)


class RoutineEvidenceRematchingPostgresTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_app()
        cls.context = cls.app.app_context()
        cls.context.push()
        if db.engine.dialect.name != "postgresql":
            raise RuntimeError("Estas pruebas requieren PostgreSQL real.")

    @classmethod
    def tearDownClass(cls) -> None:
        db.session.remove()
        cls.context.pop()

    def setUp(self) -> None:
        key = uuid4().hex
        self.source_record_prefix = f"TEST_REMATCH_{key}"
        self.provider_key = f"TEST_REMATCH_{key}"
        self.now = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        db.session.rollback()
        member_ids = select(RoutineControlMemberORM.id).where(
            RoutineControlMemberORM.source_system == "gasca",
            RoutineControlMemberORM.source_record_id.like(
                f"{self.source_record_prefix}-%"
            ),
        )
        evidence_ids = select(RoutineAssignmentEvidenceORM.id).where(
            RoutineAssignmentEvidenceORM.provider_key == self.provider_key
        )
        db.session.execute(delete(RoutineControlMemberEvidenceORM).where(
            (RoutineControlMemberEvidenceORM.member_id.in_(member_ids))
            | (RoutineControlMemberEvidenceORM.evidence_id.in_(evidence_ids))
        ))
        db.session.execute(delete(RoutineAssignmentEvidenceORM).where(
            RoutineAssignmentEvidenceORM.provider_key == self.provider_key
        ))
        db.session.execute(delete(RoutineControlMemberORM).where(
            RoutineControlMemberORM.id.in_(member_ids)
        ))
        db.session.commit()
        db.session.remove()

    def _member(
        self,
        *,
        external_id: str = "244190",
        email: str | None = "jairomendozasanchez@gmail.com",
        name: str = "JAIRO MENDOZA SANCHEZ",
        sale_date: date = date(2026, 7, 17),
    ) -> RoutineControlMemberORM:
        suffix = uuid4().hex
        member = RoutineControlMemberORM(
            source_system="gasca",
            source_record_id=f"{self.source_record_prefix}-{suffix}",
            source_identity_key=f"identity-{suffix}",
            external_member_id=external_id,
            external_sale_id=f"sale-{suffix}",
            sucursal_id=None,
            source_branch_name=None,
            member_name=name,
            email_original=email,
            email_normalized=email,
            sale_date=sale_date,
            cohort_month=sale_date.replace(day=1),
            classification_status="CLASSIFIED",
            current_status="SIN_RUTINA",
            status_version=1,
            first_seen_at=self.now,
            last_seen_at=self.now,
            source_updated_at_utc=None,
            payload_hash="m" * 64,
            source_metadata=None,
        )
        db.session.add(member)
        db.session.flush()
        return member

    def _evidence(
        self,
        *,
        external_id: str | None = "244190",
        email: str | None = "jairomendozasanchez@gmail.com",
        name: str | None = "JAIRO MENDOZA SANCHEZ",
        activity_date: date = date(2026, 1, 6),
    ) -> RoutineAssignmentEvidenceORM:
        suffix = uuid4().hex
        evidence = RoutineAssignmentEvidenceORM(
            provider_key=self.provider_key,
            provider_member_id=f"provider-{suffix}",
            evidence_identity_key=f"evidence-{suffix}",
            external_member_id=external_id,
            external_routine_id=None,
            member_name_original=name,
            member_name_normalized=(name.casefold() if name else None),
            email_original=email,
            email_normalized=email,
            provider_center_key="center",
            provider_center_name="Center",
            sucursal_id=None,
            routine_activity_date=activity_date,
            instructor_name="Instructor",
            instructor_name_normalized="instructor",
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
        db.session.add(evidence)
        db.session.flush()
        return evidence

    def _link(
        self,
        member: RoutineControlMemberORM,
        evidence: RoutineAssignmentEvidenceORM,
        *,
        active: bool = True,
    ) -> RoutineControlMemberEvidenceORM:
        link = RoutineControlMemberEvidenceORM(
            member_id=member.id,
            evidence_id=evidence.id,
            match_method="EXTERNAL_ID",
            is_active=active,
            linked_at_utc=self.now,
            unlinked_at_utc=None if active else self.now,
            unlink_reason=None if active else "Previous rematch",
        )
        db.session.add(link)
        db.session.commit()
        return link

    def _switch_fixture(self):
        previous = self._member(sale_date=date(2026, 7, 1))
        winner = self._member(sale_date=date(2026, 7, 14))
        evidence = self._evidence(activity_date=date(2026, 7, 15))
        previous_link = self._link(previous, evidence)
        previous.current_status = "CON_RUTINA"
        previous.first_routine_at = evidence.routine_activity_date
        previous.latest_routine_at = evidence.routine_activity_date
        previous.current_instructor_name = evidence.instructor_name
        previous.routine_assignment_type = "POSTERIOR"
        db.session.commit()
        return previous, winner, evidence, previous_link

    def test_dry_run_proposes_jairo_unlink_without_modifying_database(self) -> None:
        member = self._member()
        evidence = self._evidence()
        link = self._link(member, evidence)

        result = rematch_routine_evidences(
            [int(evidence.id)],
            None,
            self.now,
            dry_run=True,
        )

        item = result.items[0]
        self.assertEqual(item.selection.status, TEMPORALLY_INVALID)
        self.assertEqual(item.selection.temporal_delta_days, -192)
        self.assertTrue(any(
            action.action == "unlink" and action.link_id == link.id
            for action in item.actions
        ))
        db.session.refresh(link)
        self.assertTrue(link.is_active)
        self.assertEqual(result.members_reconciled, 0)

    def test_dry_run_does_not_commit(self) -> None:
        _previous, _winner, evidence, previous_link = self._switch_fixture()

        with patch.object(
            db.session,
            "commit",
            wraps=db.session.commit,
        ) as commit:
            result = rematch_routine_evidences(
                [int(evidence.id)],
                None,
                self.now,
                dry_run=True,
            )

        commit.assert_not_called()
        db.session.refresh(previous_link)
        self.assertTrue(previous_link.is_active)
        self.assertEqual(result.members_reconciled, 0)

    def test_link_failure_rolls_back_previous_unlink_and_member_states(self) -> None:
        previous, winner, evidence, previous_link = self._switch_fixture()

        with patch(
            "app.routine_control.services.evidence_rematching_service."
            "link_routine_member_evidence",
            side_effect=RuntimeError("simulated link failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated link failure"):
                rematch_routine_evidences(
                    [int(evidence.id)],
                    None,
                    self.now,
                    dry_run=False,
                )

        db.session.refresh(previous_link)
        db.session.refresh(previous)
        db.session.refresh(winner)
        self.assertTrue(previous_link.is_active)
        self.assertEqual(previous.current_status, "CON_RUTINA")
        self.assertEqual(winner.current_status, "SIN_RUTINA")
        winner_links = db.session.execute(select(
            RoutineControlMemberEvidenceORM
        ).where(
            RoutineControlMemberEvidenceORM.member_id == winner.id,
            RoutineControlMemberEvidenceORM.evidence_id == evidence.id,
        )).scalars().all()
        self.assertEqual(winner_links, [])

    def test_reconciliation_failure_rolls_back_unlink_and_link(self) -> None:
        previous, winner, evidence, previous_link = self._switch_fixture()

        with patch(
            "app.routine_control.services.evidence_rematching_service."
            "reconcile_routine_member",
            side_effect=RuntimeError("simulated reconciliation failure"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "simulated reconciliation failure",
            ):
                rematch_routine_evidences(
                    [int(evidence.id)],
                    None,
                    self.now,
                    dry_run=False,
                )

        db.session.refresh(previous_link)
        db.session.refresh(previous)
        db.session.refresh(winner)
        self.assertTrue(previous_link.is_active)
        self.assertEqual(previous.current_status, "CON_RUTINA")
        self.assertEqual(winner.current_status, "SIN_RUTINA")
        active_links = db.session.execute(select(
            RoutineControlMemberEvidenceORM
        ).where(
            RoutineControlMemberEvidenceORM.evidence_id == evidence.id,
            RoutineControlMemberEvidenceORM.is_active.is_(True),
        )).scalars().all()
        self.assertEqual([link.id for link in active_links], [previous_link.id])

    def test_success_commits_unlink_link_and_reconciliation_together(self) -> None:
        previous, winner, evidence, previous_link = self._switch_fixture()

        result = rematch_routine_evidences(
            [int(evidence.id)],
            None,
            self.now,
            dry_run=False,
        )

        db.session.refresh(previous_link)
        db.session.refresh(previous)
        db.session.refresh(winner)
        self.assertFalse(previous_link.is_active)
        self.assertEqual(previous.current_status, "SIN_RUTINA")
        self.assertEqual(winner.current_status, "CON_RUTINA")
        active_links = db.session.execute(select(
            RoutineControlMemberEvidenceORM
        ).where(
            RoutineControlMemberEvidenceORM.evidence_id == evidence.id,
            RoutineControlMemberEvidenceORM.is_active.is_(True),
        )).scalars().all()
        self.assertEqual(len(active_links), 1)
        self.assertEqual(active_links[0].member_id, winner.id)
        self.assertEqual(result.members_reconciled, 2)

    def test_applied_rematch_unlinks_and_reconciles_member(self) -> None:
        member = self._member()
        evidence = self._evidence()
        link = self._link(member, evidence)
        member.current_status = "CON_RUTINA"
        member.first_routine_at = evidence.routine_activity_date
        member.latest_routine_at = evidence.routine_activity_date
        member.current_instructor_name = evidence.instructor_name
        member.routine_assignment_type = "PREEXISTENTE"
        db.session.commit()

        result = rematch_routine_evidences(
            [int(evidence.id)],
            None,
            self.now,
            dry_run=False,
        )

        db.session.refresh(link)
        db.session.refresh(member)
        self.assertFalse(link.is_active)
        self.assertEqual(link.unlink_reason, "IDENTITY_TEMPORAL_V2_REMATCH")
        self.assertEqual(member.current_status, "SIN_RUTINA")
        self.assertIsNone(member.first_routine_at)
        self.assertEqual(result.members_reconciled, 1)

    def test_insufficient_historical_identity_preserves_active_link(self) -> None:
        member = self._member(email=None)
        evidence = self._evidence(email=None, name=None)
        link = self._link(member, evidence)

        result = rematch_routine_evidences(
            [int(evidence.id)],
            None,
            self.now,
            dry_run=False,
        )

        self.assertEqual(result.items[0].actions[0].action, "insufficient identity")
        db.session.refresh(link)
        self.assertTrue(link.is_active)

    def test_new_match_persists_v2_audit_and_single_active_link(self) -> None:
        member = self._member(sale_date=date(2026, 7, 17))
        evidence = self._evidence(activity_date=date(2026, 7, 10))
        db.session.commit()

        result = rematch_routine_evidences(
            [int(evidence.id)],
            None,
            self.now,
            dry_run=False,
        )

        self.assertEqual(result.items[0].selection.status, MATCHED)
        links = db.session.execute(select(RoutineControlMemberEvidenceORM).where(
            RoutineControlMemberEvidenceORM.evidence_id == evidence.id,
            RoutineControlMemberEvidenceORM.is_active.is_(True),
        )).scalars().all()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].member_id, member.id)
        self.assertEqual(links[0].identity_corroborator, "EMAIL_AND_NAME")
        self.assertEqual(links[0].temporal_delta_days, -7)
        self.assertEqual(
            links[0].matching_contract_version,
            "IDENTITY_TEMPORAL_V2",
        )

    def test_inactive_winner_requires_reactivation_without_duplicate(self) -> None:
        member = self._member()
        evidence = self._evidence(activity_date=date(2026, 7, 10))
        old_link = self._link(member, evidence, active=False)

        result = rematch_routine_evidences(
            [int(evidence.id)],
            None,
            self.now,
            dry_run=False,
        )

        action = result.items[0].actions[-1]
        self.assertEqual(action.action, "reactivation required")
        self.assertEqual(action.reason, REACTIVATION_REQUIRED)
        links = db.session.execute(select(RoutineControlMemberEvidenceORM).where(
            RoutineControlMemberEvidenceORM.evidence_id == evidence.id
        )).scalars().all()
        self.assertEqual([link.id for link in links], [old_link.id])
        self.assertFalse(links[0].is_active)


class JairoRematchProposalUnitTestCase(unittest.TestCase):
    def test_link_1601_is_proposed_for_unlink_with_delta_minus_192(self) -> None:
        evidence = EvidenceMatchInput(
            evidence_id=99,
            external_member_id="244190",
            email_normalized="jairomendozasanchez@gmail.com",
            member_name_normalized="jairo mendoza sanchez",
            routine_activity_date=date(2026, 1, 6),
        )
        candidate = MemberMatchCandidate(
            member_id=26,
            external_member_id="244190",
            email_normalized="jairomendozasanchez@gmail.com",
            member_name_normalized="jairo mendoza sanchez",
            sale_date=date(2026, 7, 17),
        )
        selection = select_evidence_match(
            evidence,
            external_id_candidates=(candidate,),
            email_candidates=(candidate,),
        )
        actions = _proposed_actions(
            evidence=SimpleNamespace(id=99),
            selection=selection,
            active_links=[SimpleNamespace(id=1601, member_id=26)],
            link_repository=SimpleNamespace(find_by_pair=lambda **_: None),
        )
        unlink = next(action for action in actions if action.action == "unlink")
        self.assertEqual(selection.temporal_delta_days, -192)
        self.assertEqual(unlink.link_id, 1601)


if __name__ == "__main__":
    unittest.main()
