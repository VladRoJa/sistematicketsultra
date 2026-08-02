from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.routine_control.domain.commands import (
    LinkRoutineMemberEvidenceCommand,
    ReconcileRoutineMemberCommand,
    UnlinkRoutineMemberEvidenceCommand,
)
from app.routine_control.domain.identity_normalization import (
    normalize_identity_name,
)
from app.routine_control.pipeline.matching_policy import (
    AMBIGUOUS,
    INSUFFICIENT_IDENTITY_DATA,
    MATCHED,
    MATCHING_CONTRACT_VERSION,
    EvidenceMatchInput,
    EvidenceMatchResult,
    MemberMatchCandidate,
    select_evidence_match,
)
from app.routine_control.pipeline.matching_repository import (
    RoutineControlMatchingRepository,
)
from app.routine_control.repositories.member_evidence_repository import (
    RoutineControlMemberEvidenceRepository,
)
from app.routine_control.repositories.reconciliation_repository import (
    RoutineControlReconciliationRepository,
)
from app.routine_control.services.member_evidence_service import (
    link_routine_member_evidence,
    unlink_routine_member_evidence,
)
from app.routine_control.services.reconciliation_service import (
    reconcile_routine_member,
)


REACTIVATION_REQUIRED = "REACTIVATION_REQUIRED"
_UNLINK_REASON = "IDENTITY_TEMPORAL_V2_REMATCH"


@dataclass(frozen=True, slots=True)
class RoutineEvidenceRematchAction:
    action: str
    evidence_id: int
    member_id: int | None
    link_id: int | None
    selection_status: str
    reason: str
    match_method: str | None = None
    identity_corroborator: str | None = None
    temporal_delta_days: int | None = None
    matching_contract_version: str | None = None


@dataclass(frozen=True, slots=True)
class RoutineEvidenceRematchItem:
    evidence_id: int
    selection: EvidenceMatchResult
    actions: tuple[RoutineEvidenceRematchAction, ...]


@dataclass(frozen=True, slots=True)
class RoutineEvidenceRematchResult:
    dry_run: bool
    items: tuple[RoutineEvidenceRematchItem, ...]
    affected_member_ids: tuple[int, ...]
    members_reconciled: int


def _aware_utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("observed_at_utc debe incluir timezone.")
    return value.astimezone(timezone.utc)


def _candidate(member: Any) -> MemberMatchCandidate:
    return MemberMatchCandidate(
        member_id=int(member.id),
        external_member_id=member.external_member_id,
        email_normalized=member.email_normalized,
        member_name_normalized=normalize_identity_name(member.member_name),
        sale_date=member.sale_date,
    )


def _selection(
    evidence: Any,
    matching: RoutineControlMatchingRepository,
) -> EvidenceMatchResult:
    evidence_input = EvidenceMatchInput(
        evidence_id=int(evidence.id),
        external_member_id=evidence.external_member_id,
        email_normalized=evidence.email_normalized,
        member_name_normalized=evidence.member_name_normalized,
        routine_activity_date=evidence.routine_activity_date,
    )
    external_candidates = (
        matching.find_members_by_external_id(evidence.external_member_id)
        if evidence.external_member_id
        else []
    )
    email_candidates = (
        matching.find_members_by_email(evidence.email_normalized)
        if evidence.email_normalized
        else []
    )
    return select_evidence_match(
        evidence_input,
        external_id_candidates=tuple(map(_candidate, external_candidates)),
        email_candidates=tuple(map(_candidate, email_candidates)),
    )


def _status_action(selection: EvidenceMatchResult) -> str:
    if selection.status == AMBIGUOUS:
        return "ambiguous"
    if selection.status == INSUFFICIENT_IDENTITY_DATA:
        return "insufficient identity"
    return "unmatched"


def _action(
    *,
    action: str,
    evidence_id: int,
    selection: EvidenceMatchResult,
    member_id: int | None = None,
    link_id: int | None = None,
    reason: str | None = None,
) -> RoutineEvidenceRematchAction:
    return RoutineEvidenceRematchAction(
        action=action,
        evidence_id=evidence_id,
        member_id=member_id,
        link_id=link_id,
        selection_status=selection.status,
        reason=reason or selection.reason,
        match_method=selection.match_method,
        identity_corroborator=selection.identity_corroborator,
        temporal_delta_days=selection.temporal_delta_days,
        matching_contract_version=(
            MATCHING_CONTRACT_VERSION if selection.status == MATCHED else None
        ),
    )


def _proposed_actions(
    *,
    evidence: Any,
    selection: EvidenceMatchResult,
    active_links: list[Any],
    link_repository: RoutineControlMemberEvidenceRepository,
) -> tuple[RoutineEvidenceRematchAction, ...]:
    evidence_id = int(evidence.id)
    actions: list[RoutineEvidenceRematchAction] = []
    active_by_member = {int(link.member_id): link for link in active_links}

    if selection.status == INSUFFICIENT_IDENTITY_DATA:
        return (_action(
            action="insufficient identity",
            evidence_id=evidence_id,
            selection=selection,
        ),)

    winner_id = selection.member_id if selection.status == MATCHED else None
    for member_id, link in active_by_member.items():
        if member_id == winner_id:
            continue
        actions.append(_action(
            action="unlink",
            evidence_id=evidence_id,
            member_id=member_id,
            link_id=int(link.id),
            selection=selection,
            reason=_UNLINK_REASON,
        ))

    if winner_id is None:
        actions.append(_action(
            action=_status_action(selection),
            evidence_id=evidence_id,
            selection=selection,
        ))
        return tuple(actions)

    active_winner = active_by_member.get(winner_id)
    if active_winner is not None:
        actions.append(_action(
            action="keep",
            evidence_id=evidence_id,
            member_id=winner_id,
            link_id=int(active_winner.id),
            selection=selection,
        ))
        return tuple(actions)

    existing_pair = link_repository.find_by_pair(
        member_id=winner_id,
        evidence_id=evidence_id,
    )
    if existing_pair is not None and not existing_pair.is_active:
        actions.append(_action(
            action="reactivation required",
            evidence_id=evidence_id,
            member_id=winner_id,
            link_id=int(existing_pair.id),
            selection=selection,
            reason=REACTIVATION_REQUIRED,
        ))
        return tuple(actions)

    actions.append(_action(
        action="link",
        evidence_id=evidence_id,
        member_id=winner_id,
        selection=selection,
    ))
    return tuple(actions)


def _apply_actions(
    actions: tuple[RoutineEvidenceRematchAction, ...],
    *,
    provider_run_id: int | None,
    observed_at_utc: datetime,
    link_repository: RoutineControlMemberEvidenceRepository,
) -> set[int]:
    affected: set[int] = set()
    for action in actions:
        if action.action != "unlink" or action.member_id is None:
            continue
        unlink_routine_member_evidence(
            UnlinkRoutineMemberEvidenceCommand(
                member_id=action.member_id,
                evidence_id=action.evidence_id,
                unlink_reason=action.reason,
                provider_run_id=provider_run_id,
                unlinked_at_utc=observed_at_utc,
            ),
            repository=link_repository,
            manage_transaction=False,
        )
        affected.add(action.member_id)

    for action in actions:
        if action.action not in ("link", "keep") or action.member_id is None:
            continue
        link_routine_member_evidence(
            LinkRoutineMemberEvidenceCommand(
                member_id=action.member_id,
                evidence_id=action.evidence_id,
                match_method=action.match_method or "EXTERNAL_ID",
                identity_corroborator=action.identity_corroborator,
                temporal_delta_days=action.temporal_delta_days,
                matching_contract_version=action.matching_contract_version,
                provider_run_id=provider_run_id,
                linked_at_utc=observed_at_utc,
            ),
            repository=link_repository,
            manage_transaction=False,
        )
        affected.add(action.member_id)
    return affected


def _apply_evidence_matching_decision(
    *,
    evidence: Any,
    provider_run_id: int | None,
    observed_at_utc: datetime,
    dry_run: bool,
    matching: RoutineControlMatchingRepository,
    link_repository: RoutineControlMemberEvidenceRepository,
    reconciliation_repository: RoutineControlReconciliationRepository,
) -> tuple[RoutineEvidenceRematchItem, set[int]]:
    session = link_repository.session
    evidence_id = int(evidence.id)

    if dry_run:
        selection = _selection(evidence, matching)
        actions = _proposed_actions(
            evidence=evidence,
            selection=selection,
            active_links=link_repository.find_active_by_evidence(
                evidence_id=evidence_id
            ),
            link_repository=link_repository,
        )
        return RoutineEvidenceRematchItem(
            evidence_id=evidence_id,
            selection=selection,
            actions=actions,
        ), set()

    try:
        link_repository.acquire_evidence_lock(evidence_id=evidence_id)
        selection = _selection(evidence, matching)
        actions = _proposed_actions(
            evidence=evidence,
            selection=selection,
            active_links=link_repository.find_active_by_evidence(
                evidence_id=evidence_id
            ),
            link_repository=link_repository,
        )
        affected_member_ids = _apply_actions(
            actions,
            provider_run_id=provider_run_id,
            observed_at_utc=observed_at_utc,
            link_repository=link_repository,
        )
        for member_id in sorted(affected_member_ids):
            reconcile_routine_member(
                ReconcileRoutineMemberCommand(
                    member_id=member_id,
                    as_of_utc=observed_at_utc,
                ),
                repository=reconciliation_repository,
                manage_transaction=False,
            )
        session.flush()
        item = RoutineEvidenceRematchItem(
            evidence_id=evidence_id,
            selection=selection,
            actions=actions,
        )
        session.commit()
        return item, affected_member_ids
    except Exception:
        session.rollback()
        raise


def rematch_routine_evidences(
    evidence_ids: list[int] | tuple[int, ...] | None,
    provider_run_id: int | None,
    observed_at_utc: datetime,
    dry_run: bool = True,
    *,
    session: Any | None = None,
) -> RoutineEvidenceRematchResult:
    observed_at = _aware_utc(observed_at_utc)
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run debe ser booleano.")
    ids = tuple(sorted(set(evidence_ids or ())))
    if not ids and provider_run_id is None:
        raise ValueError("Debe indicarse evidence_ids o provider_run_id.")
    if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in ids):
        raise ValueError("evidence_ids debe contener enteros positivos.")
    if provider_run_id is not None and (
        not isinstance(provider_run_id, int)
        or isinstance(provider_run_id, bool)
        or provider_run_id <= 0
    ):
        raise ValueError("provider_run_id debe ser un entero positivo.")

    active_session = session or db.session
    matching = RoutineControlMatchingRepository(active_session)
    link_repository = RoutineControlMemberEvidenceRepository(active_session)
    reconciliation_repository = RoutineControlReconciliationRepository(
        active_session
    )
    evidences = (
        matching.find_evidences_by_ids(ids)
        if ids
        else matching.find_evidences_by_provider_run(int(provider_run_id))
    )
    if ids and {int(evidence.id) for evidence in evidences} != set(ids):
        raise ValueError("No se encontraron todas las evidencias solicitadas.")

    items: list[RoutineEvidenceRematchItem] = []
    affected_member_ids: set[int] = set()
    for evidence in evidences:
        item, evidence_affected_member_ids = _apply_evidence_matching_decision(
            evidence=evidence,
            provider_run_id=provider_run_id,
            observed_at_utc=observed_at,
            dry_run=dry_run,
            matching=matching,
            link_repository=link_repository,
            reconciliation_repository=reconciliation_repository,
        )
        items.append(item)
        affected_member_ids.update(evidence_affected_member_ids)

    return RoutineEvidenceRematchResult(
        dry_run=dry_run,
        items=tuple(items),
        affected_member_ids=tuple(sorted(affected_member_ids)),
        members_reconciled=(0 if dry_run else len(affected_member_ids)),
    )
