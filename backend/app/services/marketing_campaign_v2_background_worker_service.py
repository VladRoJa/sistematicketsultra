"""Issue #1129 M1c: dedicated one-shot governed background dispatch worker.

The D2c service owns the ONLY provider call and commits SUBMITTING before HTTP.
No credentials/JWT/recipient data are stored in jobs. Never auto-retry or
reclaim RUNNING after a crash. This module is not a Flask request handler.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.extensions import db
from app.models.marketing import MarketingCampaignV2ProviderCampaignORM as Child
from app.models.marketing_campaign_v2_background_job import (
    MarketingCampaignV2BackgroundJobORM as Job,
    MarketingCampaignV2BackgroundJobEventORM as Event,
)
from app.models.user_model import UserORM
from app.services.marketing_access import (
    MarketingAuthorizationError, resolve_marketing_access,
)
from app.services.marketing_campaign_v2_governed_dispatch_service import (
    BackgroundDispatchClaim, BackgroundDispatchStoppedBeforeClaim,
    execute_governed_child,
)

LEASE = timedelta(minutes=15)
FLAGS = (
    "CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED",
    "CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY",
    "CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED",
    "CAMPAIGN_V2_PROVIDER_SEND_ENABLED",
)


class BackgroundWorkerReview(RuntimeError):
    """No further children may be attempted without manual reconciliation."""


def _now(value: datetime | None = None) -> datetime:
    value = datetime.now(timezone.utc) if value is None else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise BackgroundWorkerReview("INVALID_TIMESTAMP")
    return value.astimezone(timezone.utc)


def _pg(session: Any) -> None:
    if session.get_bind().dialect.name != "postgresql":
        raise BackgroundWorkerReview("POSTGRES_REQUIRED")


def _enabled(config: Any) -> bool:
    return all(config.get(flag) is True for flag in FLAGS)


def _event(session: Any, job: Job, kind: str, at: datetime, *,
           child_id: int | None = None, reason: str | None = None) -> None:
    number = (session.query(Event.event_no).filter(Event.job_id == job.id)
              .order_by(Event.event_no.desc()).limit(1).scalar() or 0) + 1
    session.add(Event(job_id=job.id, event_no=number, event_kind=kind,
                      child_id=child_id, reason_code=reason, occurred_at=at))


def _review(session: Any, job: Job, reason: str, at: datetime) -> None:
    if job.status in ("STOPPED", "COMPLETED", "REVIEW_REQUIRED"):
        return
    job.status = "REVIEW_REQUIRED"
    job.stop_reason_code = reason
    job.worker_lease_until = None
    job.finished_at = at
    job.updated_at = at
    _event(session, job, "REVIEW_REQUIRED", at, reason=reason[:64])


def _stop_or_complete(session: Any, job: Job, at: datetime, *, done: bool) -> None:
    completed = done and job.status == "RUNNING"
    job.status = "COMPLETED" if completed else "STOPPED"
    job.current_child_id = None
    job.finished_at = at
    job.worker_lease_until = None
    job.updated_at = at
    job.stop_reason_code = None if completed else "OPERATOR_STOP"
    _event(session, job, "COMPLETED" if completed else "STOPPED",
           at, reason=job.stop_reason_code)


def _ids(job: Job) -> list[int]:
    ids = job.pending_child_ids
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 30
            or any(type(i) is not int or i <= 0 for i in ids)
            or len(set(ids)) != len(ids) or len(ids) != job.initial_pending_count):
        raise BackgroundWorkerReview("JOB_MANIFEST_INVALID")
    digest = hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode("ascii")).hexdigest()
    if digest != job.pending_children_digest:
        raise BackgroundWorkerReview("JOB_MANIFEST_CHANGED")
    return ids


def _owned(session: Any, job_id: int, worker_id: str, generation: int,
           at: datetime, *, lock: bool = True) -> Job:
    q = session.query(Job).filter(Job.id == job_id)
    job = (q.with_for_update() if lock else q).one_or_none()
    if job is None or job.worker_instance_id != worker_id or (
            job.worker_claim_generation != generation):
        raise BackgroundWorkerReview("WORKER_OWNERSHIP_LOST")
    if job.status not in ("RUNNING", "STOP_REQUESTED"):
        raise BackgroundWorkerReview("JOB_NOT_RUNNING")
    lease = job.worker_lease_until
    if lease is None or _now(lease) <= at:
        raise BackgroundWorkerReview("WORKER_LEASE_EXPIRED")
    return job


def _actor(session: Any, user_id: int) -> None:
    user = session.get(UserORM, user_id)
    try:
        access = resolve_marketing_access(user)
    except MarketingAuthorizationError as exc:
        raise BackgroundWorkerReview("OPERATOR_PERMISSION_REVOKED") from exc
    if not (access.is_global and access.can_manage_dispatch_config
            and access.can_send_campaigns):
        raise BackgroundWorkerReview("OPERATOR_PERMISSION_REVOKED")


def claim_next_queued(*, session: Any, worker_id: str, config: Any,
                      now: datetime | None = None) -> tuple[int, int] | None:
    """Atomic SKIP LOCKED claim; a previously RUNNING job is never reclaimed."""
    if not isinstance(worker_id, str) or not 1 <= len(worker_id) <= 64:
        raise BackgroundWorkerReview("INVALID_WORKER_ID")
    if not _enabled(config):
        return None
    _pg(session)
    at = _now(now)
    try:
        job = (session.query(Job).filter(Job.status == "QUEUED")
               .order_by(Job.created_at, Job.id)
               .with_for_update(skip_locked=True).first())
        if job is None:
            session.rollback()
            return None
        if at >= _now(job.start_deadline_at):
            _review(session, job, "START_DEADLINE_EXPIRED", at)
            session.commit()
            return None
        _actor(session, int(job.operator_user_id))
        _ids(job)
        job.status = "RUNNING"
        job.worker_instance_id = worker_id
        job.worker_claim_generation += 1
        job.worker_lease_until = at + LEASE
        job.started_at = at
        job.updated_at = at
        _event(session, job, "STARTED", at)
        result = int(job.id), int(job.worker_claim_generation)
        session.commit()
        return result
    except BackgroundWorkerReview as exc:
        # A revoked actor or invalid manifest must never remain QUEUED:
        # quarantine the exact locked job, with no provider interaction.
        if "job" in locals() and job is not None:
            _review(session, job, str(exc), at)
            session.commit()
            return None
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise


def expire_stale_running(*, session: Any, now: datetime | None = None,
                         limit: int = 5) -> int:
    """Expired lease is terminal REVIEW_REQUIRED; never replay HTTP."""
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("invalid limit")
    _pg(session)
    at = _now(now)
    try:
        rows = (session.query(Job).filter(
            Job.status.in_(("RUNNING", "STOP_REQUESTED")), Job.worker_lease_until < at,
        ).order_by(Job.worker_lease_until)
            .with_for_update(skip_locked=True).limit(limit).all())
        for job in rows:
            _review(session, job, "WORKER_LEASE_EXPIRED", at)
        session.commit()
        return len(rows)
    except Exception:
        session.rollback()
        raise


def _prepare(session: Any, job_id: int, worker_id: str, generation: int,
             index: int, config: Any, at: datetime) -> tuple[dict, BackgroundDispatchClaim] | None:
    job = _owned(session, job_id, worker_id, generation, at)
    if job.status == "STOP_REQUESTED":
        _stop_or_complete(session, job, at, done=False)
        session.commit()
        return None
    if not _enabled(config):
        _review(session, job, "DISPATCH_DISABLED", at)
        session.commit()
        return None
    _actor(session, int(job.operator_user_id))
    ids = _ids(job)
    if index >= len(ids):
        _stop_or_complete(session, job, at, done=True)
        session.commit()
        return None
    child_id = ids[index]
    child = session.get(Child, child_id)
    if (child is None or child.campaign_v2_id != job.campaign_v2_id
            or child.status != "READY" or child.submit_started_at is not None
            or child.provider_campaign_id is not None or child.submitted_at is not None):
        raise BackgroundWorkerReview("CHILD_ALREADY_ATTEMPTED_OR_CHANGED")
    job.current_child_id = child_id
    job.updated_at = at
    job.worker_lease_until = at + LEASE
    details = {
        "campaign_id": int(job.campaign_v2_id), "execution_id": int(job.execution_id),
        "child_id": child_id, "expected_digest": str(job.manifest_digest),
        "actor_user_id": int(job.operator_user_id),
    }
    grant = BackgroundDispatchClaim(
        job_id=int(job.id), worker_instance_id=worker_id,
        worker_claim_generation=generation,
    )
    session.commit()
    return details, grant


def _accepted(session: Any, job_id: int, worker_id: str, generation: int,
              child_id: int, at: datetime) -> bool:
    job = _owned(session, job_id, worker_id, generation, at)
    if job.current_child_id != child_id:
        raise BackgroundWorkerReview("CURRENT_CHILD_CHANGED")
    child = session.get(Child, child_id)
    if (child is None or child.status != "SUBMITTED"
            or child.provider_campaign_id is None or child.submitted_at is None):
        raise BackgroundWorkerReview("PROVIDER_ACCEPTANCE_UNCONFIRMED")
    job.last_accepted_child_id = child_id
    job.current_child_id = None
    job.updated_at = at
    _event(session, job, "CHILD_ACCEPTED", at, child_id=child_id)
    if job.status == "STOP_REQUESTED":
        _stop_or_complete(session, job, at, done=False)
    elif child_id == _ids(job)[-1]:
        _stop_or_complete(session, job, at, done=True)
    else:
        job.worker_lease_until = at + LEASE
    finished = job.status in ("STOPPED", "COMPLETED")
    session.commit()
    return finished


def _stopped_before_claim(session: Any, job_id: int, worker_id: str,
                          generation: int, child_id: int) -> None:
    """STOPPED only when READY was never claimed as SUBMITTING."""
    session.rollback()
    at = _now()
    try:
        job = session.query(Job).filter(Job.id == job_id).with_for_update().one_or_none()
        if (job is None or job.worker_instance_id != worker_id
                or job.worker_claim_generation != generation):
            session.rollback()
            return
        child = session.get(Child, child_id)
        if (job.status == "STOP_REQUESTED" and job.current_child_id == child_id
                and child is not None and child.campaign_v2_id == job.campaign_v2_id
                and child.status == "READY" and child.submit_started_at is None
                and child.submitted_at is None and child.provider_campaign_id is None):
            _stop_or_complete(session, job, at, done=False)
        else:
            _review(session, job, "STOP_CLAIM_RACE_UNCERTAIN", at)
        session.commit()
    except Exception:
        session.rollback()
        raise


def _fail_closed(session: Any, job_id: int, worker_id: str,
                 generation: int, reason: str) -> None:
    session.rollback()
    try:
        job = session.query(Job).filter(Job.id == job_id).with_for_update().one_or_none()
        if (job is not None and job.worker_instance_id == worker_id
                and job.worker_claim_generation == generation):
            _review(session, job, reason[:64], _now())
            session.commit()
        else:
            session.rollback()
    except Exception:
        session.rollback()
        raise


def process_claimed_job(*, session: Any, job_id: int, worker_id: str,
                        generation: int, config: Any, provider_factory: Callable[[], Any],
                        clock: Callable[[], datetime] = _now,
                        should_terminate: Callable[[], bool] | None = None) -> None:
    """One ordered suffix only; D2c performs the sole provider request."""
    child_id = None
    try:
        job = _owned(session, job_id, worker_id, generation, _now(clock()), lock=False)
        ids = _ids(job)
        session.rollback()
        for index, child_id in enumerate(ids):
            if should_terminate is not None and should_terminate():
                _fail_closed(session, job_id, worker_id, generation, "WORKER_SHUTDOWN")
                return
            pending = _prepare(session, job_id, worker_id, generation, index,
                               config, _now(clock()))
            if pending is None:
                return
            details, grant = pending
            # Constructed only after local validations. No retries after ambiguity.
            response = execute_governed_child(
                **details, background_claim=grant,
                allowed_sucursal_keys=None, provider=provider_factory(),
                send_enabled=_enabled(config),
                governed_enabled=_enabled(config), session=session,
            )
            if response.get("status") != "SUBMITTED" or response.get("child_id") != child_id:
                raise BackgroundWorkerReview("PROVIDER_RESULT_REVIEW_REQUIRED")
            session.expire_all()
            if _accepted(session, job_id, worker_id, generation,
                         child_id, _now(clock())):
                return
    except BackgroundDispatchStoppedBeforeClaim:
        if child_id is not None:
            _stopped_before_claim(session, job_id, worker_id, generation, child_id)
    except BackgroundWorkerReview as exc:
        _fail_closed(session, job_id, worker_id, generation, str(exc))
    except Exception:
        _fail_closed(session, job_id, worker_id, generation, "UNEXPECTED_WORKER_FAILURE")
        raise
