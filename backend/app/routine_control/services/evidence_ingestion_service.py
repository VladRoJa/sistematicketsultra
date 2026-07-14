from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.routine_control import RoutineAssignmentEvidenceORM
from app.routine_control.domain.commands import RegisterRoutineEvidenceCommand
from app.routine_control.domain.exceptions import (
    RoutineControlEvidenceIdentityConflict,
    RoutineControlEvidenceValidationError,
)
from app.routine_control.domain.results import RegisterRoutineEvidenceResult
from app.routine_control.repositories.evidence_repository import (
    RoutineAssignmentEvidenceRepository,
)


_SOURCE_FIELDS = (
    "external_member_id",
    "external_routine_id",
    "email_original",
    "email_normalized",
    "provider_center_key",
    "provider_center_name",
    "sucursal_id",
    "routine_activity_date",
    "instructor_name",
    "instructor_name_normalized",
    "routine_count",
    "weighing_count",
    "payload_hash",
    "source_metadata",
)


def _validate_command(command: RegisterRoutineEvidenceCommand) -> None:
    required_text_fields = (
        "provider_key",
        "provider_member_id",
        "evidence_identity_key",
        "provider_center_key",
        "provider_center_name",
        "instructor_name",
        "instructor_name_normalized",
    )
    for field_name in required_text_fields:
        value = getattr(command, field_name)
        if not isinstance(value, str) or not value.strip():
            raise RoutineControlEvidenceValidationError(
                f"{field_name} no puede estar vacío."
            )

    if (
        not isinstance(command.routine_count, int)
        or isinstance(command.routine_count, bool)
        or command.routine_count <= 0
    ):
        raise RoutineControlEvidenceValidationError(
            "routine_count debe ser mayor que cero."
        )
    if (
        not isinstance(command.weighing_count, int)
        or isinstance(command.weighing_count, bool)
        or command.weighing_count < 0
    ):
        raise RoutineControlEvidenceValidationError(
            "weighing_count no puede ser negativo."
        )
    if (
        command.observed_at_utc is not None
        and (
            command.observed_at_utc.tzinfo is None
            or command.observed_at_utc.utcoffset() is None
        )
    ):
        raise RoutineControlEvidenceValidationError(
            "observed_at_utc debe incluir timezone."
        )


def _source_values(command: RegisterRoutineEvidenceCommand) -> dict[str, Any]:
    return {
        "external_member_id": command.external_member_id,
        "external_routine_id": command.external_routine_id,
        "email_original": command.email_original,
        "email_normalized": command.email_normalized,
        "provider_center_key": command.provider_center_key,
        "provider_center_name": command.provider_center_name,
        "sucursal_id": command.sucursal_id,
        "routine_activity_date": command.routine_activity_date,
        "instructor_name": command.instructor_name,
        "instructor_name_normalized": command.instructor_name_normalized,
        "routine_count": command.routine_count,
        "weighing_count": command.weighing_count,
        "payload_hash": command.payload_hash,
        "source_metadata": (
            None if command.source_metadata is None else dict(command.source_metadata)
        ),
    }


def _resolve_evidence(
    repository: RoutineAssignmentEvidenceRepository,
    command: RegisterRoutineEvidenceCommand,
) -> RoutineAssignmentEvidenceORM | None:
    evidence = repository.find_by_identity(
        provider_key=command.provider_key,
        evidence_identity_key=command.evidence_identity_key,
    )
    if (
        evidence is not None
        and evidence.provider_member_id != command.provider_member_id
    ):
        raise RoutineControlEvidenceIdentityConflict(
            "La evidencia almacenada pertenece a otro provider_member_id."
        )
    return evidence


def _new_evidence(
    command: RegisterRoutineEvidenceCommand,
    *,
    observed_at_utc: datetime,
) -> RoutineAssignmentEvidenceORM:
    return RoutineAssignmentEvidenceORM(
        provider_key=command.provider_key,
        provider_member_id=command.provider_member_id,
        evidence_identity_key=command.evidence_identity_key,
        **_source_values(command),
        first_observed_at=observed_at_utc,
        last_observed_at=observed_at_utc,
        first_provider_run_id=command.provider_run_id,
        last_provider_run_id=command.provider_run_id,
        is_valid=True,
        invalidated_at_utc=None,
        invalidated_by_user_id=None,
        invalidation_reason=None,
    )


def _update_evidence(
    evidence: RoutineAssignmentEvidenceORM,
    command: RegisterRoutineEvidenceCommand,
    *,
    observed_at_utc: datetime,
) -> tuple[bool, str]:
    previous_payload_hash = evidence.payload_hash
    previous_last_observed_at = evidence.last_observed_at
    source_values = _source_values(command)
    source_changed = any(
        getattr(evidence, field_name) != source_values[field_name]
        for field_name in _SOURCE_FIELDS
    )

    for field_name in _SOURCE_FIELDS:
        setattr(evidence, field_name, source_values[field_name])

    if command.provider_run_id is not None and (
        observed_at_utc >= previous_last_observed_at
    ):
        evidence.last_provider_run_id = command.provider_run_id
    evidence.last_observed_at = max(previous_last_observed_at, observed_at_utc)

    return source_changed, previous_payload_hash


def _result(
    evidence: RoutineAssignmentEvidenceORM,
    *,
    created: bool,
    source_changed: bool,
    previous_payload_hash: str | None,
) -> RegisterRoutineEvidenceResult:
    return RegisterRoutineEvidenceResult(
        evidence_id=int(evidence.id),
        created=created,
        source_changed=source_changed,
        previous_payload_hash=previous_payload_hash,
        current_payload_hash=evidence.payload_hash,
        is_valid=bool(evidence.is_valid),
    )


def _recover_after_integrity_error(
    *,
    command: RegisterRoutineEvidenceCommand,
    observed_at_utc: datetime,
    repository: RoutineAssignmentEvidenceRepository,
    integrity_error: IntegrityError,
) -> RegisterRoutineEvidenceResult:
    session = repository.session

    try:
        repository.acquire_identity_lock(
            provider_key=command.provider_key,
            evidence_identity_key=command.evidence_identity_key,
        )
        evidence = _resolve_evidence(repository, command)
        if evidence is None:
            session.rollback()
            raise integrity_error

        source_changed, previous_payload_hash = _update_evidence(
            evidence,
            command,
            observed_at_utc=observed_at_utc,
        )
        session.flush()
        result = _result(
            evidence,
            created=False,
            source_changed=source_changed,
            previous_payload_hash=previous_payload_hash,
        )
        session.commit()
        return result
    except RoutineControlEvidenceIdentityConflict:
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise


def register_routine_evidence(
    command: RegisterRoutineEvidenceCommand,
    *,
    repository: RoutineAssignmentEvidenceRepository | None = None,
) -> RegisterRoutineEvidenceResult:
    if not isinstance(command, RegisterRoutineEvidenceCommand):
        raise TypeError("command debe ser RegisterRoutineEvidenceCommand.")
    _validate_command(command)

    observed_at_utc = command.observed_at_utc or datetime.now(timezone.utc)
    evidence_repository = repository or RoutineAssignmentEvidenceRepository(
        db.session
    )
    session = evidence_repository.session

    try:
        evidence_repository.acquire_identity_lock(
            provider_key=command.provider_key,
            evidence_identity_key=command.evidence_identity_key,
        )
        evidence = _resolve_evidence(evidence_repository, command)

        if evidence is None:
            evidence = _new_evidence(command, observed_at_utc=observed_at_utc)
            evidence_repository.add(evidence)
            created = True
            source_changed = True
            previous_payload_hash = None
        else:
            created = False
            source_changed, previous_payload_hash = _update_evidence(
                evidence,
                command,
                observed_at_utc=observed_at_utc,
            )

        session.flush()
        result = _result(
            evidence,
            created=created,
            source_changed=source_changed,
            previous_payload_hash=previous_payload_hash,
        )
        session.commit()
        return result
    except RoutineControlEvidenceIdentityConflict:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        return _recover_after_integrity_error(
            command=command,
            observed_at_utc=observed_at_utc,
            repository=evidence_repository,
            integrity_error=exc,
        )
    except Exception:
        session.rollback()
        raise
