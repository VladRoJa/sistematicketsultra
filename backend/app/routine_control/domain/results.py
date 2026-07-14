from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UpsertRoutineMemberResult:
    member_id: int
    created: bool
    source_changed: bool
    previous_payload_hash: str | None
    current_payload_hash: str
