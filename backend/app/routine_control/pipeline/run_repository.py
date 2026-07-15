from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from sqlalchemy import select, text

from app.models.routine_control import (
    RoutineControlPipelineRunORM,
    RoutineControlProviderRunORM,
)


GASCA_PROVIDER_KEY = "gasca"
GASCA_DATASET_KEY = "new_members"
TRAININGYM_PROVIDER_KEY = "trainingym"
TRAININGYM_DATASET_KEY = "routine_assignments"


def build_manual_pipeline_idempotency_key(
    *,
    gasca_content_hash: str,
    trainingym_content_hash: str,
) -> str:
    payload = (
        f"manual\x00{gasca_content_hash}\x00{trainingym_content_hash}"
    ).encode("ascii")
    return f"manual:{hashlib.sha256(payload).hexdigest()}"


def build_pipeline_advisory_lock_key(idempotency_key: str) -> int:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def sanitize_error_message(value: object, *, limit: int = 500) -> str:
    normalized = " ".join(str(value or "Pipeline failure").split())
    return normalized[:limit] or "Pipeline failure"


class RoutineControlRunRepository:
    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    def acquire_pipeline_lock(self, *, idempotency_key: str) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": build_pipeline_advisory_lock_key(idempotency_key)},
        )

    def find_pipeline_run(
        self,
        *,
        idempotency_key: str,
    ) -> RoutineControlPipelineRunORM | None:
        statement = select(RoutineControlPipelineRunORM).where(
            RoutineControlPipelineRunORM.idempotency_key == idempotency_key
        )
        return self._session.execute(statement).scalar_one_or_none()

    def create_pipeline_run(
        self,
        *,
        idempotency_key: str,
        business_date: date,
    ) -> RoutineControlPipelineRunORM:
        run = RoutineControlPipelineRunORM(
            business_date=business_date,
            date_from=business_date,
            date_to=business_date,
            generation_mode="MANUAL",
            status="PENDING",
            idempotency_key=idempotency_key,
            requested_by_user_id=None,
            trigger_source="MANUAL_CLI",
            attempt_number=1,
        )
        self._session.add(run)
        self._session.flush()
        return run

    def find_provider_run(
        self,
        *,
        pipeline_run_id: int,
        provider_key: str,
        dataset_key: str,
    ) -> RoutineControlProviderRunORM | None:
        statement = select(RoutineControlProviderRunORM).where(
            RoutineControlProviderRunORM.pipeline_run_id == pipeline_run_id,
            RoutineControlProviderRunORM.provider_key == provider_key,
            RoutineControlProviderRunORM.dataset_key == dataset_key,
        )
        return self._session.execute(statement).scalar_one_or_none()

    def ensure_provider_run(
        self,
        *,
        pipeline_run: RoutineControlPipelineRunORM,
        provider_key: str,
        dataset_key: str,
        content_hash: str,
    ) -> RoutineControlProviderRunORM:
        provider_run = self.find_provider_run(
            pipeline_run_id=int(pipeline_run.id),
            provider_key=provider_key,
            dataset_key=dataset_key,
        )
        if provider_run is None:
            provider_run = RoutineControlProviderRunORM(
                pipeline_run_id=pipeline_run.id,
                provider_key=provider_key,
                dataset_key=dataset_key,
                status="PENDING",
                date_from=pipeline_run.date_from,
                date_to=pipeline_run.date_to,
                content_hash=content_hash,
            )
            self._session.add(provider_run)
            self._session.flush()
        return provider_run

    @staticmethod
    def start_pipeline(
        run: RoutineControlPipelineRunORM,
        *,
        at_utc: datetime,
        reused: bool,
    ) -> None:
        if reused:
            run.attempt_number += 1
        run.status = "RUNNING"
        run.current_stage = "INITIALIZING"
        run.started_at_utc = at_utc
        run.finished_at_utc = None
        run.heartbeat_at_utc = at_utc
        run.error_code = None
        run.error_message = None

    @staticmethod
    def start_provider(
        run: RoutineControlProviderRunORM,
        *,
        at_utc: datetime,
    ) -> None:
        run.status = "RUNNING"
        run.attempt_count += 1
        run.last_attempt_at_utc = at_utc
        run.started_at_utc = at_utc
        run.finished_at_utc = None
        run.error_code = None
        run.error_message = None
        run.records_received = 0
        run.records_valid = 0
        run.records_rejected = 0
        run.records_excluded = 0
        run.records_created = 0
        run.records_updated = 0

    @staticmethod
    def finish_provider_success(
        run: RoutineControlProviderRunORM,
        *,
        at_utc: datetime,
        records_received: int,
        records_valid: int,
        records_rejected: int,
        records_excluded: int,
        records_created: int,
        records_updated: int,
    ) -> None:
        run.status = "SUCCESS" if records_valid else "SUCCESS_EMPTY"
        run.finished_at_utc = at_utc
        run.records_received = records_received
        run.records_valid = records_valid
        run.records_rejected = records_rejected
        run.records_excluded = records_excluded
        run.records_created = records_created
        run.records_updated = records_updated

    @staticmethod
    def finish_provider_failed(
        run: RoutineControlProviderRunORM,
        *,
        at_utc: datetime,
        error_code: str,
        error_message: object,
    ) -> None:
        run.status = "FAILED"
        run.finished_at_utc = at_utc
        run.error_code = error_code[:120]
        run.error_message = sanitize_error_message(error_message)

    @staticmethod
    def finish_pipeline_success(
        run: RoutineControlPipelineRunORM,
        *,
        at_utc: datetime,
        members_created: int,
        members_updated: int,
        evidences_created: int,
        evidences_updated: int,
        status_changes: int,
        incidents_created: int,
        records_rejected: int,
    ) -> None:
        run.status = "SUCCESS"
        run.current_stage = "COMPLETED"
        run.finished_at_utc = at_utc
        run.heartbeat_at_utc = at_utc
        run.members_created = members_created
        run.members_updated = members_updated
        run.evidences_created = evidences_created
        run.evidences_updated = evidences_updated
        run.status_changes = status_changes
        run.incidents_created = incidents_created
        run.records_rejected = records_rejected
        run.error_code = None
        run.error_message = None

    @staticmethod
    def finish_pipeline_failed(
        run: RoutineControlPipelineRunORM,
        *,
        at_utc: datetime,
        error_code: str,
        error_message: object,
    ) -> None:
        run.status = "FAILED"
        run.current_stage = "FAILED"
        run.finished_at_utc = at_utc
        run.heartbeat_at_utc = at_utc
        run.error_code = error_code[:120]
        run.error_message = sanitize_error_message(error_message)
