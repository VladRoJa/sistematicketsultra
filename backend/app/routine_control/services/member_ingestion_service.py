from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.routine_control import RoutineControlMemberORM
from app.routine_control.domain.commands import UpsertRoutineMemberCommand
from app.routine_control.domain.exceptions import (
    RoutineControlMemberIdentityConflict,
)
from app.routine_control.domain.results import UpsertRoutineMemberResult
from app.routine_control.repositories.member_repository import (
    RoutineControlMemberRepository,
)


_SOURCE_FIELDS = (
    "external_member_id",
    "external_sale_id",
    "sucursal_id",
    "source_branch_name",
    "member_name",
    "email_original",
    "email_normalized",
    "sale_date",
    "cohort_month",
    "source_updated_at_utc",
    "payload_hash",
    "source_metadata",
)


def _cohort_month(command: UpsertRoutineMemberCommand):
    return command.sale_date.replace(day=1)


def _source_values(command: UpsertRoutineMemberCommand) -> dict[str, Any]:
    return {
        "external_member_id": command.external_member_id,
        "external_sale_id": command.external_sale_id,
        "sucursal_id": command.sucursal_id,
        "source_branch_name": command.source_branch_name,
        "member_name": command.member_name,
        "email_original": command.email_original,
        "email_normalized": command.email_normalized,
        "sale_date": command.sale_date,
        "cohort_month": _cohort_month(command),
        "source_updated_at_utc": command.source_updated_at_utc,
        "payload_hash": command.payload_hash,
        "source_metadata": (
            None if command.source_metadata is None else dict(command.source_metadata)
        ),
    }


def _resolve_member(
    repository: RoutineControlMemberRepository,
    command: UpsertRoutineMemberCommand,
) -> RoutineControlMemberORM | None:
    by_primary = repository.find_by_primary_identity(
        source_system=command.source_system,
        source_record_id=command.source_record_id,
    )
    by_secondary = repository.find_by_secondary_identity(
        source_system=command.source_system,
        source_identity_key=command.source_identity_key,
    )

    if (
        by_primary is not None
        and by_secondary is not None
        and by_primary.id != by_secondary.id
    ):
        raise RoutineControlMemberIdentityConflict(
            "Las identidades primaria y secundaria apuntan a miembros distintos."
        )

    member = by_primary or by_secondary
    if member is None:
        return None

    if (
        member.source_system != command.source_system
        or member.source_record_id != command.source_record_id
        or member.source_identity_key != command.source_identity_key
    ):
        raise RoutineControlMemberIdentityConflict(
            "La identidad almacenada no coincide completamente con el comando."
        )

    return member


def _new_member(
    command: UpsertRoutineMemberCommand,
    *,
    observed_at_utc: datetime,
) -> RoutineControlMemberORM:
    return RoutineControlMemberORM(
        source_system=command.source_system,
        source_record_id=command.source_record_id,
        source_identity_key=command.source_identity_key,
        **_source_values(command),
        classification_status="CLASSIFIED",
        current_status="SIN_RUTINA",
        status_version=1,
        first_seen_at=observed_at_utc,
        last_seen_at=observed_at_utc,
    )


def _update_member(
    member: RoutineControlMemberORM,
    command: UpsertRoutineMemberCommand,
    *,
    observed_at_utc: datetime,
) -> tuple[bool, str]:
    previous_payload_hash = member.payload_hash
    source_values = _source_values(command)
    source_changed = any(
        getattr(member, field_name) != source_values[field_name]
        for field_name in _SOURCE_FIELDS
    )

    for field_name in _SOURCE_FIELDS:
        setattr(member, field_name, source_values[field_name])
    member.last_seen_at = max(member.last_seen_at, observed_at_utc)

    return source_changed, previous_payload_hash


def _result(
    member: RoutineControlMemberORM,
    *,
    created: bool,
    source_changed: bool,
    previous_payload_hash: str | None,
) -> UpsertRoutineMemberResult:
    return UpsertRoutineMemberResult(
        member_id=int(member.id),
        created=created,
        source_changed=source_changed,
        previous_payload_hash=previous_payload_hash,
        current_payload_hash=member.payload_hash,
    )


def _recover_after_integrity_error(
    *,
    command: UpsertRoutineMemberCommand,
    observed_at_utc: datetime,
    repository: RoutineControlMemberRepository,
    integrity_error: IntegrityError,
) -> UpsertRoutineMemberResult:
    session = repository.session

    try:
        repository.acquire_primary_identity_lock(
            source_system=command.source_system,
            source_record_id=command.source_record_id,
        )
        member = _resolve_member(repository, command)
        if member is None:
            session.rollback()
            raise integrity_error

        source_changed, previous_payload_hash = _update_member(
            member,
            command,
            observed_at_utc=observed_at_utc,
        )
        session.flush()
        result = _result(
            member,
            created=False,
            source_changed=source_changed,
            previous_payload_hash=previous_payload_hash,
        )
        session.commit()
        return result
    except RoutineControlMemberIdentityConflict:
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise


def upsert_routine_member(
    command: UpsertRoutineMemberCommand,
    *,
    repository: RoutineControlMemberRepository | None = None,
) -> UpsertRoutineMemberResult:
    if not isinstance(command, UpsertRoutineMemberCommand):
        raise TypeError("command debe ser UpsertRoutineMemberCommand.")

    observed_at_utc = command.observed_at_utc or datetime.now(timezone.utc)
    member_repository = repository or RoutineControlMemberRepository(db.session)
    session = member_repository.session

    try:
        member_repository.acquire_primary_identity_lock(
            source_system=command.source_system,
            source_record_id=command.source_record_id,
        )
        member = _resolve_member(member_repository, command)

        if member is None:
            member = _new_member(command, observed_at_utc=observed_at_utc)
            member_repository.add(member)
            created = True
            source_changed = True
            previous_payload_hash = None
        else:
            created = False
            source_changed, previous_payload_hash = _update_member(
                member,
                command,
                observed_at_utc=observed_at_utc,
            )

        session.flush()
        result = _result(
            member,
            created=created,
            source_changed=source_changed,
            previous_payload_hash=previous_payload_hash,
        )
        session.commit()
        return result
    except RoutineControlMemberIdentityConflict:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        return _recover_after_integrity_error(
            command=command,
            observed_at_utc=observed_at_utc,
            repository=member_repository,
            integrity_error=exc,
        )
    except Exception:
        session.rollback()
        raise
