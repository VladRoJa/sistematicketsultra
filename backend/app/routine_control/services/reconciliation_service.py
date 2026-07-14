from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.models.routine_control import RoutineControlMemberORM
from app.routine_control.domain.commands import ReconcileRoutineMemberCommand
from app.routine_control.domain.exceptions import (
    RoutineControlReconciliationError,
    RoutineControlReconciliationNotFound,
    RoutineControlReconciliationValidationError,
)
from app.routine_control.domain.results import (
    RoutineControlReconciliationResult,
)
from app.routine_control.repositories.reconciliation_repository import (
    RoutineControlReconciliationRepository,
)


_PROJECTION_FIELDS = (
    "classification_status",
    "current_status",
    "first_routine_at",
    "latest_routine_at",
    "current_instructor_name",
    "routine_assignment_type",
)


def _validated_as_of_utc(command: ReconcileRoutineMemberCommand) -> datetime:
    if (
        not isinstance(command.member_id, int)
        or isinstance(command.member_id, bool)
        or command.member_id <= 0
    ):
        raise RoutineControlReconciliationValidationError(
            "member_id debe ser un entero positivo."
        )
    if command.as_of_utc is None:
        return datetime.now(timezone.utc)
    if (
        not isinstance(command.as_of_utc, datetime)
        or command.as_of_utc.tzinfo is None
        or command.as_of_utc.utcoffset() is None
    ):
        raise RoutineControlReconciliationValidationError(
            "as_of_utc debe incluir timezone."
        )
    return command.as_of_utc.astimezone(timezone.utc)


def _evidence_projection(member, evidences) -> dict[str, object | None]:
    if not evidences:
        return {
            "first_routine_at": None,
            "latest_routine_at": None,
            "current_instructor_name": None,
            "routine_assignment_type": None,
        }

    first = evidences[0]
    latest = evidences[-1]
    first_routine_at = first.routine_activity_date
    if first_routine_at < member.sale_date:
        assignment_type = "PREEXISTENTE"
    elif first_routine_at == member.sale_date:
        assignment_type = "MISMO_DIA"
    else:
        assignment_type = "POSTERIOR"
    return {
        "first_routine_at": first_routine_at,
        "latest_routine_at": latest.routine_activity_date,
        "current_instructor_name": latest.instructor_name,
        "routine_assignment_type": assignment_type,
    }


def _projection(
    member: RoutineControlMemberORM,
    *,
    evidences,
    has_blocking_incident: bool,
    has_no_routine_decision: bool,
) -> dict[str, object | None]:
    evidence_values = _evidence_projection(member, evidences)
    if has_blocking_incident:
        status_values = {
            "classification_status": "INCIDENT",
            "current_status": None,
        }
    elif evidences:
        status_values = {
            "classification_status": "CLASSIFIED",
            "current_status": "CON_RUTINA",
        }
    elif has_no_routine_decision:
        status_values = {
            "classification_status": "CLASSIFIED",
            "current_status": "NO_DESEA_RUTINA",
        }
    else:
        status_values = {
            "classification_status": "CLASSIFIED",
            "current_status": "SIN_RUTINA",
        }
    return {**status_values, **evidence_values}


def _result(
    member: RoutineControlMemberORM,
    *,
    changed: bool,
) -> RoutineControlReconciliationResult:
    return RoutineControlReconciliationResult(
        member_id=int(member.id),
        changed=changed,
        classification_status=member.classification_status,
        current_status=member.current_status,
        first_routine_at=member.first_routine_at,
        latest_routine_at=member.latest_routine_at,
        current_instructor_name=member.current_instructor_name,
        routine_assignment_type=member.routine_assignment_type,
        status_version=int(member.status_version),
    )


def reconcile_routine_member(
    command: ReconcileRoutineMemberCommand,
    *,
    repository: RoutineControlReconciliationRepository | None = None,
) -> RoutineControlReconciliationResult:
    if not isinstance(command, ReconcileRoutineMemberCommand):
        raise TypeError("command debe ser ReconcileRoutineMemberCommand.")

    reconciliation_repository = (
        repository or RoutineControlReconciliationRepository(db.session)
    )
    session = reconciliation_repository.session

    try:
        as_of_utc = _validated_as_of_utc(command)
        reconciliation_repository.acquire_member_lock(
            member_id=command.member_id
        )
        member = reconciliation_repository.find_member_for_update(
            member_id=command.member_id
        )
        if member is None:
            raise RoutineControlReconciliationNotFound(
                "El miembro solicitado no existe."
            )

        evidences = reconciliation_repository.find_active_valid_evidences(
            member_id=command.member_id
        )
        projection = _projection(
            member,
            evidences=evidences,
            has_blocking_incident=(
                reconciliation_repository.has_active_blocking_incident(
                    member_id=command.member_id
                )
            ),
            has_no_routine_decision=(
                reconciliation_repository.has_current_no_routine_decision(
                    member_id=command.member_id,
                    as_of_utc=as_of_utc,
                )
            ),
        )
        changed = any(
            getattr(member, field_name) != projection[field_name]
            for field_name in _PROJECTION_FIELDS
        )
        if changed:
            for field_name in _PROJECTION_FIELDS:
                setattr(member, field_name, projection[field_name])
            member.status_version += 1

        session.flush()
        result = _result(member, changed=changed)
        session.commit()
        return result
    except RoutineControlReconciliationError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
