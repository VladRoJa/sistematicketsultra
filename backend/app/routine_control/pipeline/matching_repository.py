from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select

from app.models.routine_control import (
    RoutineAssignmentEvidenceORM,
    RoutineControlMemberEvidenceORM,
    RoutineControlMemberORM,
)


class RoutineControlMatchingRepository:
    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    def find_member_by_source_record(
        self,
        *,
        source_system: str,
        source_record_id: str,
    ) -> RoutineControlMemberORM | None:
        statement = select(RoutineControlMemberORM).where(
            RoutineControlMemberORM.source_system == source_system,
            RoutineControlMemberORM.source_record_id == source_record_id,
        )
        return self._session.execute(statement).scalar_one_or_none()

    def find_members_by_ids(
        self,
        member_ids: Iterable[int],
    ) -> list[RoutineControlMemberORM]:
        ids = sorted(set(member_ids))
        if not ids:
            return []
        statement = select(RoutineControlMemberORM).where(
            RoutineControlMemberORM.id.in_(ids)
        )
        return list(self._session.execute(statement).scalars().all())

    def find_members_by_external_id(
        self,
        external_member_id: str,
    ) -> list[RoutineControlMemberORM]:
        statement = (
            select(RoutineControlMemberORM)
            .where(
                RoutineControlMemberORM.external_member_id
                == external_member_id
            )
            .order_by(RoutineControlMemberORM.id.asc())
        )
        return list(self._session.execute(statement).scalars().all())

    def find_members_by_email(
        self,
        email_normalized: str,
    ) -> list[RoutineControlMemberORM]:
        statement = (
            select(RoutineControlMemberORM)
            .where(
                RoutineControlMemberORM.email_normalized
                == email_normalized
            )
            .order_by(RoutineControlMemberORM.id.asc())
        )
        return list(self._session.execute(statement).scalars().all())

    def find_gasca_members_by_emails(
        self,
        emails: Iterable[str],
    ) -> list[RoutineControlMemberORM]:
        normalized = sorted({email for email in emails if email})
        if not normalized:
            return []
        statement = (
            select(RoutineControlMemberORM)
            .where(
                RoutineControlMemberORM.source_system == "gasca",
                RoutineControlMemberORM.email_normalized.in_(normalized),
            )
            .order_by(RoutineControlMemberORM.id.asc())
        )
        return list(self._session.execute(statement).scalars().all())

    def find_evidence(
        self,
        evidence_id: int,
    ) -> RoutineAssignmentEvidenceORM | None:
        return self._session.get(RoutineAssignmentEvidenceORM, evidence_id)

    def find_evidences_by_identities(
        self,
        identities: Iterable[str],
    ) -> list[RoutineAssignmentEvidenceORM]:
        normalized = sorted(set(identities))
        if not normalized:
            return []
        statement = select(RoutineAssignmentEvidenceORM).where(
            RoutineAssignmentEvidenceORM.provider_key == "trainingym",
            RoutineAssignmentEvidenceORM.evidence_identity_key.in_(normalized),
        )
        return list(self._session.execute(statement).scalars().all())

    def find_active_links_by_evidence_ids(
        self,
        evidence_ids: Iterable[int],
    ) -> list[RoutineControlMemberEvidenceORM]:
        ids = sorted(set(evidence_ids))
        if not ids:
            return []
        statement = select(RoutineControlMemberEvidenceORM).where(
            RoutineControlMemberEvidenceORM.evidence_id.in_(ids),
            RoutineControlMemberEvidenceORM.is_active.is_(True),
        )
        return list(self._session.execute(statement).scalars().all())
