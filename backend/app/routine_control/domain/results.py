from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class UpsertRoutineMemberResult:
    member_id: int
    created: bool
    source_changed: bool
    previous_payload_hash: str | None
    current_payload_hash: str


@dataclass(frozen=True, slots=True)
class RegisterRoutineEvidenceResult:
    evidence_id: int
    created: bool
    source_changed: bool
    previous_payload_hash: str | None
    current_payload_hash: str
    is_valid: bool


@dataclass(frozen=True, slots=True)
class RoutineControlMemberEvidenceResult:
    link_id: int
    member_id: int
    evidence_id: int
    created: bool
    changed: bool
    is_active: bool
    match_method: str


@dataclass(frozen=True, slots=True)
class RoutineControlReconciliationResult:
    member_id: int
    changed: bool
    classification_status: str
    current_status: str | None
    first_routine_at: date | None
    latest_routine_at: date | None
    current_instructor_name: str | None
    routine_assignment_type: str | None
    status_version: int
