from dataclasses import dataclass


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
