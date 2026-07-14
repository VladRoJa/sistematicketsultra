from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.routine_control import RoutineControlMemberEvidenceORM
from app.routine_control.domain.commands import (
    LinkRoutineMemberEvidenceCommand,
    UnlinkRoutineMemberEvidenceCommand,
)
from app.routine_control.domain.exceptions import (
    RoutineControlMemberEvidenceConflict,
    RoutineControlMemberEvidenceNotFound,
    RoutineControlMemberEvidenceValidationError,
)
from app.routine_control.domain.results import (
    RoutineControlMemberEvidenceResult,
)
from app.routine_control.repositories.member_evidence_repository import (
    RoutineControlMemberEvidenceRepository,
)


_MATCH_METHODS = frozenset(("EXTERNAL_ID", "EMAIL"))


def _validate_positive_id(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RoutineControlMemberEvidenceValidationError(
            f"{field_name} debe ser un entero positivo."
        )


def _validate_timezone(value: datetime | None, field_name: str) -> None:
    if value is not None and (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise RoutineControlMemberEvidenceValidationError(
            f"{field_name} debe incluir timezone."
        )


def _validate_link_command(command: LinkRoutineMemberEvidenceCommand) -> None:
    _validate_positive_id(command.member_id, "member_id")
    _validate_positive_id(command.evidence_id, "evidence_id")
    if (
        not isinstance(command.match_method, str)
        or command.match_method not in _MATCH_METHODS
    ):
        raise RoutineControlMemberEvidenceValidationError(
            "match_method debe ser EXTERNAL_ID o EMAIL."
        )
    _validate_timezone(command.linked_at_utc, "linked_at_utc")


def _validate_unlink_command(command: UnlinkRoutineMemberEvidenceCommand) -> None:
    _validate_positive_id(command.member_id, "member_id")
    _validate_positive_id(command.evidence_id, "evidence_id")
    if not isinstance(command.unlink_reason, str) or not command.unlink_reason.strip():
        raise RoutineControlMemberEvidenceValidationError(
            "unlink_reason debe contener texto."
        )
    _validate_timezone(command.unlinked_at_utc, "unlinked_at_utc")


def _result(
    link: RoutineControlMemberEvidenceORM,
    *,
    created: bool,
    changed: bool,
) -> RoutineControlMemberEvidenceResult:
    return RoutineControlMemberEvidenceResult(
        link_id=int(link.id),
        member_id=int(link.member_id),
        evidence_id=int(link.evidence_id),
        created=created,
        changed=changed,
        is_active=bool(link.is_active),
        match_method=link.match_method,
    )


def _apply_active_match_method(
    link: RoutineControlMemberEvidenceORM,
    match_method: str,
) -> bool:
    if link.match_method == "EMAIL" and match_method == "EXTERNAL_ID":
        link.match_method = "EXTERNAL_ID"
        return True
    return False


def _recover_link_after_integrity_error(
    *,
    command: LinkRoutineMemberEvidenceCommand,
    repository: RoutineControlMemberEvidenceRepository,
    integrity_error: IntegrityError,
) -> RoutineControlMemberEvidenceResult:
    session = repository.session
    try:
        repository.acquire_pair_lock(
            member_id=command.member_id,
            evidence_id=command.evidence_id,
        )
        link = repository.find_by_pair(
            member_id=command.member_id,
            evidence_id=command.evidence_id,
        )
        if link is None:
            session.rollback()
            raise integrity_error
        if not link.is_active:
            raise RoutineControlMemberEvidenceConflict(
                "Un vínculo inactivo no puede reactivarse sin perder auditoría."
            )

        changed = _apply_active_match_method(link, command.match_method)
        session.flush()
        result = _result(link, created=False, changed=changed)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def link_routine_member_evidence(
    command: LinkRoutineMemberEvidenceCommand,
    *,
    repository: RoutineControlMemberEvidenceRepository | None = None,
) -> RoutineControlMemberEvidenceResult:
    if not isinstance(command, LinkRoutineMemberEvidenceCommand):
        raise TypeError("command debe ser LinkRoutineMemberEvidenceCommand.")
    _validate_link_command(command)

    link_repository = repository or RoutineControlMemberEvidenceRepository(
        db.session
    )
    session = link_repository.session

    try:
        link_repository.acquire_pair_lock(
            member_id=command.member_id,
            evidence_id=command.evidence_id,
        )
        if link_repository.find_member(command.member_id) is None:
            raise RoutineControlMemberEvidenceNotFound("El miembro no existe.")
        evidence = link_repository.find_evidence(command.evidence_id)
        if evidence is None:
            raise RoutineControlMemberEvidenceNotFound("La evidencia no existe.")

        link = link_repository.find_by_pair(
            member_id=command.member_id,
            evidence_id=command.evidence_id,
        )
        if link is None:
            if not evidence.is_valid:
                raise RoutineControlMemberEvidenceConflict(
                    "No se puede crear un vínculo hacia evidencia invalidada."
                )
            link = RoutineControlMemberEvidenceORM(
                member_id=command.member_id,
                evidence_id=command.evidence_id,
                match_method=command.match_method,
                is_active=True,
                linked_by_provider_run_id=command.provider_run_id,
                linked_at_utc=command.linked_at_utc or datetime.now(timezone.utc),
                unlinked_by_provider_run_id=None,
                unlinked_at_utc=None,
                unlink_reason=None,
            )
            link_repository.add(link)
            created = True
            changed = True
        else:
            if not link.is_active:
                raise RoutineControlMemberEvidenceConflict(
                    "Un vínculo inactivo no puede reactivarse sin perder auditoría."
                )
            created = False
            changed = _apply_active_match_method(link, command.match_method)

        session.flush()
        result = _result(link, created=created, changed=changed)
        session.commit()
        return result
    except IntegrityError as exc:
        session.rollback()
        return _recover_link_after_integrity_error(
            command=command,
            repository=link_repository,
            integrity_error=exc,
        )
    except Exception:
        session.rollback()
        raise


def unlink_routine_member_evidence(
    command: UnlinkRoutineMemberEvidenceCommand,
    *,
    repository: RoutineControlMemberEvidenceRepository | None = None,
) -> RoutineControlMemberEvidenceResult:
    if not isinstance(command, UnlinkRoutineMemberEvidenceCommand):
        raise TypeError("command debe ser UnlinkRoutineMemberEvidenceCommand.")
    _validate_unlink_command(command)

    link_repository = repository or RoutineControlMemberEvidenceRepository(
        db.session
    )
    session = link_repository.session

    try:
        link_repository.acquire_pair_lock(
            member_id=command.member_id,
            evidence_id=command.evidence_id,
        )
        link = link_repository.find_by_pair(
            member_id=command.member_id,
            evidence_id=command.evidence_id,
        )
        if link is None:
            raise RoutineControlMemberEvidenceNotFound("El vínculo no existe.")

        if link.is_active:
            link.is_active = False
            link.unlinked_at_utc = (
                command.unlinked_at_utc or datetime.now(timezone.utc)
            )
            link.unlink_reason = command.unlink_reason.strip()
            link.unlinked_by_provider_run_id = command.provider_run_id
            changed = True
        else:
            changed = False

        session.flush()
        result = _result(link, created=False, changed=changed)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
