from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select, text

from app.models.routine_control import (
    RoutineAssignmentEvidenceORM,
    RoutineControlDecisionORM,
    RoutineControlIncidentORM,
    RoutineControlMemberEvidenceORM,
    RoutineControlMemberORM,
)


_ALLOWED_BLOCKING_INCIDENT_TYPES = frozenset(
    (
        "EMAIL_VACIO",
        "EMAIL_DUPLICADO_GASCA",
        "COINCIDENCIA_AMBIGUA",
        "SUCURSAL_NO_RESUELTA",
        "FECHA_VENTA_INVALIDA",
        "COHORTE_NO_DETERMINADA",
        "REGISTRO_ORIGEN_INVALIDO",
    )
)


def build_reconciliation_advisory_lock_key(*, member_id: int) -> int:
    digest = hashlib.sha256(str(member_id).encode("ascii")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class RoutineControlReconciliationRepository:
    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    def acquire_member_lock(self, *, member_id: int) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": build_reconciliation_advisory_lock_key(
                member_id=member_id
            )},
        )

    def find_member_for_update(
        self,
        *,
        member_id: int,
    ) -> RoutineControlMemberORM | None:
        statement = (
            select(RoutineControlMemberORM)
            .where(RoutineControlMemberORM.id == member_id)
            .with_for_update()
        )
        return self._session.execute(statement).scalar_one_or_none()

    def find_active_valid_evidences(
        self,
        *,
        member_id: int,
    ) -> list[RoutineAssignmentEvidenceORM]:
        statement = (
            select(RoutineAssignmentEvidenceORM)
            .join(
                RoutineControlMemberEvidenceORM,
                RoutineControlMemberEvidenceORM.evidence_id
                == RoutineAssignmentEvidenceORM.id,
            )
            .where(
                RoutineControlMemberEvidenceORM.member_id == member_id,
                RoutineControlMemberEvidenceORM.is_active.is_(True),
                RoutineAssignmentEvidenceORM.is_valid.is_(True),
            )
            .order_by(
                RoutineAssignmentEvidenceORM.routine_activity_date.asc(),
                RoutineAssignmentEvidenceORM.id.asc(),
            )
        )
        return list(self._session.execute(statement).scalars().all())

    def has_active_blocking_incident(self, *, member_id: int) -> bool:
        statement = (
            select(RoutineControlIncidentORM.id)
            .where(
                RoutineControlIncidentORM.member_id == member_id,
                RoutineControlIncidentORM.is_active.is_(True),
                RoutineControlIncidentORM.is_blocking.is_(True),
                RoutineControlIncidentORM.resolved_at_utc.is_(None),
                RoutineControlIncidentORM.incident_type.in_(
                    _ALLOWED_BLOCKING_INCIDENT_TYPES
                ),
            )
            .limit(1)
        )
        return self._session.execute(statement).scalar_one_or_none() is not None

    def has_current_no_routine_decision(
        self,
        *,
        member_id: int,
        as_of_utc: datetime,
    ) -> bool:
        statement = (
            select(RoutineControlDecisionORM.id)
            .where(
                RoutineControlDecisionORM.member_id == member_id,
                RoutineControlDecisionORM.decision_type == "NO_DESEA_RUTINA",
                RoutineControlDecisionORM.is_active.is_(True),
                RoutineControlDecisionORM.revoked_at_utc.is_(None),
                RoutineControlDecisionORM.effective_from_utc <= as_of_utc,
                or_(
                    RoutineControlDecisionORM.effective_to_utc.is_(None),
                    RoutineControlDecisionORM.effective_to_utc > as_of_utc,
                ),
            )
            .limit(1)
        )
        return self._session.execute(statement).scalar_one_or_none() is not None
