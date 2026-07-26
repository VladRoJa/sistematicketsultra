from __future__ import annotations

from typing import Any

from sqlalchemy import select, text

from app.models.routine_control import (
    RoutineControlDecisionORM,
    RoutineControlMemberORM,
)
from app.routine_control.repositories.reconciliation_repository import (
    build_reconciliation_advisory_lock_key,
)


class RoutineControlDecisionRepository:
    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    def acquire_member_lock(
        self,
        *,
        member_id: int,
    ) -> None:
        self._session.execute(
            text(
                "SELECT pg_advisory_xact_lock(:lock_key)"
            ),
            {
                "lock_key": (
                    build_reconciliation_advisory_lock_key(
                        member_id=member_id
                    )
                )
            },
        )

    def find_member_for_update(
        self,
        *,
        member_id: int,
    ) -> RoutineControlMemberORM | None:
        statement = (
            select(RoutineControlMemberORM)
            .where(
                RoutineControlMemberORM.id == member_id
            )
            .with_for_update()
        )
        return self._session.execute(
            statement
        ).scalar_one_or_none()

    def find_active_decision_for_update(
        self,
        *,
        member_id: int,
    ) -> RoutineControlDecisionORM | None:
        statement = (
            select(RoutineControlDecisionORM)
            .where(
                RoutineControlDecisionORM.member_id
                == member_id,
                RoutineControlDecisionORM.decision_type
                == "NO_DESEA_RUTINA",
                RoutineControlDecisionORM.is_active.is_(
                    True
                ),
            )
            .with_for_update()
        )
        return self._session.execute(
            statement
        ).scalar_one_or_none()

    def find_decision_for_update(
        self,
        *,
        member_id: int,
        decision_id: int,
    ) -> RoutineControlDecisionORM | None:
        statement = (
            select(RoutineControlDecisionORM)
            .where(
                RoutineControlDecisionORM.id
                == decision_id,
                RoutineControlDecisionORM.member_id
                == member_id,
                RoutineControlDecisionORM.decision_type
                == "NO_DESEA_RUTINA",
            )
            .with_for_update()
        )
        return self._session.execute(
            statement
        ).scalar_one_or_none()

    def add(
        self,
        decision: RoutineControlDecisionORM,
    ) -> None:
        self._session.add(decision)
