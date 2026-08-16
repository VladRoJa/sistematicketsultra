from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.routine_control import (
    RoutineControlDecisionORM,
)
from app.routine_control.domain.commands import (
    CreateNoRoutineDecisionCommand,
    ReconcileRoutineMemberCommand,
    RevokeNoRoutineDecisionCommand,
)
from app.routine_control.domain.exceptions import (
    RoutineControlDecisionConflict,
    RoutineControlDecisionError,
    RoutineControlDecisionNotFound,
    RoutineControlDecisionValidationError,
)
from app.routine_control.domain.results import (
    RoutineControlDecisionMutationResult,
)
from app.routine_control.repositories.decision_repository import (
    RoutineControlDecisionRepository,
)
from app.routine_control.repositories.reconciliation_repository import (
    RoutineControlReconciliationRepository,
)
from app.routine_control.services.reconciliation_service import (
    reconcile_routine_member,
)


NO_ROUTINE_REASON_CODES = frozenset(
    {
        "NO_INTERESADO",
        "RUTINA_PROPIA",
        "ENTRENADOR_EXTERNO",
        "LIMITACION_MEDICA",
        "SOLO_CLASES_GRUPALES",
        "OTRO",
    }
)


def _positive_int(
    value,
    *,
    field: str,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        raise RoutineControlDecisionValidationError(
            f"{field} debe ser un entero positivo."
        )

    return value


def _utc_datetime(
    value,
    *,
    field: str,
) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)

    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise RoutineControlDecisionValidationError(
            f"{field} debe incluir timezone."
        )

    return value.astimezone(timezone.utc)


def _optional_text(value) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    return normalized or None


def _required_text(
    value,
    *,
    field: str,
) -> str:
    normalized = _optional_text(value)

    if normalized is None:
        raise RoutineControlDecisionValidationError(
            f"{field} es obligatorio."
        )

    return normalized


def _validated_reason_code(value) -> str:
    reason_code = str(value or "").strip().upper()

    if reason_code not in NO_ROUTINE_REASON_CODES:
        raise RoutineControlDecisionValidationError(
            "reason_code inválido."
        )

    return reason_code


def _result(
    decision: RoutineControlDecisionORM,
    *,
    action: str,
    reconciliation,
) -> RoutineControlDecisionMutationResult:
    return RoutineControlDecisionMutationResult(
        decision_id=int(decision.id),
        member_id=int(decision.member_id),
        action=action,
        is_active=bool(decision.is_active),
        reason_code=decision.reason_code,
        notes=decision.notes,
        decided_at_utc=decision.decided_at_utc,
        revoked_at_utc=decision.revoked_at_utc,
        classification_status=(
            reconciliation.classification_status
        ),
        current_status=reconciliation.current_status,
        status_version=int(
            reconciliation.status_version
        ),
    )


def create_no_routine_decision(
    command: CreateNoRoutineDecisionCommand,
    *,
    repository: RoutineControlDecisionRepository
    | None = None,
) -> RoutineControlDecisionMutationResult:
    if not isinstance(
        command,
        CreateNoRoutineDecisionCommand,
    ):
        raise TypeError(
            "command debe ser "
            "CreateNoRoutineDecisionCommand."
        )

    if command.confirmed is not True:
        raise RoutineControlDecisionValidationError(
            "Debes confirmar explícitamente la decisión."
        )

    member_id = _positive_int(
        command.member_id,
        field="member_id",
    )
    actor_user_id = _positive_int(
        command.actor_user_id,
        field="actor_user_id",
    )
    reason_code = _validated_reason_code(
        command.reason_code
    )
    notes = _optional_text(command.notes)

    if reason_code == "OTRO" and notes is None:
        raise RoutineControlDecisionValidationError(
            "notes es obligatorio cuando reason_code "
            "es OTRO."
        )

    decided_at_utc = _utc_datetime(
        command.decided_at_utc,
        field="decided_at_utc",
    )

    decision_repository = (
        repository
        or RoutineControlDecisionRepository(db.session)
    )
    session = decision_repository.session
    reconciliation_repository = (
        RoutineControlReconciliationRepository(session)
    )

    try:
        decision_repository.acquire_member_lock(
            member_id=member_id
        )
        member = (
            decision_repository.find_member_for_update(
                member_id=member_id
            )
        )

        if member is None:
            raise RoutineControlDecisionNotFound(
                "El socio solicitado no existe."
            )

        if (
            reconciliation_repository
            .has_active_blocking_incident(
                member_id=member_id
            )
        ):
            raise RoutineControlDecisionConflict(
                "No se puede registrar la decisión "
                "mientras exista una incidencia bloqueante."
            )

        if (
            reconciliation_repository
            .find_active_valid_evidences(
                member_id=member_id
            )
        ):
            raise RoutineControlDecisionConflict(
                "El socio ya cuenta con evidencia válida "
                "de rutina."
            )

        if (
            decision_repository
            .find_active_decision_for_update(
                member_id=member_id
            )
            is not None
        ):
            raise RoutineControlDecisionConflict(
                "El socio ya tiene una decisión activa."
            )

        decision = RoutineControlDecisionORM(
            member_id=member_id,
            decision_type="NO_DESEA_RUTINA",
            reason_code=reason_code,
            notes=notes,
            is_active=True,
            decided_at_utc=decided_at_utc,
            effective_from_utc=decided_at_utc,
            effective_to_utc=None,
            created_by_user_id=actor_user_id,
            created_from_sucursal_id=(
                member.sucursal_id
            ),
            revoked_at_utc=None,
            revoked_by_user_id=None,
            revocation_reason=None,
        )
        decision_repository.add(decision)
        session.flush()

        reconciliation = reconcile_routine_member(
            ReconcileRoutineMemberCommand(
                member_id=member_id,
                as_of_utc=decided_at_utc,
            ),
            repository=reconciliation_repository,
            manage_transaction=False,
        )

        result = _result(
            decision,
            action="CREATED",
            reconciliation=reconciliation,
        )
        session.commit()
        return result

    except RoutineControlDecisionError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise


def revoke_no_routine_decision(
    command: RevokeNoRoutineDecisionCommand,
    *,
    repository: RoutineControlDecisionRepository
    | None = None,
) -> RoutineControlDecisionMutationResult:
    if not isinstance(
        command,
        RevokeNoRoutineDecisionCommand,
    ):
        raise TypeError(
            "command debe ser "
            "RevokeNoRoutineDecisionCommand."
        )

    member_id = _positive_int(
        command.member_id,
        field="member_id",
    )
    decision_id = _positive_int(
        command.decision_id,
        field="decision_id",
    )
    actor_user_id = _positive_int(
        command.actor_user_id,
        field="actor_user_id",
    )
    revocation_reason = _required_text(
        command.revocation_reason,
        field="revocation_reason",
    )
    implicit_revocation_time = (
        command.revoked_at_utc is None
    )
    revoked_at_utc = _utc_datetime(
        command.revoked_at_utc,
        field="revoked_at_utc",
    )

    decision_repository = (
        repository
        or RoutineControlDecisionRepository(db.session)
    )
    session = decision_repository.session
    reconciliation_repository = (
        RoutineControlReconciliationRepository(session)
    )

    try:
        decision_repository.acquire_member_lock(
            member_id=member_id
        )
        member = (
            decision_repository.find_member_for_update(
                member_id=member_id
            )
        )

        if member is None:
            raise RoutineControlDecisionNotFound(
                "El socio solicitado no existe."
            )

        decision = (
            decision_repository.find_decision_for_update(
                member_id=member_id,
                decision_id=decision_id,
            )
        )

        if decision is None:
            raise RoutineControlDecisionNotFound(
                "La decisión solicitada no existe."
            )

        if not decision.is_active:
            raise RoutineControlDecisionConflict(
                "La decisión ya fue revertida."
            )

        if (
            implicit_revocation_time
            and revoked_at_utc <= decision.effective_from_utc
        ):
            revoked_at_utc = (
                decision.effective_from_utc
                + timedelta(microseconds=1)
            )

        if revoked_at_utc <= decision.effective_from_utc:
            raise RoutineControlDecisionValidationError(
                "revoked_at_utc debe ser posterior a "
                "effective_from_utc."
            )

        decision.is_active = False
        decision.effective_to_utc = revoked_at_utc
        decision.revoked_at_utc = revoked_at_utc
        decision.revoked_by_user_id = actor_user_id
        decision.revocation_reason = revocation_reason

        session.flush()

        reconciliation = reconcile_routine_member(
            ReconcileRoutineMemberCommand(
                member_id=member_id,
                as_of_utc=revoked_at_utc,
            ),
            repository=reconciliation_repository,
            manage_transaction=False,
        )

        result = _result(
            decision,
            action="REVOKED",
            reconciliation=reconciliation,
        )
        session.commit()
        return result

    except RoutineControlDecisionError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
