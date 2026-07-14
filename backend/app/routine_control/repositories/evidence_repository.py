from __future__ import annotations

import hashlib
import struct
from typing import Any

from sqlalchemy import select, text

from app.models.routine_control import RoutineAssignmentEvidenceORM


def build_evidence_advisory_lock_key(
    *,
    provider_key: str,
    evidence_identity_key: str,
) -> int:
    provider_key_bytes = provider_key.encode("utf-8")
    evidence_identity_key_bytes = evidence_identity_key.encode("utf-8")
    identity_bytes = b"".join(
        (
            struct.pack(">I", len(provider_key_bytes)),
            provider_key_bytes,
            struct.pack(">I", len(evidence_identity_key_bytes)),
            evidence_identity_key_bytes,
        )
    )
    digest = hashlib.sha256(identity_bytes).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class RoutineAssignmentEvidenceRepository:
    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    def acquire_identity_lock(
        self,
        *,
        provider_key: str,
        evidence_identity_key: str,
    ) -> None:
        lock_key = build_evidence_advisory_lock_key(
            provider_key=provider_key,
            evidence_identity_key=evidence_identity_key,
        )
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def find_by_identity(
        self,
        *,
        provider_key: str,
        evidence_identity_key: str,
    ) -> RoutineAssignmentEvidenceORM | None:
        statement = select(RoutineAssignmentEvidenceORM).where(
            RoutineAssignmentEvidenceORM.provider_key == provider_key,
            RoutineAssignmentEvidenceORM.evidence_identity_key
            == evidence_identity_key,
        )
        return self._session.execute(statement).scalar_one_or_none()

    def add(self, evidence: RoutineAssignmentEvidenceORM) -> None:
        self._session.add(evidence)
