from __future__ import annotations

import hashlib
import struct
from typing import Any

from sqlalchemy import select, text

from app.models.routine_control import RoutineControlMemberORM


def build_member_advisory_lock_key(
    *,
    source_system: str,
    source_record_id: str,
) -> int:
    source_system_bytes = source_system.encode("utf-8")
    source_record_id_bytes = source_record_id.encode("utf-8")
    identity_bytes = b"".join(
        (
            struct.pack(">I", len(source_system_bytes)),
            source_system_bytes,
            struct.pack(">I", len(source_record_id_bytes)),
            source_record_id_bytes,
        )
    )
    digest = hashlib.sha256(identity_bytes).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class RoutineControlMemberRepository:
    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    def acquire_primary_identity_lock(
        self,
        *,
        source_system: str,
        source_record_id: str,
    ) -> None:
        lock_key = build_member_advisory_lock_key(
            source_system=source_system,
            source_record_id=source_record_id,
        )
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def find_by_primary_identity(
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

    def find_by_secondary_identity(
        self,
        *,
        source_system: str,
        source_identity_key: str,
    ) -> RoutineControlMemberORM | None:
        statement = select(RoutineControlMemberORM).where(
            RoutineControlMemberORM.source_system == source_system,
            RoutineControlMemberORM.source_identity_key == source_identity_key,
        )
        return self._session.execute(statement).scalar_one_or_none()

    def add(self, member: RoutineControlMemberORM) -> None:
        self._session.add(member)
