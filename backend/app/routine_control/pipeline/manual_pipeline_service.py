from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.routine_control.domain.commands import (
    LinkRoutineMemberEvidenceCommand,
    ReconcileRoutineMemberCommand,
)
from app.routine_control.domain.exceptions import (
    RoutineControlEvidenceError,
    RoutineControlMemberError,
    RoutineControlMemberEvidenceError,
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
from app.routine_control.repositories.member_evidence_repository import (
    RoutineControlMemberEvidenceRepository,
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
from app.routine_control.services.member_evidence_service import (
    link_routine_member_evidence,
)
from app.routine_control.services.member_ingestion_service import (
    upsert_routine_member,
)
from app.routine_control.services.reconciliation_service import (
    reconcile_routine_member,
)


LOGGER = logging.getLogger(__name__)
_REQUESTED_BY_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")
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

    def to_dict(self) -> dict[str, object]:
        values = {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
            if field_name != "status_counts"
        }
        values["status_counts"] = dict(self.status_counts)
        return values


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
    normalized = _REQUESTED_BY_UNSAFE.sub("_", str(value).strip())[:80]
    return normalized or None


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
    links = matching.find_active_links_by_evidence_ids(
        int(evidence.id) for evidence in evidences
    )
    member_ids.update(int(link.member_id) for link in links)
    statuses = Counter()
    for member in matching.find_members_by_ids(member_ids):
        statuses[_status_key(member.classification_status, member.current_status)] += 1

    linked_evidence_ids = {int(link.evidence_id) for link in links}
    ambiguous = 0
    unmatched = 0
    for evidence in evidences:
        if int(evidence.id) in linked_evidence_ids:
            continue
        candidates = (
            matching.find_members_by_email(evidence.email_normalized)
            if evidence.email_normalized
            else []
        )
        if len({candidate.external_member_id for candidate in candidates}) > 1:
            ambiguous += 1
        else:
            unmatched += 1

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
        links_existing=len(links),
        links_by_external_id=sum(link.match_method == "EXTERNAL_ID" for link in links),
        links_by_email=sum(link.match_method == "EMAIL" for link in links),
        unmatched_evidences=unmatched,
        ambiguous_evidences=ambiguous,
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
    requested_by: str | None = None,
    session: Any | None = None,
    gasca_branch_resolver: Callable[[str], int | None] | None = None,
    trainingym_center_resolver: Callable[[str], int | None] | None = None,
) -> ManualRoutineControlPipelineResult:
    observed_at = _aware_utc(observed_at_utc)
    gasca_path = _source_path(gasca_xlsx, field_name="gasca_xlsx")
    trainingym_path = _source_path(
        trainingym_xlsx,
        field_name="trainingym_xlsx",
    )
    _sanitize_requested_by(requested_by)
    pipeline_session = session or db.session
    gasca_hash = _content_hash(gasca_path)
    trainingym_hash = _content_hash(trainingym_path)
    idempotency_key = build_manual_pipeline_idempotency_key(
        gasca_content_hash=gasca_hash,
        trainingym_content_hash=trainingym_hash,
    )
    runs = RoutineControlRunRepository(pipeline_session)
    runs.acquire_pipeline_lock(idempotency_key=idempotency_key)
    pipeline_run = runs.find_pipeline_run(idempotency_key=idempotency_key)
    reused = pipeline_run is not None
    if pipeline_run is None:
        pipeline_run = runs.create_pipeline_run(
            idempotency_key=idempotency_key,
            business_date=observed_at.date(),
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
    pipeline_session.flush()
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
        pipeline_session.commit()
        return _reused_success_result(
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
    if reused and pipeline_run.status == "RUNNING":
        pipeline_session.rollback()
        raise ManualRoutineControlPipelineError(
            "Ya existe una corrida RUNNING para estos archivos."
        )
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
    link_repository = RoutineControlMemberEvidenceRepository(pipeline_session)
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
        for evidence_id in valid_evidence_ids:
            evidence = matching.find_evidence(evidence_id)
            if evidence is None:
                raise ManualRoutineControlPipelineError(
                    "La evidencia registrada no pudo releerse."
                )
            candidates = (
                matching.find_members_by_external_id(
                    evidence.external_member_id
                )
                if evidence.external_member_id
                else []
            )
            match_method = "EXTERNAL_ID"
            if not candidates:
                match_method = "EMAIL"
                candidates = (
                    matching.find_members_by_email(evidence.email_normalized)
                    if evidence.email_normalized
                    else []
                )
                external_ids = {
                    member.external_member_id for member in candidates
                }
                if len(external_ids) > 1:
                    ambiguous_evidences += 1
                    for member in candidates:
                        member_id = int(member.id)
                        reconciliation_ids.add(member_id)
                        created, resolved = _sync_incident(
                            incident_repository,
                            member_id=member_id,
                            incident_type="COINCIDENCIA_AMBIGUA",
                            active=True,
                            observed_at_utc=observed_at,
                        )
                        incidents_created += int(created)
                        incidents_resolved += int(resolved)
                    continue
                if not candidates:
                    unmatched_evidences += 1
                    continue

            for member in candidates:
                member_id = int(member.id)
                reconciliation_ids.add(member_id)
                try:
                    link_result = link_routine_member_evidence(
                        LinkRoutineMemberEvidenceCommand(
                            member_id=member_id,
                            evidence_id=evidence_id,
                            match_method=match_method,
                            provider_run_id=int(trainingym_provider_run.id),
                            linked_at_utc=observed_at,
                        ),
                        repository=link_repository,
                    )
                except RoutineControlMemberEvidenceError as exc:
                    LOGGER.warning(
                        "Evidence link skipped: %s",
                        type(exc).__name__,
                    )
                    continue
                links_created += int(link_result.created)
                links_existing += int(not link_result.created)
                links_by_external_id += int(match_method == "EXTERNAL_ID")
                links_by_email += int(match_method == "EMAIL")
                created, resolved = _sync_incident(
                    incident_repository,
                    member_id=member_id,
                    incident_type="COINCIDENCIA_AMBIGUA",
                    active=False,
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
        pipeline_session.rollback()
        try:
            if active_provider_run is not None:
                runs.finish_provider_failed(
                    active_provider_run,
                    at_utc=datetime.now(timezone.utc),
                    error_code=type(exc).__name__,
                    error_message=type(exc).__name__,
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
                error_code=type(exc).__name__,
                error_message=type(exc).__name__,
            )
            pipeline_session.commit()
        except Exception:
            pipeline_session.rollback()
        if isinstance(exc, (GascaNormalizationError, TrainingymNormalizationError)):
            LOGGER.error("Structural XLSX failure: %s", type(exc).__name__)
        else:
            LOGGER.exception("Manual routine-control pipeline failed")
        return replace(
            result,
            incidents_created=incidents_created,
            incidents_resolved=incidents_resolved,
            succeeded=False,
        )
