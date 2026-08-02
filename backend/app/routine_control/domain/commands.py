from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class UpsertRoutineMemberCommand:
    source_system: str
    source_record_id: str
    source_identity_key: str
    external_member_id: str
    external_sale_id: str | None
    sucursal_id: int | None
    source_branch_name: str | None
    member_name: str | None
    email_original: str | None
    email_normalized: str | None
    sale_date: date
    source_updated_at_utc: datetime | None
    payload_hash: str
    source_metadata: dict[str, Any] | None
    observed_at_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class RegisterRoutineEvidenceCommand:
    provider_key: str
    provider_member_id: str
    evidence_identity_key: str
    external_member_id: str | None
    external_routine_id: str | None
    member_name_original: str | None
    member_name_normalized: str | None
    email_original: str | None
    email_normalized: str | None
    provider_center_key: str
    provider_center_name: str
    sucursal_id: int | None
    routine_activity_date: date
    instructor_name: str
    instructor_name_normalized: str
    routine_count: int
    weighing_count: int
    provider_run_id: int | None
    payload_hash: str
    source_metadata: dict[str, Any] | None
    observed_at_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class LinkRoutineMemberEvidenceCommand:
    member_id: int
    evidence_id: int
    match_method: str
    identity_corroborator: str | None = None
    temporal_delta_days: int | None = None
    matching_contract_version: str | None = None
    provider_run_id: int | None = None
    linked_at_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class UnlinkRoutineMemberEvidenceCommand:
    member_id: int
    evidence_id: int
    unlink_reason: str
    provider_run_id: int | None = None
    unlinked_at_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class ReconcileRoutineMemberCommand:
    member_id: int
    as_of_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class CreateNoRoutineDecisionCommand:
    member_id: int
    reason_code: str
    notes: str | None
    actor_user_id: int
    confirmed: bool
    decided_at_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class RevokeNoRoutineDecisionCommand:
    member_id: int
    decision_id: int
    actor_user_id: int
    revocation_reason: str
    revoked_at_utc: datetime | None = None
