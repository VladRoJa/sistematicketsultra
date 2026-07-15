from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import select, text

from app.models.routine_control import RoutineControlIncidentORM


class RoutineControlIncidentRepository:
    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    def acquire_member_type_lock(
        self,
        *,
        member_id: int,
        incident_type: str,
    ) -> None:
        payload = f"{member_id}\x00{incident_type}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def find_active(
        self,
        *,
        member_id: int,
        incident_type: str,
    ) -> RoutineControlIncidentORM | None:
        statement = select(RoutineControlIncidentORM).where(
            RoutineControlIncidentORM.member_id == member_id,
            RoutineControlIncidentORM.incident_type == incident_type,
            RoutineControlIncidentORM.is_active.is_(True),
        )
        return self._session.execute(statement).scalar_one_or_none()

    def synchronize(
        self,
        *,
        member_id: int,
        incident_type: str,
        should_be_active: bool,
        observed_at_utc: datetime,
    ) -> tuple[bool, bool]:
        self.acquire_member_type_lock(
            member_id=member_id,
            incident_type=incident_type,
        )
        incident = self.find_active(
            member_id=member_id,
            incident_type=incident_type,
        )
        if should_be_active:
            if incident is not None:
                return False, False
            self._session.add(
                RoutineControlIncidentORM(
                    member_id=member_id,
                    incident_type=incident_type,
                    is_blocking=True,
                    is_active=True,
                    detected_at_utc=observed_at_utc,
                    resolved_at_utc=None,
                    resolution_note=None,
                )
            )
            self._session.flush()
            return True, False

        if incident is None:
            return False, False
        incident.is_active = False
        incident.resolved_at_utc = observed_at_utc
        incident.resolution_note = "Condición ausente en corrida manual."
        self._session.flush()
        return False, True

