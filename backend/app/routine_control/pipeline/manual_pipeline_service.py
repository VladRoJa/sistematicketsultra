from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.routine_control.domain.commands import (
    ReconcileRoutineMemberCommand,
)
from app.routine_control.domain.exceptions import (
    RoutineControlEvidenceError,
    RoutineControlMemberError,
)
from app.routine_control.pipeline.branch_resolver import (
    resolve_gasca_branch_id,
    resolve_trainingym_center_id,
)
from app.routine_control.pipeline.incident_repository import (
    RoutineControlIncidentRepository,
)
from app.routine_control.pipeline.matching_repository import (
    RoutineControlMatchingRepository,
)
from app.routine_control.pipeline.run_repository import (
    GASCA_DATASET_KEY,
    GASCA_PROVIDER_KEY,
    TRAININGYM_DATASET_KEY,
    TRAININGYM_PROVIDER_KEY,
    RoutineControlRunRepository,
    build_manual_pipeline_idempotency_key,
)
from app.routine_control.providers.gasca_member_normalizer import (
    GascaNormalizationError,
    load_gasca_member_commands_from_xlsx,
)
from app.routine_control.providers.trainingym_evidence_normalizer import (
    TrainingymNormalizationError,
    load_trainingym_evidence_commands_from_xlsx,
)
from app.routine_control.repositories.evidence_repository import (
    RoutineAssignmentEvidenceRepository,
)
from app.routine_control.repositories.member_repository import (
    RoutineControlMemberRepository,
)
from app.routine_control.repositories.reconciliation_repository import (
    RoutineControlReconciliationRepository,
)
from app.routine_control.services.evidence_ingestion_service import (
    register_routine_evidence,
)
from app.routine_control.services.evidence_rematching_service import (
    rematch_routine_evidences,
)
from app.routine_control.services.member_ingestion_service import (
    upsert_routine_member,
)
from app.routine_control.services.reconciliation_service import (
    reconcile_routine_member,
)


LOGGER = logging.getLogger(__name__)
_REQUESTED_BY_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")
_SAFE_EXCEPTION_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,119}$")
_UNEXPECTED_ERROR_CODE = "ROUTINE_CONTROL_PIPELINE_UNEXPECTED_ERROR"
_UNEXPECTED_PUBLIC_MESSAGE = (
    "El pipeline terminó por un error interno inesperado."
)
_STATUS_KEYS = (
    "CLASSIFIED/SIN_RUTINA",
    "CLASSIFIED/CON_RUTINA",
    "CLASSIFIED/NO_DESEA_RUTINA",
    "INCIDENT/NULL",
)


class ManualRoutineControlPipelineError(RuntimeError):
    """Error de validación o concurrencia del pipeline manual."""


@dataclass(frozen=True, slots=True)
class ManualRoutineControlPipelineResult:
    pipeline_run_id: int
    reused_existing_run: bool
    gasca_provider_run_id: int
    trainingym_provider_run_id: int
    gasca_source_rows: int
    gasca_accepted: int
    gasca_rejected: int
    members_created: int
    members_updated: int
    trainingym_source_rows: int
    trainingym_accepted: int
    trainingym_rejected: int
    evidences_created: int
    evidences_updated: int
    links_created: int
    links_existing: int
    links_by_external_id: int
    links_by_email: int
    unmatched_evidences: int
    ambiguous_evidences: int
    incidents_created: int
    incidents_resolved: int
    members_reconciled: int
    status_counts: Mapping[str, int]
    succeeded: bool
    insufficient_identity_evidences: int = 0
    reactivation_required_evidences: int = 0
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        values = {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
            if field_name != "status_counts"
        }
        values["status_counts"] = dict(self.status_counts)
        return values


@dataclass(frozen=True, slots=True)
class _MatchingCounterSnapshot:
    links_created: int
    links_existing: int
    links_by_external_id: int
    links_by_email: int
    unmatched_evidences: int
    ambiguous_evidences: int
    insufficient_identity_evidences: int
    reactivation_required_evidences: int
    considered_member_ids: frozenset[int]


@dataclass(frozen=True, slots=True)
class _UnexpectedErrorDetails:
    error_code: str
    exception_type: str
    public_message: str


def _unexpected_error_details(exc: BaseException) -> _UnexpectedErrorDetails:
    exception_type = type(exc).__name__
    if _SAFE_EXCEPTION_TYPE.fullmatch(exception_type) is None:
        exception_type = "Exception"
    return _UnexpectedErrorDetails(
        error_code=_UNEXPECTED_ERROR_CODE,
        exception_type=exception_type,
        public_message=_UNEXPECTED_PUBLIC_MESSAGE,
    )


def _status_mapping(values: Mapping[str, int] | None = None):
    source = values or {}
    return MappingProxyType({key: int(source.get(key, 0)) for key in _STATUS_KEYS})


def _aware_utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ManualRoutineControlPipelineError(
            "observed_at_utc debe incluir timezone."
        )
    return value.astimezone(timezone.utc)


def _resolve_pipeline_date_range(
    *,
    observed_at_utc: datetime,
    date_from: date | None,
    date_to: date | None,
) -> tuple[date, date]:
    if (date_from is None) != (date_to is None):
        raise ManualRoutineControlPipelineError(
            "date_from y date_to deben proporcionarse juntos."
        )

    if date_from is None:
        observed_date = observed_at_utc.date()
        return observed_date, observed_date

    if type(date_from) is not date or type(date_to) is not date:
        raise ManualRoutineControlPipelineError(
            "date_from y date_to deben ser fechas."
        )

    if date_from > date_to:
        raise ManualRoutineControlPipelineError(
            "date_from no puede ser posterior a date_to."
        )

    return date_from, date_to


def _source_path(value: str | Path, *, field_name: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise ManualRoutineControlPipelineError(
            f"{field_name} no existe o no es un archivo."
        )
    return path


def _content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sanitize_requested_by(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = _REQUESTED_BY_UNSAFE.sub(
        "_",
        str(value).strip(),
    )[:80]

    return normalized or None


_ALLOWED_GENERATION_MODES = frozenset(
    {
        "SCHEDULED",
        "MANUAL",
        "BACKFILL",
        "RETRY",
    }
)


def _normalize_generation_mode(value: str) -> str:
    normalized = str(value or "").strip().upper()

    if normalized not in _ALLOWED_GENERATION_MODES:
        raise ManualRoutineControlPipelineError(
            "generation_mode inválido."
        )

    return normalized


def _normalize_trigger_source(value: str) -> str:
    normalized = _sanitize_requested_by(value)

    if normalized is None:
        raise ManualRoutineControlPipelineError(
            "trigger_source es obligatorio."
        )

    return normalized.upper()


def _set_stage(run, session: Any, stage: str, at_utc: datetime) -> None:
    run.current_stage = stage
    run.heartbeat_at_utc = at_utc
    session.commit()


def _empty_result(
    *,
    pipeline_run_id: int,
    reused: bool,
    gasca_provider_run_id: int,
    trainingym_provider_run_id: int,
) -> ManualRoutineControlPipelineResult:
    return ManualRoutineControlPipelineResult(
        pipeline_run_id=pipeline_run_id,
        reused_existing_run=reused,
        gasca_provider_run_id=gasca_provider_run_id,
        trainingym_provider_run_id=trainingym_provider_run_id,
        gasca_source_rows=0,
        gasca_accepted=0,
        gasca_rejected=0,
        members_created=0,
        members_updated=0,
        trainingym_source_rows=0,
        trainingym_accepted=0,
        trainingym_rejected=0,
        evidences_created=0,
        evidences_updated=0,
        links_created=0,
        links_existing=0,
        links_by_external_id=0,
        links_by_email=0,
        unmatched_evidences=0,
        ambiguous_evidences=0,
        incidents_created=0,
        incidents_resolved=0,
        members_reconciled=0,
        status_counts=_status_mapping(),
        succeeded=False,
    )


def _sync_incident(
    repository: RoutineControlIncidentRepository,
    *,
    member_id: int,
    incident_type: str,
    active: bool,
    observed_at_utc: datetime,
) -> tuple[bool, bool]:
    try:
        outcome = repository.synchronize(
            member_id=member_id,
            incident_type=incident_type,
            should_be_active=active,
            observed_at_utc=observed_at_utc,
        )
        repository.session.commit()
        return outcome
    except Exception:
        repository.session.rollback()
        raise


def _status_key(classification_status: str, current_status: str | None) -> str:
    return f"{classification_status}/{current_status or 'NULL'}"


def _dry_run_matching_counters(
    *,
    evidences: list[Any],
    provider_run_id: int,
    observed_at_utc: datetime,
    matching: RoutineControlMatchingRepository,
    session: Any,
) -> _MatchingCounterSnapshot:
    evidence_ids = [int(evidence.id) for evidence in evidences]
    if evidence_ids:
        rematching = rematch_routine_evidences(
            evidence_ids,
            provider_run_id,
            observed_at_utc,
            dry_run=True,
            session=session,
        )
        items = rematching.items
    else:
        items = ()

    active_links = matching.find_active_links_by_evidence_ids(evidence_ids)
    active_links_by_id = {int(link.id): link for link in active_links}
    links_created = 0
    links_existing = 0
    links_by_external_id = 0
    links_by_email = 0
    unmatched_evidences = 0
    ambiguous_evidences = 0
    insufficient_identity_evidences = 0
    reactivation_required_evidences = 0
    considered_member_ids: set[int] = set()

    for item in items:
        considered_member_ids.update(item.selection.considered_member_ids)
        considered_member_ids.update(
            action.member_id
            for action in item.actions
            if action.member_id is not None
        )

        if item.selection.status == "AMBIGUOUS":
            ambiguous_evidences += 1
        elif item.selection.status == "INSUFFICIENT_IDENTITY_DATA":
            insufficient_identity_evidences += 1
        elif item.selection.status != "MATCHED":
            unmatched_evidences += 1

        if any(
            action.action == "reactivation required"
            for action in item.actions
        ):
            reactivation_required_evidences += 1

        kept_actions = [
            action
            for action in item.actions
            if action.action == "keep" and action.link_id is not None
        ]
        for action in kept_actions:
            link = active_links_by_id.get(int(action.link_id))
            if link is None:
                continue
            if link.linked_by_provider_run_id == provider_run_id:
                links_created += 1
            else:
                links_existing += 1
            links_by_external_id += int(
                action.match_method == "EXTERNAL_ID"
            )
            links_by_email += int(action.match_method == "EMAIL")

    return _MatchingCounterSnapshot(
        links_created=links_created,
        links_existing=links_existing,
        links_by_external_id=links_by_external_id,
        links_by_email=links_by_email,
        unmatched_evidences=unmatched_evidences,
        ambiguous_evidences=ambiguous_evidences,
        insufficient_identity_evidences=insufficient_identity_evidences,
        reactivation_required_evidences=reactivation_required_evidences,
        considered_member_ids=frozenset(considered_member_ids),
    )


def _reused_success_result(
    *,
    base: ManualRoutineControlPipelineResult,
    pipeline_run: Any,
    gasca_provider_run: Any,
    trainingym_provider_run: Any,
    gasca_path: Path,
    trainingym_path: Path,
    observed_at_utc: datetime,
    session: Any,
    gasca_resolver: Callable[[str], int | None],
    center_resolver: Callable[[str], int | None],
) -> ManualRoutineControlPipelineResult:
    matching = RoutineControlMatchingRepository(session)
    gasca_batch = load_gasca_member_commands_from_xlsx(
        gasca_path,
        observed_at_utc=observed_at_utc,
        branch_resolver=gasca_resolver,
        require_resolved_branch=False,
    )
    trainingym_batch = load_trainingym_evidence_commands_from_xlsx(
        trainingym_path,
        observed_at_utc=observed_at_utc,
        provider_run_id=int(trainingym_provider_run.id),
        center_resolver=center_resolver,
    )
    member_ids = {
        int(member.id)
        for command in gasca_batch.commands
        if (
            member := matching.find_member_by_source_record(
                source_system=command.source_system,
                source_record_id=command.source_record_id,
            )
        )
        is not None
    }
    evidences = matching.find_evidences_by_identities(
        command.evidence_identity_key for command in trainingym_batch.commands
    )
    matching_counters = _dry_run_matching_counters(
        evidences=evidences,
        provider_run_id=int(trainingym_provider_run.id),
        observed_at_utc=observed_at_utc,
        matching=matching,
        session=session,
    )
    member_ids.update(matching_counters.considered_member_ids)
    member_ids.update(
        int(member.id)
        for member in matching.find_gasca_members_by_emails(
            command.email_normalized
            for command in gasca_batch.commands
            if command.email_normalized
        )
    )
    statuses = Counter()
    for member in matching.find_members_by_ids(member_ids):
        statuses[_status_key(member.classification_status, member.current_status)] += 1

    return replace(
        base,
        gasca_source_rows=int(gasca_provider_run.records_received),
        gasca_accepted=int(gasca_provider_run.records_valid),
        gasca_rejected=int(gasca_provider_run.records_rejected),
        members_created=int(pipeline_run.members_created),
        members_updated=int(pipeline_run.members_updated),
        trainingym_source_rows=int(trainingym_provider_run.records_received),
        trainingym_accepted=int(trainingym_provider_run.records_valid),
        trainingym_rejected=int(trainingym_provider_run.records_rejected),
        evidences_created=int(pipeline_run.evidences_created),
        evidences_updated=int(pipeline_run.evidences_updated),
        links_created=matching_counters.links_created,
        links_existing=matching_counters.links_existing,
        links_by_external_id=matching_counters.links_by_external_id,
        links_by_email=matching_counters.links_by_email,
        unmatched_evidences=matching_counters.unmatched_evidences,
        ambiguous_evidences=matching_counters.ambiguous_evidences,
        insufficient_identity_evidences=(
            matching_counters.insufficient_identity_evidences
        ),
        reactivation_required_evidences=(
            matching_counters.reactivation_required_evidences
        ),
        incidents_created=int(pipeline_run.incidents_created),
        members_reconciled=len(member_ids),
        status_counts=_status_mapping(statuses),
        succeeded=True,
    )


def run_manual_routine_control_pipeline(
    *,
    gasca_xlsx: str | Path,
    trainingym_xlsx: str | Path,
    observed_at_utc: datetime,
    date_from: date | None = None,
    date_to: date | None = None,
    requested_by: str | None = None,
    generation_mode: str = "MANUAL",
    trigger_source: str = "MANUAL_CLI",
    session: Any | None = None,
    gasca_branch_resolver: Callable[[str], int | None] | None = None,
    trainingym_center_resolver: Callable[[str], int | None] | None = None,
) -> ManualRoutineControlPipelineResult:
    observed_at = _aware_utc(observed_at_utc)
    effective_date_from, effective_date_to = _resolve_pipeline_date_range(
        observed_at_utc=observed_at,
        date_from=date_from,
        date_to=date_to,
    )
    gasca_path = _source_path(gasca_xlsx, field_name="gasca_xlsx")
    trainingym_path = _source_path(
        trainingym_xlsx,
        field_name="trainingym_xlsx",
    )
    _sanitize_requested_by(requested_by)
    effective_generation_mode = _normalize_generation_mode(
        generation_mode
    )
    effective_trigger_source = _normalize_trigger_source(
        trigger_source
    )
    pipeline_session = session or db.session
    gasca_hash = _content_hash(gasca_path)
    trainingym_hash = _content_hash(trainingym_path)
    idempotency_key = build_manual_pipeline_idempotency_key(
        gasca_content_hash=gasca_hash,
        trainingym_content_hash=trainingym_hash,
        date_from=effective_date_from,
        date_to=effective_date_to,
        generation_mode=effective_generation_mode,
        trigger_source=effective_trigger_source,
    )
    runs = RoutineControlRunRepository(pipeline_session)
    runs.acquire_pipeline_lock(idempotency_key=idempotency_key)
    pipeline_run = runs.find_pipeline_run(idempotency_key=idempotency_key)
    reused = pipeline_run is not None
    if pipeline_run is None:
        pipeline_run = runs.create_pipeline_run(
            idempotency_key=idempotency_key,
            business_date=effective_date_to,
            date_from=effective_date_from,
            date_to=effective_date_to,
            generation_mode=effective_generation_mode,
            trigger_source=effective_trigger_source,
        )
    gasca_provider_run = runs.ensure_provider_run(
        pipeline_run=pipeline_run,
        provider_key=GASCA_PROVIDER_KEY,
        dataset_key=GASCA_DATASET_KEY,
        content_hash=gasca_hash,
    )
    trainingym_provider_run = runs.ensure_provider_run(
        pipeline_run=pipeline_run,
        provider_key=TRAININGYM_PROVIDER_KEY,
        dataset_key=TRAININGYM_DATASET_KEY,
        content_hash=trainingym_hash,
    )
    base = _empty_result(
        pipeline_run_id=int(pipeline_run.id),
        reused=reused,
        gasca_provider_run_id=int(gasca_provider_run.id),
        trainingym_provider_run_id=int(trainingym_provider_run.id),
    )
    gasca_resolver = gasca_branch_resolver or (
        lambda branch: resolve_gasca_branch_id(branch, session=pipeline_session)
    )
    center_resolver = trainingym_center_resolver or (
        lambda center: resolve_trainingym_center_id(
            center,
            session=pipeline_session,
        )
    )
    if reused and pipeline_run.status == "SUCCESS":
        try:
            with pipeline_session.no_autoflush:
                reused_result = _reused_success_result(
                    base=base,
                    pipeline_run=pipeline_run,
                    gasca_provider_run=gasca_provider_run,
                    trainingym_provider_run=trainingym_provider_run,
                    gasca_path=gasca_path,
                    trainingym_path=trainingym_path,
                    observed_at_utc=observed_at,
                    session=pipeline_session,
                    gasca_resolver=gasca_resolver,
                    center_resolver=center_resolver,
                )
        finally:
            pipeline_session.rollback()
        return reused_result
    if reused and pipeline_run.status == "RUNNING":
        pipeline_session.rollback()
        raise ManualRoutineControlPipelineError(
            "Ya existe una corrida RUNNING para estos archivos."
        )
    pipeline_session.flush()
    runs.start_pipeline(
        pipeline_run,
        at_utc=datetime.now(timezone.utc),
        reused=reused,
    )
    pipeline_session.commit()

    result = base
    processed_member_ids: set[int] = set()
    reconciliation_ids: set[int] = set()
    valid_evidence_ids: list[int] = []
    incidents_created = 0
    incidents_resolved = 0
    row_errors = 0
    trainingym_row_errors = 0
    members_created = 0
    members_updated = 0
    evidences_created = 0
    evidences_updated = 0
    status_changes = 0
    total_records_rejected = 0
    active_provider_run = None

    member_repository = RoutineControlMemberRepository(pipeline_session)
    evidence_repository = RoutineAssignmentEvidenceRepository(pipeline_session)
    reconciliation_repository = RoutineControlReconciliationRepository(
        pipeline_session
    )
    incident_repository = RoutineControlIncidentRepository(pipeline_session)
    matching = RoutineControlMatchingRepository(pipeline_session)

    try:
        _set_stage(
            pipeline_run,
            pipeline_session,
            "GASCA",
            datetime.now(timezone.utc),
        )
        active_provider_run = gasca_provider_run
        runs.start_provider(
            gasca_provider_run,
            at_utc=datetime.now(timezone.utc),
        )
        pipeline_session.commit()
        gasca_batch = load_gasca_member_commands_from_xlsx(
            gasca_path,
            observed_at_utc=observed_at,
            branch_resolver=gasca_resolver,
            require_resolved_branch=False,
        )
        persisted_members = 0
        affected_emails: set[str] = set()
        for command in gasca_batch.commands:
            previous = matching.find_member_by_source_record(
                source_system=command.source_system,
                source_record_id=command.source_record_id,
            )
            if previous is not None and previous.email_normalized:
                affected_emails.add(previous.email_normalized)
            try:
                member_result = upsert_routine_member(
                    command,
                    repository=member_repository,
                )
            except (RoutineControlMemberError, IntegrityError) as exc:
                row_errors += 1
                LOGGER.warning(
                    "Gasca row rejected during persistence: %s",
                    type(exc).__name__,
                )
                continue
            persisted_members += 1
            members_created += int(member_result.created)
            members_updated += int(
                not member_result.created and member_result.source_changed
            )
            member_id = member_result.member_id
            processed_member_ids.add(member_id)
            reconciliation_ids.add(member_id)
            if command.email_normalized:
                affected_emails.add(command.email_normalized)
            for incident_type, active in (
                ("EMAIL_VACIO", command.email_normalized is None),
                ("SUCURSAL_NO_RESUELTA", command.sucursal_id is None),
            ):
                created, resolved = _sync_incident(
                    incident_repository,
                    member_id=member_id,
                    incident_type=incident_type,
                    active=active,
                    observed_at_utc=observed_at,
                )
                incidents_created += int(created)
                incidents_resolved += int(resolved)

        candidates = matching.find_gasca_members_by_emails(affected_emails)
        candidates_by_email: dict[str, list[Any]] = defaultdict(list)
        for member in candidates:
            candidates_by_email[member.email_normalized].append(member)
        duplicate_synced_ids: set[int] = set()
        for email_members in candidates_by_email.values():
            duplicated = len(
                {member.external_member_id for member in email_members}
            ) > 1
            for member in email_members:
                member_id = int(member.id)
                duplicate_synced_ids.add(member_id)
                reconciliation_ids.add(member_id)
                created, resolved = _sync_incident(
                    incident_repository,
                    member_id=member_id,
                    incident_type="EMAIL_DUPLICADO_GASCA",
                    active=duplicated,
                    observed_at_utc=observed_at,
                )
                incidents_created += int(created)
                incidents_resolved += int(resolved)
        for member_id in processed_member_ids - duplicate_synced_ids:
            created, resolved = _sync_incident(
                incident_repository,
                member_id=member_id,
                incident_type="EMAIL_DUPLICADO_GASCA",
                active=False,
                observed_at_utc=observed_at,
            )
            incidents_created += int(created)
            incidents_resolved += int(resolved)

        runs.finish_provider_success(
            gasca_provider_run,
            at_utc=datetime.now(timezone.utc),
            records_received=gasca_batch.total_source_rows,
            records_valid=persisted_members,
            records_rejected=len(gasca_batch.rejected_rows) + row_errors,
            records_excluded=len(gasca_batch.rejected_rows),
            records_created=members_created,
            records_updated=members_updated,
        )
        total_records_rejected += len(gasca_batch.rejected_rows) + row_errors
        pipeline_session.commit()
        result = replace(
            result,
            gasca_source_rows=gasca_batch.total_source_rows,
            gasca_accepted=len(gasca_batch.commands),
            gasca_rejected=len(gasca_batch.rejected_rows) + row_errors,
            members_created=members_created,
            members_updated=members_updated,
            incidents_created=incidents_created,
            incidents_resolved=incidents_resolved,
        )

        _set_stage(
            pipeline_run,
            pipeline_session,
            "TRAININGYM",
            datetime.now(timezone.utc),
        )
        active_provider_run = trainingym_provider_run
        runs.start_provider(
            trainingym_provider_run,
            at_utc=datetime.now(timezone.utc),
        )
        pipeline_session.commit()
        trainingym_batch = load_trainingym_evidence_commands_from_xlsx(
            trainingym_path,
            observed_at_utc=observed_at,
            provider_run_id=int(trainingym_provider_run.id),
            center_resolver=center_resolver,
        )
        persisted_evidences = 0
        for command in trainingym_batch.commands:
            try:
                evidence_result = register_routine_evidence(
                    command,
                    repository=evidence_repository,
                )
            except (RoutineControlEvidenceError, IntegrityError) as exc:
                trainingym_row_errors += 1
                LOGGER.warning(
                    "Trainingym row rejected during persistence: %s",
                    type(exc).__name__,
                )
                continue
            persisted_evidences += 1
            evidences_created += int(evidence_result.created)
            evidences_updated += int(
                not evidence_result.created and evidence_result.source_changed
            )
            if evidence_result.is_valid:
                valid_evidence_ids.append(evidence_result.evidence_id)

        runs.finish_provider_success(
            trainingym_provider_run,
            at_utc=datetime.now(timezone.utc),
            records_received=trainingym_batch.total_source_rows,
            records_valid=persisted_evidences,
            records_rejected=(
                len(trainingym_batch.rejected_rows) + trainingym_row_errors
            ),
            records_excluded=len(trainingym_batch.rejected_rows),
            records_created=evidences_created,
            records_updated=evidences_updated,
        )
        total_records_rejected += (
            len(trainingym_batch.rejected_rows) + trainingym_row_errors
        )
        pipeline_session.commit()
        result = replace(
            result,
            trainingym_source_rows=trainingym_batch.total_source_rows,
            trainingym_accepted=len(trainingym_batch.commands),
            trainingym_rejected=(
                len(trainingym_batch.rejected_rows) + trainingym_row_errors
            ),
            evidences_created=evidences_created,
            evidences_updated=evidences_updated,
        )

        active_provider_run = None
        _set_stage(
            pipeline_run,
            pipeline_session,
            "MATCHING",
            datetime.now(timezone.utc),
        )
        links_created = 0
        links_existing = 0
        links_by_external_id = 0
        links_by_email = 0
        unmatched_evidences = 0
        ambiguous_evidences = 0
        insufficient_identity_evidences = 0
        reactivation_required_evidences = 0
        rematching = rematch_routine_evidences(
            valid_evidence_ids,
            int(trainingym_provider_run.id),
            observed_at,
            dry_run=False,
            session=pipeline_session,
        )
        reconciliation_ids.update(rematching.affected_member_ids)
        for item in rematching.items:
            actions = item.actions
            linked_actions = [
                action
                for action in actions
                if action.action in ("link", "keep")
            ]
            links_created += sum(
                action.action == "link" for action in linked_actions
            )
            links_existing += sum(
                action.action == "keep" for action in linked_actions
            )
            links_by_external_id += sum(
                action.match_method == "EXTERNAL_ID"
                for action in linked_actions
            )
            links_by_email += sum(
                action.match_method == "EMAIL" for action in linked_actions
            )

            if item.selection.status == "AMBIGUOUS":
                ambiguous_evidences += 1
            elif item.selection.status == "INSUFFICIENT_IDENTITY_DATA":
                insufficient_identity_evidences += 1
            elif item.selection.status != "MATCHED":
                unmatched_evidences += 1
            if any(
                action.action == "reactivation required"
                for action in actions
            ):
                reactivation_required_evidences += 1

            incident_member_ids = set(
                item.selection.considered_member_ids
            )
            incident_member_ids.update(
                action.member_id
                for action in actions
                if action.member_id is not None
            )
            ambiguous_member_ids = set(
                item.selection.ambiguous_member_ids
            )
            for member_id in sorted(incident_member_ids):
                reconciliation_ids.add(member_id)
                created, resolved = _sync_incident(
                    incident_repository,
                    member_id=member_id,
                    incident_type="COINCIDENCIA_AMBIGUA",
                    active=member_id in ambiguous_member_ids,
                    observed_at_utc=observed_at,
                )
                incidents_created += int(created)
                incidents_resolved += int(resolved)

        _set_stage(
            pipeline_run,
            pipeline_session,
            "RECONCILIATION",
            datetime.now(timezone.utc),
        )
        statuses = Counter()
        for member_id in sorted(reconciliation_ids):
            reconciliation = reconcile_routine_member(
                ReconcileRoutineMemberCommand(
                    member_id=member_id,
                    as_of_utc=observed_at,
                ),
                repository=reconciliation_repository,
            )
            status_changes += int(reconciliation.changed)
            statuses[
                _status_key(
                    reconciliation.classification_status,
                    reconciliation.current_status,
                )
            ] += 1

        result = replace(
            result,
            links_created=links_created,
            links_existing=links_existing,
            links_by_external_id=links_by_external_id,
            links_by_email=links_by_email,
            unmatched_evidences=unmatched_evidences,
            ambiguous_evidences=ambiguous_evidences,
            insufficient_identity_evidences=(
                insufficient_identity_evidences
            ),
            reactivation_required_evidences=(
                reactivation_required_evidences
            ),
            incidents_created=incidents_created,
            incidents_resolved=incidents_resolved,
            members_reconciled=len(reconciliation_ids),
            status_counts=_status_mapping(statuses),
        )
        runs.finish_pipeline_success(
            pipeline_run,
            at_utc=datetime.now(timezone.utc),
            members_created=result.members_created,
            members_updated=result.members_updated,
            evidences_created=result.evidences_created,
            evidences_updated=result.evidences_updated,
            status_changes=status_changes,
            incidents_created=incidents_created,
            records_rejected=result.gasca_rejected + result.trainingym_rejected,
        )
        pipeline_session.commit()
        return replace(result, succeeded=True)

    except Exception as exc:
        structural_error = isinstance(
            exc,
            (GascaNormalizationError, TrainingymNormalizationError),
        )
        unexpected_error = _unexpected_error_details(exc)
        failure_error_code = (
            type(exc).__name__
            if structural_error
            else unexpected_error.error_code
        )
        failure_error_message = (
            type(exc).__name__
            if structural_error
            else unexpected_error.public_message
        )
        failure_pipeline_run_id = int(pipeline_run.id)
        failure_stage = pipeline_run.current_stage or "UNKNOWN"
        failure_provider = (
            active_provider_run.provider_key
            if active_provider_run is not None
            else "NONE"
        )
        pipeline_session.rollback()
        try:
            if active_provider_run is not None:
                runs.finish_provider_failed(
                    active_provider_run,
                    at_utc=datetime.now(timezone.utc),
                    error_code=failure_error_code,
                    error_message=failure_error_message,
                )
            pipeline_run.members_created = members_created
            pipeline_run.members_updated = members_updated
            pipeline_run.evidences_created = evidences_created
            pipeline_run.evidences_updated = evidences_updated
            pipeline_run.status_changes = status_changes
            pipeline_run.incidents_created = incidents_created
            pipeline_run.records_rejected = total_records_rejected
            runs.finish_pipeline_failed(
                pipeline_run,
                at_utc=datetime.now(timezone.utc),
                error_code=failure_error_code,
                error_message=failure_error_message,
            )
            pipeline_session.commit()
        except Exception:
            pipeline_session.rollback()
        if structural_error:
            LOGGER.error("Structural XLSX failure: %s", type(exc).__name__)
        else:
            LOGGER.error(
                "Routine Control pipeline failed unexpectedly. "
                "error_code=%s exception_type=%s pipeline_run_id=%s "
                "stage=%s provider=%s generation_mode=%s "
                "date_from=%s date_to=%s",
                unexpected_error.error_code,
                unexpected_error.exception_type,
                failure_pipeline_run_id,
                failure_stage,
                failure_provider,
                effective_generation_mode,
                effective_date_from.isoformat(),
                effective_date_to.isoformat(),
            )
        return replace(
            result,
            incidents_created=incidents_created,
            incidents_resolved=incidents_resolved,
            succeeded=False,
            error_code=(
                None if structural_error else unexpected_error.error_code
            ),
            error_message=(
                None if structural_error else unexpected_error.public_message
            ),
        )
