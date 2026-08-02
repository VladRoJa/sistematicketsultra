from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date


MATCHING_CONTRACT_VERSION = "IDENTITY_TEMPORAL_V2"

MATCHED = "MATCHED"
UNMATCHED = "UNMATCHED"
AMBIGUOUS = "AMBIGUOUS"
INSUFFICIENT_IDENTITY_DATA = "INSUFFICIENT_IDENTITY_DATA"
IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
TEMPORALLY_INVALID = "TEMPORALLY_INVALID"


@dataclass(frozen=True, slots=True)
class EvidenceMatchInput:
    evidence_id: int
    external_member_id: str | None
    email_normalized: str | None
    member_name_normalized: str | None
    routine_activity_date: date


@dataclass(frozen=True, slots=True)
class MemberMatchCandidate:
    member_id: int
    external_member_id: str
    email_normalized: str | None
    member_name_normalized: str | None
    sale_date: date


@dataclass(frozen=True, slots=True)
class EvidenceMatchResult:
    status: str
    member_id: int | None
    match_method: str | None
    identity_corroborator: str | None
    temporal_delta_days: int | None
    assignment_type: str | None
    reason: str
    considered_member_ids: tuple[int, ...] = ()
    ambiguous_member_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class _IdentityEvaluation:
    corroborator: str | None
    conflict: bool


def _id_identity(
    evidence: EvidenceMatchInput,
    candidate: MemberMatchCandidate,
) -> _IdentityEvaluation:
    email_comparable = bool(
        evidence.email_normalized and candidate.email_normalized
    )
    name_comparable = bool(
        evidence.member_name_normalized and candidate.member_name_normalized
    )
    if email_comparable and (
        evidence.email_normalized != candidate.email_normalized
    ):
        return _IdentityEvaluation(None, True)
    if name_comparable and (
        evidence.member_name_normalized != candidate.member_name_normalized
    ):
        return _IdentityEvaluation(None, True)

    email_matches = email_comparable
    name_matches = name_comparable
    if email_matches and name_matches:
        return _IdentityEvaluation("EMAIL_AND_NAME", False)
    if email_matches:
        return _IdentityEvaluation("EMAIL", False)
    if name_matches:
        return _IdentityEvaluation("NAME", False)
    return _IdentityEvaluation(None, False)


def _email_identity(
    evidence: EvidenceMatchInput,
    candidate: MemberMatchCandidate,
) -> _IdentityEvaluation:
    if (
        not evidence.email_normalized
        or not candidate.email_normalized
        or evidence.email_normalized != candidate.email_normalized
    ):
        return _IdentityEvaluation(None, False)
    if (
        evidence.member_name_normalized
        and candidate.member_name_normalized
        and evidence.member_name_normalized
        != candidate.member_name_normalized
    ):
        return _IdentityEvaluation(None, True)
    if (
        evidence.member_name_normalized
        and candidate.member_name_normalized
    ):
        return _IdentityEvaluation("EMAIL_AND_NAME", False)
    return _IdentityEvaluation("EMAIL", False)


def _assignment_type(delta_days: int) -> str:
    if delta_days < 0:
        return "PREEXISTENTE"
    if delta_days == 0:
        return "MISMO_DIA"
    return "POSTERIOR"


def _route_result(
    *,
    evidence: EvidenceMatchInput,
    candidates: Sequence[MemberMatchCandidate],
    match_method: str,
    identity_evaluator: Callable[
        [EvidenceMatchInput, MemberMatchCandidate],
        _IdentityEvaluation,
    ],
) -> EvidenceMatchResult:
    considered_ids = tuple(sorted({candidate.member_id for candidate in candidates}))
    valid: list[tuple[MemberMatchCandidate, str, int]] = []
    invalid_temporal: list[tuple[MemberMatchCandidate, str, int]] = []
    identity_conflicts = 0
    insufficient_identity = 0
    temporally_invalid = 0

    for candidate in candidates:
        identity = identity_evaluator(evidence, candidate)
        if identity.conflict:
            identity_conflicts += 1
            continue
        if identity.corroborator is None:
            insufficient_identity += 1
            continue
        delta_days = (
            evidence.routine_activity_date - candidate.sale_date
        ).days
        if delta_days < -30:
            temporally_invalid += 1
            invalid_temporal.append(
                (candidate, identity.corroborator, delta_days)
            )
            continue
        valid.append((candidate, identity.corroborator, delta_days))

    if valid:
        minimum_distance = min(abs(item[2]) for item in valid)
        nearest = [item for item in valid if abs(item[2]) == minimum_distance]
        if len(nearest) > 1:
            ambiguous_ids = tuple(
                sorted({candidate.member_id for candidate, _, _ in nearest})
            )
            return EvidenceMatchResult(
                status=AMBIGUOUS,
                member_id=None,
                match_method=match_method,
                identity_corroborator=None,
                temporal_delta_days=None,
                assignment_type=None,
                reason=(
                    "Multiple candidates share the minimum temporal distance."
                ),
                considered_member_ids=considered_ids,
                ambiguous_member_ids=ambiguous_ids,
            )
        candidate, corroborator, delta_days = nearest[0]
        return EvidenceMatchResult(
            status=MATCHED,
            member_id=candidate.member_id,
            match_method=match_method,
            identity_corroborator=corroborator,
            temporal_delta_days=delta_days,
            assignment_type=_assignment_type(delta_days),
            reason=(
                "Unique identity-compatible candidate with minimum temporal "
                "distance."
            ),
            considered_member_ids=considered_ids,
        )

    if temporally_invalid:
        status = TEMPORALLY_INVALID
        reason = "Identity matched, but every candidate was earlier than -30 days."
    elif identity_conflicts:
        status = IDENTITY_CONFLICT
        reason = "Every comparable candidate had an explicit identity conflict."
    elif insufficient_identity:
        status = INSUFFICIENT_IDENTITY_DATA
        reason = "Candidates lacked a non-conflicting identity corroborator."
    else:
        status = UNMATCHED
        reason = "No candidates were available for this matching route."
    nearest_invalid = (
        min(invalid_temporal, key=lambda item: abs(item[2]))
        if invalid_temporal
        else None
    )
    return EvidenceMatchResult(
        status=status,
        member_id=None,
        match_method=match_method,
        identity_corroborator=(nearest_invalid[1] if nearest_invalid else None),
        temporal_delta_days=(nearest_invalid[2] if nearest_invalid else None),
        assignment_type=(
            _assignment_type(nearest_invalid[2]) if nearest_invalid else None
        ),
        reason=reason,
        considered_member_ids=considered_ids,
    )


def select_evidence_match(
    evidence: EvidenceMatchInput,
    *,
    external_id_candidates: Sequence[MemberMatchCandidate],
    email_candidates: Sequence[MemberMatchCandidate],
) -> EvidenceMatchResult:
    id_result = _route_result(
        evidence=evidence,
        candidates=external_id_candidates,
        match_method="EXTERNAL_ID",
        identity_evaluator=_id_identity,
    )
    if id_result.status in (MATCHED, AMBIGUOUS):
        return id_result

    if evidence.email_normalized:
        email_result = _route_result(
            evidence=evidence,
            candidates=email_candidates,
            match_method="EMAIL",
            identity_evaluator=_email_identity,
        )
        if email_candidates or not external_id_candidates:
            return email_result

    if (
        not evidence.external_member_id
        and not evidence.email_normalized
    ):
        return EvidenceMatchResult(
            status=INSUFFICIENT_IDENTITY_DATA,
            member_id=None,
            match_method=None,
            identity_corroborator=None,
            temporal_delta_days=None,
            assignment_type=None,
            reason="Evidence has neither external ID nor normalized email.",
        )
    return id_result
