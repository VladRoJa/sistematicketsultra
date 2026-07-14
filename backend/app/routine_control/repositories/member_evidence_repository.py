from __future__ import annotations

import hashlib
import struct
from typing import Any

from sqlalchemy import select, text

from app.models.routine_control import (
    RoutineAssignmentEvidenceORM,
    RoutineControlMemberEvidenceORM,
    RoutineControlMemberORM,
)


def build_member_evidence_advisory_lock_key(
    *,
    member_id: int,
    evidence_id: int,
) -> int:
    member_id_bytes = str(member_id).encode("ascii")
    evidence_id_bytes = str(evidence_id).encode("ascii")
    pair_bytes = b"".join(
        (
            struct.pack(">I", len(member_id_bytes)),
            member_id_bytes,
            struct.pack(">I", len(evidence_id_bytes)),
            evidence_id_bytes,
        )
    )
    digest = hashlib.sha256(pair_bytes).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class RoutineControlMemberEvidenceRepository:
    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    def acquire_pair_lock(self, *, member_id: int, evidence_id: int) -> None:
        lock_key = build_member_evidence_advisory_lock_key(
            member_id=member_id,
            evidence_id=evidence_id,
        )
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def find_member(self, member_id: int) -> RoutineControlMemberORM | None:
        return self._session.get(RoutineControlMemberORM, member_id)

    def find_evidence(
        self,
        evidence_id: int,
    ) -> RoutineAssignmentEvidenceORM | None:
        return self._session.get(RoutineAssignmentEvidenceORM, evidence_id)

    def find_by_pair(
        self,
        *,
        member_id: int,
        evidence_id: int,
    ) -> RoutineControlMemberEvidenceORM | None:
        statement = select(RoutineControlMemberEvidenceORM).where(
            RoutineControlMemberEvidenceORM.member_id == member_id,
            RoutineControlMemberEvidenceORM.evidence_id == evidence_id,
        )
        return self._session.execute(statement).scalar_one_or_none()

    def add(self, link: RoutineControlMemberEvidenceORM) -> None:
        self._session.add(link)
